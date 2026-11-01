import math
from dataclasses import replace

import pytest
from shapely.geometry import Polygon

from app.domain.errors import DomainError
from app.domain.geometry import (
    assess_geometry,
    geodesic_area_m2,
    manual_geometry,
    parse_polygon,
    to_metric,
    to_wgs84,
)
from tests.unit.helpers import ORIGIN_X, ORIGIN_Y, geojson_rect, metric_rect


def test_utm_origin_is_in_delhi():
    lon, lat = to_wgs84(metric_rect(1, 1)).exterior.coords[0]
    assert 76.83 < lon < 77.35 and 28.40 < lat < 28.89


def test_geodesic_area_of_known_rectangle_within_1_percent():
    outline = parse_polygon(geojson_rect(10, 5))
    assert geodesic_area_m2(outline) == pytest.approx(50, rel=0.01)


@pytest.mark.parametrize("hole_clockwise", [True, False])
def test_geodesic_area_subtracts_a_courtyard_whatever_the_ring_direction(hole_clockwise):
    outer = list(to_wgs84(metric_rect(20, 20)).exterior.coords)
    hole = list(to_wgs84(metric_rect(5, 5, 5, 5)).exterior.coords)
    roof = Polygon(outer, [hole[::-1] if hole_clockwise else hole])
    assert geodesic_area_m2(roof) == pytest.approx(400 - 25, rel=0.01)


def test_projection_round_trip():
    rect = metric_rect(10, 5)
    back = to_metric(to_wgs84(rect))
    assert back.symmetric_difference(rect).area < 1e-6


def test_setback_only(geo_params):
    g = assess_geometry(geojson_rect(10, 5), [], geo_params)
    assert g.outline_area_m2 == pytest.approx(50, rel=0.01)
    assert g.usable_area_m2 == pytest.approx(9 * 4, rel=1e-3)
    assert g.setback_area_m2 == pytest.approx(50 - 36, rel=1e-2)
    assert g.no_go_area_m2 == pytest.approx(0, abs=1e-9)
    assert g.georeferenced


def test_no_go_subtracted(geo_params):
    tank = geojson_rect(2, 2, x=4, y=1.5)
    g = assess_geometry(geojson_rect(10, 5), [tank], geo_params)
    assert g.no_go_area_m2 == pytest.approx(4, rel=1e-3)
    assert g.usable_area_m2 == pytest.approx(32, rel=1e-3)


def test_no_go_clearance_grows_the_blocked_area(geo_params):
    tank = geojson_rect(2, 2, x=4, y=1.5)
    g = assess_geometry(geojson_rect(10, 5), [tank], replace(geo_params, no_go_clearance_m=0.5))
    # 2x2 square buffered by 0.5 m: 4 + perimeter*0.5 + pi*0.5^2
    expected = 4 + 8 * 0.5 + math.pi * 0.25
    assert g.no_go_area_m2 == pytest.approx(expected, rel=5e-3)


def test_no_go_in_setback_strip_is_not_counted_twice(geo_params):
    # Tank sits half inside the 0.5 m edge strip.
    tank = geojson_rect(1, 1, x=0, y=2)
    g = assess_geometry(geojson_rect(10, 5), [tank], geo_params)
    assert g.no_go_area_m2 == pytest.approx(0.5, rel=1e-2)
    assert g.usable_area_m2 == pytest.approx(36 - 0.5, rel=1e-3)


def test_deductions_add_up(geo_params):
    tank = geojson_rect(2, 2, x=4, y=1.5)
    g = assess_geometry(geojson_rect(10, 5), [tank], geo_params)
    total = g.usable_area_m2 + g.setback_area_m2 + g.no_go_area_m2
    assert total == pytest.approx(g.outline_area_m2, rel=1e-3)


def test_setback_larger_than_roof_leaves_nothing(geo_params):
    g = assess_geometry(geojson_rect(4, 3), [], replace(geo_params, edge_setback_m=2))
    assert g.usable_area_m2 == 0


def test_outside_delhi_rejected(geo_params):
    mumbai = {"type": "Polygon", "coordinates": [[[72.8, 19.0], [72.8001, 19.0], [72.8001, 19.0001], [72.8, 19.0001], [72.8, 19.0]]]}
    with pytest.raises(DomainError) as exc:
        assess_geometry(mumbai, [], geo_params)
    assert exc.value.code == "outside_delhi"


def test_too_small_and_too_large_rejected(geo_params):
    with pytest.raises(DomainError) as exc:
        assess_geometry(geojson_rect(2, 2), [], geo_params)
    assert exc.value.code == "outline_too_small"
    with pytest.raises(DomainError) as exc:
        assess_geometry(geojson_rect(100, 50), [], geo_params)
    assert exc.value.code == "outline_too_large"


def test_self_crossing_outline_rejected():
    x, y = ORIGIN_X, ORIGIN_Y
    bowtie = to_wgs84(Polygon([(x, y), (x + 10, y + 10), (x + 10, y), (x, y + 10)]))
    gj = {"type": "Polygon", "coordinates": [list(map(list, bowtie.exterior.coords))]}
    with pytest.raises(DomainError) as exc:
        parse_polygon(gj)
    assert exc.value.code == "invalid_outline"


@pytest.mark.parametrize("bad", [None, {"type": "Point", "coordinates": [77.2, 28.5]}, {"type": "Polygon", "coordinates": [[[1, 2]]]}])
def test_non_polygon_rejected(bad):
    with pytest.raises(DomainError):
        parse_polygon(bad)


def test_manual_dimensions():
    g = manual_geometry(10, 5, [4], edge_setback_m=0.5)
    assert g.outline_area_m2 == 50
    assert g.setback_area_m2 == 14
    assert g.no_go_area_m2 == 4
    assert g.usable_area_m2 == 32
    assert g.usable_m.area == pytest.approx(32)
    assert not g.georeferenced


def test_manual_no_go_capped_at_inner_area():
    g = manual_geometry(4, 3, [100], edge_setback_m=0.5)
    assert g.usable_area_m2 == 0
    assert g.usable_m.is_empty


def test_manual_rejects_bad_dimensions():
    with pytest.raises(DomainError):
        manual_geometry(0, 5, [], edge_setback_m=0.5)
