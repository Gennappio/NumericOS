"""Documents written by the agent under a real supervisor, with the stand-in as the agent:
the theory with the files it was written from, the pipeline as boxes and arrows over one text,
descriptions of files and when they go stale, a plan put on the board."""

from __future__ import annotations

import json

from numericos.agents import layout
from numericos.config import Settings
from numericos.executor.worker import Worker
from tests.lab import Json, Lab, drive

SOLVER = "examples/heat2d-python/heat2d.py"
PARAMETERS = "examples/heat2d-python/experiment.yaml"


def written(lab: Lab, what: str) -> Json | None:
    """The document once nothing is pending on it any more."""
    document = lab.single(what)
    return document if document and document["pending_message_id"] is None else None


def settled(lab: Lab) -> bool:
    return bool(lab.files()["counts"]["generating"] == 0)


def test_the_theory_is_written_and_knows_the_files_it_was_written_from(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("docs/notes.md", "explicit Euler\n")
    lab.generate("theory", f"READ {SOLVER}\nREAD docs/notes.md")

    theory = drive(supervisor, lambda: written(lab, "theory"))

    assert theory["status"] == "ready" and theory["version"] == 1
    assert theory["title"] == "Explicit scheme for the 2D heat equation"
    assert theory["markdown"].startswith("# Explicit scheme for the 2D heat equation")
    assert (
        "\\tag{1}" in theory["markdown"]
        and "![The grid of the solver](docs/grid.png)" in theory["markdown"]
    )
    assert theory["model"] == "fake-model"
    assert theory["generated_at"] is not None
    assert theory["message_id"] is not None and theory["status_reason"] is None
    assert [source["path"] for source in theory["sources"]] == [SOLVER, "docs/notes.md"]
    assert theory["sources"][0]["sha"] == lab.repo.git("rev-parse", f"HEAD:{SOLVER}")
    assert theory["sources"][1]["sha"] == lab.repo.git("hash-object", "docs/notes.md")
    assert (theory["stale"], theory["changed_sources"]) == (False, [])
    finished = [
        e for e in lab.turn_events(theory["message_id"]) if e["type"].startswith("DOCUMENT")
    ]
    assert [e["type"] for e in finished] == [
        "DOCUMENT_GENERATION_QUEUED",
        "DOCUMENT_GENERATION_FINISHED",
    ]
    assert finished[1]["payload"]["written"] == ["theory"] and finished[1]["producer"] == "worker"


def test_the_theory_goes_stale_when_a_file_it_was_written_from_changes(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("docs/notes.md", "explicit Euler\n")
    lab.generate("theory", f"READ {SOLVER}\nREAD docs/notes.md")
    drive(supervisor, lambda: written(lab, "theory"))

    lab.repo.write(SOLVER, "print('implicit now')\n")
    (lab.repo.root / "docs/notes.md").unlink()
    stale = lab.single("theory")
    lab.generate("theory")  # the instructions of the first request are kept
    again = drive(supervisor, lambda: written(lab, "theory"))

    assert stale is not None
    assert (stale["stale"], stale["changed_sources"]) == (True, [SOLVER, "docs/notes.md"])
    assert stale["markdown"].startswith("# Explicit scheme")  # still readable while stale
    assert again["version"] == 2 and again["stale"] is False
    # The file that is gone could not be read again: only what was read is a source.
    assert [source["path"] for source in again["sources"]] == [SOLVER]
    assert again["sources"][0]["sha"] == lab.repo.git("hash-object", SOLVER)


def test_a_failed_request_says_why_and_keeps_what_was_written_before(
    lab: Lab, supervisor: Worker
) -> None:
    lab.generate("theory", "FAIL the model refused")
    never = drive(supervisor, lambda: written(lab, "theory"))
    lab.generate("theory", "")
    good = drive(supervisor, lambda: written(lab, "theory"))
    lab.generate("theory", "EXIT 3")
    kept = drive(supervisor, lambda: written(lab, "theory"))

    assert (never["status"], never["version"], never["markdown"]) == ("failed", 0, "")
    assert never["status_reason"] == (
        "the agent's turn ended failed: error_during_execution: the model refused"
    )
    assert (good["status"], good["version"]) == ("ready", 1)
    assert (kept["status"], kept["version"]) == ("ready", 1)
    assert kept["markdown"] == good["markdown"]
    assert kept["status_reason"].startswith("the agent's turn ended interrupted")


def test_the_pipeline_is_written_as_boxes_and_arrows_over_one_text(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    lab.repo.write(PARAMETERS, "name: heat\n")
    asked = lab.generate("pipeline", "Scrivi in italiano.")

    document = drive(supervisor, lambda: written(lab, "pipeline"))
    text, nodes = document["markdown"], document["pipeline"]["nodes"]

    assert (document["kind"], document["status"], document["version"]) == ("pipeline", "ready", 1)
    assert asked["pipeline"] is None and asked["status"] == "generating"
    assert document["title"] == "Pipeline of the 2D heat solver"
    assert document["summary"].startswith("One run reads its parameters, builds the grid")
    # One text: the title, the summary, then a section per box, in the order of a run.
    assert text.startswith("# Pipeline of the 2D heat solver\n\nOne run reads its parameters")
    assert [(node["id"], node["kind"], node["title"]) for node in nodes] == [
        ("parameters", "input", "Read the parameters"),
        ("grid", "process", "Build the grid"),
        ("time-loop", "process", "Advance in time"),
        ("results", "output", "Write the results"),
    ]
    # Every box names its own section of the text, heading included.
    loop = nodes[2]
    assert text[loop["start"] : loop["end"]].startswith(
        "## Advance in time\n\nThe explicit scheme updates every interior point"
    )
    assert text[loop["start"] : loop["end"]].endswith("\\le \\frac{1}{4}.$$")
    assert text[nodes[3]["start"] : nodes[3]["end"]] == (
        "## Write the results\n\nThe final field and the residual history go to the run directory."
    )
    assert loop["repeats"] == "every time step, until the final time"
    assert nodes[0]["repeats"] is None
    # A path the agent gave as absolute is a path of the project.
    assert nodes[0]["files"] == [PARAMETERS] and nodes[3]["files"] == []
    # The arrow to a box that is not there is left out, and counted.
    assert document["pipeline"]["edges"] == [
        {"source": "parameters", "target": "grid", "label": "n, alpha, dt"},
        {"source": "grid", "target": "time-loop", "label": "initial field"},
        {"source": "time-loop", "target": "results", "label": "final field"},
    ]
    # Written from the files the agent read and the files its boxes name.
    assert document["sources"] == [
        {"path": PARAMETERS, "sha": lab.repo.git("hash-object", PARAMETERS)},
        {"path": SOLVER, "sha": lab.repo.git("rev-parse", f"HEAD:{SOLVER}")},
    ]
    assert (document["stale"], document["changed_sources"]) == (False, [])

    # A read-only turn of its own task, asked for a structured answer.
    session = lab.get(f"/v1/agent-sessions/{document['session_id']}")
    assert (session["task"], session["permission_mode"]) == ("pipeline", "read_only")
    turn_dir = layout.turn_dir(settings.data_dir, document["message_id"])
    prompt = (turn_dir / layout.PROMPT).read_text()
    assert prompt.startswith("[NumericOS task: pipeline]")
    assert "Additional instructions from the researcher:\nScrivi in italiano." in prompt
    assert "Do not read, describe or list that folder" in prompt
    argv = json.loads((turn_dir / layout.SPEC).read_text())["argv"]
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["properties"]["nodes"]["items"]["properties"]["kind"]["enum"] == [
        "input",
        "process",
        "output",
        "external",
    ]
    finished = [
        e
        for e in lab.turn_events(document["message_id"])
        if e["type"] == "DOCUMENT_GENERATION_FINISHED"
    ]
    assert finished[0]["payload"]["written"] == ["pipeline"]
    assert (
        finished[0]["payload"]["boxes"],
        finished[0]["payload"]["arrows"],
        finished[0]["payload"]["entries_skipped"],
    ) == (4, 3, 1)


def test_a_pipeline_goes_stale_with_the_files_of_its_boxes(lab: Lab, supervisor: Worker) -> None:
    lab.generate("pipeline")
    first = drive(supervisor, lambda: written(lab, "pipeline"))

    lab.repo.write(SOLVER, "print('implicit now')\n")
    stale = lab.single("pipeline")
    lab.generate("pipeline")
    again = drive(supervisor, lambda: written(lab, "pipeline"))

    # The file of the first box does not exist here: a file that is named is no source by that.
    assert [source["path"] for source in first["sources"]] == [SOLVER]
    assert stale is not None
    assert (stale["stale"], stale["changed_sources"]) == (True, [SOLVER])
    # Which boxes are affected can be told: the ones that name the file.
    assert [node["id"] for node in stale["pipeline"]["nodes"] if SOLVER in node["files"]] == [
        "grid",
        "time-loop",
    ]
    assert stale["markdown"] == first["markdown"]  # still readable while stale
    assert (again["version"], again["stale"]) == (2, False)
    assert again["sources"] == [{"path": SOLVER, "sha": lab.repo.git("hash-object", SOLVER)}]


def test_a_box_may_name_paths_that_are_no_files_of_the_project(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("src/solver.py", "pass\n")
    answer = {
        "title": "P",
        "summary": "",
        "nodes": [
            {
                "id": "a",
                "title": "A",
                "kind": "process",
                "description": "x",
                "files": [
                    "src/solver.py",
                    "src",
                    "../elsewhere.py",
                    "gone.py",
                    f"/etc/{'x' * 300}",
                ],
                "repeats": None,
            }
        ],
        "edges": [],
    }
    lab.generate("pipeline", f"JSON {json.dumps(answer)}")

    document = drive(supervisor, lambda: written(lab, "pipeline"))

    # The box says what the agent said; only what is a file of the project is a source.
    assert document["pipeline"]["nodes"][0]["files"][:4] == [
        "src/solver.py",
        "src",
        "../elsewhere.py",
        "gone.py",
    ]
    assert document["sources"] == [
        {"path": "src/solver.py", "sha": lab.repo.git("hash-object", "src/solver.py")}
    ]


def test_an_answer_without_boxes_is_no_pipeline(lab: Lab, supervisor: Worker) -> None:
    lab.generate("pipeline", 'JSON {"title": "Nothing", "summary": "", "nodes": [], "edges": []}')
    empty = drive(supervisor, lambda: written(lab, "pipeline"))
    lab.generate("pipeline", "")
    good = drive(supervisor, lambda: written(lab, "pipeline"))
    lab.generate("pipeline", 'JSON {"answer": "a sentence"}')
    kept = drive(supervisor, lambda: written(lab, "pipeline"))

    assert (empty["status"], empty["version"], empty["pipeline"]) == ("failed", 0, None)
    assert empty["status_reason"] == "the agent's answer had no box that could be used"
    assert (good["status"], good["version"]) == ("ready", 1)
    # A later answer that is no pipeline leaves the one before in place, and says why.
    assert (kept["status"], kept["version"]) == ("ready", 1)
    assert kept["pipeline"] == good["pipeline"] and kept["markdown"] == good["markdown"]
    assert kept["status_reason"] == "the agent's answer did not have the requested structure"


def test_a_description_keeps_its_formulas_as_they_were_meant(lab: Lab, supervisor: Worker) -> None:
    answer = {
        "files": [
            {
                "path": SOLVER,
                "category": "code",
                "summary": "The solver.",
                "description": (
                    "Stable when $\\\\alpha\\\\,\\\\Delta t/h^2 \\\\le 1/4$; `\\\\d+` is code."
                ),
            }
        ]
    }

    lab.describe(paths=[SOLVER], instructions=f"JSON {json.dumps(answer)}")
    drive(supervisor, lambda: settled(lab))

    # The backslashes of LaTeX that the answer doubled are single again; code is as written.
    assert lab.description(SOLVER)["markdown"] == (
        "Stable when $\\alpha\\,\\Delta t/h^2 \\le 1/4$; `\\\\d+` is code."
    )


def test_files_are_described_and_a_changed_file_asks_for_its_description_again(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    lab.repo.write("results/u_final.csv", "x,u\n0,1\n")
    lab.repo.write("docs/grid.png", "PNG")
    settings.agent_files_per_turn = 3

    asked = lab.describe(scope="undescribed")
    drive(supervisor, lambda: settled(lab))
    listing = lab.files()
    solver = lab.description(SOLVER)

    assert (asked["queued"], asked["turns"]) == (4, 2)
    assert listing["counts"] == {
        "total": 4,
        "described": 4,
        "stale": 0,
        "generating": 0,
        "failed": 0,
        "undescribed": 0,
    }
    entry = lab.file(SOLVER)
    assert entry["category"] == "code"  # the agent's word now
    assert lab.file("docs/grid.png")["category"] == "image"
    assert entry["description"]["summary"] == f"Fake summary of {SOLVER}."
    assert (entry["description"]["status"], entry["description"]["stale"]) == ("ready", False)
    assert solver["markdown"].startswith(f"`{SOLVER}` holds $u_t")
    assert solver["sources"] == [
        {"path": SOLVER, "sha": lab.repo.git("rev-parse", f"HEAD:{SOLVER}")}
    ]
    assert solver["title"] == SOLVER and solver["version"] == 1

    lab.repo.write(SOLVER, "print('edited')\n")
    changed = lab.files()
    updated = lab.describe(scope="stale")
    drive(supervisor, lambda: settled(lab))

    assert changed["counts"]["stale"] == 1 and changed["counts"]["described"] == 3
    assert lab.file(SOLVER)["description"]["stale"] is False  # described again
    assert (updated["queued"], updated["turns"]) == (1, 1)
    assert lab.description(SOLVER)["version"] == 2
    assert lab.description("docs/grid.png")["version"] == 1  # untouched
    assert lab.description(SOLVER)["stale"] is False


def test_a_file_the_agent_left_out_says_so_and_can_be_asked_again(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("a.py", "a = 1\n")
    lab.repo.write("b.py", "b = 2\n")

    lab.describe(paths=["a.py", "b.py"], instructions="OMIT b.py")
    drive(supervisor, lambda: settled(lab))
    counts = lab.files()["counts"]
    missing = lab.file("b.py")["description"]
    again = lab.describe(scope="undescribed", instructions="")
    drive(supervisor, lambda: settled(lab))

    assert lab.file("a.py")["description"]["status"] == "ready"
    assert (missing["status"], missing["status_reason"]) == (
        "failed",
        "the agent returned no description of this file",
    )
    assert (counts["described"], counts["failed"]) == (1, 1)
    # A failed description counts as not described: the two files never asked for, and b.py.
    assert again["queued"] == 3
    assert lab.file("b.py")["description"]["status"] == "ready"


def test_a_plan_puts_cards_on_the_board_and_a_second_one_changes_them(
    lab: Lab, supervisor: Worker
) -> None:
    lab.generate("plan")
    plan = drive(supervisor, lambda: written(lab, "plan"))
    cards = lab.board()

    assert plan["status"] == "ready"
    assert plan["markdown"] == "Check stability **first**, then accuracy."
    assert plan["summary"] == "2 card(s) added, 0 changed"
    assert [(c["title"], c["type"], c["workflow_status"], c["origin"]) for c in cards] == [
        ("The scheme is first order in time", "hypothesis", "backlog", "agent"),
        ("Run the stability sweep", "experiment", "planned", "agent"),
    ]
    created = [
        e
        for e in lab.turn_events(plan["message_id"])
        if e["type"] == "DOCUMENT_GENERATION_FINISHED"
    ]
    assert created[0]["payload"]["cards_created"] == 2

    sweep = next(card for card in cards if card["title"] == "Run the stability sweep")
    answer = (
        '{"rationale": "Start the sweep.", "cards": ['
        f'{{"id": "{sweep["id"]}", "type": "experiment", "title": "Run the stability sweep now",'
        ' "description": "Started.", "status": "active"},'
        ' {"type": "issue", "title": "Boundary values are never checked", "description": "",'
        ' "status": "backlog"},'
        ' {"type": "nonsense", "title": "x", "description": "", "status": "backlog"}]}'
    )
    lab.generate("plan", f"JSON {answer}")
    second = drive(supervisor, lambda: written(lab, "plan"))
    after = {card["id"]: card for card in lab.board()}

    assert second["version"] == 2
    assert second["summary"] == (
        "1 card(s) added, 1 changed, 1 entry(ies) of the answer could not be used"
    )
    moved = after[sweep["id"]]
    assert (moved["title"], moved["workflow_status"], moved["version"]) == (
        "Run the stability sweep now",
        "active",
        2,
    )
    assert len(after) == 3
    issue = next(card for card in after.values() if card["type"] == "issue")
    assert (issue["origin"], issue["workflow_status"]) == ("agent", "backlog")
