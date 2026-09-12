import argparse
import os
import json
import sys
from typing import List, NamedTuple, Optional, Tuple

import client_sprites
import fetch_assets
import paths
from Appearances_pb2 import Appearances
from google.protobuf.descriptor import FieldDescriptor


# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

# Grupo de saída -> campo do `appearances.dat`. Os quatro vivem no mesmo
# arquivo protobuf do cliente; antes eram quatro containers `.aec` separados,
# de ~270 MB no total, que nenhum clone tinha.
APPEARANCE_GROUPS = {
    "items": "object",
    "effects": "effect",
    "missiles": "missile",
    "outfits": "outfit",
}

# Fonte de pixels, resolvida em main(). Módulo-level porque o caminho de
# extração é recursivo e passar isso por sete assinaturas não paga.
SPRITES: Optional[client_sprites.ClientSprites] = None

# Os grupos que uma execução sem argumento extrai. `effects` entrou pelo efeito
# de nascimento de monstro (CONST_ME_TELEPORT, id 11) — ver SPRITE_METADATA.md,
# seção "Effects". Rodar só um grupo (`--group effects`) evita reparsear os
# 130MB de outfits.aec quando não é ele que mudou.
ENABLED_GROUPS = [
    "outfits",
    "effects",
]

OUT_DIR = os.path.join(EXTRACTOR_DIR, "sprites")


# =========================
# EIXOS E LEI DE ÍNDICE
# =========================

class SpriteAxes(NamedTuple):
    """Os eixos de uma appearance, com os nomes que eles significam.

    O protobuf chama estes campos de pattern_width/height/depth, que dizem o
    formato e não o sentido. Num outfit: width é direção, height é addon,
    depth é montaria.
    """

    directions: int  # x — pattern_width
    addons: int      # y — pattern_height
    mounts: int      # z — pattern_depth
    layers: int
    phases: int

    def total(self) -> int:
        return self.directions * self.addons * self.mounts * self.layers * self.phases


# A forma dos 22 outfits de jogador em outfits.aec: 432 sprites, dois frame
# groups (idle com 1 fase, moving com 8).
PLAYER_SOURCE_AXES = SpriteAxes(directions=4, addons=3, mounts=2, layers=2, phases=9)

# O que a extração declara no JSON. Igual à fonte menos montaria, que é
# descartada — ver OUTFIT_SPRITES_DOCUMENTATION.md. Declarar é o ponto: sem
# isto o consumidor deduz os eixos da contagem de frames, que é o hábito que
# produziu a documentação errada.
PLAYER_DECLARED_AXES = {
    "directions": PLAYER_SOURCE_AXES.directions,
    "phases": PLAYER_SOURCE_AXES.phases,
    "layers": PLAYER_SOURCE_AXES.layers,
    "addons": PLAYER_SOURCE_AXES.addons,
    "mounts": 1,
}

# O catálogo fixo de outfits de jogador, tirado de `data/XML/outfits.xml` do
# Canary (não do .aec, que não guarda nome nenhum — ver OUTFIT_NAMES). São 242
# ids (121 outfits x macho/fêmea), os 22 clássicos entre eles. Todo id fora
# desta lista que ainda assim bate na forma de outfit de jogador (addon,
# montaria, layer) é outra coisa — GM, id removido, etc. — e continua sendo
# descartado por `has_non_creature_axis`.
def _load_outfit_names() -> dict:
    path = os.path.join(SCRIPTS_DIR, "outfit_names.json")
    with open(path, "r", encoding="utf-8") as handle:
        return {int(k): v for k, v in json.load(handle).items()}


OUTFIT_NAMES = _load_outfit_names()
PLAYER_OUTFIT_IDS = tuple(sorted(OUTFIT_NAMES))

DIRECTION_NAMES = ("north", "east", "south", "west")
LAYER_NAMES = ("base", "mask")


def frame_index(phase: int, z: int, y: int, x: int, layer: int,
                axes: SpriteAxes = PLAYER_SOURCE_AXES) -> int:
    """A posição de uma sprite na lista plana de uma appearance.

    O eixo que varia mais rápido é `layer`, o mais lento é `fase` — os frames
    vêm intercalados por direção, nunca agrupados por ela. Mesma lei do
    ADR-0014 do tibia-idle, com o eixo `layer` a mais.
    """
    return ((((phase * axes.mounts + z) * axes.addons + y) * axes.directions + x)
            * axes.layers) + layer


def is_player_outfit(app_id: int) -> bool:
    """True para os ids do catálogo fixo de outfits.xml (ver PLAYER_OUTFIT_IDS).

    A pergunta é "este outfit é de jogador?", e não "este outfit tem eixos
    demais?" — a lista é conhecida e finita, e vem do jogo, não do .aec. Ver
    `has_non_creature_axis` para o que acontece com o resto.
    """
    return app_id in PLAYER_OUTFIT_IDS


