"""Panel packing and the capacity range that follows from it.

Azimuth follows Open-Meteo: 0 = south, -90 = east, 90 = west, ±180 = north.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import shapely
from shapely.affinity import rotate
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from app.domain.errors import DomainError
from app.domain.geometry import to_geojson, to_wgs84
from app.domain.units import round_area_m2, round_pct

Orientation = Literal["portrait", "landscape"]
ShadeLevel = Literal["none", "partial", "heavy"]
Confidence = Literal["low", "medium", "high"]

SIDES = ("east", "south", "west", "north")
ORIENTATIONS: tuple[Orientation, ...] = ("portrait", "landscape")
GRID_OFFSETS = (0.0, 1 / 3, 2 / 3)  # fractions of a footprint, tried in this order
_EDGE_TOLERANCE_M = 1e-6  # absorbs float error from rotating back and forth


@dataclass(frozen=True)
class ModuleSpec:
    length_m: float
    width_m: float
    wp: float


EARTH_AXIAL_TILT_DEG = 23.44


def winter_noon_sun_elevation_deg(lat: float) -> float:
    """Sun height at solar noon on the December solstice (northern hemisphere)."""
    return 90.0 - lat - EARTH_AXIAL_TILT_DEG


@dataclass(frozen=True)
class LayoutParams:
    tilt_deg: float
    azimuth_deg: float
    row_gap_m: float  # minimum gap behind each row (flat), or the flush gap (sloped)
    # When set, tilted rows are spaced so they do not shade each other with the
    # sun at this height; the gap then depends on panel orientation.
    shade_free_sun_elevation_deg: float | None = None


@dataclass(frozen=True)
class PanelLayout:
    panel_count: int
    capacity_kwp: float
    orientation: Orientation | None
    panels_m: tuple[Polygon, ...]
    row_gap_m: float | None = None  # gap used for the chosen orientation


def _footprint(module: ModuleSpec, orientation: Orientation, tilt_deg: float) -> tuple[float, float]:
    """(width across the row, depth along the slope) of one panel seen from above."""
    along_slope = module.length_m if orientation == "portrait" else module.width_m
    across = module.width_m if orientation == "portrait" else module.length_m
    return across, along_slope * math.cos(math.radians(tilt_deg))


def row_gap(module: ModuleSpec, orientation: Orientation, params: LayoutParams) -> float:
    """Gap behind a row: the shadow of its raised edge, never less than the minimum."""
    elevation = params.shade_free_sun_elevation_deg
    if elevation is None or params.tilt_deg == 0:
        return params.row_gap_m
    if not 0 < elevation < 90:
        raise DomainError("invalid_layout", "Sun elevation for row spacing must be between 0 and 90 degrees.")
    along_slope = module.length_m if orientation == "portrait" else module.width_m
    height = along_slope * math.sin(math.radians(params.tilt_deg))
    return max(params.row_gap_m, height / math.tan(math.radians(elevation)))


def _grid(area: BaseGeometry, w: float, d: float, pitch: float, ox: float, oy: float) -> np.ndarray:
    min_x, min_y, max_x, max_y = area.bounds
    xs = np.arange(min_x + ox, max_x, w)
    ys = np.arange(min_y + oy, max_y, pitch)
    gx, gy = np.meshgrid(xs, ys)  # row by row, south to north, then west to east
    gx, gy = gx.ravel(), gy.ravel()
    boxes = shapely.box(gx, gy, gx + w, gy + d)
    return boxes[shapely.contains(area, boxes)]


def pack_panels(usable_m: BaseGeometry, module: ModuleSpec, params: LayoutParams) -> PanelLayout:
    """Fill the usable area with whole panels in rows facing the array azimuth.

    Deterministic: tries portrait then landscape, each with a fixed set of grid
    offsets, and keeps the first arrangement with the most panels.
    """
    if module.length_m <= 0 or module.width_m <= 0 or module.wp <= 0:
        raise DomainError("invalid_module", "Module size and wattage must be positive.")
    if not 0 <= params.tilt_deg < 90:
        raise DomainError("invalid_tilt", "Tilt must be between 0 and 90 degrees.")
    if params.row_gap_m < 0:
        raise DomainError("invalid_layout", "Row gap cannot be negative.")
    if usable_m.is_empty or usable_m.area == 0:
        return PanelLayout(0, 0.0, None, ())

    # Rotate so the panels face -y; rows then run along x and the gap sits on the +y side.
    origin = usable_m.centroid
    area = rotate(usable_m, params.azimuth_deg, origin=origin)
    area = area.buffer(_EDGE_TOLERANCE_M, join_style="mitre")
    shapely.prepare(area)

    best: np.ndarray = np.empty(0, dtype=object)
    best_orientation: Orientation | None = None
    best_gap: float | None = None
    for orientation in ORIENTATIONS:
        w, d = _footprint(module, orientation, params.tilt_deg)
        gap = row_gap(module, orientation, params)
        pitch = d + gap
        for fy in GRID_OFFSETS:
            for fx in GRID_OFFSETS:
                boxes = _grid(area, w, d, pitch, fx * w, fy * pitch)
                if len(boxes) > len(best):
                    best, best_orientation, best_gap = boxes, orientation, gap

    panels = tuple(rotate(b, -params.azimuth_deg, origin=origin) for b in best)
    count = len(panels)
    return PanelLayout(
        panel_count=count,
        capacity_kwp=round(count * module.wp / 1000, 3),
        orientation=best_orientation if count else None,
        panels_m=panels,
        row_gap_m=best_gap if count else None,
    )


def panels_to_geojson(panels_m: tuple[Polygon, ...]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"index": i}, "geometry": to_geojson(to_wgs84(p))}
            for i, p in enumerate(panels_m)
        ],
    }


# --- Capacity range, constraints and confidence ------------------------------------------


@dataclass(frozen=True)
class CapacityParams:
    shading_by_level: dict[str, float]  # none / partial / heavy → loss fraction
    shading_cap_fraction: float
    shading_haircut_fraction: float  # share of panels dropped from `min` under heavy shade
    small_area_m2: float
    many_obstructions_fraction: float


@dataclass(frozen=True)
class Constraint:
    code: str
    message: str


@dataclass(frozen=True)
class CapacityResult:
    panel_count: dict[str, int]  # min / likely / max
    capacity_kwp: dict[str, float]  # min / likely / max
    shading_loss_fraction: float
    constraints: list[Constraint] = field(default_factory=list)
    confidence: Confidence = "medium"


def assess_capacity(
    *,
    panel_count: int,
    module_wp: float,
    shading: dict[str, ShadeLevel],
    roof_type: Literal["flat", "sloped"],
    azimuth_deg: float,
    usable_area_m2: float,
    outline_area_m2: float,
    no_go_area_m2: float,
    traced: bool,
    params: CapacityParams,
) -> CapacityResult:
    unknown = set(shading) - set(SIDES)
    if unknown:
        raise DomainError("invalid_shading", f"Unknown shading side(s): {sorted(unknown)}.")
    levels = {side: shading.get(side, "none") for side in SIDES}
    for side, level in levels.items():
        if level not in params.shading_by_level:
            raise DomainError("invalid_shading", f"Unknown shading level '{level}' for {side}.")

    heavy = [s for s in SIDES if levels[s] == "heavy"]
    partial = [s for s in SIDES if levels[s] == "partial"]
    loss = min(sum(params.shading_by_level[levels[s]] for s in SIDES), params.shading_cap_fraction)

    constraints: list[Constraint] = []
    if panel_count == 0:
        constraints.append(Constraint("no_panels_fit", "No full panel fits in the usable area."))
    small = usable_area_m2 < params.small_area_m2
    if small:
        constraints.append(Constraint(
            "small_area",
            f"Usable roof area is {round_area_m2(usable_area_m2)} m², which is small; "
            "only a few panels fit.",
        ))
    for side in heavy:
        constraints.append(Constraint(
            f"heavy_shade_{side}",
            f"Heavy shade from the {side} lowers output and makes the estimate less certain.",
        ))
    for side in partial:
        constraints.append(Constraint(
            f"partial_shade_{side}", f"Some shade from the {side} lowers output a little."
        ))
    if outline_area_m2 > 0 and no_go_area_m2 / outline_area_m2 > params.many_obstructions_fraction:
        constraints.append(Constraint(
            "many_obstructions",
            f"Tanks, stair rooms and other no-go areas take up "
            f"{round_pct(100 * no_go_area_m2 / outline_area_m2):g}% of the roof.",
        ))
    if roof_type == "sloped" and abs(azimuth_deg) > 90:
        constraints.append(Constraint(
            "north_facing_slope", "The roof slopes away from the sun, which lowers output."
        ))

    likely = panel_count
    low = math.floor(panel_count * (1 - params.shading_haircut_fraction)) if heavy else likely

    if heavy or small or panel_count == 0:
        confidence: Confidence = "low"
    elif roof_type == "flat" and traced and not partial:
        confidence = "high"
    else:
        confidence = "medium"

    def kwp(n: int) -> float:
        return round(n * module_wp / 1000, 3)

    return CapacityResult(
        panel_count={"min": low, "likely": likely, "max": likely},
        capacity_kwp={"min": kwp(low), "likely": kwp(likely), "max": kwp(likely)},
        shading_loss_fraction=loss,
        constraints=constraints,
        confidence=confidence,
    )
