"""Application settings, read from environment variables and `.env` files."""

import re
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

# Values copied from .env.example that were never filled in, e.g. "<from-meko-portal>".
_PLACEHOLDER = re.compile(r"<[^>]*>")


def is_configured(value: str | None) -> bool:
    """True when a setting holds a real value, not empty and not an example placeholder."""
    return bool(value and value.strip()) and not _PLACEHOLDER.search(value)


class Settings(BaseSettings):
    # backend/.env wins over a repo-root .env when both exist.
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    mongodb_uri: str = ""
    mongodb_db: str = "aroha_db"
    mongodb_timeout_ms: int = 5000

    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"

    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = ""

    meko_mcp_url: str = "https://mcp.mekodata.ai/mcp"
    meko_api_key: str = ""
    meko_enabled_default: bool = True
    meko_datapack: str = "aroha"  # created on first use if missing
    meko_recall_timeout_s: float = 18.0  # whole recall: connect (~1.5 s) + Meko search (10-14 s measured)
    chat_max_per_minute: int = 6  # per user; protects the free LLM quota
    chat_max_total_per_minute: int = 30  # all users together

    # Satellite tiles are fetched by the backend so the key never reaches the browser.
    map_tiles_provider: str = "maptiler"  # "maptiler" or "esri"
    maptiler_api_key: str = ""
    maptiler_tile_url: str = "https://api.maptiler.com/maps/satellite/256/{z}/{x}/{y}.jpg"
    # From MapTiler's satellite TileJSON (checked live 1 Nov 2026); the map renders it as HTML.
    maptiler_attribution: str = (
        '<a href="https://www.maptiler.com/copyright/" target="_blank">&copy; MapTiler</a> '
        '<a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>'
    )
    esri_api_key: str = ""
    esri_imagery_tile_url: str = (
        "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    )
    # Credit line from the World Imagery item's "Credits (Attribution)"; re-check before the demo.
    esri_imagery_attribution: str = "Esri, Vantor, Earthstar Geographics, and the GIS User Community"

    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    use_mock_weather: bool = False
    use_mock_geocoding: bool = False
    use_mock_meko: bool = False
    use_mock_llm: bool = False
    use_mock_tiles: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
