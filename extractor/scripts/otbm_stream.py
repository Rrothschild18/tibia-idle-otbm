"""Leitura e escrita de OTBM em nível de nó, sem interpretar item.

O `vendor/otbm2json.js` decodifica o arquivo inteiro numa árvore de objetos: o
mapa-mundo do otservbr (184 MB) viraria alguns GB de JSON, e a fatia de uma
cidade não precisa de nada disso. Aqui o arquivo é percorrido uma vez e o nó
que interessa é **copiado byte a byte** — os bytes do nó já vêm escapados da
fonte, então recortar não reinterpreta id de item, atributo nem conteúdo de
container.

Formato: 4 bytes de identificador, depois uma árvore de nós delimitada por
`0xFE` (início) e `0xFF` (fim), com `0xFD` escapando um byte literal que
colidiria com os dois. O primeiro byte do payload de um nó é o tipo.
"""

import re
import struct
from typing import Callable, Iterator, List, Optional, Tuple

NODE_ESC = 0xFD
NODE_INIT = 0xFE
NODE_TERM = 0xFF

OTBM_MAP_HEADER = 0x00
OTBM_MAP_DATA = 0x02
OTBM_TILE_AREA = 0x04
OTBM_TILE = 0x05
OTBM_ITEM = 0x06
OTBM_TOWNS = 0x0C
OTBM_TOWN = 0x0D
OTBM_HOUSETILE = 0x0E
OTBM_WAYPOINTS = 0x0F

OTBM_ATTR_DESCRIPTION = 0x01
OTBM_ATTR_TILE_FLAGS = 0x03
OTBM_ATTR_ITEM = 0x09
OTBM_ATTR_EXT_SPAWN_FILE = 0x0B
OTBM_ATTR_EXT_HOUSE_FILE = 0x0D

IDENTIFIER = b"\x00\x00\x00\x00"

_SPECIAL = re.compile(rb"[\xfd\xfe\xff]")


