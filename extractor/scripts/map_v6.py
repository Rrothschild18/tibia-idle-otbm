"""`map.json` v6 — the tile with its ordered stack is the whole unit.

Builds the v6 document from an OTBM dump. No I/O: the caller supplies the
per-appearance analysis and the sheet packer, and gets back the document plus
the `{sheet: {gid: source png}}` plan for rendering the sheets.

What v6 drops, relative to v5:

- **Render roles.** No `layerClass`, no `depthOffset`, no seven objectgroup
  layers, no `Roof` — those were an invented model (see `docs/adr/0006`). Draw
  order is a walk: floors ascending, tiles by row, items by stack position,
  creatures last.
- **The `Ground` tilelayer and its `tilesets`.** Ground is a draw slot, not a
  layer, so a 64×64 ground no longer has to be smuggled out of a 32×32 grid.
  It packs into the same footprint sheets as everything else.

What it adds: `shift` and `elevation` per appearance (see `CONTEXT.md`), the two
positioning properties the client has always had and the pipeline never emitted.

Written to its own output tree; the directory the game consumes today is
untouched. See `.scratch/modelo-render-rme/issues/04-schema-v6-pilha-por-tile.md`.
"""

import posixpath
from typing import Callable, Dict, List, Optional, Set, Tuple

import tile_stack
import travel_graph

TILE_SIZE = 32
VERSION = 6

# Marker signs (item 2016) placed by the travel-graph tooling use a reserved
# uid range — tooling input, never a renderable object. Same rule as v5. The
# rule itself lives in `travel_graph.is_marker_item`, which also knows the
# items that are markers by id alone (a painted route path carries no uid).
SIGN_ITEM_ID = 2016
MARKER_UID_MIN = 10001

# Action id marking where a hunt starts, read off whatever item carries it so
# the pipeline knows the tile's position and floor. In Rookgaard it rides a
# real item placed by hand in the editor; `build_curated_hunts.py` instead
# injects a fresh item 352 for this alone — a synthetic carrier, not map
# content. Either way it is tooling input, same category as a marker sign
# (`SIGN_ITEM_ID` above): stripped from the stack below, never drawn. Without
# this, the injected 352 entered `tile_stack` and showed up as a patch of dirt
# on the entrance tile of every curated hunt.
HUNT_START_ACTION_ID = 3366

# A tile row is [tileX, tileY, ground, *stack]. Appearance ids start well above
# zero, so 0 is unambiguous as "this tile has no ground".
NO_GROUND = 0

# Flags the v5 model derived to answer "where does this draw?" — `isRoof` from
# the five-flag roof heuristic, `hookDirection` from the wall-orientation one.
# Both are render roles wearing a flag's clothes, and v6 answers that question
# with the stack instead. `isFloorTransition` stays: it is derived too, but it
# answers a game-logic question (does stepping here change floor? — ADR 0002),
# not a drawing one.
DROPPED_V5_FLAGS = frozenset({"isRoof", "hookDirection"})


def _tile_placements(tile: Dict, analyze: Callable[[int], Dict]) -> List[Tuple[int, Dict]]:
    """The tile's appearances as `(id, flags)`, in the order the OTBM holds
    them: ground slot first, then items as inserted, markers dropped."""
    placements: List[Tuple[int, Dict]] = []

    ground_id = tile.get("tileid")
    if ground_id is not None:
        placements.append((ground_id, analyze(ground_id)["flags"]))

    for raw_item in tile.get("items") or []:
        appearance_id = raw_item.get("id")
        if appearance_id is None:
            continue
        if travel_graph.is_marker_item(raw_item):
            continue
        if raw_item.get("aid") == HUNT_START_ACTION_ID:
            continue
        placements.append((appearance_id, analyze(appearance_id)["flags"]))

    return placements


