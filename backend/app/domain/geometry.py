"""Roof geometry: outline area, edge setback, no-go areas and usable area.

Outlines arrive as WGS84 GeoJSON (lon, lat). Metric work happens in
UTM zone 43N (EPSG:32643), which covers Delhi.
"""

from dataclasses import dataclass
from typing import Any

import shapely
from pyproj import Geod, Transformer
from shapely import make_valid
from shapely.geometry import Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.domain.errors import DomainError

UTM_43N = "EPSG:32643"
_GEOD = Geod(ellps="WGS84")
_TO_UTM = Transformer.from_crs("EPSG:4326", UTM_43N, always_xy=True)
_TO_WGS84 = Transformer.from_crs(UTM_43N, "EPSG:4326", always_xy=True)


@dataclass(frozen=True)
class GeometryParams:
    edge_setback_m: float
    no_go_clearance_m: float
    bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat
    min_outline_m2: float
    max_outline_m2: float


@dataclass(frozen=True)
class RoofGeometry:
    outline_area_m2: float
    setback_area_m2: float  # removed by the edge setback
    no_go_area_m2: float  # removed by no-go areas and their clearance, inside the setback line
    usable_area_m2: float
    usable_m: BaseGeometry  # metric polygon panels are packed into
    georeferenced: bool  # False for the manual-dimensions fallback


def to_metric(geom: BaseGeometry) -> BaseGeometry:
    return shapely.transform(geom, _TO_UTM.transform, interleaved=False)


def to_wgs84(geom: BaseGeometry) -> BaseGeometry:
    return shapely.transform(geom, _TO_WGS84.transform, interleaved=False)


def geodesic_area_m2(polygon_wgs84: BaseGeometry) -> float:
    area, _ = _GEOD.geometry_area_perimeter(polygon_wgs84)
    return abs(area)


def parse_polygon(geojson: dict[str, Any], what: str = "outline") -> Polygon:
    """GeoJSON Polygon → valid shapely Polygon, or a DomainError explaining why not."""
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        raise DomainError("invalid_outline", f"The {what} must be a GeoJSON Polygon.")
    try:
        poly = shape(geojson)
    except (ValueError, TypeError, IndexError) as exc:
        raise DomainError("invalid_outline", f"The {what} coordinates are malformed.") from exc
    if poly.is_empty or poly.area == 0:
        raise DomainError("invalid_outline", f"The {what} has no area.")
    if not poly.is_valid:
        poly = make_valid(poly)
        if not isinstance(poly, Polygon):
            raise DomainError("invalid_outline", f"The {what} crosses itself; please redraw it.")
    return poly


def check_point_in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> None:
    min_lon, min_lat, max_lon, max_lat = bbox
    if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
        raise DomainError("outside_delhi", "The location must be inside Delhi.")


def _check_outline(outline: Polygon, params: GeometryParams) -> float:
    min_lon, min_lat, max_lon, max_lat = params.bbox
    if not box(min_lon, min_lat, max_lon, max_lat).contains(outline):
        raise DomainError("outside_delhi", "The roof must be inside Delhi.")
    area = geodesic_area_m2(outline)
    if area < params.min_outline_m2:
        raise DomainError(
            "outline_too_small",
            f"The outline covers {area:.1f} m², below the {params.min_outline_m2:g} m² minimum.",
        )
    if area > params.max_outline_m2:
        raise DomainError(
            "outline_too_large",
            f"The outline covers {area:.1f} m², above the {params.max_outline_m2:g} m² maximum. "
            "Trace a single house roof.",
        )
    return area


def assess_geometry(
    outline_geojson: dict[str, Any],
    no_go_geojson: list[dict[str, Any]],
    params: GeometryParams,
) -> RoofGeometry:
    outline = parse_polygon(outline_geojson)
    outline_area = _check_outline(outline, params)

    outline_m = to_metric(outline)
    inside_setback = outline_m.buffer(-params.edge_setback_m, join_style="mitre")

    no_go_m = [to_metric(parse_polygon(g, "no-go area")) for g in no_go_geojson]
    if no_go_m:
        blocked = unary_union(no_go_m).buffer(params.no_go_clearance_m)
        usable = inside_setback.difference(blocked)
    else:
        usable = inside_setback

    return RoofGeometry(
        outline_area_m2=outline_area,
        setback_area_m2=outline_m.area - inside_setback.area,
        no_go_area_m2=inside_setback.area - usable.area,
        usable_area_m2=usable.area,
        usable_m=usable,
        georeferenced=True,
    )


def manual_geometry(
    length_m: float,
    width_m: float,
    no_go_areas_m2: list[float],
    edge_setback_m: float,
) -> RoofGeometry:
    """Fallback when the map cannot be used.

    The usable area is (L − 2s)(W − 2s) − Σ no-go. For panel counting it is
    modelled as a rectangle of the full inner width, shortened by the no-go
    area, because the positions of the no-go areas are unknown.
    """
    if length_m <= 0 or width_m <= 0:
        raise DomainError("invalid_dimensions", "Length and width must be positive.")
    if any(a < 0 for a in no_go_areas_m2):
        raise DomainError("invalid_dimensions", "No-go areas cannot be negative.")

    inner_l = max(length_m - 2 * edge_setback_m, 0.0)
    inner_w = max(width_m - 2 * edge_setback_m, 0.0)
    inner_area = inner_l * inner_w
    no_go = min(sum(no_go_areas_m2), inner_area)
    usable_area = inner_area - no_go

    usable_l = usable_area / inner_w if inner_w > 0 else 0.0
    usable = box(0, 0, usable_l, inner_w) if usable_area > 0 else Polygon()

    return RoofGeometry(
        outline_area_m2=length_m * width_m,
        setback_area_m2=length_m * width_m - inner_area,
        no_go_area_m2=no_go,
        usable_area_m2=usable_area,
        usable_m=usable,
        georeferenced=False,
    )


def to_geojson(geom: BaseGeometry, precision: int = 7) -> dict[str, Any]:
    """Shapely geometry → GeoJSON dict with rounded coordinates (7 dp ≈ 1 cm)."""
    def _round(coords: Any) -> Any:
        if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
            return [round(c, precision) for c in coords]
        return [_round(c) for c in coords]

    gj = mapping(geom)
    return {"type": gj["type"], "coordinates": _round(gj["coordinates"])}
