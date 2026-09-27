"""A paleta de cores de outfit do Tibia, e a recolorização de um frame.

Porte direto do que o front já faz em `libs/models/character/outfit-colors.ts` e
`design-system/outfit-texture/outfit-composition.ts`. Existe aqui porque um
**monstro humanoide** usa outfit de jogador: o sprite é desenho (`base`) mais
máscara de recolorização (`mask`), e sem aplicar as quatro cores do bicho ele
sai na paleta padrão do outfit — a Amazon vira a Hunter.

As duas metades precisam dar exatamente o mesmo pixel, senão o mesmo monstro
aparece de uma cor no card da hunt (que usa o atlas bakeado aqui) e de outra
onde o front compõe em runtime. É o mesmo motivo de `getStepDurationMs` morar
num lugar só.
"""

import math
from typing import Dict, Iterable, List, Tuple

from PIL import Image

HUE_STEPS = 19
TONE_STEPS = 7
COLOR_COUNT = HUE_STEPS * TONE_STEPS

TONES = [
    (0.25, 1.0),
    (0.25, 0.75),
    (0.5, 0.75),
    (2 / 3, 0.75),
    (1.0, 1.0),
    (1.0, 0.75),
    (1.0, 0.5),
]

# Cada região da máscara é uma cor chapada; o pixel do `base` embaixo dela é
# multiplicado pela cor escolhida para aquela região.
MASK_REGIONS = {
    (255, 255, 0): "head",
    (255, 0, 0): "body",
    (0, 255, 0): "legs",
    (0, 0, 255): "feet",
}

Rgb = Tuple[int, int, int]


def _hue_to_rgb(hue: float, saturation: float, intensity: float):
    low = intensity * (1 - saturation)
    sector = int(hue * 6)
    offset = hue * 6 - sector
    rising = low + (intensity - low) * offset
    falling = intensity - (intensity - low) * offset

    return [
        (intensity, rising, low),
        (falling, intensity, low),
        (low, intensity, rising),
        (low, falling, intensity),
        (rising, low, intensity),
        (intensity, low, falling),
    ][min(sector, 5)]


def outfit_color(index: int) -> Rgb:
    """O índice de cor do Tibia (0-132) -> RGB."""
    safe = index if isinstance(index, int) and 0 <= index < COLOR_COUNT else 0
    hue_step = safe % HUE_STEPS

    if hue_step == 0:
        grey = 1 - safe / HUE_STEPS / (TONE_STEPS - 1)
        channels = (grey, grey, grey)
    else:
        saturation, intensity = TONES[safe // HUE_STEPS]
        channels = _hue_to_rgb(hue_step / 18, saturation, intensity)

    # `math.floor(x + 0.5)` e não `round`: o do Python é bancário (arredonda
    # 212.5 para 212) e o `Math.round` do JS é meio-pra-cima. Com `round` duas
    # cores da paleta saíam um valor diferente das do front.
    return tuple(
        math.floor(min(max(value, 0.0), 1.0) * 255 + 0.5) for value in channels
    )


def region_colors(appearance: Dict) -> Dict[str, Rgb]:
    return {
        region: outfit_color(int(appearance.get(region, 0)))
        for region in ("head", "body", "legs", "feet")
    }


def tint_frame(base: Image.Image, mask: Image.Image, colors: Dict[str, Rgb]) -> Image.Image:
    """`base` recolorido onde a `mask` marca região. Fora das quatro regiões o
    pixel fica como está — é o que preserva pele, olho e arma do desenho."""
    base = base.convert("RGBA")
    mask = mask.convert("RGBA")
    if base.size != mask.size:
        raise ValueError(f"base {base.size} e máscara {mask.size} de tamanhos diferentes")

    out = base.copy()
    base_px = base.load()
    mask_px = mask.load()
    out_px = out.load()

    for y in range(base.height):
        for x in range(base.width):
            if base_px[x, y][3] == 0 or mask_px[x, y][3] == 0:
                continue
            region = MASK_REGIONS.get(mask_px[x, y][:3])
            if region is None:
                continue
            tint = colors[region]
            red, green, blue, alpha = base_px[x, y]
            out_px[x, y] = (
                math.floor(red * tint[0] / 255 + 0.5),
                math.floor(green * tint[1] / 255 + 0.5),
                math.floor(blue * tint[2] / 255 + 0.5),
                alpha,
            )

    return out


def enabled_addons(addons: int) -> List[int]:
    """`lookaddons` é bitmask: 1 e 2 são camadas desenhadas **sobre** a base.

    A camada de addon é esparsa — no frame `south_0` do Cult Believer a base
    tem ~600 pixels opacos e o addon 1 tem 195 —, então ela soma, não
    substitui. Mesmo `enabledAddons` de `outfit-composition.ts`.
    """
    layers = [0]
    if addons & 1:
        layers.append(1)
    if addons & 2:
        layers.append(2)
    return layers


def compose_frame(
    layers: Iterable[Tuple[Image.Image, Image.Image]], colors: Dict[str, Rgb]
) -> Image.Image:
    """Cada camada `(base, mask)` tingida e empilhada de baixo para cima."""
    out = None
    for base, mask in layers:
        painted = tint_frame(base, mask, colors)
        out = painted if out is None else Image.alpha_composite(out, painted)

    if out is None:
        raise ValueError("nada a empilhar: a lista de camadas está vazia")

    return out


def appearance_key(appearance: Dict) -> str:
    """`137:113:120:95:115:0` -> `137-113-120-95-115-0`, o nome do atlas.

    Mesma chave do `appearanceKey` do front, com `-` no lugar de `:` porque
    isto vira nome de arquivo. Ela é necessária porque **78 looktypes são
    usados por monstros de cores diferentes** (o 137 por quatro): um atlas por
    outfit guardaria só um deles.
    """
    return "-".join(
        str(int(appearance.get(field, 0)))
        for field in ("looktype", "head", "body", "legs", "feet", "addons")
    )


def has_colors(appearance: Dict) -> bool:
    return any(int(appearance.get(field, 0)) for field in ("head", "body", "legs", "feet"))


def needs_appearance_atlas(appearance: Dict) -> bool:
    """Um atlas por looktype só serve para quem não tem cor **nem** addon.

    O atlas por looktype não consegue guardar addon: ele é de um outfit, e o
    addon é do monstro. Sem esta segunda metade um humanoide sem cor e com
    `lookaddons` cairia no atlas por looktype e perderia o acessório calado.
    """
    return has_colors(appearance) or bool(int(appearance.get("addons", 0)))