def _appearance_entry(analysis: Dict, packer, frame_sources: Dict[str, Dict[int, str]]) -> Dict:
    """One `appearances` record: where its frames live, plus the properties
    that are the same for every placement of it."""
    sprites = analysis["sprites"]
    first_available = next((s for s in sprites if s["available"]), None)
    width = first_available["width"] if first_available else TILE_SIZE
    height = first_available["height"] if first_available else TILE_SIZE

    sheet_key, gids = packer.add_appearance(
        analysis["appearanceId"], width, height, frame_count=len(sprites) or 1,
    )
    sources = frame_sources.setdefault(sheet_key, {})
    for gid, sprite in zip(gids, sprites):
        if sprite["available"]:
            sources[gid] = sprite["sourcePath"]

    entry: Dict = {"type": analysis["type"], "sheet": sheet_key, "gids": gids}

    if width != TILE_SIZE:
        entry["spriteWidth"] = width
    if height != TILE_SIZE:
        entry["spriteHeight"] = height

    if not analysis["hasSprite"]:
        entry["hasSprite"] = False
    if analysis.get("random"):
        entry["random"] = True
    if analysis.get("animated"):
        entry["animated"] = True
        entry["animation"] = analysis["animation"]

    # How many position variants this appearance has, and therefore how to read
    # `gids`: the list is `phases x patterns`, phase-major, so the frames of one
    # variant are `gids[phase * (w*h*d) + index]`. Without this the list is
    # unreadable — 42 gids look like 42 frames when they are 3 shore shapes of
    # 14 frames each, and the renderer has no way to tell. Emitted only when
    # there is more than one variant, which is the minority of appearances;
    # absent means 1x1x1, the whole list belongs to one tile.
    sprite_info = analysis.get("spriteInfo") or {}
    pattern = {
        "w": sprite_info.get("patternWidth", 1),
        "h": sprite_info.get("patternHeight", 1),
        "d": sprite_info.get("patternDepth", 1),
    }
    if pattern["w"] * pattern["h"] * pattern["d"] > 1:
        entry["pattern"] = pattern

    # `SpriteInfo.is_opaque`, não uma `AppearanceFlags` — é o sinal que
    # `Tile::isFullyOpaque` do mehah-client usa (junto de `fullbank`) pra
    # decidir o que esconde a visão de um andar abaixo.
    if sprite_info.get("isOpaque"):
        entry["isOpaque"] = True

    # Both are pure positioning, and both are absent far more often than
    # present — emitting the zero would be noise in every tile of every map.
    shift = analysis.get("shift") or {}
    if shift.get("x") or shift.get("y"):
        entry["shift"] = {"x": shift.get("x", 0), "y": shift.get("y", 0)}
    elevation = analysis.get("elevation") or 0
    if elevation:
        entry["elevation"] = elevation

    # A cor que este appearance pinta no minimapa. Fica aqui e não em `flags`
    # porque aquele bloco só serializa chave truthy e é booleano por natureza:
    # um índice de cor caberia lá exatamente até alguém precisar do valor.
    automap_color = analysis.get("automapColor") or 0
    if automap_color:
        entry["automapColor"] = automap_color

    light = analysis.get("light") or {}
    if light.get("intensity"):
        entry["light"] = {"intensity": light["intensity"], "color": light.get("color", 0)}

    flags_true = {
        key: value for key, value in analysis.get("flags", {}).items()
        if value and key not in DROPPED_V5_FLAGS
    }
    if flags_true:
        entry["flags"] = flags_true
    if analysis.get("issues"):
        entry["issues"] = list(analysis["issues"])

    return entry


def map_bounds(dump: Dict) -> Dict[str, int]:
    """`{minX, minY, maxX, maxY}` do dump, sem construir documento nenhum.

    Mesma união entre andares que `build_map_v6` calcula (ADR 0002): `(tileX,
    tileY)` é a mesma coluna física em todo andar. Existe separado porque o
    mapa de cidade inteira precisa de `bounds` para o `respawn.json` e não
    gera mapa — construir um documento inteiro só para ler quatro números foi
    exatamente o desperdício que o ticket 06 removeu.
    """
    min_x = min_y = 10 ** 9
    max_x = max_y = -(10 ** 9)

    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            for tile in feature.get("tiles", []):
                tile_x = tile.get("x")
                tile_y = tile.get("y")
                if tile_x is None or tile_y is None:
                    continue
                x = base_x + tile_x
                y = base_y + tile_y
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)

    if min_x == 10 ** 9:
        min_x = min_y = max_x = max_y = 0

    return {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y}


