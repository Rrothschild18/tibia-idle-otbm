"""Sprites vindos da pasta `assets/` de um cliente Tibia, por sprite id.

Substitui os quatro containers `.aec` (~270 MB, export de uma ferramenta GUI de
terceiros) como fonte de pixels. O `.aec` era insustentável: o editor ainda em
manutenção (`beats-dh/Beats-Assets-Editor`) passou a escrever os bytes de sprite
num arquivo **companheiro** `.aec.sprites`, então um export novo produziria
containers com o campo não-padrão `sprite_data = 7` vazio — zero sprite
extraído, provavelmente sem erro.

O cliente traz tudo o que falta:

- `catalog-content.json` diz **quais folhas existem e que faixa de sprite id
  cada uma cobre** — a faixa vem pronta, não é calculada.
- cada folha é um BMP comprimido em LZMA1 com um cabeçalho proprietário de 32
  bytes na frente.
- `spritetype` dá o tamanho do sprite, e daí quantos cabem na folha.

Decodificação sem dependência nova: os 32 primeiros bytes são cabeçalho
proprietário, os props do LZMA1 começam no offset 32 (`5d 00 00 ...`), e o campo
de tamanho de 8 bytes vem zerado — precisa virar `0xFF * 8` (tamanho
desconhecido) para o `LZMADecompressor(FORMAT_ALONE)` da stdlib aceitar.
"""

import io
import json
import lzma
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image

# spritetype -> (largura, altura) em pixels. Confirmado contra o cliente
# 15.25.0a00a0: uma folha de spritetype 0 decodifica para 384x384, que é uma
# grade 12x12 de 32x32 = 144 sprites, batendo com a faixa 0-143 do catálogo.
SPRITE_SIZES: Dict[int, Tuple[int, int]] = {
    0: (32, 32),
    1: (32, 64),
    2: (64, 32),
    3: (64, 64),
}

_LZMA_PROPS_OFFSET = 32
_LZMA_PROPS_LEN = 5
_LZMA_SIZE_FIELD_LEN = 8


class SpriteSheetError(Exception):
    """Folha ilegível ou incoerente com o que o catálogo declara."""


def decode_sheet(raw: bytes) -> Image.Image:
    """Bytes de um `sprites-<sha>.bmp.lzma` -> a imagem BMP descomprimida."""
    if len(raw) <= _LZMA_PROPS_OFFSET + _LZMA_PROPS_LEN + _LZMA_SIZE_FIELD_LEN:
        raise SpriteSheetError(f"folha truncada ({len(raw)} bytes)")

    props = raw[_LZMA_PROPS_OFFSET:_LZMA_PROPS_OFFSET + _LZMA_PROPS_LEN]
    payload = raw[_LZMA_PROPS_OFFSET + _LZMA_PROPS_LEN + _LZMA_SIZE_FIELD_LEN:]

    # Tamanho desconhecido: 0xFF * 8 é a convenção do LZMA_ALONE para "leia até
    # o fim do stream". O cliente grava zeros, que o decodificador leria como
    # "stream de tamanho zero".
    stream = props + b"\xff" * _LZMA_SIZE_FIELD_LEN + payload

    try:
        decompressed = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(stream)
    except lzma.LZMAError as exc:
        raise SpriteSheetError(f"LZMA inválido: {exc}") from exc

    try:
        return Image.open(io.BytesIO(decompressed)).convert("RGBA")
    except OSError as exc:
        raise SpriteSheetError(f"BMP inválido depois de descomprimir: {exc}") from exc


