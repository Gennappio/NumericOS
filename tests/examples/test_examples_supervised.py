"""The examples of this repository, run from their own contract files under a supervisor.

These are the acceptance experiments of the metrics ticket: real programs, real series, a real
instability stopped by an explicit guardrail, and a run that exits normally without having
reached the accuracy it reports.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from typing import Any

import pytest

from numericos.executor.worker import Worker
from tests.lab import Lab

Json = dict[str, Any]


def levels(metrics: Json) -> dict[str, str]:
    return {level["level"]: level["status"] for level in metrics["coverage"]["levels"]}


def test_a_stable_heat_run_is_observed_at_every_level_it_declares(
    lab: Lab, supervisor: Worker
) -> None:
    experiment = lab.register(lab.install_example("heat2d-python"))
    queued = lab.queue(experiment, parameters={"dt": 0.0002})

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    metrics = lab.metrics(run["id"])
    series = lab.series(run["id"])
    assert (run["status"], run["exit_code"]) == ("succeeded", 0)
    assert sorted(series) == [
        "cpu_time",
        "l2_error",
        "max_abs_u",
        "max_rss",
        "norm_l2",
        "wall_time",
    ]
    assert {name: item["source"] for name, item in series.items()} == {
        "l2_error": "instrumentation",
        "max_abs_u": "instrumentation",
        "norm_l2": "parser",
        "wall_time": "supervisor",
        "cpu_time": "supervisor",
        "max_rss": "supervisor",
    }
    assert all(item["declared"] and item["non_finite"] == 0 for item in series.values())
    # Steps 0, 10, ..., 600: one sample per report, by record and by parsed line alike.
    assert {series[name]["samples"] for name in ("l2_error", "max_abs_u", "norm_l2")} == {61}
    assert (series["max_abs_u"]["first_step"], series["max_abs_u"]["last_step"]) == (0, 600)
    assert series["max_abs_u"]["max_value"] == 1.0  # the invariant of the stable scheme
    assert (metrics["records"], metrics["parsed_lines"]) == (122, 61)
    assert metrics["diagnostics"] == []
    assert metrics["truncated"] is False

    # The error of the scheme has a closed form for this initial condition.
    h, r = 1 / 32, 0.0002 * 1024
    g = 1.0 - 8.0 * r * math.sin(math.pi * h / 2.0) ** 2
    expected = 0.5 * abs(g**600 - math.exp(-2.0 * math.pi**2 * 600 * 0.0002))
    assert series["l2_error"]["last_value"] == pytest.approx(expected, abs=1e-13)
    assert series["norm_l2"]["last_value"] == pytest.approx(0.5 * g**600, rel=1e-9)

    # What the supervisor measures has one exact sample, taken when the program ended.
    usage = run["outcome"]["rusage"]
    assert series["wall_time"]["samples"] == 1
    assert series["wall_time"]["last_value"] == run["outcome"]["program_seconds"]
    assert series["cpu_time"]["last_value"] == pytest.approx(
        usage["cpu_user_seconds"] + usage["cpu_system_seconds"]
    )
    assert series["max_rss"]["last_value"] == usage["max_rss_bytes"]

    assert levels(metrics) == {
        "L0": "observed",
        "L1": "observed",
        "L2": "observed",
        "L3": "not_configured",  # nothing has judged the result
    }
    assert {item["status"] for item in metrics["coverage"]["metrics"]} == {"observed"}
    assert metrics["coverage"]["undeclared"] == []


def test_the_series_of_a_run_are_read_by_cursor_and_in_buckets(
    lab: Lab, supervisor: Worker
) -> None:
    experiment = lab.register(lab.install_example("heat2d-python"))
    queued = lab.queue(experiment, parameters={"dt": 0.0002})
    supervisor.run_until_idle()
    path = f"/v1/runs/{queued['id']}/metrics/l2_error"

    first = lab.get(path, limit=3)
    rest = lab.get(path, after=first["next_cursor"], limit=5000)
    last = lab.get(path, tail=1)
    overview = lab.get(f"{path}/overview", buckets=10)
    parsed = lab.samples(queued["id"], "norm_l2")

    assert [sample["step"] for sample in first["samples"]] == [0, 10, 20]
    assert [sample["time"] for sample in first["samples"]] == pytest.approx([0.0, 0.002, 0.004])
    assert first["samples"][0]["value"] == 0.0  # the initial condition is the exact solution
    assert (first["has_more"], first["complete"]) == (True, False)
    assert len(rest["samples"]) == 58 and rest["complete"] is True
    assert last["samples"][0]["step"] == 600
    assert (parsed[1]["step"], parsed[1]["time"]) == (10, 0.002)  # both read from the line
    assert set(first["samples"][0]) == {
        "t",
        "value",
        "non_finite",
        "step",
        "time",
        "source_timestamp",
    }

    buckets = overview["buckets"]
    assert overview["samples"] == 61 and overview["complete"] is True
    assert len(buckets) <= 10
    assert sum(bucket["samples"] for bucket in buckets) == 61
    assert (buckets[0]["first_step"], buckets[-1]["last_step"]) == (0, 600)
    assert max(bucket["max_value"] for bucket in buckets) == max(
        sample["value"] for sample in [*first["samples"], *rest["samples"]]
    )
    assert overview["next_cursor"] == rest["next_cursor"]

    # Records are kept as samples, not as output; the parsed progress lines stay output.
    logs = lab.get(f"/v1/runs/{queued['id']}/logs", limit=5000)["lines"]
    assert not any("numericos.metric.v1" in line["text"] for line in logs)
    assert sum(line["metric"] for line in logs) == 61
    assert lab.run(queued["id"])["outcome"]["output"]["records"] == 122
    artifacts = lab.artifacts(queued["id"])
    assert artifacts["metrics/l2_error.jsonl"]["kind"] == "metric_series"
    assert artifacts["metrics.json"]["kind"] == "metric_summary"
    assert artifacts["outputs/u_final.csv"]["kind"] == "result"


def test_an_unstable_heat_run_is_stopped_by_the_guardrail_and_stays_inspectable(
    lab: Lab, supervisor: Worker
) -> None:
    experiment = lab.register(lab.install_example("heat2d-python"))
    queued = lab.queue(experiment, parameters={"dt": 0.0003})  # r = 0.3072, above the limit

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    series = lab.series(run["id"])
    violated = lab.event(run["id"], "RUN_GUARDRAIL_VIOLATED")
    assert (run["status"], run["failure_class"]) == ("failed", "numerical_instability")
    assert run["status_reason"].startswith(
        "metric max_abs_u was above 1.0 for 3 consecutive sample(s); the last one was"
    )
    assert run["outcome"]["termination"]["reason"] == "guardrail"
    assert run["exit_signal"] == "SIGTERM"  # stopped, it did not end by itself
    assert violated["severity"] == "error"
    assert violated["payload"]["metric"] == "max_abs_u"
    assert (violated["payload"]["threshold"], violated["payload"]["consecutive"]) == (1.0, 3)
    assert violated["payload"]["step"] == 130  # beyond the bound at 110, 120 and 130
    assert violated["payload"]["value"] > 1.0
    # The run is evidence: its series are there up to the moment it was stopped.
    assert series["max_abs_u"]["last_value"] > 1.0
    assert 130 <= series["max_abs_u"]["last_step"] < 600
    assert series["l2_error"]["samples"] == series["max_abs_u"]["samples"]
    assert series["wall_time"]["samples"] == 1  # measured for a stopped program as well
    assert "outputs/u_final.csv" not in lab.artifacts(run["id"])  # it never got that far
    order = lab.event_types(run["id"])
    assert order.index("RUN_GUARDRAIL_VIOLATED") < order.index("RUN_FINISHED")


def test_a_non_finite_metric_is_a_hard_event_and_a_typed_sample(
    lab: Lab, supervisor: Worker
) -> None:
    contract = lab.install_example("heat2d-python")
    contract["name"] = "heat2d-overflow"
    contract["independent_variables"] = {"dt": [0.0078125]}  # r = 0.5 on the 8 x 8 grid
    contract["controls"] = {"grid": 8, "steps": 1200, "alpha": 1.0, "report_every": 50}
    contract["guardrails"] = {"non_finite": "halt"}  # no bound: only NaN and infinity stop it
    queued = lab.queue(lab.register(contract), parameters={"dt": 0.0078125})

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    event = lab.event(run["id"], "RUN_METRIC_NON_FINITE")
    response = lab.http.get(f"/v1/runs/{run['id']}/metrics/{event['payload']['metric']}")
    last = response.json()["samples"][-1]
    assert (run["status"], run["failure_class"]) == ("failed", "numerical_instability")
    assert re.fullmatch(
        r"metric (max_abs_u|l2_error) became (inf|nan) at step \d+", run["status_reason"]
    )
    assert event["severity"] == "error"
    assert event["payload"]["action"] == "halt"
    assert (last["value"], last["non_finite"]) == (None, event["payload"]["value"])
    assert "NaN" not in response.text and "Infinity" not in response.text  # valid JSON only
    series = lab.series(run["id"])[event["payload"]["metric"]]
    assert series["non_finite"] >= 1 and series["last_non_finite"] == event["payload"]["value"]
    json.loads(json.dumps(lab.metrics(run["id"]), allow_nan=False))  # no NaN anywhere


@pytest.mark.skipif(shutil.which("c++") is None, reason="needs a C++ compiler")
def test_conjugate_gradient_in_single_precision_exits_normally_without_the_accuracy_it_reports(
    lab: Lab, supervisor: Worker
) -> None:
    experiment = lab.register(lab.install_example("sparse-cg-cpp"))
    double = lab.queue(experiment, parameters={"precision": "double"})
    single = lab.queue(experiment, parameters={"precision": "single"})

    supervisor.run_until_idle(timeout=300)

    exact, reduced = lab.run(double["id"]), lab.run(single["id"])
    in_double, in_single = lab.series(double["id"]), lab.series(single["id"])
    # Both processes end normally and both say they converged.
    assert (exact["status"], reduced["status"]) == ("succeeded", "succeeded")
    assert (in_double["converged"]["last_value"], in_single["converged"]["last_value"]) == (1, 1)
    assert in_double["residual_rel"]["last_value"] <= 1e-10
    assert in_single["residual_rel"]["last_value"] <= 1e-10
    # In double precision the true residual agrees with the reported one.
    assert in_double["true_residual_rel"]["last_value"] < 1e-9
    assert in_double["error_rel"]["last_value"] < 1e-7
    # In single precision it is orders of magnitude away from it: the recurrence residual
    # is not the residual, and the residual is not the error.
    assert in_single["true_residual_rel"]["last_value"] > 1e-8
    assert (
        in_single["true_residual_rel"]["last_value"] > 100 * in_single["residual_rel"]["last_value"]
    )
    assert in_single["error_rel"]["last_value"] > 100 * in_double["error_rel"]["last_value"]
    # The recurrence residual decreases overall while CG iterates.
    assert in_double["residual_rel"]["last_value"] < in_double["residual_rel"]["first_value"]
    assert in_double["iterations"]["last_value"] == in_double["residual_rel"]["last_step"]

    # Provenance of a compiled program: the binary that ran and the compiler that built it.
    executable = exact["environment"]["executable"]
    assert executable["path"].endswith("/code/examples/sparse-cg-cpp/cg")
    assert executable["sha256"] is not None
    assert executable["sha256"] == reduced["environment"]["executable"]["sha256"]  # same build
    (probe,) = exact["environment"]["probes"]
    assert (probe["argv"], probe["exit_code"]) == (["c++", "--version"], 0)
    results = [
        name for name, item in lab.artifacts(exact["id"]).items() if item["kind"] == "result"
    ]
    assert results == []  # the binary is a build product, not a result
    assert levels(lab.metrics(exact["id"]))["L2"] == "observed"