def _floor_transitions(dump: Dict, analyze: Callable[[int], Dict],
                       used_ids: Set[int],
                       stacks: Dict[int, Dict[Tuple[int, int], Dict]],
                       min_x: int, min_y: int,
                       floorchange_by_id: Optional[Dict[int, str]],
                       ladder_ids: Optional[Set[int]]) -> List[int]:
    """As arestas de mudança de andar do bundle, achatadas a 6 inteiros cada.

    Origem `(x, y, z)` e destino `(x, y, z)` em tile local — o mesmo espaço de
    `floors[].tiles` —, não-direcionadas, uma entrada por par. Quem consome é o
    A* do gerador de rota, que não sabe o que é escada: só segue aresta.

    A regra é a de `travel_graph`, a mesma que alimenta o grafo de viagem.
    Emitida aqui porque o grafo de viagem vive numa etapa que o mapa de hunt
    nunca roda, e reimplementá-la seria manter duas geometrias divergindo.

    Só sai aresta cujas duas pontas o documento de fato publica: uma tile sem
    nada para desenhar não vira linha em `floors`, então uma aresta até ela
    seria aresta para lugar nenhum."""
    flags_by_id = {str(appearance_id): analyze(appearance_id)["flags"]
                   for appearance_id in used_ids}
    tiles = travel_graph.extract_tile_flags(dump, flags_by_id, floorchange_by_id, ladder_ids)

    transitions: List[int] = []
    for (ax, ay, az), (bx, by, bz) in travel_graph.floor_transition_edges(tiles):
        if (ax, ay) not in stacks.get(az, {}) or (bx, by) not in stacks.get(bz, {}):
            continue
        transitions.extend([ax - min_x, ay - min_y, az, bx - min_x, by - min_y, bz])

    return transitions


