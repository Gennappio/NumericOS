"""The Claude Code adapter: the argument vector of a turn and the reading of its stream."""

from __future__ import annotations

import json
from pathlib import Path

from numericos.agents import claude_code
from numericos.core.agents import ACTIVITY_LIMIT
from numericos.core.enums import PermissionMode

SESSION = "0d5a2c4e-1b2f-4c6d-9e8f-123456789abc"


def argv(**overrides: object) -> list[str]:
    options: dict[str, object] = {
        "session_id": SESSION,
        "resume": False,
        "mode": PermissionMode.EDIT,
        "system": "You are inside NumericOS.",
        "max_budget_usd": 2.5,
    }
    options.update(overrides)
    return claude_code.command(["claude"], **options)  # type: ignore[arg-type]


def test_a_first_turn_names_its_session_and_a_later_one_resumes_it() -> None:
    first = argv()
    later = argv(resume=True)
    forked = argv(resume=True, fork=True)

    assert first[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    assert first[first.index("--max-budget-usd") + 1] == "2.5"
    assert first[first.index("--session-id") + 1] == SESSION
    assert "--resume" not in first
    assert later[later.index("--resume") + 1] == SESSION
    assert "--session-id" not in later
    assert "--fork-session" not in later
    assert "--fork-session" in forked
    # The system prompt travels with every launch; Claude Code keeps the one of the first.
    assert first[first.index("--append-system-prompt") + 1] == "You are inside NumericOS."


def test_permission_modes_map_to_flags_the_provider_enforces() -> None:
    read_only = argv(mode=PermissionMode.READ_ONLY)
    edit = argv(mode=PermissionMode.EDIT)
    full = argv(mode=PermissionMode.FULL)

    assert read_only[read_only.index("--permission-mode") + 1] == "default"
    assert read_only[read_only.index("--disallowedTools") + 1] == (
        "Edit,Write,MultiEdit,NotebookEdit,Bash"
    )
    assert edit[edit.index("--permission-mode") + 1] == "acceptEdits"
    assert "--disallowedTools" not in edit
    assert full[full.index("--permission-mode") + 1] == "bypassPermissions"


def test_model_effort_and_schema_are_passed_only_when_asked() -> None:
    plain = argv()
    specific = argv(model="claude-haiku-5-5", effort="low", json_schema={"type": "object"})

    assert "--model" not in plain and "--effort" not in plain and "--json-schema" not in plain
    assert specific[specific.index("--model") + 1] == "claude-haiku-5-5"
    assert specific[specific.index("--effort") + 1] == "low"
    assert json.loads(specific[specific.index("--json-schema") + 1]) == {"type": "object"}


def test_the_models_offered_are_full_names_and_the_efforts_the_levels_of_the_flag() -> None:
    assert [choice.id for choice in claude_code.MODELS] == [
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
    ]
    assert claude_code.EFFORTS == ["low", "medium", "high", "xhigh", "max"]


def test_the_use_of_the_plan_is_taken_from_the_rate_limit_record() -> None:
    progress = claude_code.Progress()

    progress.fold(
        record(
            "rate_limit_event",
            rate_limit_info={
                "status": "allowed",
                "isUsingOverage": False,
                "unifiedWindows": {
                    "five_hour": {"utilization": 0.49, "resetsAt": 1791835200},
                    "seven_day": {"utilization": 0.04, "resetsAt": 1792429200},
                },
            },
        ),
        Path("/repo"),
    )
    progress.fold(record("rate_limit_event", rate_limit_info={"status": "allowed"}), Path("/repo"))

    assert progress.plan_usage is not None
    assert progress.plan_usage.five_hour is not None
    assert progress.plan_usage.five_hour.utilization == 0.49
    assert progress.plan_usage.seven_day is not None
    assert progress.plan_usage.seven_day.resets_at == 1792429200
    assert progress.plan_usage.using_overage is False


def test_the_environment_hides_that_a_claude_session_may_be_running(
    monkeypatch: object,
) -> None:
    import os

    os.environ["CLAUDECODE"] = "1"
    try:
        env = claude_code.environment({"NUMERICOS_MESSAGE_ID": "msg_1"})
    finally:
        del os.environ["CLAUDECODE"]

    assert "CLAUDECODE" not in env
    assert env["NUMERICOS_MESSAGE_ID"] == "msg_1"
    assert env["PATH"] == os.environ["PATH"]


def test_tool_summaries_say_what_the_tool_was_pointed_at() -> None:
    assert claude_code.summarize_tool("Read", {"file_path": "/repo/solver.py"}) == "/repo/solver.py"
    assert (
        claude_code.summarize_tool("Read", {"file_path": "/repo/solver.py"}, Path("/repo"))
        == "solver.py"
    )
    assert claude_code.summarize_tool("Bash", {"command": "pytest -q\necho done"}) == "pytest -q"
    assert claude_code.summarize_tool("Grep", {"pattern": "dt", "path": "src"}) == "dt in src"
    assert claude_code.summarize_tool("Glob", {"pattern": "**/*.py"}) == "**/*.py"
    assert claude_code.summarize_tool("StructuredOutput", {"x": 1}) == "the structured answer"
    assert claude_code.summarize_tool("Mystery", {"a": "b"}) == '{"a": "b"}'
    long = claude_code.summarize_tool("Bash", {"command": "x" * 500})
    assert len(long) == 200 and long.endswith("…")


def test_files_the_agent_read_or_changed_are_relative_to_the_project() -> None:
    cwd = Path("/repo")

    assert claude_code.touched_file("Read", {"file_path": "/repo/src/a.py"}, cwd) == (
        "read",
        "src/a.py",
    )
    assert claude_code.touched_file("Edit", {"file_path": "/repo/b.py"}, cwd) == ("written", "b.py")
    assert claude_code.touched_file("Write", {"file_path": "/elsewhere/c"}, cwd) == (
        "written",
        "/elsewhere/c",
    )
    assert claude_code.touched_file("Bash", {"command": "ls"}, cwd) is None
    assert claude_code.touched_file("Read", {"file_path": ""}, cwd) is None


def record(kind: str, **fields: object) -> dict[str, object]:
    return {"type": kind, **fields}


def test_the_stream_is_folded_into_activity_files_and_a_result() -> None:
    cwd = Path("/repo")
    progress = claude_code.Progress()
    stream = [
        record("system", subtype="init", session_id=SESSION, model="claude-x"),
        record("rate_limit_event", rate_limit_info={}),
        record(
            "assistant",
            message={"content": [{"type": "text", "text": "I'll read the solver first."}]},
        ),
        record(
            "assistant",
            message={
                "content": [
                    {"type": "thinking", "thinking": "private"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Read",
                        "input": {"file_path": "/repo/solver.py"},
                    },
                ]
            },
        ),
        record(
            "user",
            message={
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "..."}]
            },
        ),
        record(
            "assistant",
            message={
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "Edit",
                        "input": {"file_path": "/repo/solver.py"},
                    }
                ]
            },
        ),
        record(
            "user",
            message={
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_2",
                        "content": "refused",
                        "is_error": True,
                    }
                ]
            },
        ),
        record(
            "result",
            subtype="success",
            is_error=False,
            result="The scheme is explicit.",
            session_id=SESSION,
            total_cost_usd=0.31,
            usage={"input_tokens": 2, "output_tokens": 4, "cache_read_input_tokens": 21857},
            num_turns=3,
            duration_ms=2247,
            permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "pytest"}}],
        ),
    ]

    for item in stream:
        progress.fold(item, cwd, now=1.0)

    assert (progress.model, progress.native_session_id) == ("claude-x", SESSION)
    assert [item.kind for item in progress.activity] == ["text", "tool", "tool"]
    assert progress.activity[0].text == "I'll read the solver first."
    read, edit = progress.activity[1].tool, progress.activity[2].tool
    assert read is not None and (read.name, read.summary, read.ok) == ("Read", "solver.py", True)
    assert edit is not None and (edit.name, edit.ok) == ("Edit", False)
    assert progress.files_read == ["solver.py"]
    assert progress.files_written == ["solver.py"]
    assert progress.result is not None
    assert progress.result.text == "The scheme is explicit."
    assert progress.result.cost_usd == 0.31
    assert progress.result.usage is not None
    assert progress.result.usage.cache_read_input_tokens == 21857
    assert progress.result.usage.cache_creation_input_tokens == 0
    assert progress.result.num_turns == 3
    assert [(d.tool_name, d.summary) for d in progress.result.permission_denials] == [
        ("Bash", "pytest")
    ]
    assert not progress.dropped


