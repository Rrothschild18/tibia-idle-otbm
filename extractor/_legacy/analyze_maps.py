import json, os, glob
from collections import defaultdict

# Analyze map JSONs
for map_file in ['dragon-darashia.raw.json', 'larva-ankrah.raw.json']:
    print(f"\n{'='*60}")
    print(f"=== MAP: {map_file} ===")
    print(f"{'='*60}")
    
    with open(map_file) as f:
        data = json.load(f)
    
    # Show top-level structure
    print(f"\nTop-level keys: {list(data.keys())}")
    
    tile_ids = set()
    item_ids = set()
    item_id_counts = defaultdict(int)
    
    def extract_ids(obj, depth=0):
        if isinstance(obj, dict):
            if 'tileid' in obj:
                tile_ids.add(obj['tileid'])
            if 'id' in obj and depth > 0:
                item_ids.add(obj['id'])
                item_id_counts[obj['id']] += 1
            for v in obj.values():
                extract_ids(v, depth+1)
        elif isinstance(obj, list):
            for item in obj:
                extract_ids(item, depth+1)
    
    extract_ids(data)
    
    print(f"\nUnique tile IDs: {len(tile_ids)}")
    print(f"Tile ID range: {min(tile_ids) if tile_ids else 'N/A'} - {max(tile_ids) if tile_ids else 'N/A'}")
    print(f"All tile IDs: {sorted(tile_ids)}")
    
    print(f"\nUnique item IDs: {len(item_ids)}")
    print(f"All item IDs (sorted): {sorted(item_ids)}")
    
    # Top 20 most used items
    top_items = sorted(item_id_counts.items(), key=lambda x: -x[1])[:20]
    print(f"\nTop 20 most-used items:")
    for item_id, count in top_items:
        print(f"  ID {item_id}: used {count} times")
    
    # Look up flags for each item
    print(f"\n--- Item flag profiles ---")
    items_dir = 'sprites/items'
    for item_id in sorted(item_ids):
        # Try to find its JSON
        json_path = os.path.join(items_dir, f'{item_id}.json')
        if os.path.exists(json_path):
            with open(json_path) as jf:
                item_data = json.load(jf)
            flags = item_data.get('flags', {})
            flag_names = list(flags.keys())
            si = item_data.get('spriteInfo', {})
            pw = si.get('patternWidth', 1)
            ph = si.get('patternHeight', 1)
            pd = si.get('patternDepth', 1)
            has_anim = 'animation' in si
            print(f"  Item {item_id}: pattern={pw}x{ph}x{pd} anim={has_anim} flags={flag_names}")
        else:
            print(f"  Item {item_id}: JSON NOT FOUND")

# Also check structure of first few tiles/items in the raw JSON
print(f"\n{'='*60}")
print("=== SAMPLE MAP STRUCTURE ===")
print(f"{'='*60}")

with open('dragon-darashia.raw.json') as f:
    data = json.load(f)

# Show first tile structure
def find_first_tiles(obj, path="root", found=[], max_found=3):
    if len(found) >= max_found:
        return
    if isinstance(obj, dict):
        if 'tileid' in obj:
            found.append((path, obj))
            return
        for k, v in obj.items():
            find_first_tiles(v, f"{path}.{k}", found, max_found)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:5]):
            find_first_tiles(item, f"{path}[{i}]", found, max_found)

tiles_found = []
find_first_tiles(data, found=tiles_found)
for path, tile in tiles_found:
    print(f"\nPath: {path}")
    tile_str = json.dumps(tile, indent=2)
    if len(tile_str) > 800:
        tile_str = tile_str[:800] + "..."
    print(tile_str)
