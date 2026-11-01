"""Satellite map tiles, served to the browser through the backend so the provider key stays here."""

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AppError


@dataclass(frozen=True)
class Tile:
    content: bytes
    media_type: str


class TilesUnavailable(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("tiles_unavailable", message, status_code=503, retryable=True)


class TileNotFound(AppError):
    def __init__(self) -> None:
        super().__init__("tile_not_found", "No imagery for this tile.", status_code=404)


class TileProvider(Protocol):
    is_mock: bool
    attribution: str
    max_zoom: int

    async def get_tile(self, z: int, x: int, y: int) -> Tile: ...


class UnconfiguredTiles:
    """Stands in when the tile provider's key is not set. The map still works for pins, just without imagery."""

    is_mock = False
    attribution = ""
    max_zoom = 19

    def __init__(self, reason: str) -> None:
        self.reason = reason  # e.g. "Satellite imagery is not set up (MAPTILER_API_KEY)."

    async def get_tile(self, z: int, x: int, y: int) -> Tile:
        raise TilesUnavailable(self.reason)
