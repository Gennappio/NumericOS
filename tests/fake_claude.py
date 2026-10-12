"""A stand-in for the Claude Code command line, for tests: the same flags and the same
stream-json records, no model and no network. Standard library only.

Directives in the prompt (one per line, anywhere in it) drive what it does:

    READ <path>            read the file (relative to the working directory) through a Read tool
    WRITE <path>::<text>   write the file through a Write tool; refused in read-only mode
    SCRATCH <name>::<text> write the file in the scratch folder NumericOS names in the
                           environment, as an agent that keeps the repository clean does
    OMIT <path or id>      leave that file, or that request, out of a structured answer
    DECLINE <id>::<why>    decline that change request instead of applying it
    REPLACE <old>=><new>   give the text with that replacement as the revised document
    JSON <json>            give exactly this as the structured answer
    SLEEP <seconds>        wait before answering (to be stopped meanwhile)
    FAIL <text>            end with ``is_error`` true and that text
    EXIT <code>            leave with that exit code and no result record
    ECHO <text>            answer with that text instead of the default note

``--version`` prints a version line, as the real command does.

A prompt that starts with a NumericOS task line is answered in the shape of that task: the
theory as a short paper, files with one entry per listed path (the first with an absolute
path, as the real agent gives them), a plan with two cards, one answer per clarification
request, one decision per change request.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

THEORY = """# Explicit scheme for the 2D heat equation

**Abstract.** The project integrates the heat equation on the unit square with an explicit
finite-difference scheme and studies when it is stable.

## Mathematical model

The temperature $u(x, y, t)$ obeys

$$\\frac{\\partial u}{\\partial t} = \\alpha \\nabla^2 u \\tag{1}$$

with homogeneous Dirichlet boundary conditions.

## Numerical method

Forward Euler in time and central differences in space; equation (1) becomes an update that
is stable when $\\alpha\\,\\Delta t / \\Delta x^2 \\le 1/4$.

![The grid of the solver](docs/grid.png)

## From theory to code

| Element | File |
| --- | --- |
| update of (1) | `examples/heat2d-python/heat2d.py` |
"""

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
    omitted: set[str] = set()
    declined: dict[str, str] = {}
    replacements: list[tuple[str, str]] = []
    forced: Any | None = None
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
                (cwd / path).parent.mkdir(parents=True, exist_ok=True)
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
        elif word == "SCRATCH" and may_write:
            name, _, text = rest.partition("::")
            target = Path(os.environ["NUMERICOS_SCRATCH_DIR"]) / name
            turns += 1
            call = tool_use("Write", {"file_path": str(target), "content": text})
            emit(assistant(session_id, [call]))
            target.write_text(text)
            emit(tool_result(session_id, call["id"], f"File written: {target}", True))
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
        elif word == "OMIT":
            omitted.add(rest)
        elif word == "DECLINE":
            request_id, _, why = rest.partition("::")
            declined[request_id] = why or "not a good idea"
        elif word == "REPLACE":
            old, _, new = rest.partition("=>")
            replacements.append((old, new))
        elif word == "JSON":
            forced = json.loads(rest)

    first_line = next((line for line in prompt.splitlines() if line.strip()), "").strip()
    task = (
        first_line.removeprefix("[NumericOS task: ").removesuffix("]")
        if first_line.startswith("[NumericOS task: ")
        else None
    )
    if answer is None and task == "theory":
        answer = THEORY
    if answer is None:
        answer = (
            f"You asked: {first_line}\n\n"
            "The heat equation $u_t = \\alpha \\nabla^2 u$ is solved with an explicit scheme, "
            "which is stable when\n\n"
            "$$\\frac{\\alpha\\,\\Delta t}{\\Delta x^2} \\le \\frac{1}{2}.$$\n"
        )
    structured: Any | None = None
    if "--json-schema" in options:
        if forced is not None:
            structured = forced
        elif task == "file_description":
            listed = [
                line[2:]
                for line in prompt.split("Files to describe:\n", 1)[1].splitlines()
                if line.startswith("- ")
            ]
            entries = []
            for index, path in enumerate(listed):
                turns += 1
                call = tool_use("Read", {"file_path": str(cwd / path)})
                emit(assistant(session_id, [call]))
                emit(tool_result(session_id, call["id"], "...", (cwd / path).is_file()))
                if path in omitted:
                    continue
                entries.append(
                    {
                        "path": str(cwd / path) if index == 0 else path,
                        "category": "image" if path.endswith(".png") else "code",
                        "summary": f"Fake summary of {path}.",
                        "description": (
                            f"`{path}` holds $u_t = \\alpha \\nabla^2 u$.\n\n- read by the solver"
                        ),
                    }
                )
            structured = {"files": entries}
        elif task in ("clarify", "resolve"):
            requests = [
                (line.split("id: ", 1)[1], lines[index + 1].split("passage: ", 1)[1])
                for lines in [prompt.splitlines()]
                for index, line in enumerate(lines)
                if line[:1].isdigit() and ". id: " in line
            ]
            kept = [
                (request_id, passage)
                for request_id, passage in requests
                if request_id not in omitted
            ]
            if task == "clarify":
                structured = {
                    "answers": [
                        {
                            "id": request_id,
                            "markdown": (
                                f"About {passage}: the bound comes from "
                                "$|1 - 4r| \\le 1$, hence $r \\le 1/2$."
                            ),
                        }
                        for request_id, passage in kept
                    ]
                }
            else:
                document = None
                if replacements and "--- document start ---\n" in prompt:
                    document = prompt.split("--- document start ---\n", 1)[1].split(
                        "\n--- document end ---", 1
                    )[0]
                    for old, new in replacements:
                        document = document.replace(old, new)
                structured = {
                    "results": [
                        {
                            "id": request_id,
                            "decision": "declined" if request_id in declined else "applied",
                            "summary": declined.get(request_id)
                            or f"Changed what {passage} says, in `heat2d.py`.",
                        }
                        for request_id, passage in kept
                    ],
                    "document": document,
                }
        elif task == "plan":
            structured = {
                "rationale": "Check stability **first**, then accuracy.",
                "cards": [
                    {
                        "type": "experiment",
                        "title": "Run the stability sweep",
                        "description": "Vary dt across the CFL limit. Done when both sides ran.",
                        "status": "planned",
                    },
                    {
                        "type": "hypothesis",
                        "title": "The scheme is first order in time",
                        "description": "Halving dt halves the error.",
                        "status": "backlog",
                    },
                ],
            }
        else:
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
