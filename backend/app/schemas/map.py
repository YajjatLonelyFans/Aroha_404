from pydantic import BaseModel, Field


class MapConfig(BaseModel):
    satellite_available: bool
    tile_url: str = Field(description="XYZ template on this API, relative to its origin")
    attribution: str
    max_zoom: int
    is_mock: bool
    detail: str | None = None
