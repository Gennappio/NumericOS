"""What the agent is asked when a document is generated, and the shape of a structured answer.

Every prompt starts with a line that names the task: it tells the reader of a conversation what
kind of turn this was, and lets a stand-in for the agent answer in the right shape. The
researcher's own instructions come last, so that they have the final word.
"""

from __future__ import annotations

import json
from typing import Any

from numericos.core.enums import CardType, FileCategory, WorkflowStatus

THEORY = """[NumericOS task: theory]
Write the theory of this computational project as a short scientific paper, for a researcher \
who has not read the code.

Read the repository first: entry points, solvers, input files, existing documentation, and the \
images or plots it contains. Base every statement on what the code actually does; where the \
code and its documentation disagree, say so.

The document contains, in this order:
1. A title (level-1 heading) and a one-paragraph abstract.
2. The problem: what is modelled or computed, and the research question.
3. The mathematical model: governing equations, unknowns, parameters, domain, boundary and \
initial conditions.
4. The numerical method: discretisation in space and time and the algorithm step by step, with \
its formulas.
5. Properties: stability and accuracy conditions, conservation, complexity; what is \
established and what is only assumed.
6. From theory to code: a table mapping each element of the theory to the file and function \
that implements it.
7. Inputs and outputs: what the program reads and writes, and how to read the results.
8. Assumptions, limitations and open questions.

Rules:
- Markdown. Mathematics in LaTeX: $...$ inline, $$...$$ for displayed equations. Number the \
important equations with \\tag{n} and refer to them by number.
- Include figures that exist in the repository where they help, as Markdown images with a \
caption: ![caption](path/from/the/repository/root.png). Do not invent image files.
- Refer to files by their path relative to the repository root, in backticks.
- Do not modify any file.
- Your final answer is the document itself and nothing else: it starts with the level-1 heading.
"""

FILES = """[NumericOS task: file_description]
Describe each of the files listed below for a researcher who needs to understand this \
computational project. Read every file; look at the images. A binary file you cannot read is \
described from its name, its size and how the code produces or uses it.

For every file give:
- category: code, input (data or parameters the program reads), output (results the program \
writes), image, config, documentation or other;
- summary: one sentence of at most 25 words saying what the file is for;
- description: Markdown, 3 to 12 sentences or a short list: what it contains, its role in the \
project, what reads or writes it, its main functions, parameters or columns, and what a \
reader must know (units, formats, assumptions). Mathematics in LaTeX between $.

Use exactly the paths given below, one entry per path. Do not modify any file.

Files to describe:
"""

PLAN = """[NumericOS task: plan]
Propose the work plan of this project as cards of a Kanban board. Read the repository and the \
research question, then decide what should be done, in which order, and what is uncertain.

The columns are workflow status only (backlog, planned, active, review, completed, blocked): \
they say how far the work is, never whether a result is valid. Card types: task, hypothesis \
(a falsifiable claim to test), experiment (a run or a comparison to make), issue (something \
wrong or unclear), decision (a choice to take or record).

Give:
- rationale: Markdown, at most 10 sentences: why this plan and what it leaves out;
- cards: between 3 and 15. A new card has no id. To change a card that is already on the board \
(reword it, move it to another column) repeat its id; do not repeat cards you would leave as \
they are. Titles of at most 80 characters; the description says what to do and what "done" \
means.

Do not modify any file.
"""


CLARIFY = """[NumericOS task: clarify]
A researcher is reading {what} and asks for clarifications of specific passages. Answer every \
request, each on its own.

For each request write a clarification of that passage only: Markdown, 2 to 8 sentences, with \
a short derivation or a small example when that is what makes it clear; mathematics in LaTeX \
between $...$ or $$...$$. It is shown next to the passage: do not repeat the passage, do not \
rewrite the text around it, do not answer other requests in it. Read the code when you need it \
to be exact. If a request shows that the text or the code is wrong, say so plainly: the \
researcher can then ask for a change.

Do not modify any file.
"""

RESOLVE = """[NumericOS task: resolve]
A researcher read {what} and asks for the changes listed below. Carry them out as you would in \
a terminal session: read what you need, edit the files of the project directly, and decide \
yourself how to reconcile requests that conflict. A request you judge wrong or impossible is \
declined, with the reason. Nobody can answer a question during this turn.

A request may be about the code, about the text itself (it says something wrong, unclear or \
incomplete), or about both.
{rewriting}
For each request give:
- decision: applied or declined;
- summary: Markdown, 1 to 5 sentences: what you changed and where (files, functions), or why \
you declined.
"""

REWRITABLE = """When the text must change, because a request asks for it or because your \
changes to the code make a statement of it false, give the complete revised text in \
`document`: the same structure and style, changed only where needed. Otherwise leave \
`document` null.
"""

