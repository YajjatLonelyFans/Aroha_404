from fastapi import APIRouter, Path, Request
from fastapi.responses import Response

from app.core.errors import AppError
from app.integrations.tiles.base import TileProvider, UnconfiguredTiles
from app.schemas.map import MapConfig

router = APIRouter(tags=["map"])

TILE_URL = "/api/tiles/satellite/{z}/{x}/{y}"
BROWSER_CACHE_S = 24 * 3600  # browsers may cache tiles; the server stores none


@router.get("/map/config", response_model=MapConfig)
async def map_config(request: Request) -> MapConfig:
    """What the map needs: the tile URL on this API, the credit line to show, and the zoom limit."""
    tiles: TileProvider = request.app.state.tiles
    unconfigured = isinstance(tiles, UnconfiguredTiles)
    return MapConfig(
        satellite_available=not unconfigured,
        tile_url=TILE_URL,
        attribution=tiles.attribution,
        max_zoom=tiles.max_zoom,
        is_mock=tiles.is_mock,
        detail=f"{tiles.reason} You can still drop a pin." if unconfigured else None,
    )


@router.get("/tiles/satellite/{z}/{x}/{y}", response_class=Response,
            responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}})
async def satellite_tile(
    request: Request,
    z: int = Path(ge=0, le=22),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
) -> Response:
    """One satellite tile, fetched from the provider with the backend's key."""
    tiles: TileProvider = request.app.state.tiles
    if z > tiles.max_zoom or x >= 2**z or y >= 2**z:
        raise AppError("tile_out_of_range", "No tile at this position.", status_code=404)
    tile = await tiles.get_tile(z, x, y)
    return Response(tile.content, media_type=tile.media_type,
                    headers={"Cache-Control": f"public, max-age={BROWSER_CACHE_S}"})
