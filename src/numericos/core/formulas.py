"""Formulas in Markdown that arrived inside JSON.

A structured answer of the agent is JSON, and its texts are Markdown with LaTeX. In JSON a
backslash is written twice; a model sometimes escapes it once more, and the text then reads
``$\\\\alpha$`` where ``$\\alpha$`` was meant: two backslashes before a command, which LaTeX
takes for a line break followed by a word. Observed with Claude Code on 2026-10-13, in some
strings of an answer and not in others.

``repair_formulas`` undoes exactly that and nothing else: only inside ``$...$`` and
``$$...$$``, only outside code, and only in a formula in which every backslash is doubled and
at least one pair stands before a letter. A formula that has a single backslash anywhere is
written normally, line breaks and all, and is left as it is.
"""

from __future__ import annotations

import re

#: Fenced blocks and code spans: what is in them is shown as written, never repaired.
_CODE = re.compile(r"(```.*?```|~~~.*?~~~|`[^`\n]*`)", re.DOTALL)
#: A displayed formula (it may run over lines), or one inside a line.
_FORMULA = re.compile(r"\$\$.+?\$\$|\$[^$\n]+?\$", re.DOTALL)
_BACKSLASHES = re.compile(r"\\+")
_PAIR_BEFORE_LETTER = re.compile(r"\\\\[A-Za-z]")


def _repair(formula: str) -> str:
    runs = _BACKSLASHES.findall(formula)
    doubled = bool(runs) and all(len(run) % 2 == 0 for run in runs)
    if not doubled or not _PAIR_BEFORE_LETTER.search(formula):
        return formula
    return formula.replace("\\\\", "\\")


def repair_formulas(markdown: str) -> str:
    """``markdown`` with the formulas whose backslashes were all doubled written once."""
    if "\\\\" not in markdown:
        return markdown
    pieces = _CODE.split(markdown)
    # Even pieces are text, odd pieces are the code between them.
    pieces[::2] = [
        _FORMULA.sub(lambda match: _repair(match.group(0)), piece) for piece in pieces[::2]
    ]
    return "".join(pieces)
