"""What is said about a file from its name, and the paths the agent gives back."""

from __future__ import annotations

from pathlib import Path

import pytest

from numericos.agents.documents import first_heading, relative_path
from numericos.agents.prompts import FILES_SCHEMA, PLAN_SCHEMA, files, plan, theory
from numericos.core.enums import FileCategory
from numericos.core.files import guess_category, is_viewable_image, media_type


@pytest.mark.parametrize(
    ("path", "category"),
    [
        ("src/solver.py", FileCategory.CODE),
        ("src/kernel.f90", FileCategory.CODE),
        ("Makefile", FileCategory.CODE),
        ("notebooks/analysis.ipynb", FileCategory.CODE),
        ("results/u_final.csv", FileCategory.DATA),
        ("mesh/unit_square.msh", FileCategory.DATA),
        ("figures/convergence.png", FileCategory.IMAGE),
        ("params.yaml", FileCategory.CONFIG),
        (".gitignore", FileCategory.CONFIG),
        ("README.md", FileCategory.DOCUMENTATION),
        ("LICENSE", FileCategory.DOCUMENTATION),
        ("paper/main.tex", FileCategory.DOCUMENTATION),
        ("bin/solver", FileCategory.OTHER),
    ],
)
def test_a_first_sorting_by_name(path: str, category: FileCategory) -> None:
    assert guess_category(path) is category


def test_images_a_browser_shows_and_media_types() -> None:
    assert is_viewable_image("fig/a.PNG") and is_viewable_image("fig/a.svg")
    assert not is_viewable_image("fig/a.eps") and not is_viewable_image("solver.py")
    assert media_type("fig/a.png") == "image/png"
    assert media_type("data/blob.unknownext") == "application/octet-stream"


def test_paths_of_the_agent_are_made_relative_to_the_project(tmp_path: Path) -> None:
    assert relative_path(str(tmp_path / "src" / "a.py"), tmp_path) == "src/a.py"
    assert relative_path("./src/a.py", tmp_path) == "src/a.py"
    assert relative_path("src/a.py", tmp_path) == "src/a.py"
    assert relative_path("/elsewhere/a.py", tmp_path) == "/elsewhere/a.py"


def test_the_title_of_a_document_is_its_first_level_one_heading() -> None:
    assert first_heading("intro\n# Heat *2D*\n## Model\n# Second") == "Heat *2D*"
    assert first_heading("## Only a section") is None


def test_prompts_name_their_task_and_end_with_the_researchers_words() -> None:
    written = theory("Heat 2D", "Is it stable?", "Scrivi in italiano.")
    listing = files(["src/a.py", "fig/b.png"], "")
    planned = plan(
        "Heat 2D",
        "",
        [
            {
                "id": "card_1",
                "type": "task",
                "workflow_status": "active",
                "title": "Port the solver",
                "description": "to\nC++",
            }
        ],
        "",
    )

    assert written.startswith("[NumericOS task: theory]\n")
    assert "Research question: Is it stable?" in written
    assert written.endswith("Additional instructions from the researcher:\nScrivi in italiano.\n")
    assert listing.startswith("[NumericOS task: file_description]\n")
    assert listing.endswith("Files to describe:\n- src/a.py\n- fig/b.png\n")
    assert "Additional instructions" not in listing
    assert planned.startswith("[NumericOS task: plan]\n")
    assert "- [card_1] (task, active) Port the solver: to C++\n" in planned
    assert "Research question: not stated yet" in planned
    assert "(the board is empty)" in plan("Heat 2D", "", [], "")


def test_the_schemas_ask_for_what_the_documents_need() -> None:
    entry = FILES_SCHEMA["properties"]["files"]["items"]
    assert entry["required"] == ["path", "category", "summary", "description"]
    assert "data" not in entry["properties"]["category"]["enum"]  # the agent must decide
    assert "input" in entry["properties"]["category"]["enum"]
    card = PLAN_SCHEMA["properties"]["cards"]["items"]
    assert card["required"] == ["type", "title", "description", "status"]
    assert card["properties"]["status"]["enum"][0] == "backlog"
