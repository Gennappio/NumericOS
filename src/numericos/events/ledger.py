"""Builder for ledger rows. Every event names its actor, producer, severity and correlation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from numericos.core.enums import EventType, Severity
from numericos.core.ids import new_id
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Event

EVENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EventContext:
    """Who caused a mutation and how to correlate it; taken from request headers or the CLI."""

    actor: str
    correlation_id: str
    producer: str = "api"


def build_event(
    *,
    event_type: EventType,
    project_id: str,
    subject_id: str,
    payload: dict[str, Any],
    context: EventContext,
    severity: Severity = Severity.INFO,
) -> Event:
    return Event(
        event_id=new_id("evt"),
        project_id=project_id,
        type=event_type.value,
        subject_id=subject_id,
        actor=context.actor,
        producer=context.producer,
        severity=severity.value,
        correlation_id=context.correlation_id,
        schema_version=EVENT_SCHEMA_VERSION,
        payload=payload,
        timestamp_utc=utcnow(),
    )
