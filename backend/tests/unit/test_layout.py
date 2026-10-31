import json
from dataclasses import replace

import pytest
from shapely.geometry import Polygon

from app.domain.errors import DomainError
from app.domain.layout import (
    CapacityParams,
    LayoutParams,
    ModuleSpec,
    assess_capacity,
    pack_panels,
    panels_to_geojson,
    row_gap,
    winter_noon_sun_elevation_deg,
)
from tests.unit.helpers import ORIGIN_X, ORIGIN_Y, metric_rect

MODULE = ModuleSpec(length_m=2.0, width_m=1.0, wp=500)
FLAT = LayoutParams(tilt_deg=0, azimuth_deg=0, row_gap_m=0)
TOL = 1e-5


def test_picks_the_orientation_that_fits_more():
    # 10 x 5 m: portrait 10 x 2 = 20, landscape 5 x 5 = 25.
    layout = pack_panels(metric_rect(10, 5), MODULE, FLAT)
    assert layout.panel_count == 25
    assert layout.orientation == "landscape"
    assert layout.capacity_kwp == 12.5


def test_tilt_shortens_depth_and_ties_go_to_portrait():
    # cos(60°) = 0.5 → portrait 1 x 1, landscape 2 x 0.5: both 50 panels.
    layout = pack_panels(metric_rect(10, 5), MODULE, replace(FLAT, tilt_deg=60))
    assert layout.panel_count == 50
    assert layout.orientation == "portrait"


def test_row_gap_sits_between_rows():
    # Portrait depth 2 + gap 1 → rows at y=0 and y=3 (2 rows x 10 = 20).
    # Landscape depth 1 + gap 1 → rows at y=0, 2, 4 (3 rows x 5 = 15).
    layout = pack_panels(metric_rect(10, 5), MODULE, replace(FLAT, row_gap_m=1))
    assert layout.panel_count == 20
    assert layout.orientation == "portrait"


def test_winter_noon_sun_in_delhi():
    assert winter_noon_sun_elevation_deg(28.6) == pytest.approx(37.96)


def test_shade_spacing_depends_on_orientation():
    # Module 2 x 1 m at 30°: raised edge 1.0 m (portrait) or 0.5 m (landscape); sun at 45° → equal shadow.
    p = LayoutParams(tilt_deg=30, azimuth_deg=0, row_gap_m=0.0, shade_free_sun_elevation_deg=45)
    assert row_gap(MODULE, "portrait", p) == pytest.approx(1.0)
    assert row_gap(MODULE, "landscape", p) == pytest.approx(0.5)


def test_minimum_gap_wins_when_shadow_is_shorter():
    p = LayoutParams(tilt_deg=30, azimuth_deg=0, row_gap_m=0.8, shade_free_sun_elevation_deg=45)
    assert row_gap(MODULE, "landscape", p) == 0.8
    assert row_gap(MODULE, "portrait", p) == pytest.approx(1.0)


def test_flat_panels_need_no_shade_spacing():
    p = LayoutParams(tilt_deg=0, azimuth_deg=0, row_gap_m=0.2, shade_free_sun_elevation_deg=45)
    assert row_gap(MODULE, "portrait", p) == 0.2


def test_shade_spacing_is_used_in_packing():
    # 10 x 5 m, tilt 30°, sun 45°:
    # portrait: depth 1.73 + gap 1.0 → rows at 0, 2.73 (ends 4.46) → 2 rows x 10 = 20
    # landscape: depth 0.87 + gap 0.5 → rows at 0, 1.37, 2.73, 4.10 (ends 4.97) → 4 rows x 5 = 20
    p = LayoutParams(tilt_deg=30, azimuth_deg=0, row_gap_m=0.0, shade_free_sun_elevation_deg=45)
    layout = pack_panels(metric_rect(10, 5), MODULE, p)
    assert layout.panel_count == 20
    assert layout.orientation == "portrait" and layout.row_gap_m == pytest.approx(1.0)


def test_bad_sun_elevation_rejected():
    with pytest.raises(DomainError):
        row_gap(MODULE, "portrait", LayoutParams(20, 0, 0.0, shade_free_sun_elevation_deg=0))


def test_east_facing_rotates_rows():
    # A 5 x 10 rectangle facing east behaves like 10 x 5 facing south.
    layout = pack_panels(metric_rect(5, 10), MODULE, replace(FLAT, azimuth_deg=-90))
    assert layout.panel_count == 25


