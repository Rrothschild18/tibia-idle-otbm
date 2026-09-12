Status: ready-for-agent

# Pipeline reprodutível: morte do v5, publicação única e insumos declarados

## Problem Statement

Three problems share one root — the pipeline's real contract lives in people's heads, not in the
repo — and they compound:

**1. The v5 map format is dead and still being built.** `tibia-idle` is v6-only and fails loudly on
anything else: `libs/game-logic/src/lib/systems/map-definition.ts:62-71` throws from `assertIsV6()`,
and `MapDefinition` doesn't even declare `tilelayer`/`objectgroup`. Yet `build_phaser_map.py` still
emits **two** trees on every run (`ready-maps/` v5 and `ready-maps-v6/`), and
`extractor/README.md:4` still tells the reader that v5 is "o que o jogo ainda consome". The one real
consumer of the v5 builder is the full-city map — and it doesn't consume a *map*: it reads
`objectDefs[<id>].flags` and nothing else (`build_travel_fragment.py:161` →
`travel_graph.py:263`). To produce that flag table, the pipeline generates a 20.3 MB `map.json`
with 10 floors of tiles, 13 sheets, 2 tilesets and 168 animations, plus a 1.8 MB `metadata.json`,
and throws all of it away.

**2. Nothing publishes.** No script copies a built bundle into the sibling repo — the human copies
`ready-maps-v6/<CIDADE>/<pasta>/` into `apps/tibia-idle-front/public/assets/<MAP>-sprites-v6/` by
hand. The evidence is in what arrived: published bundles carry `map.json` + `sheets/` but not the
`monsters/respawn.json` that `write_map_v6` also writes — a selective hand copy, not a sync.
`content_export.py` does no I/O at all; `--export` writes four JSON files and no binary. The
consequence is silent drift: `respawn.json` points monsters at `assets/outfits/...`, which **nothing
syncs and which is not published**, and four baked atlases (`outfits`, `effects`, `corpses`,
`pools`) have no sync at all while three of them were hand-copied into the front anyway.

**3. A fresh checkout can't run, and doesn't say why.** There is no `requirements.txt` /
`pyproject.toml`; `Pillow` and `protobuf` are simply expected to be there. `DEFAULT_TIBIA_IDLE_DIR`
resolves to `<workspace>/tibia-idle/tibia-idle` — a path that doesn't exist — and
`DEFAULT_CANARY_DIR` is `C:\canary-3.2.1`, a Windows path, on a Linux-only workflow. The four `.aec`
containers (~270 MB, the Assets Editor export that is the source of every sprite) are gitignored and
absent, and the failure they produce is a `FileNotFoundError` deep inside stage 2. Worse, that input
is a dead end: the current editors are Windows-only and the one still maintained
(`beats-dh/Beats-Assets-Editor`) now writes sprite bytes to a **companion** `.aec.sprites` file, so a
fresh export would satisfy the extractor's non-standard `sprite_data = 7` field with nothing at
all.

## Solution

**The v5 format is deleted, not migrated.** `ready-maps-v6/` becomes `ready-maps/`. The full-city
path stops emitting a map entirely and emits only what its consumer reads: a versioned
**appearance-flags table** (~2158 entries), with a separate `flag-overrides.json` that always wins.
`map.json` (20.3 MB) and `metadata.json` leave the repo. Nothing is "ported to v6" because the
travel graph never read a map format to begin with.

**One command writes into `tibia-idle`.** A single `publish` covers the map bundle (today manual)
and every atlas. It fails loudly when a referenced atlas was never baked, and reconciles the
destination only behind an explicit `--prune`.

**Every input is declared.** `pyproject.toml` + `uv` for Python deps; one `paths.py` with
`TIBIA_IDLE_DIR`/`CANARY_DIR` env vars over a sibling-layout fallback; the Canary slices vendored
(`items.xml` raw, the `.lua` as extracts) with their origin commit recorded; **stage 0 reads the
client's own `assets/` directly** — `catalog-content.json`, the LZMA sheets and the official
appearances protobuf — instead of a GUI tool's export, keeping `extractor/sprites/` as the unchanged
output contract so nothing downstream moves; that client folder fetched from a private bucket by
checksum **and client version**; a per-stage check that says what is missing before work starts, not
20 minutes in.

## Decisions

