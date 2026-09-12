Status: histórico — implementado. Reescrito no ticket 11 para descrever o mecanismo atual
(`--export` sobre o catálogo) em vez do `json-server`/`db.json` que nunca chegou a existir.

Status: ready-for-agent

# Travel Graph & Locations

## Problem Statement

Tibia Idle needs to convey how long it takes a character to travel between meaningful points on the
map — city temple to a hunt spot, hunt to hunt, hunt to depot, hunt to an NPC shop — without drawing
the full world map and without falling back to straight-line (euclidean) distance, which ignores
walls, water, holes and other obstacles and would make travel time feel arbitrary.

The OTBM → `map.json` pipeline already extracts everything needed to know which tiles are walkable
(`objectDefs[id].flags.unpass`) and which tiles change floor (`objectDefs[id].flags.isFloorTransition`).
Nobody should have to walk every route by hand or hand-maintain a distance table that silently drifts
out of sync with the map.

Separately, NPCs are currently invisible to the game data model entirely — there is no way to know
where an NPC stands, what it's called in-game, or what it buys/sells. That data exists today only
inside the Canary server's own script files, disconnected from this repo.

## Solution

Points of interest (city temple, hunt entrances, depots, quest spots) are marked directly in the
source `.otbm` using the existing sign item (2016), each with a reserved unique id (uid 10001+) and a
text label following the convention `CIDADE-TIPO-INCREMENTAL` (e.g. `ROOK-HUNT-001`). NPC locations
need no sign — their position comes straight from the map editor's own NPC export
(`<region>-npc.xml`), matched by name-slug against the Canary server's per-NPC Lua script to pull its
shop table (buy/sell prices), when that NPC has one.

A new pure-logic module (with a thin CLI on top, following the same shape as the existing hunt
fragment tooling) reads the full-city OTBM once, produces:

- a walkability graph over every exported floor (nodes = walkable tiles, edges = orthogonal/diagonal
  neighbors at cost 1, plus same-column edges across floors wherever a tile is flagged
  `isFloorTransition`)
- a single BFS per marked POI, spreading out until every other POI in the region has been reached
  (early exit — no need to flood the whole graph)

...and emits two collections — `locations` (the POI catalog: id, type, position, display name, and
type-specific payload such as an NPC's shop) and `travelGraph` (one `tileCount` edge per reachable
pair of locations) — as a fragment to merge into the sibling `tibia-idle` repo's content catalog,
the same way hunt/monster/loot data is merged today.

Downstream, `libs/game-logic` (separate, later ticket) turns a `tileCount` plus the traveling
character's current speed stat into a travel time in minutes/seconds — approximate and plausible,
not a tile-by-tile simulation.

## User Stories

