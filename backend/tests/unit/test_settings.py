import pytest

from app.core.settings import Settings, is_configured


@pytest.mark.parametrize(
    "value, expected",
    [
        ("mongodb+srv://u:p@cluster0.example.mongodb.net/", True),
        ("", False),
        ("   ", False),
        (None, False),
        ("<from-meko-portal>", False),
        ("mongodb+srv://<user>:<password>@<cluster>.mongodb.net/", False),
    ],
)
def test_is_configured(value, expected):
    assert is_configured(value) is expected


def test_cors_origin_list_splits_and_trims():
    s = Settings(_env_file=None, cors_origins="http://localhost:3000, https://aroha.app ,")
    assert s.cors_origin_list == ["http://localhost:3000", "https://aroha.app"]