def build_map_v6(dump: Dict, analyze: Callable[[int], Dict], packer,
                 assets_root: str,
                 map_id: Optional[str] = None,
                 floorchange_by_id: Optional[Dict[int, str]] = None,
                 ladder_ids: Optional[Set[int]] = None) -> Tuple[Dict, Dict[str, Dict[int, str]]]:
    """`(document, {sheet key: {gid: source png path}})`.

    `analyze` resolves an appearance id to the analysis dict
    `build_phaser_map.analyze_item` produces; `packer` is a `SheetPacker` this
    call is free to fill (it uses the v6 footprint-only key).

    The hunt's entrance comes from `HUNT_START_ACTION_ID`, placed by hand on
    the entrance tile: it fills `start` and decides `defaultZ`. It replaces a
    marker sign whose text had to equal `map_id` exactly — a rule no map in the
    set ever satisfied (the signs that exist read `"ROOK-0001"`, not
    `"ROOK-HUNT-0001"`), so every build fell through to the heuristic. An
    action id has nothing to spell.

    `map_id` is kept for the warning messages only.

    `floorchange_by_id` e `ladder_ids` saem do `items.xml` do Canary
    (`update_canary_data.read_floor_change_rules`) e decidem `transitions`.
    Omitidos, o documento sai com `transitions: []` — sem ligação inventada.
    """
    stacks: Dict[int, Dict[Tuple[int, int], Dict]] = {}
    used_ids: Set[int] = set()
    all_zs: Set[int] = set()
    start_marker: Optional[Tuple[int, int, int]] = None
    start_marker_conflict = False

    min_x = min_y = 10 ** 9
    max_x = max_y = -(10 ** 9)

    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", 7)

            for tile in feature.get("tiles", []):
                tile_x = tile.get("x")
                tile_y = tile.get("y")
                if tile_x is None or tile_y is None:
                    continue

                x = base_x + tile_x
                y = base_y + tile_y
                # Bounds are the union across floors: (tileX, tileY) means the
                # same physical column on every floor of the map (ADR 0002).
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)

                for raw_item in tile.get("items") or []:
                    if raw_item.get("aid") != HUNT_START_ACTION_ID:
                        continue
                    if start_marker is not None:
                        start_marker_conflict = True
                    else:
                        start_marker = (x, y, z)

                placements = _tile_placements(tile, analyze)
                if not placements:
                    # Nothing to draw — an OTBM tile whose only content was a
                    # marker sign, or an empty one. It still counts for bounds
                    # (above), but emitting a row for it is pure noise — and
                    # it must NOT count toward `all_zs` below: an empty
                    # feature with no `z` of its own defaults to `z=7`
                    # (line above), and counting that phantom floor is what
                    # made `defaultZ` pick 7 on maps that don't have a single
                    # real tile there (see the ROOK-HUNT-0001 floor-8 bug).
                    continue
                used_ids.update(appearance_id for appearance_id, _ in placements)
                stacks.setdefault(z, {})[(x, y)] = tile_stack.build_tile_stack(placements)
                all_zs.add(z)

    if min_x == 10 ** 9:
        min_x = min_y = max_x = max_y = 0
    if not all_zs:
        all_zs.add(7)

    if start_marker_conflict:
        print(f'[WARN] v6: action id {HUNT_START_ACTION_ID} (início da hunt) aparece em '
              f'mais de uma tile — usando a primeira encontrada {start_marker}.')
    elif start_marker is None:
        print(f'[WARN] v6: nenhuma tile com action id {HUNT_START_ACTION_ID} '
              f'— sem posição de entrada, e defaultZ decidido por heurística '
              f'(7 se existir, senão o menor z).')

    width = max_x - min_x + 1
    height = max_y - min_y + 1

    floors: Dict[str, Dict] = {}
    for z in sorted(all_zs):
        rows = []
        # Row-major, so a consumer reproduces paint order by reading in order.
        for (x, y), stack in sorted(stacks.get(z, {}).items(), key=lambda kv: (kv[0][1], kv[0][0])):
            ground = stack["ground"]
            rows.append([x - min_x, y - min_y,
                         NO_GROUND if ground is None else ground] + stack["stack"])
        floors[str(z)] = {"z": z, "tiles": rows}

    frame_sources: Dict[str, Dict[int, str]] = {}
    appearances = {
        str(appearance_id): _appearance_entry(analyze(appearance_id), packer, frame_sources)
        for appearance_id in sorted(used_ids)
    }

    sheets = {}
    for sheet_key in sorted(packer.sheets):
        dims = packer.sheet_dims(sheet_key)
        sheets[sheet_key] = {
            "image": posixpath.join(assets_root, "sheets", f"{sheet_key}.png"),
            "cellWidth": dims["cellSize"],
            "cellHeight": dims["cellSize"],
            "columns": dims["columns"],
        }

    document = {
        "version": VERSION,
        "tilewidth": TILE_SIZE,
        "tileheight": TILE_SIZE,
        "width": width,
        "height": height,
        "bounds": {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y},
        # The start marker's own floor wins outright when present — a human
        # pointed at a tile, which beats guessing from tile counts every time a
        # hunt's real content sits somewhere other than z=7 (a tower cut at
        # z=1..5, a dungeon cut at z=8). Otherwise: the surface is
        # conventionally z=7 in Tibia, so fall back to that, or to the lowest z
        # present for maps that (unusually) don't include it.
        "defaultZ": start_marker[2] if start_marker is not None
        else (7 if 7 in all_zs else min(all_zs)),
        "assetsRoot": assets_root,
        "appearances": appearances,
        "sheets": sheets,
        "floors": floors,
        "transitions": _floor_transitions(dump, analyze, used_ids, stacks, min_x, min_y,
                                          floorchange_by_id, ladder_ids),
    }

    # Where the player enters, in the same tile space as every other coordinate
    # in the file (relative to `bounds.minX/minY`), so a consumer never has to
    # know the map's world position to use it. Omitted when the map carries no
    # marker, which is how a consumer tells "not authored yet" from "enters at
    # tile 0,0".
    if start_marker is not None:
        document["start"] = {
            "x": start_marker[0] - min_x,
            "y": start_marker[1] - min_y,
            "z": start_marker[2],
        }

    return document, frame_sources
