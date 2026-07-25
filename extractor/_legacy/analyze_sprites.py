import json, os, glob
from collections import defaultdict

items_dir = 'sprites/items'
all_files = glob.glob(os.path.join(items_dir, '*.json')) + glob.glob(os.path.join(items_dir, '*/*.json'))
print(f'Total JSON files: {len(all_files)}')

# Track all flags, their types, and examples
flag_catalog = defaultdict(lambda: {'count': 0, 'type_examples': {}, 'example_ids': []})
pattern_combos = defaultdict(list)
animations_found = []
all_data = {}

for f in all_files:
    try:
        with open(f) as fh:
            data = json.load(fh)
        item_id = data.get('id', 'unknown')
        all_data[item_id] = data
        
        # Track patterns
        si = data.get('spriteInfo', {})
        pw = si.get('patternWidth', 1)
        ph = si.get('patternHeight', 1)
        pd = si.get('patternDepth', 1)
        layers = si.get('layers', 1)
        frames = si.get('patternFrames', 0)
        key = f'{pw}x{ph}x{pd} layers={layers} frames={frames}'
        if len(pattern_combos[key]) < 3:
            pattern_combos[key].append(item_id)
        else:
            pattern_combos[key].append(None)
        
        # Track animations
        if 'animation' in data:
            if len(animations_found) < 5:
                animations_found.append(data)
        
        # Track flags
        flags = data.get('flags', {})
        for flag_name, flag_val in flags.items():
            entry = flag_catalog[flag_name]
            entry['count'] += 1
            val_type = type(flag_val).__name__
            if val_type == 'dict':
                val_repr = json.dumps(flag_val)
            else:
                val_repr = str(flag_val)
            if val_repr not in entry['type_examples']:
                entry['type_examples'][val_repr] = val_type
            if len(entry['example_ids']) < 3:
                entry['example_ids'].append(item_id)
    except Exception as e:
        pass

print(f'\n=== FLAG CATALOG ({len(flag_catalog)} unique flags) ===')
for flag_name in sorted(flag_catalog.keys()):
    entry = flag_catalog[flag_name]
    print(f'\nFlag: "{flag_name}"')
    print(f'  Count: {entry["count"]}')
    print(f'  Examples IDs: {entry["example_ids"]}')
    print(f'  Value types/examples:')
    for val, typ in list(entry['type_examples'].items())[:5]:
        print(f'    {typ}: {val}')

print(f'\n=== PATTERN COMBINATIONS ({len(pattern_combos)} unique) ===')
for key in sorted(pattern_combos.keys()):
    examples = [x for x in pattern_combos[key] if x is not None][:3]
    total = len(pattern_combos[key])
    print(f'  {key}: count={total}, examples={examples}')

print(f'\n=== ANIMATIONS ({len(animations_found)} samples) ===')
for a in animations_found[:3]:
    print(json.dumps(a, indent=2))
    print('---')
