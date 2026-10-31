"""Loader for the versioned assumptions file (`app/config/assumptions.v1.json`).

The file is validated strictly when loaded: a typo or wrong type stops the app.
Values the team has not filled in yet stay `null`; asking for one through
`Assumptions.require()` raises an error that names the field, so nothing is ever guessed.

Run `python -m app.core.assumptions` to list the values that are still missing.
"""

import json
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.errors import AppError

ASSUMPTIONS_PATH = Path(__file__).resolve().parents[1] / "config" / "assumptions.v1.json"


class AssumptionsFileError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("assumptions_invalid", message, status_code=500)


class AssumptionMissingError(AppError):
    def __init__(self, field: str) -> None:
        super().__init__(
            "assumption_missing",
            f"Assumption '{field}' is not set in assumptions.v1.json. "
            "Fill it in with a source before using this feature.",
            status_code=503,
            details={"field": field},
        )
        self.field = field


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Module(_Section):
    length_m: float | None = None
    width_m: float | None = None
    wp: float | None = None
    gamma_per_c: float | None = None
    noct_c: float | None = None
    source: str | None = None


class Layout(_Section):
    edge_setback_m: float | None = None
    no_go_clearance_m: float | None = None
    row_gap_m: float | None = None  # minimum gap between tilted rows; shade spacing may widen it
    flush_gap_m: float | None = None  # between rows laid flush on a sloped roof
    default_flat_tilt_deg: float | None = None
    default_azimuth_deg: float | None = None
    source: str | None = None


class Capacity(_Section):
    shading_haircut_fraction: float | None = None
    small_area_m2: float | None = None
    many_obstructions_fraction: float | None = None
    source: str | None = None


class ShadingByLevel(_Section):
    none: float | None = None
    partial: float | None = None
    heavy: float | None = None


class Losses(_Section):
    l_other_fraction: float | None = None
    shading_by_level: ShadingByLevel = Field(default_factory=ShadingByLevel)
    shading_cap_fraction: float | None = None
    source: str | None = None


class Costs(_Section):
    cost_per_kwp_inr: float | None = None
    source: str | None = None
    as_of: date | None = None


class TariffSlab(_Section):
    up_to_kwh: float | None = None  # null = no upper limit (last slab)
    rate_inr_per_kwh: float


class Tariff(_Section):
    discom: str
    slabs: list[TariffSlab] = Field(default_factory=list)
    fixed_charges_inr: float | None = None
    export_rate_inr: float | None = None
    source: str | None = None
    as_of: date | None = None


class Climatology(_Section):
    years: int
    max_missing_share: float


class Forecast(_Section):
    """Rule for labelling forecast days sunny / mixed / cloudy / rain."""

    sunny_min_ratio: float | None = None  # day GTI ÷ typical day for the month
    cloudy_max_ratio: float | None = None
    rain_min_mm: float | None = None
    source: str | None = None


class Validation(_Section):
    min_outline_m2: float | None = None
    max_outline_m2: float | None = None
    delhi_bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat


class Assumptions(_Section):
    version: str
    module: Module
    layout: Layout
    capacity: Capacity
    losses: Losses
    costs: Costs
    tariff: Tariff
    seasons: dict[str, list[int]]
    climatology: Climatology
    forecast: Forecast
    validation: Validation

    @field_validator("seasons")
    @classmethod
    def _seasons_cover_every_month_once(cls, seasons: dict[str, list[int]]) -> dict[str, list[int]]:
        months = sorted(m for ms in seasons.values() for m in ms)
        if months != list(range(1, 13)):
            raise ValueError("seasons must list each month 1-12 exactly once")
        return seasons

    def missing_fields(self) -> list[str]:
        """Dotted paths of every value that is still null or an empty list."""
        return _missing(self.model_dump(), "")

    def require(self, path: str) -> Any:
        """Return the value at a dotted path such as 'module.wp', or raise if it is not set."""
        value: Any = self
        for part in path.split("."):
            value = getattr(value, part)
        if value is None or value == []:
            raise AssumptionMissingError(path)
        return value


def _missing(data: Any, prefix: str) -> list[str]:
    if isinstance(data, dict):
        out: list[str] = []
        for key, value in data.items():
            out += _missing(value, f"{prefix}.{key}" if prefix else key)
        return out
    return [prefix] if data is None or data == [] else []


def load_assumptions(path: Path = ASSUMPTIONS_PATH) -> Assumptions:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssumptionsFileError(f"Cannot read {path.name}: {exc}") from exc
    try:
        return Assumptions.model_validate(raw)
    except ValidationError as exc:
        raise AssumptionsFileError(f"{path.name} is not valid: {exc}") from exc


@lru_cache
def get_assumptions() -> Assumptions:
    return load_assumptions()


if __name__ == "__main__":
    missing = load_assumptions().missing_fields()
    if not missing:
        print("assumptions.v1.json: all values set.")
        sys.exit(0)
    print(f"assumptions.v1.json: {len(missing)} value(s) still missing:")
    for field in missing:
        print(f"  - {field}")
    sys.exit(1)