def frame_key(outfit_id: int, layer: int, addon: int, direction: int, phase: int) -> str:
    """`128_mask_a0_north_2` — deliberadamente não o `<id>_<n>` numérico dos
    atlases de criatura. Uma chave numérica fica calada quando alguém soma o
    índice errado; esta não."""
    return f"{outfit_id}_{LAYER_NAMES[layer]}_a{addon}_{DIRECTION_NAMES[direction]}_{phase}"


def player_frame_plan(outfit_id: int, axes: SpriteAxes) -> List[Tuple[str, int]]:
    """(chave, índice na lista plana) para os 216 frames que sobrevivem.

    Montaria (`z = 1`) fica de fora: aqueles frames são o personagem sentado
    em pose de montaria, e o bicho embaixo é uma appearance separada.
    Percorre na ordem da lei de índice, para que a posição no sheet assado
    depois seja previsível a olho.
    """
    plan = []
    for phase in range(axes.phases):
        for addon in range(axes.addons):
            for direction in range(axes.directions):
                for layer in range(axes.layers):
                    plan.append((
                        frame_key(outfit_id, layer, addon, direction, phase),
                        frame_index(phase, 0, addon, direction, layer, axes),
                    ))
    return plan


# =========================
# UTILS
# =========================

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def write_png(data: bytes, path: str):
    with open(path, "wb") as f:
        f.write(data)


def write_sprite(sprite_id: int, path: str) -> bool:
    """Recorta o sprite do cliente e grava. False se o id não existe.

    Antes os bytes vinham de `appearance.sprite_data[i]`, um campo não-padrão
    (`Appearances.proto:67`) que só o export `.aec` preenchia. Agora vêm da
    folha do cliente, pelo mesmo id que o protobuf oficial já declarava em
    `sprite_info.sprite_id` — o campo que este script sempre leu em paralelo.
    """
    blob = SPRITES.sprite_png(sprite_id)
    if blob is None:
        return False
    write_png(blob, path)
    return True


def concatenated_sprite_ids(appearance) -> List[int]:
    """Os sprite ids de todos os frame groups, na ordem em que `sprite_data`
    vinha concatenado — idle e depois moving. É essa concatenação que a lei de
    índice do outfit de jogador endereça."""
    ids: List[int] = []
    for fg in appearance.frame_group:
        ids.extend(fg.sprite_info.sprite_id)
    return ids


def enum_or_value(field, value):
    if field.type == FieldDescriptor.TYPE_ENUM:
        return field.enum_type.values_by_number[value].name
    return value


def _is_repeated(field) -> bool:
    """`FieldDescriptor.label` foi removido no protobuf 7; `is_repeated` é o
    substituto. Aceitar os dois evita prender o repo a uma major do runtime —
    o piso que importa é o 6.33.5 que `Appearances_pb2.py` exige no import."""
    is_repeated = getattr(field, "is_repeated", None)
    if is_repeated is not None:
        return bool(is_repeated)
    return field.label == FieldDescriptor.LABEL_REPEATED


def proto_to_dict(msg):
    if msg is None:
        return None

    result = {}

    for field, value in msg.ListFields():
        # repeated
        if _is_repeated(field):
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

def has_non_creature_axis(appearance) -> bool:
    """True se a appearance usa algum eixo que o caminho de criatura não sabe
    ler: addon (`pattern_height`), montaria (`pattern_depth`) ou layer.

    O caminho de criatura assume `frameIndex % 4 == direção` e uma camada só.
    Uma appearance que mexe em qualquer um destes três eixos quebra essa
    conta, e é por isso que ela sai por outro caminho — não por ter "sprites
    demais". Criatura com IDLE animado (Wasp, Ghost, Fire Elemental) passa
    bem dos 36 sprites e continua entrando aqui, porque mantém os três eixos
    em 1.

    Os outfits de jogador batem nos três de uma vez, e têm caminho próprio
    (`is_player_outfit`). O que sobra são appearances de criatura fora do
    formato — descartadas, como sempre foram.
    """
    for fg in appearance.frame_group:
        info = fg.sprite_info
        if info.pattern_height > 1 or info.pattern_depth > 1 or info.layers > 1:
            return True
    return False


def source_axes_of(appearance) -> SpriteAxes:
    """Os eixos declarados pela appearance, com as fases somadas entre frame
    groups. `pattern_frames` vem 0 nos outfits, então a contagem de fases sai
    da divisão do número de sprites pelos outros eixos."""
    first = appearance.frame_group[0].sprite_info
    per_phase = (first.pattern_width * first.pattern_height
                 * first.pattern_depth * first.layers)
    phases = sum(
        len(fg.sprite_info.sprite_id) // per_phase for fg in appearance.frame_group
    ) if per_phase else 0

    return SpriteAxes(
        directions=first.pattern_width,
        addons=first.pattern_height,
        mounts=first.pattern_depth,
        layers=first.layers,
        phases=phases,
    )


