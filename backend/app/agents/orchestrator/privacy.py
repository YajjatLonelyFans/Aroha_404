"""Filter for anything written to memory: no location, contact details, ids or names."""

import re

_PATTERNS = {
    "coordinates": re.compile(r"\b\d{1,3}\.\d{4,}\b"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "phone": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "long_number": re.compile(r"(?<!\d)\d{9,}(?!\d)"),  # consumer / account numbers
    "pin_code": re.compile(r"(?<!\d)1[01]\d{4}(?!\d)"),  # Delhi PIN codes
}


def privacy_problem(text: str, display_name: str | None = None) -> str | None:
    """The reason `text` must not be stored, or None if it is safe."""
    for name, pattern in _PATTERNS.items():
        if pattern.search(text):
            return name
    if display_name and len(display_name.strip()) >= 3 and display_name.strip().lower() in text.lower():
        return "name"
    return None
