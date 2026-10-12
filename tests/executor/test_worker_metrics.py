"""Metrics of supervised runs: what reaches the database, the ledger and the API."""

from __future__ import annotations

from typing import Any

from numericos.executor.worker import Worker
from tests.api.helpers import error_of
from tests.lab import Lab, drive

Json = dict[str, Any]

EMIT = """
import json, sys, time

def metric(name, value, step=None, **extra):
    record = {"schema": "numericos.metric.v1", "name": name, "value": value, **extra}
    if step is not None:
        record["step"] = step
    print(json.dumps(record), flush=True)
"""
RESIDUAL = {"name": "residual", "unit": "1", "sampled_by": "instrumentation"}


def levels(metrics: Json) -> dict[str, str]:
    return {level["level"]: level["status"] for level in metrics["coverage"]["levels"]}


def diagnostics(metrics: Json) -> dict[str, Json]:
    return {item["kind"]: item for item in metrics["diagnostics"]}


def test_metrics_appear_while_the_run_is_in_progress(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(
        EMIT
        + """
for step in range(1, 4):
    metric("residual", 1.0 / step, step)
time.sleep(1.5)
metric("residual", 0.1, 4)
""",
        metrics=[RESIDUAL, {"name": "energy", "sampled_by": "instrumentation"}],
    )
    before = lab.metrics(queued["id"])

    drive(supervisor, lambda: lab.series(queued["id"]).get("residual", {}).get("samples") == 3)
    during = lab.metrics(queued["id"])
    live = lab.samples(queued["id"], "residual")
    supervisor.run_until_idle()
    after = lab.metrics(queued["id"])

    assert levels(before) == {
        "L0": "waiting",
        "L1": "not_configured",
        "L2": "waiting",
        "L3": "not_configured",
    }
    assert lab.status(queued["id"]) == "succeeded"
    assert [sample["step"] for sample in live] == [1, 2, 3]
    assert levels(during)["L0"] == "observed"
    assert levels(during)["L2"] == "partial"  # residual has samples, energy has none yet
    coverage = {item["name"]: item["status"] for item in during["coverage"]["metrics"]}
    assert coverage == {"residual": "observed", "energy": "waiting"}
    assert lab.series(queued["id"])["residual"]["samples"] == 4
    # The run has ended: a declared metric without a sample is missing, not still awaited.
    coverage = {item["name"]: item["status"] for item in after["coverage"]["metrics"]}
    assert coverage == {"residual": "observed", "energy": "missing"}
    assert levels(after)["L2"] == "partial"


def test_what_the_program_emits_beyond_the_contract_is_kept_and_what_is_wrong_is_said(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(
        EMIT
        + """
metric("residual", 0.5, 1, unit="percent")
metric("debug_norm", 3.0, 1)
metric("wall_time", 12.0)
print('{"schema": "numericos.metric.v1", "name": "residual", "value": "tiny"}', flush=True)
print("progress 50%")
""",
        metrics=[RESIDUAL, {"name": "wall_time", "unit": "s", "sampled_by": "supervisor"}],
    )

    supervisor.run_until_idle()

    metrics = lab.metrics(queued["id"])
    series = lab.series(queued["id"])
    found = diagnostics(metrics)
    assert (series["debug_norm"]["declared"], series["residual"]["declared"]) == (False, True)
    assert metrics["coverage"]["undeclared"] == ["debug_norm"]
    # The supervisor's own measurement stands; the program's value for it was not taken.
    assert series["wall_time"]["source"] == "supervisor"
    assert series["wall_time"]["last_value"] != 12.0
    assert sorted(found) == [
        "malformed_record",
        "source_mismatch",
        "undeclared_metric",
        "unit_mismatch",
    ]
    assert "'value' must be a number" in found["malformed_record"]["examples"][0]
    # The malformed record is still in the output for a person to read; valid ones are not.
    assert lab.output(queued["id"]) == [
        '{"schema": "numericos.metric.v1", "name": "residual", "value": "tiny"}',
        "progress 50%",
    ]
    assert metrics["records"] == 3


def test_a_bound_that_only_records_leaves_a_warning_and_lets_the_run_finish(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(
        EMIT
        + """
for step, value in enumerate([1.0, 0.97, 0.96, 1.0]):
    metric("mass", value, step)
""",
        metrics=[{"name": "mass", "unit": "kg", "sampled_by": "instrumentation"}],
        guardrails={
            "rules": [{"metric": "mass", "below": 0.99, "patience": 2, "action": "record"}]
        },
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    violated = lab.event(run["id"], "RUN_GUARDRAIL_VIOLATED")
    assert run["status"] == "succeeded"
    assert violated["severity"] == "warning"
    assert violated["payload"] == {
        "metric": "mass",
        "bound": "below",
        "threshold": 0.99,
        "value": 0.96,
        "non_finite": None,
        "step": 2,
        "consecutive": 2,
        "action": "record",
        "observed_at": violated["payload"]["observed_at"],
    }


def test_a_nan_that_does_not_stop_the_run_is_still_an_error_event(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(
        EMIT
        + """
metric("residual", 0.5, 1)
metric("residual", float("nan"), 2)  # json.dumps writes NaN, which is not JSON
metric("residual", 0.25, 3)
""",
        metrics=[RESIDUAL],  # non_finite defaults to "record"
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    event = lab.event(run["id"], "RUN_METRIC_NON_FINITE")
    samples = lab.samples(run["id"], "residual")
    assert run["status"] == "succeeded"  # the contract did not ask for a stop
    assert (event["severity"], event["payload"]["action"]) == ("error", "record")
    assert (event["payload"]["metric"], event["payload"]["step"]) == ("residual", 2)
    assert [(sample["value"], sample["non_finite"]) for sample in samples] == [
        (0.5, None),
        (None, "nan"),
        (0.25, None),
    ]
    series = lab.series(run["id"])["residual"]
    assert (series["non_finite"], series["min_value"], series["max_value"]) == (1, 0.25, 0.5)


def test_samples_beyond_the_storage_limit_are_counted_and_the_run_says_so(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(
        EMIT
        + """
for step in range(40000):
    print('{"schema":"numericos.metric.v1","name":"residual","value":0.5,"step":%d}' % step)
""",
        metrics=[RESIDUAL],
        limits={"wall_seconds": 30, "max_metrics_mb": 1},
    )

    supervisor.run_until_idle()

    metrics = lab.metrics(queued["id"])
    series = lab.series(queued["id"])["residual"]
    assert lab.status(queued["id"]) == "succeeded"
    assert series["samples"] == 40000
    assert 0 < series["stored"] < 40000
    assert series["last_step"] == 39999  # the summary covers every sample
    assert metrics["truncated"] is True
    assert lab.event(queued["id"], "RUN_METRICS_TRUNCATED")["payload"]["limit_bytes"] == 1024 * 1024


def test_a_program_puts_its_own_events_on_the_timeline(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(
        """
import json
def event(name, message, severity="info", step=None):
    print(json.dumps({"schema": "numericos.event.v1", "name": name, "message": message,
                      "severity": severity, "step": step}), flush=True)
event("mesh_loaded", "4096 cells")
event("restart", "time step halved after a failed solve", "warning", 120)
"""
    )

    supervisor.run_until_idle()

    events = [e for e in lab.events(queued["id"]) if e["type"] == "RUN_PROGRAM_EVENT"]
    assert [(e["payload"]["name"], e["severity"]) for e in events] == [
        ("mesh_loaded", "info"),
        ("restart", "warning"),
    ]
    assert events[1]["payload"]["message"] == "time step halved after a failed solve"
    assert events[1]["payload"]["step"] == 120
    assert lab.metrics(queued["id"])["program_events"] == 2
    assert lab.output(queued["id"]) == []  # records are not output


def test_a_run_without_metrics_says_that_nothing_numerical_is_observed(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit('print("residual 1e-9")')

    supervisor.run_until_idle()

    metrics = lab.metrics(queued["id"])
    assert metrics["series"] == []
    assert levels(metrics) == {
        "L0": "observed",
        "L1": "not_configured",
        "L2": "not_configured",
        "L3": "not_configured",
    }
    assert "says whether the result is valid" in metrics["coverage"]["levels"][3]["detail"]


def test_a_metric_that_does_not_exist_is_not_found(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(EMIT + 'metric("residual", 1.0)', metrics=[RESIDUAL])
    supervisor.run_until_idle()
    base = f"/v1/runs/{queued['id']}/metrics"

    unknown = lab.http.get(f"{base}/energy")
    unknown_overview = lab.http.get(f"{base}/energy/overview")
    not_a_name = lab.http.get(f"{base}/..%2Fspec.json")
    bad_name = lab.http.get(f"{base}/9lives")
    too_few = lab.http.get(f"{base}/residual/overview", params={"buckets": 1})

    assert (unknown.status_code, error_of(unknown)["code"]) == (404, "NOT_FOUND")
    assert unknown_overview.status_code == 404
    assert not_a_name.status_code in (404, 422)  # never a file outside the series
    assert bad_name.status_code == 422
    assert too_few.status_code == 422
    assert lab.get(f"{base}/residual/overview")["samples"] == 1
