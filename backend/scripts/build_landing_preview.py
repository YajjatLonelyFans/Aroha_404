"""Build the landing page's roof preview: the real SSCBS main building, run through Aroha's own
geometry and panel-packing code.

Usage (from backend/, venv active):  python -m scripts.build_landing_preview
Writes frontend/src/features/landing/sscbs-roof.json (shapes in local metres + figures).

The footprint is OpenStreetMap relation 19386159 (building=college, flat roof, with a central
courtyard), © OpenStreetMap contributors, ODbL. It is fetched once from the Overpass API.

The campus is not a home, so the 2,000 m² house-roof limit is lifted for this one run; every
other step (edge walkway, packing, panel size, row spacing) is exactly what a homeowner's roof
goes through.
"""

from datetime import date

import httpx
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import polygonize, unary_union

from app.core.assumptions import load_assumptions
from app.core.settings import REPO_DIR, get_settings
from app.domain.geometry import GeometryParams, assess_geometry, to_metric
from app.domain.layout import LayoutParams, ModuleSpec, pack_panels, winter_noon_sun_elevation_deg

OUT = REPO_DIR / "frontend" / "src" / "features" / "landing" / "sscbs-roof.json"
OSM_RELATION = 19386159
OVERPASS = "https://overpass-api.de/api/interpreter"


def fetch_footprint() -> Polygon:
    """The building as a polygon with its courtyard as a hole (lon, lat)."""
    r = httpx.post(OVERPASS, data={"data": f"[out:json];relation({OSM_RELATION});out geom;"},
                   headers={"User-Agent": get_settings().nominatim_user_agent}, timeout=60)
    r.raise_for_status()
    members = r.json()["elements"][0]["members"]
    rings = {role: list(polygonize(unary_union([
        LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in members if m["role"] == role
    ]))) for role in ("outer", "inner")}
    outer = max(rings["outer"], key=lambda p: p.area)
    return Polygon(outer.exterior.coords, [i.exterior.coords for i in rings["inner"]])


def main() -> None:
    footprint = fetch_footprint()
    lat = footprint.centroid.y
    a = load_assumptions()
    geom = assess_geometry(mapping(footprint), [], GeometryParams(
        edge_setback_m=a.require("layout.edge_setback_m"),
        no_go_clearance_m=a.require("layout.no_go_clearance_m"),
        bbox=a.validation.delhi_bbox,
        min_outline_m2=a.require("validation.min_outline_m2"),
        max_outline_m2=50_000,  # a campus building, not a house: the house-roof limit does not apply
    ))
    module = ModuleSpec(a.require("module.length_m"), a.require("module.width_m"), a.require("module.wp"))
    layout = pack_panels(geom.usable_m, module, LayoutParams(
        a.require("layout.default_flat_tilt_deg"), a.require("layout.default_azimuth_deg"),
        a.require("layout.row_gap_m"), winter_noon_sun_elevation_deg(lat),
    ))

    # Local metres for drawing: origin at the top-left of the footprint, y pointing down like SVG.
    footprint_m = to_metric(footprint)
    minx, miny, maxx, maxy = footprint_m.bounds
    local = lambda coords: [[round(x - minx, 2), round(maxy - y, 2)] for x, y in coords]
    data = {
        "source": f"OpenStreetMap relation {OSM_RELATION}, © OpenStreetMap contributors (ODbL)",
        "built_on": date.today().isoformat(),
        "width_m": round(maxx - minx, 2),
        "height_m": round(maxy - miny, 2),
        "outline": local(footprint_m.exterior.coords),
        "courtyard": [local(r.coords) for r in footprint_m.interiors],
        "panels": [local(p.exterior.coords)[:-1] for p in layout.panels_m],
        "figures": {
            "outline_area_m2": round(geom.outline_area_m2),
            "usable_area_m2": round(geom.usable_area_m2),
            "panel_count": layout.panel_count,
            "capacity_kwp": round(layout.capacity_kwp, 1),
            "module_wp": module.wp,
        },
    }
    OUT.write_text(__import__("json").dumps(data, separators=(",", ":")), encoding="utf-8")
    f = data["figures"]
    print(f"roof {f['outline_area_m2']} m² (courtyard excluded), usable {f['usable_area_m2']} m², "
          f"{f['panel_count']} panels, {f['capacity_kwp']} kWp, {data['width_m']} x {data['height_m']} m")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