NOT_REWRITABLE = """The text is an answer that was already given: it is a record and is not \
rewritten. Leave `document` null and say in the summaries what is different now.
"""

DOCUMENT_START = "--- document start ---"
DOCUMENT_END = "--- document end ---"
REQUESTS = "Requests:"


def _text_block(what: str, title: str, markdown: str, question: str | None) -> str:
    asked = (
        f"The question it answered:\n--- question start ---\n{question.rstrip()}\n"
        "--- question end ---\n\n"
        if question
        else ""
    )
    return (
        f"{asked}The text ({what}; {title}):\n{DOCUMENT_START}\n{markdown.rstrip()}\n"
        f"{DOCUMENT_END}\n"
    )


def _requests(items: list[dict[str, str]]) -> str:
    """One numbered entry per comment. Strings are JSON so that each stays on one line."""
    lines = [REQUESTS]
    for number, item in enumerate(items, 1):
        around = f"{item['prefix']}[[{item['quote']}]]{item['suffix']}"
        lines += [
            f"{number}. id: {item['id']}",
            f"   passage: {json.dumps(item['quote'], ensure_ascii=False)}",
            f"   where (passage between [[ ]]): {json.dumps(around, ensure_ascii=False)}",
            f"   request: {json.dumps(item['body'], ensure_ascii=False)}",
        ]
    return "\n".join(lines) + "\n"


def clarify(
    *,
    what: str,
    title: str,
    markdown: str,
    question: str | None,
    items: list[dict[str, str]],
    first: bool,
    instructions: str,
) -> str:
    """The first turn of a session shows the text; later turns only add requests about it."""
    if first:
        head = f"{CLARIFY.format(what=what)}\n{_text_block(what, title, markdown, question)}"
    else:
        head = "[NumericOS task: clarify]\nMore requests about the same text, on the same terms.\n"
    return _with_instructions(f"{head}\n{_requests(items)}", instructions)


def resolve(
    *,
    what: str,
    title: str,
    markdown: str,
    question: str | None,
    items: list[dict[str, str]],
    first: bool,
    rewritable: bool,
    instructions: str,
) -> str:
    if first:
        rules = RESOLVE.format(what=what, rewriting=REWRITABLE if rewritable else NOT_REWRITABLE)
        head = f"{rules}\n{_text_block(what, title, markdown, question)}"
    else:
        head = (
            "[NumericOS task: resolve]\n"
            "More change requests about the same text, on the same terms.\n"
        )
    return _with_instructions(f"{head}\n{_requests(items)}", instructions)


def _project_lines(project_name: str, research_question: str) -> str:
    question = research_question.strip() or "not stated yet"
    return f"Project: {project_name}\nResearch question: {question}\n"


def _with_instructions(text: str, instructions: str) -> str:
    extra = instructions.strip()
    if not extra:
        return text
    return f"{text}\nAdditional instructions from the researcher:\n{extra}\n"


def theory(project_name: str, research_question: str, instructions: str) -> str:
    return _with_instructions(
        f"{THEORY}\n{_project_lines(project_name, research_question)}", instructions
    )


def files(paths: list[str], instructions: str) -> str:
    listing = "".join(f"- {path}\n" for path in paths)
    return _with_instructions(f"{FILES}{listing}", instructions)


def plan(
    project_name: str, research_question: str, cards: list[dict[str, Any]], instructions: str
) -> str:
    if cards:
        board = "".join(
            f"- [{card['id']}] ({card['type']}, {card['workflow_status']}) {card['title']}"
            + (
                f": {' '.join(str(card['description']).split())[:300]}"
                if card["description"]
                else ""
            )
            + "\n"
            for card in cards
        )
    else:
        board = "(the board is empty)\n"
    project = _project_lines(project_name, research_question)
    return _with_instructions(f"{PLAN}\n{project}\nCards on the board now:\n{board}", instructions)


FILES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            category.value
                            for category in FileCategory
                            if category is not FileCategory.DATA
                        ],
                    },
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["path", "category", "summary", "description"],
            },
        }
    },
    "required": ["files"],
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": ["string", "null"]},
                    "type": {"type": "string", "enum": [kind.value for kind in CardType]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": [status.value for status in WorkflowStatus],
                    },
                },
                "required": ["type", "title", "description", "status"],
            },
        },
    },
    "required": ["rationale", "cards"],
}

CLARIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "markdown": {"type": "string"}},
                "required": ["id", "markdown"],
            },
        }
    },
    "required": ["answers"],
}

RESOLVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["applied", "declined"]},
                    "summary": {"type": "string"},
                },
                "required": ["id", "decision", "summary"],
            },
        },
        "document": {"type": ["string", "null"]},
    },
    "required": ["results", "document"],
}
