"""Shapes shared by the API and the supervisor about turns, independent of any provider."""

from __future__ import annotations

from typing import Any

from numericos.agents.claude_code import SUGGESTED_POLICY
from numericos.persistence.models import AgentMessage, AgentSession


def choice_for(
    session: AgentSession, policy_tasks: dict[str, Any] | None
) -> tuple[str | None, str | None]:
    """The model and effort a turn of ``session`` is started with: the session's own choice,
    else the policy's for its task (the suggested policy while none was saved), else nothing
    (the provider's default)."""
    chosen = (policy_tasks if policy_tasks is not None else SUGGESTED_POLICY).get(
        session.task
    ) or {}
    model = session.model or chosen.get("model")
    effort = session.effort or chosen.get("effort")
    return (model if isinstance(model, str) and model else None), (
        effort if isinstance(effort, str) and effort else None
    )


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