class ClientSprites:
    """Índice sprite id -> PNG, sobre as folhas do cliente.

    As folhas são decodificadas sob demanda e mantidas em cache: o catálogo tem
    4927 delas e um mapa costuma tocar poucas, mas toca cada uma várias vezes.
    """

    def __init__(self, assets_dir: str, cache_size: int = 8):
        self.assets_dir = assets_dir
        self._cache_size = cache_size
        self._sheets: Dict[str, Image.Image] = {}
        self._order: List[str] = []
        self._entries = self._load_catalog()

    def _load_catalog(self) -> List[dict]:
        path = os.path.join(self.assets_dir, "catalog-content.json")
        if not os.path.exists(path):
            raise SpriteSheetError(
                f"catalog-content.json não encontrado em {path}; "
                f"rode 'uv run python extractor/scripts/fetch_assets.py'"
            )
        with open(path, "r", encoding="utf-8") as handler:
            catalog = json.load(handler)

        entries = [entry for entry in catalog if entry.get("type") == "sprite"]
        # Ordenado por faixa para permitir busca binária por sprite id.
        entries.sort(key=lambda entry: entry["firstspriteid"])
        return entries

    @property
    def appearances_file(self) -> Optional[str]:
        """Caminho do `appearances-<sha>.dat` que o catálogo declara."""
        path = os.path.join(self.assets_dir, "catalog-content.json")
        with open(path, "r", encoding="utf-8") as handler:
            for entry in json.load(handler):
                if entry.get("type") == "appearances":
                    return os.path.join(self.assets_dir, entry["file"])
        return None

    @property
    def sheet_count(self) -> int:
        """Quantas folhas o catálogo declara."""
        return len(self._entries)

    @property
    def max_sprite_id(self) -> int:
        return max(entry["lastspriteid"] for entry in self._entries)

    def _entry_for(self, sprite_id: int) -> Optional[dict]:
        low, high = 0, len(self._entries) - 1
        while low <= high:
            mid = (low + high) // 2
            entry = self._entries[mid]
            if sprite_id < entry["firstspriteid"]:
                high = mid - 1
            elif sprite_id > entry["lastspriteid"]:
                low = mid + 1
            else:
                return entry
        return None

    def _sheet_image(self, entry: dict) -> Image.Image:
        name = entry["file"]
        cached = self._sheets.get(name)
        if cached is not None:
            return cached

        path = os.path.join(self.assets_dir, name)
        if not os.path.exists(path):
            raise SpriteSheetError(f"folha {name} declarada no catálogo mas ausente em {path}")
        with open(path, "rb") as handler:
            image = decode_sheet(handler.read())

        self._sheets[name] = image
        self._order.append(name)
        while len(self._order) > self._cache_size:
            self._sheets.pop(self._order.pop(0), None)
        return image

    def sprite_image(self, sprite_id: int) -> Optional[Image.Image]:
        """O sprite recortado, ou `None` se nenhuma folha cobre esse id.

        `None` em vez de exceção porque appearance referenciando sprite que não
        existe é um caso conhecido do pipeline, já tratado com
        `missing_sprite:<id>` rio abaixo.
        """
        entry = self._entry_for(sprite_id)
        if entry is None:
            return None

        width, height = SPRITE_SIZES.get(entry["spritetype"], (32, 32))
        sheet = self._sheet_image(entry)
        columns = sheet.width // width
        if columns == 0:
            raise SpriteSheetError(
                f"folha {entry['file']} tem {sheet.width}px de largura, "
                f"menor que um sprite de {width}px (spritetype {entry['spritetype']})"
            )

        offset = sprite_id - entry["firstspriteid"]
        left = (offset % columns) * width
        top = (offset // columns) * height
        if top + height > sheet.height:
            raise SpriteSheetError(
                f"sprite {sprite_id} cai fora de {entry['file']} "
                f"({sheet.width}x{sheet.height}, sprite {width}x{height}, offset {offset})"
            )

        return sheet.crop((left, top, left + width, top + height))

    def sprite_png(self, sprite_id: int) -> Optional[bytes]:
        """O sprite como bytes PNG — o mesmo que `sprite_data` entregava."""
        image = self.sprite_image(sprite_id)
        if image is None:
            return None
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
