import json, os, glob

items_dir = 'sprites/items'

# Check for animation in ANY key
all_files = glob.glob(os.path.join(items_dir, '*.json')) + glob.glob(os.path.join(items_dir, '*/*.json'))

anim_count = 0
anim_examples = []
multi_sprite = []
subdir_files = []

for f in all_files:
    try:
        with open(f) as fh:
            raw = fh.read()
        data = json.loads(raw)
        
        # Check if file is in a subdirectory
        if '/' in f.replace(items_dir + '/', '').replace(items_dir + '\\', ''):
            if len(subdir_files) < 5:
                subdir_files.append((f, data))
        
        # Check for animation anywhere in the JSON
        if 'animation' in raw and len(anim_examples) < 3:
            anim_examples.append(data)
            anim_count += 1
        elif 'animation' in raw:
            anim_count += 1
        
        # Check for multiple sprites
        sprites = data.get('spriteId', [])
        if len(sprites) > 4 and len(multi_sprite) < 5:
            multi_sprite.append(data)
            
    except:
        pass

print(f"Animation items found: {anim_count}")
print("\n=== ANIMATION EXAMPLES ===")
for a in anim_examples:
    print(json.dumps(a, indent=2))
    print("---")

print(f"\n=== MULTI-SPRITE ITEMS ({len(multi_sprite)} examples) ===")
for m in multi_sprite:
    print(f"ID={m.get('id')}, sprites={len(m.get('spriteId',[]))}, spriteInfo={m.get('spriteInfo')}")

print(f"\n=== SUBDIRECTORY FILES ({len(subdir_files)} examples) ===")
for path, data in subdir_files:
    print(f"Path: {path}")
    print(json.dumps(data, indent=2)[:500])
    print("---")

# Read missile files
missiles_dir = 'sprites/missiles'
missile_files = glob.glob(os.path.join(missiles_dir, '*.json')) + glob.glob(os.path.join(missiles_dir, '*/*.json'))
print(f"\n=== MISSILE FILES ({len(missile_files)} total) ===")
for mf in missile_files[:5]:
    with open(mf) as fh:
        data = json.load(fh)
    print(json.dumps(data, indent=2))
    print("---")
