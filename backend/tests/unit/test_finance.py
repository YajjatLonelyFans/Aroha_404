import pytest

from app.domain.errors import DomainError
from app.domain.finance import (
    Slab,
    energy_charge_inr,
    estimate_finance,
    monthly_saving_inr,
    recommend_size,
)
from app.domain.generation import Percentiles

# Illustrative slabs for tests only; real values come from assumptions.v1.json.
SLABS = [Slab(200, 3.0), Slab(400, 4.5), Slab(None, 6.5)]
GEN = tuple(Percentiles(400.0, 500.0, 600.0) for _ in range(12))


def test_energy_charge_is_telescopic():
    assert energy_charge_inr(0, SLABS) == 0
    assert energy_charge_inr(150, SLABS) == 450
    assert energy_charge_inr(350, SLABS) == 200 * 3 + 150 * 4.5
    assert energy_charge_inr(500, SLABS) == 200 * 3 + 200 * 4.5 + 100 * 6.5


def test_last_slab_must_be_open_ended():
    with pytest.raises(DomainError):
        energy_charge_inr(500, [Slab(200, 3.0)])


def test_self_use_saves_at_the_top_slab_first():
    # 350 units, 100 generated: avoided = charge(350) - charge(250)
    assert monthly_saving_inr(100, 350, SLABS, 2.0) == pytest.approx(1275 - 825)


def test_export_is_credited_at_export_rate():
    saving = monthly_saving_inr(400, 350, SLABS, 2.0)
    assert saving == pytest.approx(energy_charge_inr(350, SLABS) + 50 * 2.0)


def _finance(**kw):
    args = dict(capacity_kwp=5.0, monthly_kwh=GEN, monthly_consumption_kwh=350,
                cost_per_kwp_inr=60000, subsidy_inr=0, slabs=SLABS, export_rate_inr=2.0)
    args.update(kw)
    return estimate_finance(**args)


def test_zero_subsidy():
    f = _finance()
    assert f.gross_cost_inr == 300000
    assert f.net_cost_inr == 300000
    assert f.missing == []
    assert f.payback_years.likely == pytest.approx(300000 / f.annual_savings_inr.likely)


def test_subsidy_above_cost_floors_net_cost_at_zero():
    f = _finance(subsidy_inr=500000)
    assert f.net_cost_inr == 0
    assert f.payback_years.likely == 0


def test_missing_tariff_returns_none_with_reason():
    f = _finance(slabs=[])
    assert f.annual_savings_inr.likely is None
    assert f.payback_years.likely is None
    assert any("Tariff" in m for m in f.missing)
    assert f.gross_cost_inr == 300000  # cost still computed


def test_missing_cost_returns_none_with_reason():
    f = _finance(cost_per_kwp_inr=None)
    assert f.gross_cost_inr is None and f.net_cost_inr is None
    assert f.payback_years.likely is None
    assert f.annual_savings_inr.likely is not None


def test_ranges_are_ordered():
    f = _finance()
    s, p = f.annual_savings_inr, f.payback_years
    assert s.low <= s.likely <= s.high
    assert p.low <= p.likely <= p.high


def test_missing_month_of_generation():
    gen = GEN[:11] + (Percentiles(None, None, None),)
    f = _finance(monthly_kwh=gen)
    assert f.annual_savings_inr.likely is None
    assert f.missing


def test_size_limited_by_roof():
    r = recommend_size(roof_panel_count=8, module_wp=550, annual_consumption_kwh=14000,
                       annual_yield_kwh_per_kwp=1400)
    assert r.consumption_kwp == pytest.approx(10.0)
    assert r.binding_constraint == "roof"
    assert r.recommended_kwp == 4.4


def test_size_limited_by_consumption():
    r = recommend_size(roof_panel_count=20, module_wp=500, annual_consumption_kwh=4200,
                       annual_yield_kwh_per_kwp=1400)
    assert r.consumption_kwp == pytest.approx(3.0)
    assert r.panel_count == 6
    assert r.recommended_kwp == 3.0
    assert r.binding_constraint == "consumption"


def test_size_limited_by_cap():
    r = recommend_size(roof_panel_count=20, module_wp=500, annual_consumption_kwh=14000,
                       annual_yield_kwh_per_kwp=1400, limit_kwp=3.0)
    assert r.recommended_kwp == 3.0
    assert r.binding_constraint == "limit"


def test_size_raised_to_minimum_for_low_use():
    r = recommend_size(roof_panel_count=20, module_wp=550, annual_consumption_kwh=960,
                       annual_yield_kwh_per_kwp=1490, min_kwp=1.0)
    assert r.consumption_kwp == pytest.approx(0.644, abs=0.001)
    assert r.panel_count == 2 and r.recommended_kwp == 1.1
    assert r.binding_constraint == "minimum"


def test_minimum_never_exceeds_the_roof():
    r = recommend_size(roof_panel_count=1, module_wp=550, annual_consumption_kwh=500,
                       annual_yield_kwh_per_kwp=1490, min_kwp=1.0)
    assert r.panel_count == 1 and r.binding_constraint == "roof"


def test_minimum_never_exceeds_a_limit():
    r = recommend_size(roof_panel_count=20, module_wp=550, annual_consumption_kwh=500,
                       annual_yield_kwh_per_kwp=1490, limit_kwp=0.6, min_kwp=1.0)
    assert r.panel_count == 1 and r.binding_constraint == "limit"


def test_minimum_does_not_touch_normal_use():
    r = recommend_size(roof_panel_count=20, module_wp=500, annual_consumption_kwh=4200,
                       annual_yield_kwh_per_kwp=1400, min_kwp=1.0)
    assert r.panel_count == 6 and r.binding_constraint == "consumption"


def test_size_needs_positive_yield():
    with pytest.raises(DomainError):
        recommend_size(roof_panel_count=10, module_wp=500, annual_consumption_kwh=4200,
                       annual_yield_kwh_per_kwp=0)
