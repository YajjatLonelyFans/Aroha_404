"""Every number in an assistant reply must already appear in the facts it was given.

Numbers are compared by value after removing thousands separators, so "₹1,37,500"
matches "₹137,500". Rounding, converting or inventing a number fails validation.
"""

import re
from collections.abc import Iterable

# Digits with optional thousands separators (Western or Indian grouping) and decimals.
# Units may touch the number ("3,900kWh"), so only digits and separators bound it.
_NUMBER = re.compile(r"(?<![\d.,])\d+(?:,\d+)*(?:\.\d+)?(?!\d)")
# Small counting words like "3 options" or "2 sizes" are allowed without a source.
ALWAYS_ALLOWED = {0.0, 1.0, 2.0, 3.0}


def numbers_in(text: str) -> set[float]:
    out = set()
    for match in _NUMBER.findall(text):
        try:
            out.add(float(match.replace(",", "")))
        except ValueError:
            continue
    return out


def unknown_numbers(reply: str, sources: Iterable[str]) -> list[float]:
    """Numbers in the reply that appear in none of the source texts."""
    allowed = set(ALWAYS_ALLOWED)
    for text in sources:
        allowed |= numbers_in(text)
    return sorted(n for n in numbers_in(reply) if n not in allowed)
