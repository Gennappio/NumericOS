"""Demo data. Created only by the explicit ``numericos seed-demo`` command, through the API.

The project is flagged ``is_demo`` so every surface can label it. The cards illustrate the board:
they are plans and open items, not recorded results.
"""

from __future__ import annotations

from typing import Any

from numericos.cli.client import ApiClient

DEMO_PROJECT: dict[str, Any] = {
    "name": "Demo: 2D heat equation stability",
    "research_question": (
        "For the explicit FTCS scheme on a uniform grid, which time steps keep the 2D heat "
        "equation solver stable, and what do they cost in accuracy and runtime?"
    ),
    "description": (
        "Demo data created by `numericos seed-demo`. The cards illustrate the board; "
        "none of them is a recorded result."
    ),
    "root_path": None,
    "is_demo": True,
}

DEMO_CARDS: list[dict[str, Any]] = [
    {
        "type": "task",
        "title": "Set up the reference FTCS solver with a manufactured solution",
        "workflow_status": "completed",
    },
    {
        "type": "hypothesis",
        "title": "H01: the blow-up at dt = 0.02 comes from violating the scheme's stability limit",
        "description": (
            "Prediction: residual growth disappears once dt is below the limit derived for this "
            "discretization.\n"
            "Falsification: divergence persists for every smaller dt on the same mesh and "
            "boundary conditions."
        ),
        "workflow_status": "active",
    },
    {
        "type": "experiment",
        "title": "Run dt in {0.02, 0.01, 0.005} on grid-128 with fixed initial and boundary data",
        "description": "Controls: mesh, boundary condition version, solver revision, precision.",
        "workflow_status": "planned",
    },
    {
        "type": "decision",
        "title": "Judge candidates against the analytic solution, not only against residuals",
        "workflow_status": "review",
    },
    {
        "type": "issue",
        "title": "Right-wall boundary condition is applied one cell too far inside the domain",
        "workflow_status": "backlog",
    },
    {
        "type": "task",
        "title": "Instrument the solver to emit residual and L2 error at every step",
        "workflow_status": "backlog",
    },
]


def seed_demo(client: ApiClient) -> dict[str, Any]:
    """Create the demo project unless it already exists (same name, flagged as demo)."""
    projects = client.get("/v1/projects")["projects"]
    existing = next(
        (p for p in projects if p["is_demo"] and p["name"] == DEMO_PROJECT["name"]), None
    )
    if existing is not None:
        board = client.get(f"/v1/projects/{existing['id']}/board")
        return {"created": False, "project": existing, "card_count": len(board["cards"])}

    project = client.post("/v1/projects", DEMO_PROJECT)
    for card in DEMO_CARDS:
        client.post(f"/v1/projects/{project['id']}/cards", card)
    return {"created": True, "project": project, "card_count": len(DEMO_CARDS)}
