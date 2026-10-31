import json
from pathlib import Path

import pytest

from app.core.assumptions import (
    ASSUMPTIONS_PATH,
    AssumptionMissingError,
    AssumptionsFileError,
    load_assumptions,
)


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "assumptions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _shipped() -> dict:
    return json.loads(ASSUMPTIONS_PATH.read_text(encoding="utf-8"))


def test_shipped_file_loads():
    a = load_assumptions()
    assert a.version == "v1"
    assert a.climatology.years == 10
    assert a.validation.delhi_bbox == (76.83, 28.40, 77.35, 28.89)


def test_missing_fields_lists_nulls_and_empty_lists_only(tmp_path):
    data = _shipped()
    data["module"]["wp"] = None
    data["tariff"]["slabs"] = []
    data["losses"]["shading_by_level"] = {"none": 0, "partial": None, "heavy": 0.2}
    data["layout"]["default_azimuth_deg"] = 0
    missing = load_assumptions(_write(tmp_path, data)).missing_fields()
    assert "module.wp" in missing
    assert "tariff.slabs" in missing
    assert "losses.shading_by_level.partial" in missing
    assert "layout.default_azimuth_deg" not in missing  # set to 0
    assert "losses.shading_by_level.none" not in missing  # 0 is a value, not missing


def test_require_returns_set_value(tmp_path):
    data = _shipped()
    data["module"]["wp"] = 550
    a = load_assumptions(_write(tmp_path, data))
    assert a.require("module.wp") == 550
    assert a.require("layout.default_azimuth_deg") == 0


def test_require_raises_with_field_name(tmp_path):
    data = _shipped()
    data["costs"]["cost_per_kwp_inr"] = None
    a = load_assumptions(_write(tmp_path, data))
    with pytest.raises(AssumptionMissingError) as exc:
        a.require("costs.cost_per_kwp_inr")
    assert exc.value.field == "costs.cost_per_kwp_inr"
    assert "costs.cost_per_kwp_inr" in exc.value.message


def test_require_treats_empty_list_as_missing(tmp_path):
    data = _shipped()
    data["tariff"]["slabs"] = []
    with pytest.raises(AssumptionMissingError):
        load_assumptions(_write(tmp_path, data)).require("tariff.slabs")


def test_unknown_key_is_rejected(tmp_path):
    data = _shipped()
    data["module"]["wattage"] = 550  # typo for "wp"
    with pytest.raises(AssumptionsFileError):
        load_assumptions(_write(tmp_path, data))


def test_wrong_type_is_rejected(tmp_path):
    data = _shipped()
    data["module"]["wp"] = "five hundred"
    with pytest.raises(AssumptionsFileError):
        load_assumptions(_write(tmp_path, data))


def test_seasons_must_cover_every_month_once(tmp_path):
    data = _shipped()
    data["seasons"]["winter"] = [12, 1]  # February missing
    with pytest.raises(AssumptionsFileError):
        load_assumptions(_write(tmp_path, data))


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(AssumptionsFileError):
        load_assumptions(path)


def test_tariff_slabs_parse(tmp_path):
    data = _shipped()
    data["tariff"]["slabs"] = [
        {"up_to_kwh": 200, "rate_inr_per_kwh": 3.0},
        {"up_to_kwh": None, "rate_inr_per_kwh": 8.0},
    ]
    slabs = load_assumptions(_write(tmp_path, data)).require("tariff.slabs")
    assert slabs[0].up_to_kwh == 200
    assert slabs[1].up_to_kwh is None
