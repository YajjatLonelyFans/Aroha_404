"""Mock tiles for offline development: grey squares with a visible grid, labelled mock in the UI."""

import struct
import zlib
from functools import lru_cache

from app.integrations.tiles.base import Tile

SIZE = 256


@lru_cache
def _grey_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    fill, edge = bytes([200, 200, 196]), bytes([150, 150, 146])  # darker edges make the tile grid visible
    border = b"\x00" + edge * SIZE  # each row: filter byte + RGB pixels
    inner = b"\x00" + edge + fill * (SIZE - 2) + edge
    rows = border + inner * (SIZE - 2) + border
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)  # 8-bit RGB
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class MockTiles:
    is_mock = True
    attribution = "Mock imagery (not a real satellite view)"
    max_zoom = 19

    async def get_tile(self, z: int, x: int, y: int) -> Tile:
        return Tile(_grey_png(), "image/png")
