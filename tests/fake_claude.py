"""A stand-in for the Claude Code command line, for tests: the same flags and the same
stream-json records, no model and no network. Standard library only.

Directives in the prompt (one per line, anywhere in it) drive what it does:

    READ <path>            read the file (relative to the working directory) through a Read tool
    WRITE <path>::<text>   write the file through a Write tool; refused in read-only mode
    SLEEP <seconds>        wait before answering (to be stopped meanwhile)
    FAIL <text>            end with ``is_error`` true and that text
    EXIT <code>            leave with that exit code and no result record
    ECHO <text>            answer with that text instead of the default note

``--version`` prints a version line, as the real command does.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

VERSION = "9.9.9 (fake claude)"
MODEL = "fake-model"
COST = 0.0123

FLAGS_WITH_VALUE = {
    "--output-format",
    "--max-budget-usd",
    "--permission-mode",
    "--disallowedTools",
    "--allowedTools",
    "--resume",
    "--session-id",
    "--append-system-prompt",
    "--model",
    "--json-schema",
    "--max-turns",
}


def parse(argv: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {"flags": []}
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in FLAGS_WITH_VALUE:
            options[item] = argv[index + 1]
            index += 2
        else:
            options["flags"].append(item)
            index += 1
    return options


def emit(record: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


def main() -> int:
    argv = sys.argv[1:]
    if argv == ["--version"]:
        print(VERSION)
        return 0
    options = parse(argv)
    session_id = options.get("--resume") or options.get("--session-id") or str(uuid.uuid4())
    if "--fork-session" in options["flags"]:
        session_id = str(uuid.uuid4())
    mode = options.get("--permission-mode", "default")
    disallowed = set(options.get("--disallowedTools", "").split(",")) - {""}
    may_write = mode in ("acceptEdits", "bypassPermissions") and "Write" not in disallowed
    cwd = Path.cwd()
    model = options.get("--model") or MODEL
    prompt = sys.stdin.read()

    emit(
        {
            "type": "system",
            "subtype": "init",
            "session_id": session_id,
            "model": model,
            "effort": options.get("--effort"),
            "cwd": str(cwd),
            "permissionMode": mode,
            "argv": argv,
            "system_prompt": options.get("--append-system-prompt"),
        }
    )
    emit(
        {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed",
                "rateLimitType": "five_hour",
                "isUsingOverage": False,
                "unifiedWindows": {
                    "five_hour": {"utilization": 0.21, "resetsAt": 1791835200},
                    "seven_day": {"utilization": 0.04, "resetsAt": 1792429200},
                },
            },
        }
    )
    emit(assistant(session_id, [{"type": "text", "text": "Looking at the repository."}]))

    answer: str | None = None
    failure: str | None = None
    denials: list[dict[str, Any]] = []
    turns = 1
    for line in prompt.splitlines():
        word, _, rest = line.strip().partition(" ")
        if word == "READ":
            turns += 1
            call = tool_use("Read", {"file_path": str(cwd / rest)})
            emit(assistant(session_id, [call]))
            try:
                content, ok = (cwd / rest).read_text(), True
            except OSError as error:
                content, ok = str(error), False
            emit(tool_result(session_id, call["id"], content, ok))
        elif word == "WRITE":
            path, _, text = rest.partition("::")
            tool_input = {"file_path": str(cwd / path), "content": text}
            if may_write:
                turns += 1
                call = tool_use("Write", tool_input)
                emit(assistant(session_id, [call]))
                (cwd / path).write_text(text)
                emit(tool_result(session_id, call["id"], f"File written: {path}", True))
            else:
                denials.append({"tool_name": "Write", "tool_input": tool_input})
                emit(
                    assistant(
                        session_id,
                        [{"type": "text", "text": f"I was not allowed to write {path}."}],
                    )
                )
        elif word == "SLEEP":
            time.sleep(float(rest))
        elif word == "FAIL":
            failure = rest or "the fake agent was told to fail"
        elif word == "EXIT":
            sys.stderr.write("fake claude: leaving without an answer\n")
            sys.stderr.flush()
            return int(rest or 1)
        elif word == "ECHO":
            answer = rest

    first_line = next((line for line in prompt.splitlines() if line.strip()), "").strip()
    if answer is None:
        answer = (
            f"You asked: {first_line}\n\n"
            "The heat equation $u_t = \\alpha \\nabla^2 u$ is solved with an explicit scheme, "
            "which is stable when\n\n"
            "$$\\frac{\\alpha\\,\\Delta t}{\\Delta x^2} \\le \\frac{1}{2}.$$\n"
        )
    structured: Any | None = None
    if "--json-schema" in options:
        structured = {"echo": first_line}
        answer = json.dumps(structured)
    if failure is not None:
        answer = failure
    result = {
        "type": "result",
        "subtype": "success" if failure is None else "error_during_execution",
        "is_error": failure is not None,
        "result": answer,
        "session_id": session_id,
        "total_cost_usd": COST,
        "usage": {
            "input_tokens": 12,
            "output_tokens": 34,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 5,
        },
        "num_turns": turns,
        "duration_ms": 7,
        "permission_denials": denials,
        "modelUsage": {model: {"inputTokens": 12, "outputTokens": 34, "costUSD": COST}},
    }
    if structured is not None:
        result["structured_output"] = structured
    emit(result)
    return 1 if failure is not None else 0


def assistant(session_id: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "assistant",
        "session_id": session_id,
        "message": {"id": f"msg_{uuid.uuid4().hex[:8]}", "role": "assistant", "content": content},
    }


def tool_use(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_use",
        "id": f"toolu_{uuid.uuid4().hex[:12]}",
        "name": name,
        "input": tool_input,
    }


def tool_result(session_id: str, tool_use_id: str, content: str, ok: bool) -> dict[str, Any]:
    return {
        "type": "user",
        "session_id": session_id,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": not ok,
                }
            ],
        },
    }


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
