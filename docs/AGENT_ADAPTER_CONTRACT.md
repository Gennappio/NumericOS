# NumericOS — AgentAdapter & Normalized Events Contract

**Goal:** replaceable coding agent harnesses, without turning NumericOS into another generic coding agent. Provider-specific protocol details stay in adapters; runtime decisions, scientific state and GUI consume normalized events.

## Proposed contract (Python pseudotypes, not executable package yet)

```python
from typing import Protocol, AsyncIterator

class AgentAdapter(Protocol):
    async def capabilities(self) -> dict: ...
    async def start_session(self, project_id: str, config: dict) -> str: ...
    async def install_skills(self, session_id: str, manifest: dict) -> dict: ...
    async def prompt(self, session_id: str, content: str, context_snapshot_id: str | None = None) -> str: ...
    async def events(self, session_id: str, cursor: str | None = None) -> AsyncIterator[dict]: ...
    async def interrupt(self, session_id: str) -> dict: ...
    async def resume(self, session_id: str) -> dict: ...
    async def state(self, session_id: str) -> dict: ...
    async def close(self, session_id: str) -> None: ...
```

Treat `resume` and event replay as optional provider capabilities; NumericOS can persist its own event ledger and start a new agent session if native resume isn't available. Never claim native session resume if only creating a replacement session.

## Capability negotiation

Report explicitly: `stream_text`, `stream_tool_calls`, `resume_native_session`, `interrupt_turn`, `approvals`, `structured_output`, `skill_discovery`, `skill_explicit_load`, `subagent_support`, `session_import_export`, `provider_auth_mode`. Use known/unknown/unsupported instead of invented booleans for unverified features. Include adapter/provider version and evidence link for tests.

## Normalized event categories

```json
{
  "event_id": "e-001",
  "project_id": "p-001",
  "agent_session_id": "as-001",
  "provider": "codex",
  "native_session_id": "provider-specific",
  "turn_id": "t-001",
  "sequence": 17,
  "timestamp_utc": "2026-10-09T16:00:00Z",
  "type": "AGENT_TOOL_STARTED",
  "payload": {"tool_name": "shell", "tool_call_id": "call-003"},
  "correlation_id": "research-001"
}
```

Categories: `SESSION_STARTED`, `AGENT_TURN_STARTED`, `TEXT_DELTA`, `MESSAGE_FINALIZED`, `AGENT_TOOL_STARTED`, `AGENT_TOOL_COMPLETED`, `APPROVAL_REQUESTED`, `APPROVAL_RESOLVED`, `SKILLS_ACTIVATED`, `INTERRUPTED`, `SESSION_DISCONNECTED`, `SESSION_FINISHED`, `ADAPTER_ERROR`. Full event payloads must be compact and redact secrets; persist before UI fanout. An event describes an observed or explicitly reported action, not the model's hidden chain of thought.

## Provider rollout

- **M1:** choose one real adapter. Default decision: Codex App Server because it is designed for embedded clients. During spike verify installed release, session lifecycle, app-server framing, event payloads, approval routing, agent skill paths and interruption. If unsupported/blocker, record ADR and use Claude Agent SDK or Pi RPC with the SAME contract.
- **M5:** add at least one second real adapter and smoke-test parity of session lifecycle, skill discovery, selected project context, interruption and honest feature compatibility. Claude Agent SDK and Pi RPC are preferred targets; OpenCode is optional.
- Provider policy, license/auth and costs differ; never store tokens in event log. Local-first does not exempt a product from vendor platform terms.

## Required testing

- Deterministic fake adapter for unit/contract tests (no API cost), real opt-in provider smoke test for at least one integration.
- Stream actual text/tool events, abort mid-turn, process crash, reconnect and replay NumericOS persisted events.
- Skill load receipt with exact content digest and a provider discovery verification. UI flags unsupported native capabilities instead of silently using emulation.
- Thread Ask creates an isolated provider context, no mutation of primary session's message history.
- Provider errors are typed, the GUI and CLI report them honestly and do not forge a completed message/run.
