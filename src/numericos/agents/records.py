"""Shapes shared by the API and the supervisor about turns, independent of any provider."""

from __future__ import annotations

from typing import Any

from numericos.persistence.models import AgentMessage


def finished_payload(message: AgentMessage) -> dict[str, Any]:
    """What the ledger says when a turn ends, whoever ends it."""
    return {
        "status": message.status,
        "status_reason": message.status_reason,
        "session_id": message.session_id,
        "model": message.model,
        "cost_usd": message.cost_usd,
        "num_turns": message.num_turns,
        "files_written": len(message.files_written or []),
        "permission_denials": len(message.permission_denials or []),
        "agent_started": message.started_at is not None,
    }