def _irregular() -> Polygon:
    x, y = ORIGIN_X, ORIGIN_Y
    shell = [(x, y), (x + 12, y), (x + 12, y + 4), (x + 7, y + 4), (x + 7, y + 9), (x, y + 9.5)]
    hole = [(x + 2, y + 2), (x + 4, y + 2), (x + 4, y + 4), (x + 2, y + 4)]
    return Polygon(shell, [hole])


@pytest.mark.parametrize("azimuth", [0, -90, 35, 180])
def test_panels_stay_inside_and_do_not_overlap(azimuth):
    usable = _irregular()
    layout = pack_panels(usable, MODULE, LayoutParams(tilt_deg=20, azimuth_deg=azimuth, row_gap_m=0.6))
    assert layout.panel_count > 0
    grown = usable.buffer(TOL)
    for p in layout.panels_m:
        assert grown.contains(p)
    for i, a in enumerate(layout.panels_m):
        for b in layout.panels_m[i + 1:]:
            assert a.intersection(b).area < 1e-6


def test_packing_is_deterministic():
    params = LayoutParams(tilt_deg=20, azimuth_deg=10, row_gap_m=0.6)
    a = json.dumps(panels_to_geojson(pack_panels(_irregular(), MODULE, params).panels_m))
    b = json.dumps(panels_to_geojson(pack_panels(_irregular(), MODULE, params).panels_m))
    assert a == b


def test_empty_area_gives_no_panels():
    layout = pack_panels(Polygon(), MODULE, FLAT)
    assert layout.panel_count == 0 and layout.orientation is None


def test_geojson_is_feature_collection_in_delhi():
    layout = pack_panels(metric_rect(10, 5), MODULE, FLAT)
    gj = panels_to_geojson(layout.panels_m)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 25
    lon, lat = gj["features"][0]["geometry"]["coordinates"][0][0]
    assert 76.83 < lon < 77.35 and 28.40 < lat < 28.89


@pytest.mark.parametrize("bad", [ModuleSpec(0, 1, 500), ModuleSpec(2, 1, 0)])
def test_bad_module_rejected(bad):
    with pytest.raises(DomainError):
        pack_panels(metric_rect(10, 5), bad, FLAT)


def test_bad_tilt_rejected():
    with pytest.raises(DomainError):
        pack_panels(metric_rect(10, 5), MODULE, replace(FLAT, tilt_deg=90))


# --- capacity ---------------------------------------------------------------------------

CAP = CapacityParams(
    shading_by_level={"none": 0.0, "partial": 0.05, "heavy": 0.15},
    shading_cap_fraction=0.25,
    shading_haircut_fraction=0.25,
    small_area_m2=10,
    many_obstructions_fraction=0.3,
)


def _cap(**kw):
    args = dict(
        panel_count=12, module_wp=550, shading={}, roof_type="flat", azimuth_deg=0,
        usable_area_m2=40, outline_area_m2=50, no_go_area_m2=5, traced=True, params=CAP,
    )
    args.update(kw)
    return assess_capacity(**args)


def _codes(result):
    return [c.code for c in result.constraints]


def test_clear_flat_roof_is_high_confidence():
    r = _cap()
    assert r.capacity_kwp == {"min": 6.6, "likely": 6.6, "max": 6.6}
    assert r.shading_loss_fraction == 0
    assert r.confidence == "high"
    assert r.constraints == []


def test_partial_shade_lowers_confidence_not_capacity():
    r = _cap(shading={"south": "partial"})
    assert "partial_shade_south" in _codes(r)
    assert r.shading_loss_fraction == 0.05
    assert r.panel_count["min"] == 12
    assert r.confidence == "medium"


def test_heavy_shade_cuts_min_and_confidence():
    r = _cap(shading={"west": "heavy"})
    assert "heavy_shade_west" in _codes(r)
    assert r.panel_count == {"min": 9, "likely": 12, "max": 12}
    assert r.confidence == "low"


def test_shading_loss_is_capped():
    r = _cap(shading={s: "heavy" for s in ("east", "south", "west", "north")})
    assert r.shading_loss_fraction == 0.25


def test_flags():
    assert "small_area" in _codes(_cap(usable_area_m2=8))
    assert "many_obstructions" in _codes(_cap(no_go_area_m2=20))
    assert "north_facing_slope" in _codes(_cap(roof_type="sloped", azimuth_deg=170))
    assert "no_panels_fit" in _codes(_cap(panel_count=0))


def test_manual_or_sloped_is_medium():
    assert _cap(traced=False).confidence == "medium"
    assert _cap(roof_type="sloped").confidence == "medium"


def test_unknown_shading_rejected():
    with pytest.raises(DomainError):
        _cap(shading={"up": "heavy"})
    with pytest.raises(DomainError):
        _cap(shading={"south": "total"})
