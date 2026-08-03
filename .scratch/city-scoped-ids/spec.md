Status: ready-for-agent

# City-scoped map folders + unified POI ids

## Problem Statement

Map folders under `extractor/maps/` are flat (`extractor/maps/bears-rookguard/`), so nothing in the
pipeline actually knows which city a map belongs to — `hunt_fragment.py`'s `_id_prefix_for_map`
guesses it from the folder name (`"...-rookguard"` → `"ROOK"`, anything else → its own first
hyphen-segment uppercased). That guess is the root cause of the inconsistent ids already in
`db.json`: `dragon-darashia` → `DRAGON-0001`, `grim-reaper` → `GRIM-0001`, `larva-ankrah` →
`LARVA-0001` — three unrelated one-off prefixes for what are really all Rookgaard-area test maps,
not real cities.

Separately, a hunt's `mapId` (`ROOK-0002`) and its travel-graph `Location.id` (`ROOK-HUNT-0002`) are
two different strings for the same place, reconciled today only by `resolveHuntLocationId` — a
derive-or-curate dance (strip `-HUNT-`, compare to `mapId`, or fall back to a hand-curated `huntId`
field) built for the AutoHunt travel-time feature (`tibia-idle`'s `.scratch/autohunt-travel/`). This
derivation is exactly the kind of two-places-to-keep-in-sync problem that produced the
`ROOK-HUNT-00015` bug found while using that feature: a sign typo (5 digits instead of 4) that
matched no format-validation rule and silently produced an id nothing could ever resolve to.

Both problems share one fix: stop deriving/guessing identity from unrelated inputs (folder-name
segments, id-stripping) and make the **folder path itself** the single source of truth for a map's
city and id.

## Solution

Every map folder — hunt or full-city — moves under a **city folder**: `extractor/maps/<CIDADE>/`,
`extractor/ready-maps/<CIDADE>/`, `extractor/full-maps/<CIDADE>/`. The city is never guessed from a
map's own name again; it's whichever city-folder the map physically lives under.

Within a city folder, each hunt map's own folder name **is** its id, plus a human-readable suffix:
`extractor/maps/ROOK/ROOK-HUNT-0002_bears-rookguard/`. The id is chosen by hand (the same id typed
into the map-editor sign marking that hunt's entrance on the full-city map) — the pipeline never
auto-numbers it, only validates it. The `-HUNT-` segment is deliberately kept and deliberately
redundant with the parent `ROOK/` folder: matching the exact sign text, byte for byte, into the
folder name is a copy-paste, not a translation — nothing to get wrong.

That same id — `-HUNT-` segment and all — becomes the hunt's `mapId` in `tibia-idle`'s `db.json`,
identical to the travel-graph `Location.id` it already had. `resolveHuntLocationId` becomes
unnecessary and is removed: a hunt's location *is* its `mapId`, full stop, no lookup.

NPC locations, which never had a sign-based id (`rook-npc-obi`, lowercase, no type segment), move to
the same `CIDADE-TIPO-slug` shape every other POI type already uses: `ROOK-NPC-obi`.

Test/throwaway maps (today `dragon-darashia`, `grim-reaper`, `larva-ankrah`, `sea-serpent`) become
their own fictional city, `TEST` — the exact same mechanism as a real city, no separate tagging
system. `tibia-idle`'s hunt list simply excludes `city: "TEST"` by default. `city` (and a
`status: "test"` mirror, set only when `city === "TEST"`) are both fields derived automatically from
the id, on every hunt/location — never hand-authored, so they can never drift from the id they
describe.

## Decisions

### Folder structure

- **City folder is the source of truth for city** — never derived from a map's own name.
  `extractor/maps/<CIDADE>/`, `extractor/ready-maps/<CIDADE>/` (mirrors `maps/` 1:1, same relative
  path under a different root), `extractor/full-maps/<CIDADE>/` (one full-city map per city, folder
  *is* the city code — no `-full` suffix; contents renamed to match, e.g. `ROOK.otbm`,
  `ROOK-house.xml`, `ROOK-monster.xml`, `ROOK-npc.xml`, `ROOK-zones.xml`, output `map.json` in the
  same folder).
- **A hunt map's own folder name is its id + a human-readable suffix**:
  `<CIDADE-TIPO-SEQ>_nome-descritivo`, e.g. `ROOK-HUNT-0002_bears-rookguard`. The id repeats the
  parent city on purpose (`ROOK/ROOK-HUNT-0002_.../`) — this is deliberately redundant so the exact
  same string typed into the map-editor sign can be copy-pasted straight into the folder name, no
  mental concatenation of city + type + number.
- **Test/throwaway maps are a fictional city, `TEST`** — same folder mechanism, e.g.
  `extractor/maps/TEST/TEST-HUNT-0001_dragon-darashia/`. Not a separate tagging system.
- **This is a documented, mandatory naming convention** — write it into `extractor/README.md`
  alongside the existing "Como adicionar um mapa novo" walkthrough, not just implied by example.

### Ids

- **One id, no derivation**: a hunt's `mapId` (`tibia-idle` `db.json`) and its travel-graph
  `Location.id` are the exact same string, including the `-HUNT-` type segment (`ROOK-HUNT-0002`
  both places). `resolveHuntLocationId` (`tibia-idle`, `.scratch/autohunt-travel/`) is removed —
  there is nothing left to resolve.
- **The id is never auto-numbered by the pipeline.** It's chosen by hand (typed into the sign,
  mirrored into the folder name) before any script runs. `hunt_fragment.py`'s `_id_prefix_for_map`
  and `next_map_id` (today's "guess the prefix, count existing entries, add 1" logic) are deleted
  entirely — nothing in the pipeline invents an id anymore, it only reads and validates the one
  already chosen.
- **NPC locations adopt the same `CIDADE-TIPO-slug` shape**: `ROOK-NPC-obi` (today: `rook-npc-obi`,
  lowercase, no type segment) — the slug (from the NPC's name) replaces the numeric sequence, since
  NPC identity is already unique and stable without one.
- **`city` and `status` are derived fields, never hand-authored.** Every hunt/location gets
  `city` (the id's first segment, e.g. `"ROOK"`) so `tibia-idle` can filter without parsing id
  strings. `status: "test"` is set only when `city === "TEST"`; absent otherwise. Both are computed
  by the extractor on every fragment build — a human never sets or edits them, so they can never
  disagree with the id/folder they mirror.

### Pipeline mechanics

- **`build_map.js` discovers two levels**: `extractor/maps/<CIDADE>/<pasta>/`, not the current flat
  `extractor/maps/<pasta>/`. `--all` walks every city folder automatically — adding a new city is
  purely a new folder, no code change (this is what makes Carlin/Thais/Venore a config change later,
  not a redesign).
- **`--map-id` on `build_hunt_fragment.py` stays mandatory** — even though the id already lives in
  the folder name, the CLI still requires it typed out explicitly as a second, independent
  confirmation. The script parses the id out of the folder name and **compares it against
  `--map-id`**; a mismatch is a hard error naming both values, not a silent pick-one.
- **`--edit` is required to update an id that already exists.** Default behavior (no `--edit`) on a
  `mapId`/`Location.id` that already exists in `db.json` is a hard error
  ("ID do mapa já existe — use --edit se a intenção é atualizar"), never a silent upsert. `--edit`
  is the explicit, deliberate gate for updating curated data.
- **Every validation failure gets its own specific, unambiguous message** — never a shared generic
  string covering multiple distinct reasons. This directly fixes a real bug found while building the
  AutoHunt travel-time feature: `build_travel_fragment.py`'s warning loop printed
  `"placa fora do formato CIDADE-TIPO-INCREMENTAL"` for *both* an actually-malformed sign **and** a
  duplicate-id sign, so a perfectly well-formed but duplicated sign (`ROOK-HUNT-0006`, placed twice)
  was misreported as a format problem. Each distinct failure reason (duplicate id, malformed text,
  `--map-id`/folder mismatch, id already exists without `--edit`, unrecognized city, NPC `.lua` not
  found, ...) gets its own message naming the actual cause.
- **Sign-text format validation gets stricter**: the existing regex accepts any digit-length
  sequence (`\d+`), which is how `ROOK-HUNT-00015` (5 digits, a typo) slipped through as a
  syntactically "valid" but semantically orphaned id, matching no real hunt. Format validation
  should reject stray digit counts instead of silently minting an unresolvable id.

### Migration

- **The 20 existing map folders move under `extractor/maps/ROOK/`** (all Rookgaard today, except the
  four test maps which move to `extractor/maps/TEST/`), renamed to the new
  `<CIDADE-TIPO-SEQ>_nome/` convention.
- **The 9 hunts already resolved to a location** gain the `-HUNT-` segment in their `mapId`
  (`ROOK-0001` → `ROOK-HUNT-0001`, etc.) — same sequence numbers, no renumbering, just inserting the
  segment that was always implicitly true. The other 9 hunts (no location placed yet) are unaffected
  until their sign is placed.
- **Signs on `rook-full.otbm` are hand-edited** to match the new folder names (already true for the
  9 resolved hunts; this migration doesn't change *what* they point to, only normalizes drift like
  the `ROOK-HUNT-00015` typo along the way).
- **`tibia-idle`'s `db.json` is rewritten wholesale for the affected collections**
  (`hunts`/`monsters`/`loot`/`locations`/`travelGraph`) — a full regenerate-and-replace via the
  migrated pipeline, not a careful field-by-field incremental merge. Already-curated fields
  (`displayName`, NPC `shop` entries not derived from the id change) are preserved by construction
  since the migration only touches the id shape, not the curated content itself.

## Out of Scope

- Actually processing a second city (Carlin/Thais/Venore) — this makes it a config change (new
  folder) rather than a redesign, but no second city is built as part of this work.
- A UI for choosing/switching city in `tibia-idle` beyond a plain `city` filter on the hunts list —
  a full city-selection screen is a future concern once a second city actually exists.
- Environment-based (dev/hom/prod) visibility gating mentioned as a future direction for `status` —
  `status: "test"` only ever means "belongs to the `TEST` city" for now; nothing reads it yet beyond
  the hunts-list filter.
- Changing anything about how `travel_graph.py`'s BFS/walkability graph itself works (tile costs,
  diagonal movement, floor transitions) — untouched, this is purely an id/folder-structure change.
- Any change to loot/monster data shape beyond the `mapId` they're keyed by changing shape.

## Further Notes

- This spec spans two repositories: `tibia-idle-otbm` (the extractor pipeline — tickets 01-06) and
  `tibia-idle` (the front-end consuming `db.json` — tickets 07-09). The `tibia-idle` tickets are
  blocked on the `tibia-idle-otbm` migration (06) actually landing, since the front-end change
  assumes the new id shape already exists in `db.json`.
- The `ROOK-HUNT-00015` and duplicate-`ROOK-HUNT-0006` issues were found live, by hand, while
  testing the AutoHunt travel-time feature — not hypothetical failure modes. Both are fixed as a
  side effect of this migration (stricter format validation catches the first; the folder-is-the-id
  rule makes the second structurally impossible, since two map folders can't share a name).
