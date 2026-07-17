import os
import json
from Appearances_pb2 import Appearances
from google.protobuf.descriptor import FieldDescriptor


# =========================
# CONFIG
# =========================

AEC_FILES = {
    "items": ("items.aec", "object"),
    "effects": ("effects.aec", "effect"),
    "missiles": ("missiles.aec", "missile"),
    "outfits": ("outfits.aec", "outfit"),
}

ENABLED_GROUPS = [
    "outfits",
]

OUT_DIR = "sprites"

# Limite máximo de sprites para outfits.
# Outfits padrão têm 36 sprites (4 idle + 32 moving).
# Outfits maiores (64+) possuem addons/layers/montarias.
MAX_OUTFIT_SPRITES = 36


# =========================
# UTILS
# =========================

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def write_png(data: bytes, path: str):
    with open(path, "wb") as f:
        f.write(data)


def enum_or_value(field, value):
    if field.type == FieldDescriptor.TYPE_ENUM:
        return field.enum_type.values_by_number[value].name
    return value


def proto_to_dict(msg):
    if msg is None:
        return None

    result = {}

    for field, value in msg.ListFields():
        # repeated
        if field.label == FieldDescriptor.LABEL_REPEATED:
            result[field.name] = [
                proto_to_dict(v) if hasattr(v, "ListFields") else enum_or_value(field, v)
                for v in value
            ]

        # message
        elif field.type == FieldDescriptor.TYPE_MESSAGE:
            result[field.name] = proto_to_dict(value)

        # enum
        elif field.type == FieldDescriptor.TYPE_ENUM:
            result[field.name] = field.enum_type.values_by_number[value].name

        # primitive
        else:
            result[field.name] = value

    return result


def animation_to_dict(animation):
    loop_type_name = (
        animation.DESCRIPTOR
        .fields_by_name["loop_type"]
        .enum_type
        .values_by_number[animation.loop_type]
        .name
    )

    return {
        "synchronized": animation.synchronized,
        "loopType": loop_type_name,
        "spritePhase": [
            {
                "durationMin": phase.duration_min,
                "durationMax": phase.duration_max,
            }
            for phase in animation.sprite_phase
        ],
    }


# =========================
# CORE
# =========================

def get_frame_group_name(frame_group):
    """Retorna o nome do frame group ou None."""
    if frame_group.HasField("fixed_frame_group"):
        enum_type = frame_group.DESCRIPTOR.fields_by_name["fixed_frame_group"].enum_type
        full_name = enum_type.values_by_number[frame_group.fixed_frame_group].name
        # Simplifica o nome removendo o prefixo
        if "OUTFIT_IDLE" in full_name:
            return "idle"
        elif "OUTFIT_MOVING" in full_name:
            return "moving"
        elif "OBJECT_INITIAL" in full_name:
            return "initial"
        return full_name.lower().replace("fixed_frame_group_", "")
    return None