- **The `-sprites-v6` suffix in the published URL stays.** It is not a format name: the back-end
  schema requires it (`import-source.model.ts:15`, `BUNDLE_URL_PATTERN`) and the captured `-v<N>`
  *becomes* `hunt.contentVersion` (`:281-282`). `MAP_BUNDLE_VERSION` is renamed to say what it is —
  a content version — and bumps when the bundle's bytes change. Semver in the path was considered
  and rejected: the URL's job is cache identity (ADR-0003), and "breaking vs additive" is a question
  the front's own git history already answers, at the cost of a cross-repo schema change.
- **The flag table is mechanical; curation lives beside it.** `flag-overrides.json` is a separate,
  versioned file that always wins on merge. This is the mecânico-vs-curado rule of `CONTEXT.md:44-50`
  applied to a new artifact: regenerating must never destroy information, or `--force` becomes a
  trap.
- **The flag table is committed to git**, like `monster-loot.json` and `otservbr-monster.xml`
  already are. The rule the repo already follows in practice: a derivative of an input not everyone
  has, that changes rarely, is versioned. The payoff is concrete — the travel graph keeps running on
  a checkout with no `.aec` at all, which is the only end-to-end product such a machine can build.
- **Publish adds by default; `--prune` removes.** A command that deletes in a sibling repo by
  default is regretted exactly once.
- **The sprite source stops being a third-party export.** `.aec` is the output of a GUI editor whose
  format already shifted underneath this pipeline once; the client's `assets/` is a documented input
  the Canary server itself consumes. Swapping the reader while keeping `extractor/sprites/` byte-for-
  byte identical is what makes this a small change instead of a rewrite.
- **Staleness is content hash, not mtime** — `git checkout` rewrites mtimes and copies preserve them,
  so mtime lies precisely when it costs most: serving stale output in silence. The `.aec` are the
  one exception (hashing 270 MB per invocation doesn't pay), and their checksum manifest already
  exists for the fetch step.
- **Checks run per stage, and each script also fails well on its own.** Not alternatives: the check
  answers "what do I need to run this?" before the cost is paid; the per-script message catches
  whoever entered mid-pipeline.

## Ordem de execução

Steps 01–06 run **today, on a machine with no `.aec`** — including the most delicate part, the
travel graph. From 07 on, sprites are required and the work is writable but not verifiable until the
containers arrive.

1. `01` freeze the golden fragment · 2. `02` uv/pyproject · 3. `03` paths.py · 4. `04` vendor Canary
· 5. `05` flag table + overrides · 6. `06` delete the v5 full-map path · then `07`–`13`.

## Out of Scope

- **Porting `travel_graph.py` to v6** — dissolved by the finding above: it never read a map format,
  only a flag lookup. There is nothing to port.
- **Renaming the content-version concept in `tibia-idle`** (schema, 18 folder names, every `mapUrl`)
  — real work, in another repo, for a problem that doesn't hurt yet.
- **`item-sprites-para-o-market`** — the only genuinely open work already in `.scratch/`, untouched
  by this effort.
- **The two inert v5 leftovers in `tibia-idle`** (the orphan `public/assets/map.json`, the dead
  `assetsRoot`/`portrait` keys in `catalog-source.json`) — issue only; the catalog self-heals on the
  first re-export once the extractor stops emitting them.

## Further Notes

The `.aec` are Assets Editor exports from a Tibia 12+ client, which is why they carry pixels at all:
`extractor/scripts/Appearances.proto:67` declares `repeated bytes sprite_data = 7`, a field absent
from Canary's own `appearances.proto` — which is why the 4.8 MB `appearances.dat` in the Canary
checkout was never a substitute. Ticket 08 retires that path: the two editors that exist today
(`Arch-Mina/Assets-Editor`, C#/.NET; `beats-dh/Beats-Assets-Editor`, Rust+Tauri) are Windows-only,
the first never mentions `.aec` at all, and the second splits sprite bytes into a companion
`.aec.sprites` — so a re-export would produce containers this pipeline reads as empty.

The client-version pin survives the change and matters just as much: a newer client shifts
appearance ids, and the symptom surfaces six stages later as a wrong sprite, never as an error.

`docs.opentibiabr.com` is not a source for any of this — the whole site is five pages
(`sitemap.md`), none mentioning a client download, `assets/` or `.aec`; `/downloads` and
`/downloads/tools/editors` 404.
