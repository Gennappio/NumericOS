"""Hypotheses, experiments and runs: the typed scientific objects of a project."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Response

from numericos.api.deps import Context, Uow
from numericos.api.errors import CONFLICT_RESPONSES
from numericos.core.schemas import (
    ExperimentCreate,
    ExperimentList,
    ExperimentOut,
    ExperimentPatch,
    HypothesisCreate,
    HypothesisList,
    HypothesisOut,
    HypothesisPatch,
    RunCreate,
    RunList,
    RunOut,
)
from numericos.services import experiments, hypotheses, runs

router = APIRouter()

IdempotencyKey = Annotated[
    str | None,
    Header(
        pattern=r"^[A-Za-z0-9_.:-]{1,128}$",
        description=(
            "Makes the submission repeatable: the same key and request return the run created "
            "the first time; the same key with another request is a conflict."
        ),
    ),
]


@router.post(
    "/projects/{project_id}/hypotheses",
    status_code=201,
    tags=["hypotheses"],
    summary="State a hypothesis",
)
def create_hypothesis(
    project_id: str, body: HypothesisCreate, uow: Uow, context: Context
) -> HypothesisOut:
    return hypotheses.create_hypothesis(uow, project_id, body, context)


@router.get(
    "/projects/{project_id}/hypotheses",
    tags=["hypotheses"],
    summary="List a project's hypotheses in creation order",
)
def list_hypotheses(project_id: str, uow: Uow) -> HypothesisList:
    return hypotheses.list_hypotheses(uow, project_id)


@router.get("/hypotheses/{hypothesis_id}", tags=["hypotheses"], summary="Get one hypothesis")
def get_hypothesis(hypothesis_id: str, uow: Uow) -> HypothesisOut:
    return hypotheses.get_hypothesis(uow, hypothesis_id)


@router.patch(
    "/hypotheses/{hypothesis_id}",
    tags=["hypotheses"],
    summary="Reword a hypothesis (requires its current version)",
    responses=CONFLICT_RESPONSES,
)
def update_hypothesis(
    hypothesis_id: str, body: HypothesisPatch, uow: Uow, context: Context
) -> HypothesisOut:
    return hypotheses.update_hypothesis(uow, hypothesis_id, body, context)


@router.post(
    "/projects/{project_id}/experiments",
    status_code=201,
    tags=["experiments"],
    summary="Define an experiment by its protocol",
    responses=CONFLICT_RESPONSES,
)
def create_experiment(
    project_id: str, body: ExperimentCreate, uow: Uow, context: Context
) -> ExperimentOut:
    return experiments.create_experiment(uow, project_id, body, context)


@router.get(
    "/projects/{project_id}/experiments",
    tags=["experiments"],
    summary="List a project's experiments in creation order",
)
def list_experiments(project_id: str, uow: Uow) -> ExperimentList:
    return experiments.list_experiments(uow, project_id)


@router.get("/experiments/{experiment_id}", tags=["experiments"], summary="Get one experiment")
def get_experiment(experiment_id: str, uow: Uow) -> ExperimentOut:
    return experiments.get_experiment(uow, experiment_id)


@router.patch(
    "/experiments/{experiment_id}",
    tags=["experiments"],
    summary="Rename, relink or (while it has no runs) replace the protocol of an experiment",
    responses=CONFLICT_RESPONSES,
)
def update_experiment(
    experiment_id: str, body: ExperimentPatch, uow: Uow, context: Context
) -> ExperimentOut:
    return experiments.update_experiment(uow, experiment_id, body, context)


@router.post(
    "/experiments/{experiment_id}/runs",
    status_code=201,
    tags=["runs"],
    summary="Queue one run of an experiment; returns at once",
    responses={
        200: {"model": RunOut, "description": "The run an earlier identical request created"},
        **CONFLICT_RESPONSES,
    },
)
def create_run(
    experiment_id: str,
    body: RunCreate,
    uow: Uow,
    context: Context,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> RunOut:
    run, created = runs.create_run(
        uow, experiment_id, body, context, idempotency_key=idempotency_key
    )
    if not created:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return run


@router.get(
    "/experiments/{experiment_id}/runs",
    tags=["runs"],
    summary="List the runs of an experiment in creation order",
)
def list_runs(experiment_id: str, uow: Uow) -> RunList:
    return runs.list_runs(uow, experiment_id)


@router.get("/runs/{run_id}", tags=["runs"], summary="Get one run")
def get_run(run_id: str, uow: Uow) -> RunOut:
    return runs.get_run(uow, run_id)
