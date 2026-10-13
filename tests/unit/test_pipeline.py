"""From the agent's boxes and arrows to the text and the structure of a pipeline document."""

from __future__ import annotations

from typing import Any

from numericos.agents.pipeline import (
    MAX_BOXES,
    NO_BOXES,
    NO_STRUCTURE,
    Built,
    build,
    named_files,
    outline,
)


def box(**fields: Any) -> dict[str, Any]:
    return {
        "id": "a",
        "title": "A",
        "kind": "process",
        "description": "",
        "files": [],
        "repeats": None,
        **fields,
    }


def built(answer: Any) -> Built:
    result = build(answer, lambda raw: raw.removeprefix("/repo/"))
    assert isinstance(result, Built), result
    return result


def test_every_box_is_a_section_of_one_text_and_names_its_range() -> None:
    pipeline = built(
        {
            "title": "  Heat   solver 😀 ",
            "summary": "One run reads, steps and writes.",
            "nodes": [
                box(id="read", title="Read the parameters", kind="input", description="From *x*."),
                box(id="step", title="Advance in time", description="Euler.\n\n$$u^{n+1}=u^n$$"),
                box(id="write", title="Write", kind="output"),
            ],
            "edges": [],
        }
    )
    text, nodes = pipeline.markdown, pipeline.structure["nodes"]

    assert text == (
        "# Heat solver 😀\n\nOne run reads, steps and writes.\n\n"
        "## Read the parameters\n\nFrom *x*.\n\n"
        "## Advance in time\n\nEuler.\n\n$$u^{n+1}=u^n$$\n\n"
        "## Write"
    )
    assert (pipeline.title, pipeline.summary) == (
        "Heat solver 😀",
        "One run reads, steps and writes.",
    )
    # Offsets are Unicode code points, as everywhere in the API: the emoji counts once.
    assert [text[node["start"] : node["end"]] for node in nodes] == [
        "## Read the parameters\n\nFrom *x*.",
        "## Advance in time\n\nEuler.\n\n$$u^{n+1}=u^n$$",
        "## Write",
    ]
    assert [(node["id"], node["kind"], node["title"]) for node in nodes] == [
        ("read", "input", "Read the parameters"),
        ("step", "process", "Advance in time"),
        ("write", "output", "Write"),
    ]


def test_ids_are_tidied_and_unique_and_an_unknown_kind_is_a_stage() -> None:
    pipeline = built(
        {
            "title": "",
            "summary": "",
            "nodes": [
                box(id="Time Loop!", title="Loop"),
                box(id="time-loop", title="Again", kind="magic"),
                box(id="", title="No id given"),
            ],
            "edges": [],
        }
    )

    assert pipeline.title == "Pipeline" and pipeline.markdown.startswith("# Pipeline\n\n## Loop")
    assert [(node["id"], node["kind"]) for node in pipeline.structure["nodes"]] == [
        ("time-loop", "process"),
        ("time-loop-2", "process"),
        ("no-id-given", "process"),
    ]


def test_arrows_follow_the_boxes_they_name_and_the_rest_is_counted() -> None:
    pipeline = built(
        {
            "title": "P",
            "summary": "",
            "nodes": [
                box(id="Read", title="Read the parameters"),
                box(id="step", title="Advance in time"),
                box(id="out", title="Write the results"),
                box(title=""),  # a box needs a title
                "not a box",
            ],
            "edges": [
                {"from": "Read", "to": "step", "label": "  n,   alpha "},
                {"from": "read", "to": "step", "label": "the same arrow again"},
                {"from": "step", "to": "Write the results", "label": ""},  # by its title
                {"from": "step", "to": "step", "label": "every time step"},
                {"from": "step", "to": "nowhere", "label": "x"},
                {"from": "step"},
                "not an arrow",
            ],
        }
    )
    nodes = {node["id"]: node for node in pipeline.structure["nodes"]}

    assert pipeline.structure["edges"] == [
        {"source": "read", "target": "step", "label": "n, alpha"},
        {"source": "step", "target": "out", "label": ""},
    ]
    # A box that points at itself repeats: that is said on the box, not drawn as an arrow.
    assert nodes["step"]["repeats"] == "every time step"
    assert nodes["read"]["repeats"] is None
    assert pipeline.skipped == 5  # two boxes and three arrows could not be used


