"""The Claude Code command line as an agent adapter.

``claude -p`` reads the prompt from standard input and, with ``--output-format stream-json
--verbose``, writes one JSON record per line: the session (``system``/``init``), every message
of the model with its content blocks (``assistant``: text, tool uses; ``user``: tool results)
and a final ``result`` with the answer, the cost and what the permission mode refused. This
module builds the argument vector and folds those records into provider-neutral progress.
Nothing here starts a process.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from numericos.core.agents import (
    ACTIVITY_LIMIT,
    SUMMARY_LIMIT,
    TEXT_LIMIT,
    ActivityItem,
    ModelChoice,
    PermissionDenial,
    PlanUsage,
    ToolCall,
    TurnResult,
    TurnUsage,
    WindowUsage,
)
from numericos.core.enums import PermissionMode

#: Models Claude Code can be asked for (`--model` takes a full name). The notes come from
#: turns measured on 2026-10-12: a trivial turn consumed about 0.31 USD-equivalent with Fable
#: and 0.0025 with Haiku, both mostly for the system prompt of the first turn.
MODELS: list[ModelChoice] = [
    ModelChoice(id="claude-fable-5-1", label="Fable 5.1", note="most capable; the heaviest"),
    ModelChoice(id="claude-opus-5-5", label="Opus 5.5", note="capable; heavy"),
    ModelChoice(id="claude-sonnet-5-5", label="Sonnet 5.5", note="fast; a fraction of Fable"),
    ModelChoice(
        id="claude-haiku-5-5",
        label="Haiku 5.5",
        note="lightest: about 1% of Fable on a trivial turn",
    ),
]

#: Effort levels of `--effort`, lightest first.
EFFORTS: list[str] = ["low", "medium", "high", "xhigh", "max"]

#: What a project starts with before its policy is saved: the tasks that are many small turns,
#: or a short structured answer, do not need the heaviest model. The others are left to the
#: user's own Claude Code settings.
SUGGESTED_POLICY: dict[str, dict[str, str | None]] = {
    "file_description": {"model": "claude-sonnet-5-5", "effort": "low"},
    "pipeline": {"model": "claude-sonnet-5-5", "effort": "medium"},
    "plan": {"model": "claude-sonnet-5-5", "effort": "medium"},
}

#: How each permission mode is asked of Claude Code. ``default`` mode in a non-interactive
#: session refuses every tool that would have asked for confirmation; the explicit list makes
#: the refusal of edits and commands independent of the user's own settings.
PERMISSION_FLAGS: dict[PermissionMode, list[str]] = {
    PermissionMode.READ_ONLY: [
        "--permission-mode",
        "default",
        "--disallowedTools",
        "Edit,Write,MultiEdit,NotebookEdit,Bash",
    ],
    PermissionMode.EDIT: ["--permission-mode", "acceptEdits"],
    PermissionMode.FULL: ["--permission-mode", "bypassPermissions"],
}

MODE_SENTENCE: dict[PermissionMode, str] = {
    PermissionMode.READ_ONLY: (
        "You may read the repository. Editing files and running commands is refused in this "
        "session: describe what you would change instead of trying."
    ),
    PermissionMode.EDIT: (
        "You may read and edit files. Running commands is refused in this session: say which "
        "command the person should run instead of trying."
    ),
    PermissionMode.FULL: "You may read and edit files and run commands.",
}

#: Variables that mark a running Claude Code session; a turn must start as a fresh one.
NESTING_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")

WRITING_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})


def system_prompt(project_name: str, research_question: str) -> str:
    """Recorded by Claude Code with the session at its first turn; it does not change later,
    so the permission mode, which may, travels with each turn (``mode_note``)."""
    question = research_question.strip() or "not stated yet"
    return (
        "You are working inside NumericOS, a workbench for computational research, on the "
        f"project {project_name!r}. Research question: {question}\n"
        "The current directory is the project's repository. Answer in Markdown; write "
        "mathematics in LaTeX between $ (inline) or $$ (display). Nobody can answer a question "
        "of yours during this turn: state your assumptions and go on. Each prompt ends with a "
        "note from NumericOS saying what you may do during that turn."
    )


def mode_note(mode: PermissionMode) -> str:
    return f"(NumericOS, permission mode {mode.value}: {MODE_SENTENCE[mode]})"


def command(
    base: list[str],
    *,
    session_id: str,
    resume: bool,
    mode: PermissionMode,
    system: str,
    max_budget_usd: float,
    model: str | None = None,
    effort: str | None = None,
    fork: bool = False,
    json_schema: dict[str, Any] | None = None,
    add_dirs: list[str] | None = None,
) -> list[str]:
    """The argument vector of one turn. The prompt itself goes to standard input."""
    argv = [
        *base,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-budget-usd",
        f"{max_budget_usd:g}",
        *PERMISSION_FLAGS[mode],
    ]
    if resume:
        argv += ["--resume", session_id]
        if fork:
            argv.append("--fork-session")
    else:
        argv += ["--session-id", session_id]
    # Recorded by Claude Code at the first turn and sent again on every resume.
    argv += ["--append-system-prompt", system]
    if model:
        argv += ["--model", model]
    if effort:
        argv += ["--effort", effort]
    if json_schema is not None:
        argv += ["--json-schema", json.dumps(json_schema, separators=(",", ":"))]
    # Directories outside the working directory the agent may use. Last: the flag takes any
    # number of values, and nothing that follows it must be taken for one.
    if add_dirs:
        argv += ["--add-dir", *add_dirs]
    return argv


def environment(extra: dict[str, str]) -> dict[str, str]:
    """The user's environment (Claude Code finds its login there), minus the marks of a running
    session, plus what identifies the turn to hooks and tools."""
    env = {name: value for name, value in os.environ.items() if name not in NESTING_MARKERS}
    env.update(extra)
    return env


def _clip(text: str, limit: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def summarize_tool(name: str, tool_input: Any, cwd: Path | None = None) -> str:
    """One line that says what the tool was pointed at; a file inside ``cwd`` by its relative
    path."""
    data = tool_input if isinstance(tool_input, dict) else {}
    if name in WRITING_TOOLS or name == "Read":
        text = data.get("file_path") or data.get("notebook_path") or ""
        if cwd is not None and isinstance(text, str) and text:
            touched = touched_file(name, data, cwd)
            text = touched[1] if touched else text
    elif name == "Bash":
        text = str(data.get("command", "")).splitlines()[0] if data.get("command") else ""
    elif name in ("Grep", "Glob"):
        pattern, path = data.get("pattern", ""), data.get("path")
        text = f"{pattern} in {path}" if path else str(pattern)
    elif name == "WebFetch":
        text = str(data.get("url", ""))
    elif name == "WebSearch":
        text = str(data.get("query", ""))
    elif name in ("Task", "Agent"):
        text = str(data.get("description", ""))
    elif name == "StructuredOutput":
        text = "the structured answer"
    else:
        text = json.dumps(tool_input, sort_keys=True) if tool_input else ""
    return _clip(str(text), SUMMARY_LIMIT)


def touched_file(name: str, tool_input: Any, cwd: Path) -> tuple[str, str] | None:
    """``("read" | "written", path)`` for a tool that reads or changes one file; paths inside
    the working directory are made relative to it."""
    if not isinstance(tool_input, dict):
        return None
    if name == "Read":
        kind = "read"
    elif name in WRITING_TOOLS:
        kind = "written"
    else:
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    try:
        return kind, str(path.relative_to(cwd))
    except ValueError:
        return kind, str(path)


@dataclass
class Progress:
    """What the records read so far say about a turn."""

    model: str | None = None
    native_session_id: str | None = None
    activity: list[ActivityItem] = field(default_factory=list)
    dropped: int = 0
    files_read: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    #: The last report of the account's plan windows, if the provider sent one.
    plan_usage: PlanUsage | None = None
    result: TurnResult | None = None

    def _append(self, item: ActivityItem) -> None:
        if len(self.activity) >= ACTIVITY_LIMIT:
            self.dropped += 1
            return
        self.activity.append(item)

    def _note_file(self, name: str, tool_input: Any, cwd: Path) -> None:
        touched = touched_file(name, tool_input, cwd)
        if touched is None:
            return
        kind, path = touched
        target = self.files_read if kind == "read" else self.files_written
        if path not in target:
            target.append(path)

    def fold(self, record: dict[str, Any], cwd: Path, now: float | None = None) -> None:
        """Interpret one record of the stream."""
        at = time.time() if now is None else now
        kind = record.get("type")
        if kind == "system":
            if record.get("subtype") == "init":
                self.model = record.get("model") or self.model
                self.native_session_id = record.get("session_id") or self.native_session_id
            return
        if kind == "assistant":
            for block in record.get("message", {}).get("content") or []:
                if block.get("type") == "text":
                    text = str(block.get("text", "")).strip()
                    if text:
                        self._append(
                            ActivityItem(kind="text", at=at, text=_clip_block(text, TEXT_LIMIT))
                        )
                elif block.get("type") == "tool_use":
                    name = str(block.get("name", "?"))
                    tool_input = block.get("input")
                    self._append(
                        ActivityItem(
                            kind="tool",
                            at=at,
                            tool=ToolCall(
                                id=str(block.get("id", "")),
                                name=name,
                                summary=summarize_tool(name, tool_input, cwd),
                            ),
                        )
                    )
                    self._note_file(name, tool_input, cwd)
            return
        if kind == "user":
            for block in record.get("message", {}).get("content") or []:
                if block.get("type") == "tool_result":
                    self._resolve(str(block.get("tool_use_id", "")), not block.get("is_error"))
            return
        if kind == "rate_limit_event":
            self.plan_usage = _plan_usage(record.get("rate_limit_info")) or self.plan_usage
            return
        if kind == "result":
            self.result = _result(record, cwd)

    def _resolve(self, tool_use_id: str, ok: bool) -> None:
        for item in reversed(self.activity):
            if item.tool is not None and item.tool.id == tool_use_id:
                item.tool.ok = ok
                return


def _clip_block(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _plan_usage(info: Any) -> PlanUsage | None:
    """The plan windows of a ``rate_limit_event``: ``unifiedWindows.five_hour`` and
    ``seven_day``, each with ``utilization`` (0 to 1) and ``resetsAt``."""
    if not isinstance(info, dict):
        return None
    windows = info.get("unifiedWindows")
    if not isinstance(windows, dict):
        return None

    def window(name: str) -> WindowUsage | None:
        data = windows.get(name)
        if not isinstance(data, dict) or "utilization" not in data:
            return None
        return WindowUsage(
            utilization=float(data["utilization"]), resets_at=float(data.get("resetsAt", 0))
        )

    return PlanUsage(
        five_hour=window("five_hour"),
        seven_day=window("seven_day"),
        using_overage=bool(info.get("isUsingOverage")),
    )


def _result(record: dict[str, Any], cwd: Path) -> TurnResult:
    usage = record.get("usage")
    denials = [
        PermissionDenial(
            tool_name=str(denial.get("tool_name", "?")),
            summary=summarize_tool(
                str(denial.get("tool_name", "?")), denial.get("tool_input"), cwd
            ),
        )
        for denial in record.get("permission_denials") or []
        if isinstance(denial, dict)
    ]
    answer = record.get("result")
    return TurnResult(
        is_error=bool(record.get("is_error")),
        subtype=str(record.get("subtype", "unknown")),
        text=answer if isinstance(answer, str) else "",
        structured_output=record.get("structured_output"),
        cost_usd=record.get("total_cost_usd"),
        usage=TurnUsage.model_validate({key: usage.get(key, 0) for key in TurnUsage.model_fields})
        if isinstance(usage, dict)
        else None,
        num_turns=record.get("num_turns"),
        duration_ms=record.get("duration_ms"),
        permission_denials=denials,
        native_session_id=record.get("session_id"),
    )
