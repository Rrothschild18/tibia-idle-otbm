"""
CLI: snapshot a city's marker signs out of its OTBM, before anything
overwrites that OTBM.

The POIs of a hand-made city exist only as signs placed by hand in its
.otbm (item 2016, uid 10001+, text "CIDADE-TIPO-NNNN"). They are not in the
world map -- re-cutting a city from the world map produces a map with none of
them, and a hunt whose entrance has no POI is dropped by the travel graph.
So the signs have to leave the file in a readable form first; recovering a
binary OTBM from git in the middle of a pipeline run is a worse plan than
having written the 17 rows down.

Two files come out, both under extractor/sign-snapshots/:
<CIDADE>-<sha>.json (the signs, with the uid the transplant needs) and
<CIDADE>-<sha>-monster.xml (a copy of the spawn export, which the roster
check reads after the original is gone).

Nothing outside extractor/sign-snapshots/ is written, and the source .otbm is
only ever read.

The run fails, on purpose, when the snapshot's ids don't match the catalog's
for that city: that means map and catalog already disagree, and cutting a new
map on top of that propagates the disagreement instead of fixing it. There is
no flag to skip that check -- a gate you can turn off is not a gate.

Run: python dump_marker_signs.py ROOK
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

import content_export
import paths
from travel_graph import iter_marker_sign_items, parse_marker_signs, parse_quest_slug_markers

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
SNAPSHOTS_DIR = os.path.join(EXTRACTOR_DIR, "sign-snapshots")


# ======================================================
# Pure logic
# ======================================================

def collect_sign_uids(dump):
    """(x, y, z, text) -> uid, for every reserved-range sign in the dump.

    parse_marker_signs is the authority on what counts as a marker, but it
    collapses each one to id/type/x/y/z and drops the uid. The uid is exactly
    what re-injecting the sign needs, so it is recovered from the same public
    item walk the parser itself consumes — no second copy of the filter.

    First occurrence wins, because that is what parse_marker_signs does with a
    duplicate id — it promotes the first and reports the rest. Overwriting here
    would pair the promoted sign with a later sign's uid, and the transplant
    would silently re-inject the wrong one."""
    uids = {}
    for x, y, z, uid, text in iter_marker_sign_items(dump):
        uids.setdefault((x, y, z, text), uid)
    return uids


def build_snapshot(dump, *, city, source_commit, source_otbm, source_sha256=None):
    """The snapshot document: every valid marker sign with the uid and text
    needed to put it back, plus the provenance of where it came from.

    Ordered by id so that two runs of the same map produce a byte-identical
    file and a real change shows up as a small diff."""
    locations, issues = parse_marker_signs(dump)
    uids = collect_sign_uids(dump)

    signs = []
    for location in locations:
        key = (location["x"], location["y"], location["z"], location["id"])
        if key not in uids:
            # Unreachable unless the two passes stop agreeing on what a marker
            # is. Better a named failure than a KeyError from a dict lookup.
            raise AssertionError(
                f"placa {location['id']} em {key[:3]} saiu do parser mas não tem uid no dump"
            )
        signs.append({
            "id": location["id"],
            "type": location["type"],
            "x": location["x"],
            "y": location["y"],
            "z": location["z"],
            # The sign's own id *is* its text; keeping both is redundant on
            # purpose, so the transplant writes the text it was given rather
            # than re-deriving it from a field that means something else.
            "uid": uids[key],
            "text": location["id"],
        })
    signs.sort(key=lambda sign: sign["id"])

    return {
        "city": city,
        "sourceCommit": source_commit,
        "sourceOtbm": source_otbm,
        # Which bytes this snapshot claims to describe. The mtime check below
        # is only a recency heuristic -- it can't prove the raw dump was made
        # from this .otbm. The hash can't prove it either, but it makes the
        # claim auditable after the .otbm is gone: whoever doubts the snapshot
        # can hash the file git has and compare.
        "sourceSha256": source_sha256,
        "signCount": len(signs),
        "signs": signs,
        "issues": issues,
    }


def catalog_city(location):
    """A cidade de uma linha de `locations`.

    O campo `city` é derivado do primeiro segmento do id (ver CONTEXT.md), então
    quando ele falta o id ainda responde. E faltar acontece: `ROOK-HUNT-0013`
    entrou no catálogo sem `city`. Filtrar só pelo campo deixaria essa linha
    fora da conferência sem que ninguém percebesse — um portão que se desliga
    porque um campo sumiu é pior que um portão que acusa."""
    city = location.get("city")
    if city:
        return city
    return location["id"].split("-", 1)[0]


def compare_with_catalog(snapshot, catalog_locations, *, city, marker_positions=()):
    """Do the snapshot's sign ids and the catalog's sign-born POIs agree?

    Only sign-born POIs of this city are compared. NPC locations come from
    <CIDADE>-npc.xml and never from a sign, so counting them as missing would
    fail the check on every healthy map; another city's rows aren't ours.

    `marker_positions` são as posições dos marcadores de quest por slug
    (`travel_graph.parse_quest_slug_markers`) do mesmo dump. O POI que nasce de
    um desses não tem placa nenhuma e não deveria ter: é a terceira
    procedência de POI não-NPC, ao lado da placa e do `-npc.xml`. Como o
    marcador foi pintado no mapa-mundo, ele sobrevive ao recorte por conta
    própria — cobrá-lo de placa pararia o pipeline num mapa saudável."""
    marker_positions = set(marker_positions)
    snapshot_ids = {sign["id"] for sign in snapshot["signs"]}
    catalog_ids = {
        location["id"]
        for location in catalog_locations
        if catalog_city(location) == city
        and location.get("type") != "NPC"
        and (location.get("x"), location.get("y"), location.get("z")) not in marker_positions
    }

    missing_from_snapshot = sorted(catalog_ids - snapshot_ids)
    missing_from_catalog = sorted(snapshot_ids - catalog_ids)

    return {
        "ok": not missing_from_snapshot and not missing_from_catalog,
        "matched": len(snapshot_ids & catalog_ids),
        "missingFromSnapshot": missing_from_snapshot,
        "missingFromCatalog": missing_from_catalog,
    }


# ======================================================
# CLI
# ======================================================

# git resolves a pathspec against the working directory, so every call has to
# run from the repo root -- from extractor/ a path like
# "extractor/full-maps/..." silently matches nothing and the sha comes back
# unknown, which is worse than an error because the snapshot still gets written.
REPO_DIR = os.path.dirname(EXTRACTOR_DIR)


def _git(args, cwd=REPO_DIR):
    try:
        done = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _source_commit(otbm_path):
    """The commit that last touched this .otbm, plus whether the working tree
    has since changed it. A snapshot taken from a dirty file that claims a
    clean commit is a snapshot nobody can reproduce."""
    relative = os.path.relpath(otbm_path, REPO_DIR)
    sha = _git(["log", "-1", "--format=%H", "--", relative]) or "unknown"
    dirty = _git(["status", "--porcelain", "--", relative])
    if dirty:
        sha = f"{sha}-dirty"
    return sha


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path, what):
    if not os.path.exists(path):
        sys.exit(f"error: {what} não encontrado em {path}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _require_fresh_dump(dump_path, otbm_path, city):
    """The raw dump is gitignored and regenerated by hand, so it can easily be
    older than the .otbm it is supposed to describe. Snapshotting a stale dump
    would capture signs that are no longer where the file says they are.

    Ordering mtimes is a heuristic, not proof of correspondence: a checkout can
    reset the .otbm's mtime, a touch can move the dump's, and equal mtimes say
    nothing. There is no cheap way to prove a 45 MB JSON came from a 2 MB OTBM,
    so the honest move is to re-dump rather than to argue -- which is why the
    remedy here is a command, not a flag that lets the doubt through."""
    if not os.path.exists(dump_path):
        sys.exit(
            f"error: dump bruto não encontrado em {dump_path}\n"
            f"       rode: node extractor/scripts/dump_otbm.js {city}"
        )
    if os.path.getmtime(dump_path) < os.path.getmtime(otbm_path):
        sys.exit(
            f"error: o dump {dump_path} é mais antigo que {otbm_path} — ele pode não "
            f"descrever o mapa atual.\n"
            f"       rode de novo: node extractor/scripts/dump_otbm.js {city}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("city", help="código da cidade, ex: ROOK")
    parser.add_argument("--tibia-idle-dir", help=paths.TIBIA_IDLE.flag + " (checkout do tibia-idle)")
    args = parser.parse_args()

    city = args.city
    otbm_path = os.path.join(FULL_MAPS_DIR, city, f"{city}.otbm")
    if not os.path.exists(otbm_path):
        sys.exit(f"error: mapa da cidade não encontrado em {otbm_path}")

    dump_path = os.path.join(RAW_MAPS_DIR, f"{city}.raw.json")
    _require_fresh_dump(dump_path, otbm_path, city)

    dump = _load_json(dump_path, "dump OTBM bruto")
    source_commit = _source_commit(otbm_path)
    snapshot = build_snapshot(
        dump,
        city=city,
        source_commit=source_commit,
        source_otbm=os.path.relpath(otbm_path, REPO_DIR),
        source_sha256=_sha256(otbm_path),
    )

    print(f"{city}: {snapshot['signCount']} placas de marcador, commit {source_commit}")
    for issue in snapshot["issues"]:
        print(
            f"  [!!] {issue['reason']}: uid={issue.get('uid')} "
            f"text={issue.get('text')!r} em ({issue.get('x')},{issue.get('y')},{issue.get('z')})"
        )

    tibia_idle_dir = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    catalog = _load_json(
        content_export.catalog_source_path(tibia_idle_dir), "catalog-source.json"
    )
    result = compare_with_catalog(
        snapshot,
        catalog.get("locations", []),
        city=city,
        marker_positions={
            (marker["x"], marker["y"], marker["z"])
            for marker in parse_quest_slug_markers(dump)
        },
    )
    print(f"  catálogo: {result['matched']} ids em comum")
    for missing in result["missingFromSnapshot"]:
        print(f"  [!!] o catálogo tem {missing} e o mapa não tem placa para ele")
    for missing in result["missingFromCatalog"]:
        print(f"  [!!] a placa {missing} não tem entrada no catálogo")
    if not result["ok"]:
        sys.exit(
            "error: mapa e catálogo já discordam — recortar um mapa novo em cima disso "
            "propaga a divergência. Resolva antes de seguir (ver ticket 01)."
        )

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    out_path = os.path.join(SNAPSHOTS_DIR, f"{city}-{source_commit}.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"  -> {out_path}")

    monster_xml = os.path.join(FULL_MAPS_DIR, city, f"{city}-monster.xml")
    if os.path.exists(monster_xml):
        spawn_copy = os.path.join(SNAPSHOTS_DIR, f"{city}-{source_commit}-monster.xml")
        shutil.copy2(monster_xml, spawn_copy)
        print(f"  -> {spawn_copy}")
    else:
        print(f"  [!!] {monster_xml} não existe — a conferência de roster não terá com o que comparar")


if __name__ == "__main__":
    main()
