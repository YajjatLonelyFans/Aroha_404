from types import SimpleNamespace

import pytest

from app.agents.orchestrator.privacy import privacy_problem
from app.agents.orchestrator.reply_validator import numbers_in, unknown_numbers
from app.agents.orchestrator.routing import plan, wants_forecast
from app.integrations.meko.base import MemoryUnavailable
from app.integrations.meko.mcp_client import parse_result

FACTS = ["2.75 kW: about 3,899 kWh a year, cost ₹137,500, saves about ₹14,533 a year, payback about 9.5 years.",
         "Shade lowers output by 5%."]


# --- reply validator --------------------------------------------------------------------

def test_numbers_are_parsed_with_any_grouping():
    assert numbers_in("₹1,37,500 and ₹137,500, 3,899kWh, 9.5 years, 5%") == {137500.0, 3899.0, 9.5, 5.0}


def test_reply_using_only_given_numbers_passes():
    reply = "A 2.75 kW system makes about 3,899 kWh a year and saves about ₹14,533, so payback is about 9.5 years."
    assert unknown_numbers(reply, FACTS) == []


def test_indian_grouping_of_the_same_value_passes():
    assert unknown_numbers("It costs ₹1,37,500.", FACTS) == []


def test_rounded_or_invented_numbers_fail():
    assert unknown_numbers("It makes about 3,900 kWh and pays back in 10 years.", FACTS) == [10.0, 3900.0]


def test_number_glued_to_a_unit_is_still_checked():
    assert unknown_numbers("About 4000kWh a year.", FACTS) == [4000.0]


def test_small_counts_are_allowed():
    assert unknown_numbers("Here are 3 options and 2 sizes.", FACTS) == []


def test_numbers_from_the_question_are_allowed():
    assert unknown_numbers("With a bill of 2,800 units...", FACTS + ["My bill is 2800 units"]) == []


# --- routing ----------------------------------------------------------------------------

@pytest.mark.parametrize("message, expected", [
    ("Will the monsoon hurt my output?", ["weather"]),
    ("How much will I save and what is the payback?", ["financial"]),
    ("How many panels fit on my roof?", ["roof"]),
    ("Is 3 kW enough and what does it cost?", ["roof", "financial"]),
    ("Hi, where was I?", ["roof", "weather", "financial"]),
])
def test_plan(message, expected):
    assert plan(message) == expected


def test_short_keywords_match_whole_words_only():
    assert plan("Tell me about the cursor") == ["roof", "weather", "financial"]  # "rs" inside a word
    assert "financial" in plan("Is it worth 2 lakh rs?")


def test_forecast_detection():
    assert wants_forecast("What does this week look like?")
    assert not wants_forecast("What about winter?")


# --- privacy filter ---------------------------------------------------------------------

@pytest.mark.parametrize("text, problem", [
    ("Pin at 28.7327, 77.1190", "coordinates"),
    ("Mail me at a.b@example.com", "email"),
    ("Call 9876543210", "phone"),
    ("Consumer no 150012345678", "long_number"),
    ("Lives in 110085", "pin_code"),
    ("Riya wants 3 kW", "name"),
    ("Roof assessed: 34.6 m² usable, fits 7 panels (3.85 kW).", None),
    ("Estimate: saves about ₹14,533 a year; payback about 9.5 years.", None),
])
def test_privacy(text, problem):
    assert privacy_problem(text, display_name="Riya") == problem


# --- Meko result parsing ----------------------------------------------------------------

def _result(result=None, text=None, is_error=False):
    content = [{"type": "text", "text": text}] if text is not None else []
    structured = {"result": result} if result is not None else None
    return SimpleNamespace(model_dump=lambda by_alias: {
        "structuredContent": structured, "content": content, "isError": is_error})


def test_parse_json_string_result():
    assert parse_result(_result('{"results": [{"id": "m1"}]}')) == {"results": [{"id": "m1"}]}


@pytest.mark.parametrize("bad", [
    _result('{"error": "conversation_id_required", "detail": "Pass conversation_id"}'),
    _result('Error searching memories: invalid input syntax for type uuid'),
    _result(text="1 validation error for call[memory_add]", is_error=True),
])
def test_error_shapes_raise(bad):
    with pytest.raises(MemoryUnavailable):
        parse_result(bad)