1. As a map editor, I want to drop a sign with a conventional id (`ROOK-HUNT-003`) at a hunt entrance, so that the entrance becomes a travel-graph node without touching any code.
2. As a map editor, I want the same sign mechanism to mark the city temple, depots, and quest spots, so that every kind of destination the game cares about can be represented uniformly.
3. As a map editor, I want NPC locations to require no sign at all, so that the 15+ already-placed NPCs in `rook-full-npc.xml` don't need manual re-marking.
4. As a developer, I want the extractor to read every sign with a uid in the reserved range (10001+) across all floors of the full-city OTBM, so that the POI list is derived, not hand-maintained.
5. As a developer, I want sign text validated against the `CIDADE-TIPO-INCREMENTAL` convention, so that a malformed or legacy-format sign is caught instead of silently producing a bad id.
6. As a developer, I want the marker signs stripped from the map.json used for anything player-facing, so that a debug tool inspecting that map.json doesn't show random unlit signs at hunt entrances (moot for actual gameplay today, since hunt maps are separate exports, but keeps the artifact clean for inspection/tooling).
7. As a developer, I want a walkability graph built from the full-city `map.json` (every exported floor), using the same `unpass` flag already powering `blockedTiles` in `GridMovement`, so that the graph reflects real obstacles instead of raw coordinates.
8. As a developer, I want floor-transition tiles to connect to the same `(x, y)` on both the floor above and below, so that BFS can cross floors without needing to resolve the ambiguous up/down direction the `isFloorTransition` heuristic can't determine (per ADR 0002).
9. As a developer, I want one BFS run per marked POI (not all-pairs pathfinding), so that computing every pairwise distance in a region stays cheap.
10. As a developer, I want BFS to stop early once every other POI in the region has been reached, so that a region with a handful of POIs doesn't require flooding the entire tile graph.
11. As a developer, I want two disconnected POIs to simply produce no edge between them, so that a disconnected region of the map isn't treated as an error condition.
12. As a developer, I want `locations` and `travelGraph` to be two facets of the same catalog (a location referenced by id, not two separately-maintained lists of the same points), so that POI coordinates never drift out of sync between the two.
13. As a developer, I want NPC locations built from `<region>-npc.xml` (`centerx/centery/centerz` + `name`), so that I don't have to re-enter positions the map editor already recorded.
14. As a developer, I want each NPC's name slugified and matched against a `.lua` file in the Canary server's `data-otservbr-global/npc/` directory, so that its shop table can be pulled automatically instead of transcribed by hand.
15. As a developer, I want the NPC's `npcConfig.shop` table parsed for `itemName`, `clientId`, `buy` and `sell`, so that price data reaches the game without hand-entry.
16. As a developer, I want `clientId` from the Canary shop table used directly as the item id (verified against Canary's own C++ handling and against `items.xml`, where it matches the same id this pipeline's `objectDefs`/item extraction already uses), so that no separate item-id translation table is needed.
17. As a developer, when an NPC's name doesn't match any `.lua` file, I want a Location created anyway (position + name, no `shop` field) plus a warning surfaced in the tool's output, so that a missing shop doesn't block the whole batch and doesn't get silently lost either.
18. As a developer, I want NPC location ids generated as a name slug (`rook-npc-obi`), so that ids stay stable across re-runs without needing a hand-maintained counter.
19. As a developer, I want non-NPC locations (HUNT/TEMPLE/DEPOT/QUEST) to get a placeholder `displayName` (derived from the id) flagged for human curation the first time they're generated, and never overwritten on subsequent runs, so that the workflow matches the existing hunts append-only/`_todo` convention instead of introducing a new one.
20. As a developer, I want the whole feature exercised through a pure-logic module with no file I/O, tested with small in-memory fixtures (no real `.otbm`/`.lua` files touched in unit tests), so that tests stay fast and the seam matches the rest of the extractor's fragment-generation tooling.
21. As a developer, I want a thin CLI on top of that module (reads the OTBM dump, the appearance-flags table, `npc.xml`, and the Canary NPC data from disk; writes a fragment file, or merges into the catalog with `--export`), so that generating/updating the data is a single command, same as `build_hunt_fragment.py`.
22. As a developer, I want this first implementation scoped to Rookgaard only, but parameterized by region name / OTBM path (not hardcoded), so that pointing it at another city later doesn't require a redesign.
23. As a game-logic developer (future ticket), I want a function that turns a `tileCount` and the traveling character's current speed stat into a travel time in ms, so that faster characters get proportionally shorter travel times without the travel-graph data itself needing to change.
24. As a game-logic developer (future ticket), I want buffs/equipment that modify speed to be a later extension on top of the base speed stat, so that this ticket isn't blocked on designing buff stacking.

## Implementation Decisions

