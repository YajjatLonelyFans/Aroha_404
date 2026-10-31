from datetime import date

import pytest

from app.db.seed import load_policy_records, load_procedures
from app.domain.finance import payback_with_incentive
from app.domain.policy import Profile, capital_amount_inr, check, incentive_rate

TODAY = date(2026, 11, 1)
RECORDS = {r.scheme_id: r for r in load_policy_records()}
CENTRAL, DELHI, GBI, ZERO = (RECORDS[k] for k in (
    "pm-surya-ghar-cfa", "delhi-capital-subsidy", "delhi-gbi", "delhi-zero-upfront-3kw-2026"))


def profile(**kw) -> Profile:
    base = dict(property_type="independent_house", has_roof_rights=True, discom="BRPL",
                monthly_units_kwh=350, capacity_kwp=2.75)
    return Profile(**{**base, **kw})


def test_seed_files_are_valid():
    assert len(RECORDS) == 4
    assert all(r.source_url.startswith("https://") and r.verified_on for r in RECORDS.values())
    assert load_procedures()[0].steps[0].id == "register"


@pytest.mark.parametrize("kwp, expected", [(1, 30000), (2, 60000), (2.75, 73500), (3, 78000), (5, 78000)])
def test_central_subsidy_tiers(kwp, expected):
    assert capital_amount_inr(CENTRAL.amount_rule, kwp) == expected


@pytest.mark.parametrize("kwp, expected", [(2.75, 5500), (5, 10000), (8, 10000)])
def test_delhi_subsidy_is_capped(kwp, expected):
    assert capital_amount_inr(DELHI.amount_rule, kwp) == expected


@pytest.mark.parametrize("kwp, rate", [(2.75, 3), (3, 3), (5, 2), (10, 2), (12, None)])
def test_incentive_rate_by_size(kwp, rate):
    assert incentive_rate(GBI.amount_rule, kwp) == rate


def test_eligible_homeowner():
    for rec in (CENTRAL, DELHI, GBI):
        e = check(rec, profile(), TODAY)
        assert e.eligible == "yes" and e.counts_in_estimate


def test_unverified_record_never_counts():
    e = check(ZERO, profile(), TODAY)
    assert e.eligible == "unknown" and not e.counts_in_estimate
    assert "Needs verification" in e.reasons[0]


def test_record_past_its_review_date_needs_reverification():
    e = check(CENTRAL, profile(), date(2027, 4, 1))
    assert e.eligible == "unknown" and not e.counts_in_estimate


def test_expired_record():
    assert check(CENTRAL.model_copy(update={"status": "expired"}), profile(), TODAY).eligible == "no"


@pytest.mark.parametrize("change, rec", [
    ({"has_roof_rights": False}, CENTRAL),
    ({"property_type": "other"}, CENTRAL),
    ({"discom": "other"}, DELHI),
    ({"capacity_kwp": 12}, GBI),
])
def test_rules_that_fail(change, rec):
    e = check(rec, profile(**change), TODAY)
    assert e.eligible == "no" and e.reasons and not e.counts_in_estimate


def test_central_scheme_ignores_discom():
    assert check(CENTRAL, profile(discom="other"), TODAY).eligible == "yes"


def test_size_dependent_scheme_without_a_size_is_unknown():
    assert check(GBI, profile(capacity_kwp=None), TODAY).eligible == "unknown"


def test_unit_limit_is_checked_once_verified():
    verified_zero = ZERO.model_copy(update={"status": "verified", "review_by": date(2099, 1, 1)})
    assert check(verified_zero, profile(monthly_units_kwh=500), TODAY).eligible == "no"
    assert check(verified_zero, profile(monthly_units_kwh=350), TODAY).eligible == "yes"


# --- payback with a limited-time incentive -----------------------------------------------

def test_paid_back_within_incentive_years():
    assert payback_with_incentive(60000, 15000, 15000, 5) == pytest.approx(2.0)


def test_paid_back_after_incentive_ends():
    # 5 years at 20,000 cover 100,000; the remaining 20,000 at 10,000 a year takes 2 more years.
    assert payback_with_incentive(120000, 10000, 10000, 5) == pytest.approx(7.0)


def test_no_cost_and_no_savings_cases():
    assert payback_with_incentive(0, 0, 0, 5) == 0.0
    assert payback_with_incentive(120000, 0, 10000, 5) is None