def test_files_are_paths_of_the_project_once_each() -> None:
    pipeline = built(
        {
            "title": "P",
            "summary": "",
            "nodes": [box(files=["/repo/src/a.py", "src/a.py", " ", 7, "data/in.csv"])],
            "edges": [],
        }
    )

    assert pipeline.structure["nodes"][0]["files"] == ["src/a.py", "data/in.csv"]


def test_formulas_escaped_once_too_often_are_as_they_were_meant() -> None:
    pipeline = built(
        {
            "title": "P",
            "summary": "Stable when $r=\\\\alpha\\\\,\\\\Delta t/h^2 \\\\le 1/4$.",
            "nodes": [
                box(description="Doubled: $u_{ij}\\\\leftarrow u_{ij}$. Fine: $\\Delta t$."),
                box(id="b", title="B", description="A pattern in code stays: `\\\\d+`."),
            ],
            "edges": [],
        }
    )

    assert "Stable when $r=\\alpha\\,\\Delta t/h^2 \\le 1/4$." in pipeline.markdown
    assert "Doubled: $u_{ij}\\leftarrow u_{ij}$. Fine: $\\Delta t$." in pipeline.markdown
    assert "A pattern in code stays: `\\\\d+`." in pipeline.markdown
    # The ranges are of the text as it is kept, after the repair.
    second = pipeline.structure["nodes"][1]
    assert pipeline.markdown[second["start"] : second["end"]] == (
        "## B\n\nA pattern in code stays: `\\\\d+`."
    )


def test_an_answer_without_boxes_makes_no_pipeline() -> None:
    assert build("a sentence", str) == NO_STRUCTURE
    assert build({"title": "P"}, str) == NO_STRUCTURE
    assert build({"nodes": []}, str) == NO_BOXES
    assert build({"nodes": [box(title="  ")]}, str) == NO_BOXES


def test_a_pipeline_is_bounded() -> None:
    pipeline = built(
        {"nodes": [box(id=f"b{index}", title=f"Box {index}") for index in range(MAX_BOXES + 3)]}
    )

    assert len(pipeline.structure["nodes"]) == MAX_BOXES and pipeline.skipped == 3


def test_the_outline_says_in_words_what_the_text_does_not() -> None:
    pipeline = built(
        {
            "title": "P",
            "summary": "",
            "nodes": [
                box(id="read", title="Read", kind="input", files=["a.yaml", "b.csv"]),
                box(id="step", title="Step", repeats="until the final time"),
            ],
            "edges": [{"from": "read", "to": "step", "label": "parameters"}],
        }
    )

    assert outline(pipeline.structure) == (
        "The text is drawn as a diagram: every `##` section is a box, and arrows connect the "
        "boxes.\n"
        "Boxes (id · kind · title · files):\n"
        "- read · input · Read · a.yaml, b.csv\n"
        "- step · process · Step · no file · repeats: until the final time\n"
        "Arrows (from -> to: what passes):\n"
        "- read -> step: parameters\n"
    )
    assert outline({"nodes": [], "edges": []}).endswith("what passes):\n(none)\n")


def test_the_files_an_answer_names_are_found_in_either_shape() -> None:
    answer = {"nodes": [box(files=["/repo/a.py", " b.py ", ""]), box(files="no list"), "x"]}

    assert named_files(answer) == ["/repo/a.py", "b.py"]
    # A Resolve turn gives the revised pipeline inside its answer.
    assert named_files({"results": [], "pipeline": answer}) == ["/repo/a.py", "b.py"]
    assert named_files({"results": [], "pipeline": None}) == []
    assert named_files(None) == []
