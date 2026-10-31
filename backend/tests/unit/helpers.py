from shapely.geometry import Polygon, box

from app.domain.geometry import to_geojson, to_wgs84

# A point in South Delhi, in UTM 43N metres.
ORIGIN_X, ORIGIN_Y = 714_000.0, 3_160_000.0


def metric_rect(w: float, h: float, x: float = 0.0, y: float = 0.0) -> Polygon:
    return box(ORIGIN_X + x, ORIGIN_Y + y, ORIGIN_X + x + w, ORIGIN_Y + y + h)


def geojson_rect(w: float, h: float, x: float = 0.0, y: float = 0.0) -> dict:
    return to_geojson(to_wgs84(metric_rect(w, h, x, y)), precision=10)