def test_a_structured_answer_is_kept_as_data_and_a_failure_as_such() -> None:
    progress = claude_code.Progress()

    progress.fold(
        record(
            "result",
            subtype="error_during_execution",
            is_error=True,
            result='{"answers": []}',
            structured_output={"answers": []},
        ),
        Path("/repo"),
    )

    assert progress.result is not None
    assert progress.result.is_error
    assert progress.result.subtype == "error_during_execution"
    assert progress.result.structured_output == {"answers": []}


def test_activity_is_bounded_and_the_rest_counted() -> None:
    progress = claude_code.Progress()
    text = record("assistant", message={"content": [{"type": "text", "text": "x"}]})

    for _ in range(ACTIVITY_LIMIT + 7):
        progress.fold(text, Path("/repo"), now=0.0)

    assert len(progress.activity) == ACTIVITY_LIMIT
    assert progress.dropped == 7


def test_the_mode_note_and_system_prompt_say_what_the_agent_may_do() -> None:
    system = claude_code.system_prompt("Heat 2D", "")
    assert "project 'Heat 2D'" in system
    assert "not stated yet" in system
    assert "read_only" in claude_code.mode_note(PermissionMode.READ_ONLY)
    assert "refused" in claude_code.mode_note(PermissionMode.EDIT)
    assert "run commands" in claude_code.mode_note(PermissionMode.FULL)
