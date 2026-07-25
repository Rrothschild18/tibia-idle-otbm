import json, os, glob
from collections import defaultdict

items_dir = 'sprites/items'
all_files = glob.glob(os.path.join(items_dir, '*.json')) + glob.glob(os.path.join(items_dir, '*/*.json'))

# Detailed animation analysis
anim_loop_types = defaultdict(int)
anim_sync_types = defaultdict(int)
anim_phase_counts = defaultdict(int)
anim_duration_ranges = set()
anim_examples_by_type = defaultdict(list)

# Market categories
market_categories = defaultdict(int)
market_cat_examples = defaultdict(list)

# Clothes slots
clothes_slots = defaultdict(int)
clothes_examples = defaultdict(list)

# Default actions
default_actions = defaultdict(int)

# Automap colors
automap_colors = defaultdict(int)

# Bank waypoints values
bank_waypoints = defaultdict(int)

# Height elevation values
height_values = defaultdict(int)

# Light values
light_brightness = defaultdict(int)

# Hook directions
hook_dirs = defaultdict(int)

# lenshelp ids
lenshelp_ids = defaultdict(int)

# Items without flags
no_flags_count = 0

# Upgrade classifications
upgrade_vals = defaultdict(int)

# Count items with IDs below first file
min_id = 999999
max_id = 0

# Sprite count distribution
sprite_counts = defaultdict(int)

for f in all_files:
    try:
        with open(f) as fh:
            data = json.load(fh)
        item_id = data.get('id', 0)
        min_id = min(min_id, item_id)
        max_id = max(max_id, item_id)
        
        si = data.get('spriteInfo', {})
        sprites = data.get('spriteId', [])
        sprite_counts[len(sprites)] += 1
        
        # Animation analysis
        anim = si.get('animation')
        if anim:
            lt = anim.get('loopType', 'UNKNOWN')
            anim_loop_types[lt] += 1
            sync = anim.get('synchronized', None)
            anim_sync_types[str(sync)] += 1
            phases = anim.get('spritePhase', [])
            anim_phase_counts[len(phases)] += 1
            for phase in phases:
                dur_range = (phase.get('durationMin',0), phase.get('durationMax',0))
                anim_duration_ranges.add(dur_range)
            if len(anim_examples_by_type[lt]) < 2:
                anim_examples_by_type[lt].append(item_id)
        
        flags = data.get('flags', {})
        if not flags:
            no_flags_count += 1
        
        # Market
        market = flags.get('market')
        if market:
            cat = market.get('category', 'UNKNOWN')
            market_categories[cat] += 1
            if len(market_cat_examples[cat]) < 2:
                market_cat_examples[cat].append(item_id)
        
        # Clothes
        clothes = flags.get('clothes')
        if clothes:
            slot = clothes.get('slot', -1)
            clothes_slots[slot] += 1
            if len(clothes_examples[slot]) < 2:
                clothes_examples[slot].append(item_id)
        
        # Default action
        da = flags.get('default_action')
        if da:
            default_actions[da.get('action', 'UNKNOWN')] += 1
        
        # Automap
        am = flags.get('automap')
        if am:
            automap_colors[am.get('color', -1)] += 1
        
        # Bank
        bank = flags.get('bank')
        if bank:
            bank_waypoints[bank.get('waypoints', -1)] += 1
        
        # Height
        ht = flags.get('height')
        if ht:
            height_values[ht.get('elevation', -1)] += 1
        
        # Light
        lt_flag = flags.get('light')
        if lt_flag:
            light_brightness[lt_flag.get('brightness', -1)] += 1
        
        # Hook
        hk = flags.get('hook')
        if hk:
            hook_dirs[hk.get('direction', 'UNKNOWN')] += 1
        
        # Lenshelp
        lh = flags.get('lenshelp')
        if lh:
            lenshelp_ids[lh.get('id', -1)] += 1
        
        # Upgrade
        uc = flags.get('upgradeclassification')
        if uc:
            upgrade_vals[uc.get('upgrade_classification', -1)] += 1
            
    except:
        pass

print(f"ID range: {min_id} to {max_id}")
print(f"Items with NO flags: {no_flags_count}")

print(f"\n=== SPRITE COUNT DISTRIBUTION ===")
for count in sorted(sprite_counts.keys()):
    print(f"  {count} sprites: {sprite_counts[count]} items")

print(f"\n=== ANIMATION ANALYSIS ({sum(anim_loop_types.values())} animated items) ===")
print(f"\nLoop types: {dict(anim_loop_types)}")
print(f"Synchronized: {dict(anim_sync_types)}")
print(f"Phase counts: {dict(sorted(anim_phase_counts.items()))}")
print(f"Duration ranges (min,max): {sorted(anim_duration_ranges)[:20]}...")
print(f"Examples by loop type:")
for lt, examples in anim_examples_by_type.items():
    print(f"  {lt}: {examples}")

print(f"\n=== MARKET CATEGORIES ({len(market_categories)}) ===")
for cat in sorted(market_categories.keys()):
    print(f"  {cat}: {market_categories[cat]} items, e.g. {market_cat_examples[cat]}")

print(f"\n=== CLOTHES SLOTS ({len(clothes_slots)}) ===")
for slot in sorted(clothes_slots.keys()):
    print(f"  Slot {slot}: {clothes_slots[slot]} items, e.g. {clothes_examples[slot]}")

print(f"\n=== DEFAULT ACTIONS ===")
for act in sorted(default_actions.keys()):
    print(f"  {act}: {default_actions[act]}")

print(f"\n=== AUTOMAP COLORS ({len(automap_colors)} unique) ===")
for color in sorted(automap_colors.keys()):
    print(f"  Color {color}: {automap_colors[color]} items")

print(f"\n=== BANK WAYPOINTS ({len(bank_waypoints)} unique values) ===")
for wp in sorted(bank_waypoints.keys()):
    print(f"  Waypoints {wp}: {bank_waypoints[wp]} items")

print(f"\n=== HEIGHT ELEVATIONS ({len(height_values)} unique) ===")
for el in sorted(height_values.keys()):
    print(f"  Elevation {el}: {height_values[el]} items")

print(f"\n=== LIGHT BRIGHTNESS ({len(light_brightness)} unique) ===")
for br in sorted(light_brightness.keys()):
    print(f"  Brightness {br}: {light_brightness[br]} items")

print(f"\n=== HOOK DIRECTIONS ===")
print(dict(hook_dirs))

print(f"\n=== LENSHELP IDS ({len(lenshelp_ids)} unique) ===")
for lid in sorted(lenshelp_ids.keys()):
    print(f"  ID {lid}: {lenshelp_ids[lid]} items")

print(f"\n=== UPGRADE CLASSIFICATIONS ===")
for uc in sorted(upgrade_vals.keys()):
    print(f"  Class {uc}: {upgrade_vals[uc]} items")
