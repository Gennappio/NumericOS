"""The pipeline of a project: the program as boxes and the arrows between them.

The agent answers with boxes and arrows (``prompts.PIPELINE_SCHEMA``). ``build`` turns that
answer into the two things a pipeline document keeps: one Markdown text, in which every box is
a section, and the structure, in which every box names the range of the text that is its own.
The text is what comments are attached to, exactly as for any other document; the structure
is what the page draws. Nothing here reads a file or the database.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from numericos.core.enums import PipelineNodeKind
from numericos.core.formulas import repair_formulas

MAX_BOXES = 40
MAX_ARROWS = 120
TITLE_MAX = 120
LABEL_MAX = 80
SUMMARY_MAX = 2000
DESCRIPTION_MAX = 6000
FILES_MAX = 12
DEFAULT_TITLE = "Pipeline"
NO_STRUCTURE = "the agent's answer did not have the requested structure"
NO_BOXES = "the agent's answer had no box that could be used"

KINDS = {kind.value for kind in PipelineNodeKind}


@dataclass(frozen=True)
class Built:
    title: str
    summary: str
    #: The whole pipeline as one text: the title, the summary, then one section per box.
    markdown: str
    #: ``{"nodes": [...], "edges": [...]}``; ``start`` and ``end`` of a node are offsets into
    #: ``markdown`` in Unicode code points, heading included.
    structure: dict[str, Any]
    #: Entries of the answer that could not be used: a box with no title, an arrow to nowhere.
    skipped: int


def _line(value: Any, limit: int) -> str:
    line = " ".join(str(value).split()) if isinstance(value, str) else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _text(value: Any, limit: int) -> str:
    """Markdown of the answer: trimmed, bounded, its formulas as they were meant."""
    return repair_formulas(str(value or "").replace("\r\n", "\n").strip()[:limit])


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")[:40] if value else ""


def _named(names: dict[str, str], value: Any) -> str | None:
    """The box an arrow means by ``value``: its id as written, or as it reads once tidied."""
    return names.get(str(value)) or names.get(_slug(value)) if value else None


def build(answer: Any, relative: Callable[[str], str]) -> Built | str:
    """The document a structured answer makes, or the reason why it makes none. ``relative``
    turns a path as the agent gave it into a path of the project."""
    entries = answer.get("nodes") if isinstance(answer, dict) else None
    if not isinstance(answer, dict) or not isinstance(entries, list):
        return NO_STRUCTURE
    title = _line(answer.get("title"), TITLE_MAX).lstrip("# ") or DEFAULT_TITLE
    summary = _text(answer.get("summary"), SUMMARY_MAX)
    text = f"# {title}" + (f"\n\n{summary}" if summary else "")

    boxes: list[dict[str, Any]] = []
    names: dict[str, str] = {}  # what an arrow may call a box -> the id it is kept under
    skipped = 0
    for entry in entries:
        box_title = (
            _line(entry.get("title"), TITLE_MAX).lstrip("# ") if isinstance(entry, dict) else ""
        )
        if not box_title or len(boxes) == MAX_BOXES:
            skipped += 1
            continue
        given = str(entry.get("id") or "")
        base = _slug(given) or _slug(box_title) or "box"
        box_id, number = base, 2
        while box_id in {box["id"] for box in boxes}:
            box_id, number = f"{base}-{number}", number + 1
        for name in (given, _slug(given)):
            if name:
                names.setdefault(name, box_id)
        description = _text(entry.get("description"), DESCRIPTION_MAX)
        files: list[str] = []
        listed = entry.get("files")
        for raw in listed if isinstance(listed, list) else []:
            path = relative(raw.strip()) if isinstance(raw, str) and raw.strip() else ""
            if path and path not in files and len(files) < FILES_MAX:
                files.append(path)
        start = len(text) + 2
        text = f"{text}\n\n## {box_title}" + (f"\n\n{description}" if description else "")
        boxes.append(
            {
                "id": box_id,
                "kind": entry.get("kind") if entry.get("kind") in KINDS else "process",
                "title": box_title,
                "files": files,
                "repeats": _line(entry.get("repeats"), LABEL_MAX) or None,
                "start": start,
                "end": len(text),
            }
        )
    if not boxes:
        return NO_BOXES
    # An arrow that names a box by its title is understood, after every id had its turn.
    for box in boxes:
        names.setdefault(_slug(box["title"]), box["id"])
    by_id = {box["id"]: box for box in boxes}

    arrows = answer.get("edges")
    edges: list[dict[str, str]] = []
    for arrow in arrows if isinstance(arrows, list) else []:
        ends = arrow if isinstance(arrow, dict) else {}
        source = _named(names, ends.get("from") or ends.get("source"))
        target = _named(names, ends.get("to") or ends.get("target"))
        if source is None or target is None or len(edges) == MAX_ARROWS:
            skipped += 1
            continue
        label = _line(ends.get("label"), LABEL_MAX)
        if source == target:
            # A box that points at itself repeats: that is said on the box.
            by_id[source]["repeats"] = by_id[source]["repeats"] or label or "repeats"
        elif not any(edge["source"] == source and edge["target"] == target for edge in edges):
            edges.append({"source": source, "target": target, "label": label})
    return Built(
        title=title,
        summary=_line(summary, 400),
        markdown=text,
        structure={"nodes": boxes, "edges": edges},
        skipped=skipped,
    )


def named_files(answer: Any) -> list[str]:
    """The paths a structured answer names on its boxes, as the agent wrote them: the answer
    of a turn that writes the pipeline, or of a Resolve turn that revises it."""
    if isinstance(answer, dict) and isinstance(answer.get("pipeline"), dict):
        answer = answer["pipeline"]
    entries = answer.get("nodes") if isinstance(answer, dict) else None
    return [
        raw.strip()
        for entry in (entries if isinstance(entries, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("files"), list)
        for raw in entry["files"]
        if isinstance(raw, str) and raw.strip()
    ]


def outline(structure: dict[str, Any] | None) -> str:
    """The boxes and arrows in words, for the agent that is shown the text of a pipeline (and
    for the copy kept as a file): what the text alone does not say."""
    nodes = (structure or {}).get("nodes") or []
    edges = (structure or {}).get("edges") or []
    lines = [
        "The text is drawn as a diagram: every `##` section is a box, and arrows connect "
        "the boxes.",
        "Boxes (id · kind · title · files):",
    ]
    for node in nodes:
        parts = [node["id"], node["kind"], node["title"], ", ".join(node["files"]) or "no file"]
        if node.get("repeats"):
            parts.append(f"repeats: {node['repeats']}")
        lines.append("- " + " · ".join(parts))
    lines.append("Arrows (from -> to: what passes):")
    lines += [
        f"- {edge['source']} -> {edge['target']}" + (f": {edge['label']}" if edge["label"] else "")
        for edge in edges
    ] or ["(none)"]
    return "\n".join(lines) + "\n"
