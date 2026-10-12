"""Where a passage is in a text.

A passage is a range of a Markdown source in Unicode code points (what indexing a Python
string gives), kept with the text it selects (the quote) and a little of the text before and
after it. Offsets are exact for the version of the text they were taken on. On another version
the quote is looked for again, and the context tells two equal quotes apart. A passage is
never attached to a place by guessing: without one clear place it is not found.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: Characters of context kept on each side of a passage.
CONTEXT = 64


@dataclass(frozen=True)
class Located:
    start: int
    end: int


@dataclass(frozen=True)
class NotLocated:
    reason: Literal["missing", "ambiguous"]


def context(text: str, start: int, end: int) -> tuple[str, str]:
    """The text just before and just after a range."""
    return text[max(0, start - CONTEXT) : start], text[end : end + CONTEXT]


def occurrences(text: str, quote: str) -> list[int]:
    found, index = [], text.find(quote)
    while index != -1:
        found.append(index)
        index = text.find(quote, index + 1)
    return found


def _common_suffix(left: str, right: str) -> int:
    count = 0
    while count < min(len(left), len(right)) and left[-1 - count] == right[-1 - count]:
        count += 1
    return count


def _common_prefix(left: str, right: str) -> int:
    count = 0
    while count < min(len(left), len(right)) and left[count] == right[count]:
        count += 1
    return count


def locate(text: str, quote: str, prefix: str = "", suffix: str = "") -> Located | NotLocated:
    """Find the passage ``quote`` in ``text``. Where the quote occurs more than once, the
    occurrence whose surroundings agree best with ``prefix`` and ``suffix`` is taken, if one
    agrees better than all the others."""
    if not quote:
        return NotLocated("missing")
    places = occurrences(text, quote)
    if not places:
        return NotLocated("missing")
    if len(places) == 1:
        return Located(places[0], places[0] + len(quote))
    scores = [
        _common_suffix(text[:place], prefix) + _common_prefix(text[place + len(quote) :], suffix)
        for place in places
    ]
    best = max(scores)
    if best == 0 or scores.count(best) > 1:
        return NotLocated("ambiguous")
    place = places[scores.index(best)]
    return Located(place, place + len(quote))