def extract_group(appearances, group_name: str):
    print(f"\n▶ Extraindo {group_name}")

    group_dir = os.path.join(OUT_DIR, group_name)
    ensure_dir(group_dir)

    total_pngs = 0
    skipped = 0

    for appearance in appearances:
        app_id = appearance.id
        sprite_data_offset = 0

        # Outfits com muitas sprites são ignorados (ex: animações completas de outfit)
        if group_name == "outfits":
            total_sprites = sum(
                len(fg.sprite_info.sprite_id) for fg in appearance.frame_group
            )
            if total_sprites > MAX_OUTFIT_SPRITES:
                skipped += 1
                continue

        # Processa múltiplos frame groups (IDLE, MOVING, etc.)
        frame_groups_data = []
        has_multiple_frame_groups = len(appearance.frame_group) > 1

        for fg_idx, fg in enumerate(appearance.frame_group):
            info = fg.sprite_info
            sprite_ids = list(info.sprite_id)
            has_animation = info.HasField("animation")
            frame_group_type = get_frame_group_name(fg)

            # =========================
            # SPRITE ÚNICA
            # =========================
            if len(sprite_ids) == 1:
                if has_multiple_frame_groups:
                    png_name = f"{app_id}_{fg_idx}"
                else:
                    png_name = f"{app_id}"
                png_path = os.path.join(group_dir, f"{png_name}.png")

                if not os.path.exists(png_path):
                    write_png(
                        appearance.sprite_data[sprite_data_offset],
                        png_path,
                    )
                    total_pngs += 1

                sprite_data_offset += 1

                fg_data = {
                    "spriteId": [png_name],
                    "spriteInfo": {
                        "patternWidth": info.pattern_width,
                        "patternHeight": info.pattern_height,
                        "patternDepth": info.pattern_depth,
                        "layers": info.layers,
                        "patternFrames": info.pattern_frames,
                    },
                }

                if frame_group_type:
                    fg_data["frameGroup"] = frame_group_type
                
                if has_animation:
                    fg_data["spriteInfo"]["animation"] = animation_to_dict(
                        info.animation
                    )

                frame_groups_data.append(fg_data)

            # =========================
            # VARIAÇÕES / ANIMAÇÃO
            # =========================
            else:
                anim_dir = os.path.join(group_dir, str(app_id))
                ensure_dir(anim_dir)

                sprite_names = []
                # Offset base para não sobrescrever sprites de outro frame group
                base_offset = sum(
                    len(appearance.frame_group[j].sprite_info.sprite_id)
                    for j in range(fg_idx)
                )

                for i in range(len(sprite_ids)):
                    name = f"{app_id}_{base_offset + i}"
                    sprite_names.append(name)

                    png_path = os.path.join(anim_dir, f"{name}.png")

                    if not os.path.exists(png_path):
                        write_png(
                            appearance.sprite_data[sprite_data_offset],
                            png_path,
                        )
                        total_pngs += 1

                    sprite_data_offset += 1

                fg_data = {
                    "spriteId": sprite_names,
                    "spriteInfo": {
                        "patternWidth": info.pattern_width,
                        "patternHeight": info.pattern_height,
                        "patternDepth": info.pattern_depth,
                        "layers": info.layers,
                        "patternFrames": info.pattern_frames,
                    },
                }

                if frame_group_type:
                    fg_data["frameGroup"] = frame_group_type

                if has_animation:
                    fg_data["spriteInfo"]["animation"] = animation_to_dict(
                        info.animation
                    )

                frame_groups_data.append(fg_data)

        # Salva o JSON consolidado com todos os frame groups
        if len(frame_groups_data) == 1:
            # Um único frame group - JSON simples
            json_data = {
                "id": app_id,
                **frame_groups_data[0],
                "flags": proto_to_dict(appearance.flags)
                if appearance.HasField("flags")
                else {},
            }
            
            if len(list(info.sprite_id)) == 1:
                json_path = os.path.join(group_dir, f"{app_id}.json")
            else:
                json_path = os.path.join(group_dir, str(app_id), f"{app_id}.json")
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        else:
            # Múltiplos frame groups - array de frame groups
            json_data = {
                "id": app_id,
                "frameGroups": frame_groups_data,
                "flags": proto_to_dict(appearance.flags)
                if appearance.HasField("flags")
                else {},
            }
            
            anim_dir = os.path.join(group_dir, str(app_id))
            ensure_dir(anim_dir)
            json_path = os.path.join(anim_dir, f"{app_id}.json")
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

    print(f"✔ {group_name}: {total_pngs} PNGs extraídos")
    if skipped:
        print(f"  ⏭ {skipped} outfits ignorados (>{MAX_OUTFIT_SPRITES} sprites)")


# =========================
# ENTRY POINT
# =========================

def main():
    ensure_dir(OUT_DIR)

    for group_name in ENABLED_GROUPS:
        aec_file, field_name = AEC_FILES[group_name]

        if not os.path.exists(aec_file):
            print(f"⚠ Arquivo não encontrado: {aec_file}")
            continue

        with open(aec_file, "rb") as f:
            data = f.read()

        appearances = Appearances()
        appearances.ParseFromString(data)

        extract_group(getattr(appearances, field_name), group_name)

    print("\nDONE ✔")


if __name__ == "__main__":
    main()
