"""The tile stack, built the way Remere's Map Editor builds it.

Pure model, no I/O: given the appearances an OTBM tile holds and the flags each
one carries in `appearances.dat`, it answers which one is the tile's ground and
in what order the rest are drawn.

Three rules, all read straight off the flags — no heuristic, no hand-written id
list, no wall/border/roof detection:

- **Draw slot** comes from `bank`. One ground per tile, drawn first; everything
  else is an item. Passability (`unpass`) says nothing about it: an impassable
  ground is still ground.
- **Top order** comes from `clip` (1), `bottom` (2) and `top` (3). Any of the
  three marks the appearance as a background item.
- **Stack order** is ground, then background items by ascending top order, then
  the rest in insertion order — with insertion order breaking every tie.

Depth is a consequence of that order (paint order = floor → row → stack order),
never a constant assigned per category. See `CONTEXT.md` for the vocabulary and
`.scratch/modelo-render-rme/spec.md` for why the previous eight-role model went
away.

The editor's own authoring data (`ground_equivalent`) is deliberately not
consulted: measured at zero divergence against every map in the repo — see
`.scratch/modelo-render-rme/reports/02-ground-equivalent.md`.
"""

from typing import Dict, Iterable, List, Optional, Tuple

GROUND = "ground"
ITEM = "item"

# Ascending: the lower the number, the closer to the floor the item sits.
TOP_ORDER_BY_FLAG = [("clip", 1), ("bottom", 2), ("top", 3)]

Placement = Tuple[int, Dict]  # (appearance id, flags)


def draw_slot(flags: Dict) -> str:
    """`GROUND` when the appearance carries `bank`, `ITEM` otherwise.

    Truthiness, not presence: raw `appearances.dat` metadata omits the key
    entirely and carries `{"waypoints": N}` when it is set, but the analysis
    dict `build_phaser_map.analyze_item` produces always has every flag key,
    holding `False` when absent. Both readings have to agree.
    """
    return GROUND if flags.get("bank") else ITEM


def top_order(flags: Dict) -> Optional[int]:
    """`1`/`2`/`3` for a background item, `None` for everything else.

    An appearance carrying more than one background flag takes the lowest —
    the flags are not mutually exclusive in `appearances.dat`, and the lowest
    is the one that decides how close to the floor it sits.
    """
    for flag, order in TOP_ORDER_BY_FLAG:
        if flags.get(flag):
            return order
    return None


def build_tile_stack(placements: Iterable[Placement]) -> Dict:
    """`{"ground": appearance id or None, "stack": [appearance ids]}`.

    `placements` is the tile's appearances in the order the OTBM holds them —
    the ground slot first when the tile has one, then the items as inserted.

    A tile can hold at most one ground. A second `bank` appearance (which no
    tile in the current map set has) stays drawable rather than being dropped:
    it falls back into the stack, in the plain-item group, in insertion order.
    """
    ground: Optional[int] = None
    background: List[Tuple[int, int]] = []  # (top order, appearance id)
    plain: List[int] = []

    for appearance_id, flags in placements:
        if draw_slot(flags) == GROUND and ground is None:
            ground = appearance_id
            continue

        order = top_order(flags)
        if order is None:
            plain.append(appearance_id)
        else:
            background.append((order, appearance_id))

    # `sorted` is stable, so appearances sharing a top order keep the order the
    # OTBM listed them in.
    stack = [appearance_id for _, appearance_id in sorted(background, key=lambda pair: pair[0])]
    stack.extend(plain)

    return {"ground": ground, "stack": stack}
