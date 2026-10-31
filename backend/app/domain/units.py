"""Display rounding and month names, shared so every layer rounds the same way."""

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def month_name(month: int) -> str:
    return MONTH_NAMES[month - 1]


def round_area_m2(value: float) -> float:
    return round(value, 1)


def round_kwp(value: float) -> float:
    return round(value, 2)


def round_kwh(value: float) -> float:
    return round(value, 0)


def round_inr(value: float) -> float:
    return round(value, 0)


def round_years(value: float) -> float:
    return round(value, 1)


def round_pct(value: float) -> float:
    return round(value, 0)