- **Marker item**: existing sign item **2016**. Its OTBM unique id (`uid`) uses a reserved range starting at **10001**; the sign's free-text attribute carries the POI id and is the sole parsed source of that id (no separate uid→id lookup table).
- **Id convention**: `CIDADE-TIPO-INCREMENTAL`, e.g. `ROOK-HUNT-001`, `ROOK-DEPOT-001`, `ROOK-TEMPLE-001`, `ROOK-QUEST-001`. Types marked by sign: `HUNT`, `TEMPLE`, `DEPOT`, `QUEST`. The 12 hunt signs already placed (legacy `ROOK-000X` text, no `TIPO` segment) will be hand-edited to the new convention before the extractor is run against them — the parser only supports one format, no legacy fallback.
- **NPC locations are sign-free**: type `NPC` locations are built entirely from `<region>-npc.xml` (`centerx/centery/centerz`, `name`) — never from a sign.
- **Full-city OTBM is graph-only input, never a render target**: the walkability graph and POI extraction run against the full `rook-full.otbm`, processed once through the existing OTBM→`map.json` pipeline. The resulting `map.json` is versioned in git (as a build artifact useful for inspection/debugging) but is never the map a player's client loads — hunt maps remain the existing small, separately-exported, unconnected per-hunt maps. Marker signs are filtered out of this derived `map.json`.
- **Walkability graph**: nodes are tiles without `objectDefs[id].flags.unpass`; edges connect orthogonal and diagonal neighbors on the same floor at cost 1 (no diagonal penalty). A tile flagged `isFloorTransition` also gets an edge to the same `(x, y)` on **both** `z-1` and `z+1` (whichever is walkable) — the ambiguity flagged in ADR 0002 (the ground-truth up/down direction can't be derived from the flag alone) is accepted as-is rather than resolved with extra heuristics.
- **Distance semantics**: BFS runs once per marked POI, over uniform cost-1 edges, with early exit once every other POI in the region has been reached. This produces one `tileCount` per *pair* of POIs independently — proximity is never inferred relative to a shared hub, matching the intuition that being close to POI B from POI A says nothing about the distance to POI C from POI A. Unreachable pairs (disconnected graph regions) simply produce no edge — expected, not an error.
- **Locations and POIs are one entity, not two**: a single catalog (`locations`), each entry `{id, type, x, y, z, displayName, ...type-specific payload}`. `travelGraph` holds only `{from, to, tileCount}` edges referencing those same ids — coordinates are never duplicated between the two collections.
- **NPC shop extraction**: NPC name is slugified and matched against a same-named `.lua` file under the Canary checkout's `data-otservbr-global/npc/`. The file's `npcConfig.shop` table is parsed (text/regex-based, no full Lua interpreter needed — the table shape is regular) for `itemName`, `clientId`, `buy` (optional), `sell` (optional).
- **`clientId` is the item id, verified**: despite the name, Canary's own NPC shop handler (`npc_functions.cpp`) uses the shop table's `clientId` directly as the item id with no translation, and it matches the `id` attribute already used by `items.xml` and by this pipeline's own item/`objectDefs` extraction. No clientId→itemId conversion table is needed.
- **Unmatched NPC → shop-less Location, not a hard failure**: if no `.lua` matches, the Location is still created (id, position, name) without a `shop` field, and the run's output calls it out (console warning) so it can be reviewed — mirrors, rather than duplicates, the existing `hunts` `_todo` precedent from `hunt_fragment.py`.
- **NPC location id**: a slug of the NPC's name from `npc.xml` (e.g. `rook-npc-obi`) — stable across re-runs, no incremental counter to keep in sync with anything else.
- **Non-NPC `displayName` curation**: HUNT/TEMPLE/DEPOT/QUEST locations get a placeholder `displayName` derived from the id on first generation, following the same append-only / never-overwrite-on-rerun pattern the existing `hunts` fragment uses for human-curated fields.
- **Seam**: one pure-logic module (parsing signs from the raw OTBM dump, building the walkability graph, running BFS, parsing NPC shop Lua, assembling the `locations`/`travelGraph` fragment) with a thin CLI on top that does the actual file I/O — same split as `hunt_fragment.py` / `build_hunt_fragment.py`. This is the part of the design that survived intact.
- **Distribution**: the fragment is written locally for review and never leaves `extractor/` on its own; `--export` is the separate, explicit step that merges `locations`/`travelGraph` into the `tibia-idle` catalog. See `content_export.py` and the "Export pro back-end" table in `extractor/README.md`.
- **Scope**: Rookgaard only, this round. The CLI takes a region name / OTBM path as a parameter (not hardcoded), so pointing it at another city later is a config change, not a redesign — but no other city is processed as part of this work.
- **Travel time will account for player speed** (future `libs/game-logic` ticket, decided now to avoid a rework later): `getTravelTimeMs` takes both `tileCount` and the character's current speed stat. Speed-modifying buffs/equipment are an explicit later extension, not designed here — Canary's speed stat is already a single number, so the base case needs no special modeling.

## Testing Decisions

- Tests target the pure-logic module only, following `test_hunt_fragment.py`'s style: small in-memory fixtures (dicts for parsed OTBM/`map.json` data, plain strings for Lua snippets), no real `.otbm`, `map.json`, or `.lua` files touched, no filesystem mocking.
- Cover per function group: sign parsing (valid id, malformed/legacy text rejected, uid outside the reserved range ignored), graph construction (unpass tiles excluded, diagonal neighbors included, floor-transition tiles bridge both directions), BFS (early exit once all POIs found, unreachable pair produces no edge, distance is symmetric and per-pair independent), Lua shop parsing (well-formed table, item missing `buy` or `sell`, no `shop` table present), fragment assembly (`locations`/`travelGraph` share ids, unmatched NPC gets no `shop` field plus a warning, non-NPC `displayName` defaults and its curation flag).
- Only external behavior is tested — inputs in, fragment/graph/edges out — never internal graph representation details.

## Out of Scope

- Per-tile-type movement cost (`groundSpeed`) — every tile costs 1.
- Diagonal movement cost penalty — diagonal and orthogonal both cost 1.
- Resolving the true up/down direction of a floor-transition tile — both directions get an edge.
- Storing the full walked path — only the total `tileCount` per pair.
- A*/Dijkstra or any weighted pathfinding — BFS is sufficient because every edge costs 1.
- Processing any city besides Rookgaard in this round.
- Rendering marker signs, or any part of the full-city OTBM, in a player-facing map.
- Buff/equipment-based speed modifiers in `getTravelTimeMs` (base speed stat only, for now).
- Bag-weight travel time multiplier, `RouteStep[]` route planning/automation — both explicitly noted as future extensions in the original design discussion, not part of this work.
- Migrating the 12 already-placed hunt signs to the new id convention — that's a manual map-editing task for the user, not something the extractor does.

## Further Notes

- The `clientId`-as-item-id equivalence was verified directly against Canary's C++ source
  (`npc_functions.cpp`, the shop-opening handler) and against `items.xml`, not assumed — this closed
  what looked like a real risk (a second, divergent item-id space) earlier in the design discussion.
- This repo's convention for the Rookgaard prefix is `ROOK` (see `_id_prefix_for_map` in
  `hunt_fragment.py`); the new sign-based ids should stay consistent with that existing prefix rather
  than introducing a second spelling/casing.
- The original draft of this design assumed `ServeStaticModule` + content-hash fingerprinting for
  distribution, modeled after how it believed `hunt.json`/`respawn.json` were served. It doesn't
  exist. The mechanism that does is the fragment-then-`--export` split described above.
