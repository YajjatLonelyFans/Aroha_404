import pytest

from app.domain.errors import DomainError
from app.domain.seasons import MonthClimate, season_notes, season_of

SEASONS = {"winter": [12, 1, 2], "summer": [3, 4, 5, 6], "monsoon": [7, 8, 9], "post_monsoon": [10, 11]}

GTI = [110, 125, 160, 175, 185, 170, 140, 135, 145, 150, 125, 105]
TEMP = [14, 17, 23, 29, 33, 34, 31, 30, 29, 26, 20, 15]
RAIN = [15, 18, 12, 9, 25, 70, 210, 240, 120, 15, 4, 8]
CLOUD = [20, 22, 18, 15, 20, 40, 70, 72, 50, 15, 10, 15]


def _months(**blank) -> list[MonthClimate]:
    rows = []
    for i in range(12):
        row = dict(month=i + 1, gti_kwh_m2=GTI[i], temp_mean_c=TEMP[i], cloud_cover_pct=CLOUD[i],
                   precip_mm=RAIN[i], sunshine_h=None)
        row.update({k: None for k in blank})
        rows.append(MonthClimate(**row))
    return rows


def test_season_of():
    assert season_of(1, SEASONS) == "winter"
    assert season_of(8, SEASONS) == "monsoon"
    with pytest.raises(DomainError):
        season_of(13, SEASONS)


def test_notes_come_from_the_data():
    notes = season_notes(_months(), SEASONS)
    text = " ".join(n.statement for n in notes)
    assert "May gets the most sunlight" in text and "185.0" in text
    assert "December gets the least" in text and "105.0" in text
    assert "August is the wettest month, with 240 mm" in text and "72%" in text
    assert "June is the hottest month (mean 34.0 °C)" in text


def test_every_note_lists_its_evidence():
    for n in season_notes(_months(), SEASONS):
        assert n.evidence_fields
        assert n.values


def test_season_comparison_to_yearly_average():
    notes = {n.season: n for n in season_notes(_months(), SEASONS) if "diff_pct" in n.values}
    avg = sum(GTI) / 12
    winter = (110 + 125 + 105) / 3
    assert notes["winter"].values["diff_pct"] == round(100 * (winter - avg) / avg)
    assert "below" in notes["winter"].statement
    assert "above" in notes["summer"].statement
    assert notes["post_monsoon"].statement.startswith("Post-monsoon")


def test_missing_fields_skip_their_rules():
    notes = season_notes(_months(precip_mm=True, temp_mean_c=True), SEASONS)
    fields = {f for n in notes for f in n.evidence_fields}
    assert fields == {"gti_kwh_m2"}


def test_no_data_no_notes():
    assert season_notes(_months(gti_kwh_m2=True, precip_mm=True, temp_mean_c=True), SEASONS) == []
