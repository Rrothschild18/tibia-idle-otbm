"""O minimapa de uma cidade: a lógica pura, sem I/O e sem Pillow.

Um pixel por tile, e a cor de cada pixel é a única informação de render que o
mapa de cidade inteira já tinha e ninguém usava — o `automap.color` de cada
appearance (ver `appearance_derivation.automap_color`). Por isso este estágio
existe para a cidade inteira enquanto o `map.json` não: ele não depende de
sprite nenhum, então a folha gigante que barra o full-map não se aplica.

A regra de qual cor um tile mostra é a mesma que o RME usa no seu
`Tile::getMiniMapColor` — reimplementada a partir da descrição, não copiada
(o RME é GPL): o item mais ao topo da pilha que tenha cor vence; sem nenhum,
o chão; sem chão colorido, o tile é vazio.

O CLI que lê o dump e escreve os PNGs é `build_city_minimap.py`.
"""

from typing import Dict, Iterable, List, Sequence, Tuple

# O cubo 6x6x6 do Tibia. 216 índices, e a cor é fórmula — não existe tabela
# para envelhecer fora de sincronia com quem desenha.
PALETTE_SIZE = 216
_CHANNEL_STEP = 51

# Quantas entradas um PNG indexado de 8 bits reserva. As 40 que sobram do
# cubo ficam pretas: nenhum índice válido cai nelas.
PNG_PALETTE_SLOTS = 256

# Índice de "nada aqui" — chão sem cor e tile sem chão caem nele.
EMPTY_COLOR = 0

# O andar de superfície do Tibia, por convenção. É o que a vista do front
# desenha por padrão (ver o contrato do minimapa).
SURFACE_Z = 7

# Placa de marcação do travel-graph: uid reservado, entrada de ferramenta.
# Mesmo corte que `map_v6` e `travel_graph` fazem.
MARKER_UID_MIN = 10001


def palette_rgb(index: int) -> Tuple[int, int, int]:
    """Índice da paleta -> `(r, g, b)`. Fora de 0..215, preto."""
    if index <= 0 or index >= PALETTE_SIZE:
        return (0, 0, 0)
    return (
        (index // 36) % 6 * _CHANNEL_STEP,
        (index // 6) % 6 * _CHANNEL_STEP,
        (index % 6) * _CHANNEL_STEP,
    )


def palette_bytes() -> bytes:
    """A paleta inteira achatada, do jeito que um PNG indexado a quer: 256
    triplas RGB, as 40 além do cubo em preto."""
    data = bytearray()
    for index in range(PNG_PALETTE_SLOTS):
        data.extend(palette_rgb(index))
    return bytes(data)


def tile_minimap_color(ground_color: int, item_colors: Sequence[int]) -> int:
    """A cor que um tile mostra no minimapa.

    `item_colors` vem de baixo para cima, como a pilha do OTBM. O item mais ao
    topo **com cor** vence; um item de cor 0 não pinta e não esconde o que está
    embaixo (senão uma caixa apagaria a grama). Sem nenhum item colorido, o
    chão responde — inclusive com 0, que é o tile vazio.
    """
    for color in reversed(item_colors):
        if color:
            return color
    return ground_color or EMPTY_COLOR


def city_minimap(dump: Dict, colors: Dict[int, int]) -> Dict[int, Dict[Tuple[int, int], int]]:
    """Dump cru -> `{z: {(x, y): índice de cor}}`, um andar por z que tenha
    tile. `colors` é `{appearance id: índice}` — o que a tabela de
    `appearance-flags/<CIDADE>.json` guarda em `automapColor`.

    Um tile sem cor nenhuma continua no mapa (com `EMPTY_COLOR`): é ele que
    faz o andar existir, e o andar vazio é justamente o que não deve virar
    PNG.

    A varredura é a mesma que `map_v6` e `travel_graph` fazem — inclusive em
    descartar as placas de marcação do travel-graph, que são entrada de
    ferramenta e não aparecem na cidade que o jogo mostra.
    """
    floors: Dict[int, Dict[Tuple[int, int], int]] = {}

    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", SURFACE_Z)

            for tile in feature.get("tiles", []):
                tile_x, tile_y = tile.get("x"), tile.get("y")
                if tile_x is None or tile_y is None:
                    continue

                item_colors = [
                    colors.get(raw_item.get("id"), 0)
                    for raw_item in tile.get("items") or []
                    if (raw_item.get("uid") or 0) < MARKER_UID_MIN
                ]
                color = tile_minimap_color(colors.get(tile.get("tileid"), 0), item_colors)
                floors.setdefault(z, {})[(base_x + tile_x, base_y + tile_y)] = color

    return floors


def world_to_pixel(x: int, y: int, bounds: Dict[str, int]) -> Tuple[int, int]:
    """`(x, y)` de mundo -> pixel na imagem do andar. Translação e nada mais:
    sem offset, sem meio-pixel, sem escala (escala é transform de canvas)."""
    return (x - bounds["minX"], y - bounds["minY"])


def bounds_document(city: str, bounds: Dict[str, int], floors: Iterable[int]) -> Dict:
    """O `bounds.json` que acompanha os PNGs — o que o front precisa para
    converter mundo em pixel sem conhecer o dump."""
    return {
        "city": city,
        "minX": bounds["minX"],
        "minY": bounds["minY"],
        "maxX": bounds["maxX"],
        "maxY": bounds["maxY"],
        "width": bounds["maxX"] - bounds["minX"] + 1,
        "height": bounds["maxY"] - bounds["minY"] + 1,
        "floors": sorted(floors),
        "surfaceZ": SURFACE_Z,
    }


def floor_pixels(colors_by_position: Dict[Tuple[int, int], int],
                 bounds: Dict[str, int]) -> List[int]:
    """Os índices de um andar em ordem de linha, prontos para virar imagem.
    Toda posição sem tile fica em `EMPTY_COLOR`."""
    width = bounds["maxX"] - bounds["minX"] + 1
    height = bounds["maxY"] - bounds["minY"] + 1
    pixels = [EMPTY_COLOR] * (width * height)
    for (x, y), color in colors_by_position.items():
        px, py = world_to_pixel(x, y, bounds)
        pixels[py * width + px] = color
    return pixels