def unescape(raw: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(raw):
        byte = raw[index]
        if byte == NODE_ESC:
            if index + 1 >= len(raw):
                break
            out.append(raw[index + 1])
            index += 2
        else:
            out.append(byte)
            index += 1
    return bytes(out)


def escape(raw: bytes) -> bytes:
    out = bytearray()
    for byte in raw:
        if byte in (NODE_ESC, NODE_INIT, NODE_TERM):
            out.append(NODE_ESC)
        out.append(byte)
    return bytes(out)


def node_type(data: bytes, start: int) -> int:
    byte = data[start + 1]
    return data[start + 2] if byte == NODE_ESC else byte


def node_end(data: bytes, start: int) -> int:
    """Um passado o `0xFF` que fecha o nó que começa em `start`."""
    depth = 1
    position = start + 1
    while depth:
        match = _SPECIAL.search(data, position)
        if match is None:
            raise ValueError("OTBM truncado: nó sem fim")
        byte = data[match.start()]
        if byte == NODE_ESC:
            position = match.start() + 2
            continue
        depth += 1 if byte == NODE_INIT else -1
        position = match.start() + 1
    return position


def children(data: bytes, start: int) -> Iterator[Tuple[int, int]]:
    position = start + 1
    while True:
        match = _SPECIAL.search(data, position)
        if match is None:
            return
        byte = data[match.start()]
        if byte == NODE_ESC:
            position = match.start() + 2
            continue
        if byte == NODE_TERM:
            return
        end = node_end(data, match.start())
        yield match.start(), end
        position = end


def root(data: bytes) -> Tuple[int, int]:
    start = data.index(bytes([NODE_INIT]))
    return start, node_end(data, start)


def map_header(data: bytes) -> dict:
    start, _ = root(data)
    raw = unescape(data[start + 1 : start + 1 + 17 * 2])
    version, width, height, items_major, items_minor = struct.unpack_from("<IHHII", raw, 1)
    return {
        "version": version,
        "width": width,
        "height": height,
        "itemsMajorVersion": items_major,
        "itemsMinorVersion": items_minor,
    }


def map_data_node(data: bytes) -> Tuple[int, int]:
    start, _ = root(data)
    for child_start, child_end in children(data, start):
        if node_type(data, child_start) == OTBM_MAP_DATA:
            return child_start, child_end
    raise ValueError("OTBM sem nó OTBM_MAP_DATA")


def tile_area_origin(data: bytes, start: int) -> Tuple[int, int, int]:
    raw = unescape(data[start + 1 : start + 1 + 6 * 2])
    return struct.unpack_from("<HHB", raw, 1)


def tile_offsets(data: bytes, start: int) -> Tuple[int, int]:
    raw = unescape(data[start + 1 : start + 1 + 3 * 2])
    return raw[1], raw[2]


def tile_ground_id(data: bytes, start: int) -> Optional[int]:
    """O id do chão declarado como **atributo** do tile, ou `None`.

    Não é "o chão do tile": um tile pode trazer o chão como primeiro nó de item
    filho em vez de atributo, e em Rookgaard 18.720 dos 352.416 tiles fazem
    isso. O dump do `otbm2json` traduz só o atributo para `tileid`, e é essa
    tradução que este reproduz — quem quer o chão dos outros olha os itens.

    Para de ler no primeiro atributo de largura desconhecida em vez de
    adivinhar: um byte de largura errada faria todo o resto do tile virar lixo,
    e um `None` a mais é leitura conservadora (nenhuma flag), não corrupção."""
    raw = unescape(data[start + 1 : start + 1 + 16 * 2])
    if not raw:
        return None
    # `housetile` carrega o id da casa (4 bytes) entre as coordenadas e os
    # atributos; `tile` vai direto.
    index = 7 if raw[0] == OTBM_HOUSETILE else 3

    while index < len(raw):
        attr = raw[index]
        if attr in (NODE_INIT, NODE_TERM):
            return None
        index += 1
        if attr == OTBM_ATTR_ITEM:
            if index + 2 > len(raw):
                return None
            return int.from_bytes(raw[index : index + 2], "little")
        if attr == OTBM_ATTR_TILE_FLAGS:
            index += 4
        else:
            return None

    return None


def towns(data: bytes) -> List[dict]:
    map_start, _ = map_data_node(data)
    found = []
    for child_start, _ in children(data, map_start):
        if node_type(data, child_start) != OTBM_TOWNS:
            continue
        for town_start, town_end in children(data, child_start):
            if node_type(data, town_start) != OTBM_TOWN:
                continue
            raw = unescape(data[town_start + 1 : town_end])
            town_id = struct.unpack_from("<I", raw, 1)[0]
            name_length = struct.unpack_from("<H", raw, 5)[0]
            name = raw[7 : 7 + name_length].decode("latin-1")
            x, y, z = struct.unpack_from("<HHB", raw, 7 + name_length)
            found.append({"id": town_id, "name": name, "x": x, "y": y, "z": z})
    return found


def _string16(value: str) -> bytes:
    encoded = value.encode("latin-1", errors="replace")
    return struct.pack("<H", len(encoded)) + encoded


def write_map(
    path: str,
    header: dict,
    description: str,
    spawn_file: str,
    house_file: str,
    areas: List[Tuple[Tuple[int, int, int], List[bytes]]],
    town_nodes: List[dict],
) -> int:
    """Escreve um OTBM a partir de nós de tile já escapados (`areas`).

    Cada entrada de `areas` é `((x, y, z), [bytes de nó de tile])`, e cada nó
    vem verbatim da fonte — origem da área preservada, então o deslocamento de
    um byte guardado em cada tile continua válido.
    """
    header_payload = escape(
        struct.pack(
            "<BIHHII",
            OTBM_MAP_HEADER,
            header["version"],
            header["width"],
            header["height"],
            header["itemsMajorVersion"],
            header["itemsMinorVersion"],
        )
    )

    map_payload = escape(
        bytes([OTBM_MAP_DATA])
        + bytes([OTBM_ATTR_DESCRIPTION])
        + _string16(description)
        + bytes([OTBM_ATTR_EXT_SPAWN_FILE])
        + _string16(spawn_file)
        + bytes([OTBM_ATTR_EXT_HOUSE_FILE])
        + _string16(house_file)
    )

    chunks = [IDENTIFIER, bytes([NODE_INIT]), header_payload, bytes([NODE_INIT]), map_payload]
    tiles_written = 0

    for (x, y, z), tile_nodes in areas:
        chunks.append(bytes([NODE_INIT]))
        chunks.append(escape(struct.pack("<BHHB", OTBM_TILE_AREA, x, y, z)))
        chunks.extend(tile_nodes)
        tiles_written += len(tile_nodes)
        chunks.append(bytes([NODE_TERM]))

    chunks.append(bytes([NODE_INIT]))
    chunks.append(escape(bytes([OTBM_TOWNS])))
    for town in town_nodes:
        chunks.append(bytes([NODE_INIT]))
        chunks.append(
            escape(
                struct.pack("<BI", OTBM_TOWN, town["id"])
                + _string16(town["name"])
                + struct.pack("<HHB", town["x"], town["y"], town["z"])
            )
        )
        chunks.append(bytes([NODE_TERM]))
    chunks.append(bytes([NODE_TERM]))

    chunks.append(bytes([NODE_INIT]))
    chunks.append(escape(bytes([OTBM_WAYPOINTS])))
    chunks.append(bytes([NODE_TERM]))

    chunks.append(bytes([NODE_TERM]))
    chunks.append(bytes([NODE_TERM]))

    with open(path, "wb") as handler:
        for chunk in chunks:
            handler.write(chunk)

    return tiles_written


OTBM_ATTR_ACTION_ID = 0x04
OTBM_ATTR_UNIQUE_ID = 0x05
OTBM_ATTR_TEXT = 0x06


def item_node(
    item_id: int,
    action_id: Optional[int] = None,
    unique_id: Optional[int] = None,
    text: Optional[str] = None,
) -> bytes:
    """Um nó de item solto, pronto para entrar como filho de um tile.

    `action_id` e `unique_id` são dois bytes cada; `text` é string de 16 bits
    de comprimento. As três larguras são as que o leitor do vendor espera — um
    marcador escrito com a largura errada corrompe todo o tile depois dele, e
    não só o atributo."""
    payload = struct.pack("<BH", OTBM_ITEM, item_id)
    if action_id is not None:
        payload += struct.pack("<BH", OTBM_ATTR_ACTION_ID, action_id)
    if unique_id is not None:
        payload += struct.pack("<BH", OTBM_ATTR_UNIQUE_ID, unique_id)
    if text is not None:
        payload += bytes([OTBM_ATTR_TEXT]) + _string16(text)
    return bytes([NODE_INIT]) + escape(payload) + bytes([NODE_TERM])


def with_extra_item(tile_node: bytes, item: bytes) -> bytes:
    """O mesmo nó de tile, com um item a mais no topo da pilha.

    O nó chega escapado da fonte e sai escapado: o item entra antes do `0xFF`
    que fecha o tile, e nada do que já estava lá é reinterpretado.
    """
    if not tile_node or tile_node[-1] != NODE_TERM:
        raise ValueError("nó de tile não termina em NODE_TERM")
    return tile_node[:-1] + item + bytes([NODE_TERM])


AREA_SIZE = 256


def crop_tiles(
    data: bytes,
    keep_column: Callable[[int, int], bool],
    bounds: Optional[Tuple[int, int, int, int]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> List[Tuple[Tuple[int, int, int], List[bytes]]]:
    """Os nós de tile cujas colunas `keep_column` aceita, agrupados por área.

    `bounds` é `(min_x, min_y, max_x, max_y)`: uma área de 256x256 que não
    encosta nela é descartada pelo cabeçalho, sem abrir os tiles de dentro. No
    mapa-mundo isso é a diferença entre abrir 20 milhões de tiles e abrir os
    poucos milhares que a cidade tem.
    """
    map_start, _ = map_data_node(data)
    kept: List[Tuple[Tuple[int, int, int], List[bytes]]] = []
    scanned = 0
    total_kept = 0

    for area_start, _ in children(data, map_start):
        if node_type(data, area_start) != OTBM_TILE_AREA:
            continue
        scanned += 1
        if progress and scanned % 100000 == 0:
            progress(scanned, total_kept)

        origin_x, origin_y, origin_z = tile_area_origin(data, area_start)
        if bounds is not None:
            min_x, min_y, max_x, max_y = bounds
            if (
                origin_x > max_x
                or origin_x + AREA_SIZE - 1 < min_x
                or origin_y > max_y
                or origin_y + AREA_SIZE - 1 < min_y
            ):
                continue

        nodes: List[bytes] = []
        for tile_start, tile_end in children(data, area_start):
            if node_type(data, tile_start) not in (OTBM_TILE, OTBM_HOUSETILE):
                continue
            offset_x, offset_y = tile_offsets(data, tile_start)
            if keep_column(origin_x + offset_x, origin_y + offset_y):
                nodes.append(data[tile_start:tile_end])

        if nodes:
            kept.append(((origin_x, origin_y, origin_z), nodes))
            total_kept += len(nodes)

    return kept
