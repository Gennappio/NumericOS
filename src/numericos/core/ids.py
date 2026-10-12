"""Typed identifiers ``<prefix>_<ULID>``.

ULIDs are generated from UTC milliseconds plus randomness: sortable, locale-independent and
never influenced by the host timezone. The prefix makes IDs self-describing in logs and APIs.
"""

from __future__ import annotations

import re

from ulid import ULID

#: Prefixes in use. Reserved for later milestones (not yet persisted): ``res`` (research),
#: ``ann`` (annotation), ``ctx`` (context snapshot).
PREFIXES: dict[str, str] = {
    "project": "prj",
    "card": "card",
    "event": "evt",
    "correlation": "cor",
    "hypothesis": "hyp",
    "experiment": "exp",
    "run": "run",
    "worker": "wrk",
    "artifact": "art",
    "metric_series": "ser",
    "agent_session": "ases",
    "message": "msg",
}

ID_PATTERN = re.compile(r"^[a-z]{2,6}_[0-9A-HJKMNP-TV-Z]{26}$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def is_valid_id(value: str) -> bool:
    return ID_PATTERN.match(value) is not None
