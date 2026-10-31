import pytest

from app.domain.geometry import GeometryParams


@pytest.fixture
def geo_params() -> GeometryParams:
    return GeometryParams(
        edge_setback_m=0.5,
        no_go_clearance_m=0.0,
        bbox=(76.83, 28.40, 77.35, 28.89),
        min_outline_m2=10,
        max_outline_m2=2000,
    )