def extract_player_outfit(appearance, group_dir: str) -> int:
    """Escreve os 216 PNGs e o JSON de um outfit de jogador. Devolve quantos
    PNGs foram criados.

Os sprite ids são a concatenação dos frame groups na ordem idle-depois-
    moving, e a lei de índice sobre as 9 fases somadas cai exatamente em cima
    dessa concatenação — a fase 0 é o frame group idle inteiro, as fases 1..8
    são o moving. Por isso os índices do plano endereçam a concatenação direto.
    """
    app_id = appearance.id
    axes = source_axes_of(appearance)
    sprite_ids = concatenated_sprite_ids(appearance)

    if len(sprite_ids) != axes.total():
        print(f"  [!] outfit {app_id}: {len(sprite_ids)} sprites, "
              f"esperado {axes.total()} — pulado")
        return 0

    outfit_dir = os.path.join(group_dir, str(app_id))
    ensure_dir(outfit_dir)

    plan = player_frame_plan(app_id, axes)
    written = 0

    for key, index in plan:
        png_path = os.path.join(outfit_dir, f"{key}.png")
        if not os.path.exists(png_path):
            if write_sprite(sprite_ids[index], png_path):
                written += 1
            else:
                print(f"  [!] outfit {app_id}: missing_sprite:{sprite_ids[index]}")

    declared_axes = {
        "directions": axes.directions,
        "phases": axes.phases,
        "layers": axes.layers,
        "addons": axes.addons,
        "mounts": 1,
    }

    json_data = {
        "id": app_id,
        "name": OUTFIT_NAMES.get(app_id, ""),
        "spriteId": [key for key, _ in plan],
        "axes": declared_axes,
        "flags": proto_to_dict(appearance.flags) if appearance.HasField("flags") else {},
    }

    with open(os.path.join(outfit_dir, f"{app_id}.json"), "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    return written


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
    print(f"\n[..] Extraindo {group_name}")

    group_dir = os.path.join(OUT_DIR, group_name)
    ensure_dir(group_dir)

    total_pngs = 0
    skipped = 0
    players = 0

    for appearance in appearances:
        app_id = appearance.id

        # Os outfits de jogador do catálogo fixo têm addon, montaria e layer,
        # e saem por um caminho próprio — com chave de frame explícita e o
        # bloco `axes`.
        if group_name == "outfits" and is_player_outfit(app_id):
            total_pngs += extract_player_outfit(appearance, group_dir)
            players += 1
            continue

        # O resto que mexe nesses eixos é appearance de criatura fora do
        # formato que o caminho abaixo sabe ler — ver has_non_creature_axis.
        if group_name == "outfits" and has_non_creature_axis(appearance):
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
                    if write_sprite(sprite_ids[0], png_path):
                        total_pngs += 1
                    else:
                        print(f"  [!] {group_name} {app_id}: missing_sprite:{sprite_ids[0]}")

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
                        if write_sprite(sprite_ids[i], png_path):
                            total_pngs += 1
                        else:
                            print(f"  [!] {group_name} {app_id}: missing_sprite:{sprite_ids[i]}")

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

    print(f"[OK] {group_name}: {total_pngs} PNGs extraidos")
    if players:
        print(f"  [player] {players} outfits de jogador (sem montaria; addons variam por outfit)")
    if skipped:
        print(f"  [skip] {skipped} appearances ignoradas (eixo de addon/montaria/layer)")


# =========================
# ENTRY POINT
# =========================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrai os PNGs/JSONs do cliente Tibia para extractor/sprites/."
    )
    parser.add_argument(
        "--group",
        dest="groups",
        action="append",
        choices=sorted(APPEARANCE_GROUPS),
        help="Extrai só este grupo (pode repetir). Sem a flag, roda ENABLED_GROUPS.",
    )
    parser.add_argument(
        "--client-dir",
        default=None,
        help=f"cliente Tibia extraído (default: ${paths.TIBIA_CLIENT.env_var} "
             f"ou {paths.TIBIA_CLIENT.sibling_default()})",
    )
    return parser.parse_args()


def main():
    global SPRITES
    args = parse_args()

    manifest = fetch_assets.load_manifest()
    client_dir = paths.TIBIA_CLIENT.resolve(args.client_dir)
    assets = fetch_assets.assets_dir(client_dir, manifest)

    if not os.path.isdir(assets):
        print(f"[ERROR] assets do cliente não encontrados em {assets}")
        print(f"        rode 'uv run python extractor/scripts/fetch_assets.py'")
        sys.exit(1)

    try:
        fetch_assets.verify_extracted(client_dir, manifest)
    except fetch_assets.ClientVersionMismatch as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    try:
        SPRITES = client_sprites.ClientSprites(assets)
    except client_sprites.SpriteSheetError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    appearances_path = SPRITES.appearances_file
    print(f"[OK] cliente {manifest['clientVersion']}: "
          f"{len(SPRITES._entries)} folhas, maior sprite id {SPRITES.max_sprite_id}")

    with open(appearances_path, "rb") as handler:
        appearances = Appearances()
        appearances.ParseFromString(handler.read())

    ensure_dir(OUT_DIR)

    for group_name in args.groups or ENABLED_GROUPS:
        field_name = APPEARANCE_GROUPS[group_name]
        extract_group(getattr(appearances, field_name), group_name)

    print("\nDONE")


if __name__ == "__main__":
    main()
