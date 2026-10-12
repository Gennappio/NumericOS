"""Reading what was observed of a run through the API, and controlling it."""

from __future__ import annotations

from typing import Any

from numericos.config import Settings
from numericos.executor import layout
from numericos.executor.worker import Worker
from tests import factories
from tests.api.helpers import UNKNOWN_PROJECT, error_of
from tests.lab import Lab, drive

Json = dict[str, Any]
UNKNOWN_RUN = "run_01J9W2Z4K7QX8YB3N5M6T0R1S2"
UNKNOWN_ARTIFACT = "art_01J9W2Z4K7QX8YB3N5M6T0R1S2"
MB = 1024 * 1024
WAITING = """
    import time
    print("ready", flush=True)
    time.sleep(60)
    """


def texts(page: Json) -> list[str]:
    return [line["text"] for line in page["lines"]]


def test_output_is_read_by_cursor_by_tail_and_by_stream(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(
        """
        import sys
        for n in range(5):
            print("line", n)
        print("problem", file=sys.stderr)
        """
    )
    supervisor.run_until_idle()
    path = f"/v1/runs/{queued['id']}/logs"

    first = lab.get(path, limit=2, stream="stdout")
    rest = lab.get(path, after=first["next_cursor"], stream="stdout")
    everything = lab.get(path)
    tail = lab.get(path, tail=2)

    assert texts(first) == ["line 0", "line 1"]
    assert (first["has_more"], first["complete"]) == (True, False)
    assert texts(rest) == ["line 2", "line 3", "line 4"]
    assert (rest["has_more"], rest["complete"]) == (False, True)
    assert texts(lab.get(path, stream="stderr")) == ["problem"]
    assert sorted(texts(lab.get(path, stream=["stdout", "stderr"]))) == sorted(texts(everything))
    assert len(everything["lines"]) == 6
    assert texts(tail) == texts(everything)[-2:]
    assert tail["next_cursor"] == everything["next_cursor"]
    line = everything["lines"][0]
    assert set(line) == {"t", "stream", "text", "metric", "cut"}
    assert (line["stream"], line["metric"], line["cut"]) == ("stdout", False, False)
    assert [item["t"] for item in everything["lines"]] == sorted(
        item["t"] for item in everything["lines"]
    )


def test_a_reader_is_told_when_nothing_more_will_come(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(WAITING)
    path = f"/v1/runs/{queued['id']}/logs"

    while_queued = lab.get(path)
    drive(supervisor, lambda: lab.output(queued["id"]) == ["ready"])
    while_running = lab.get(path)
    lab.cancel(queued["id"])
    supervisor.run_until_idle()
    after_the_end = lab.get(path, after=while_running["next_cursor"])

    assert while_queued == {"lines": [], "next_cursor": 0, "has_more": False, "complete": False}
    assert (while_running["has_more"], while_running["complete"]) == (False, False)
    assert after_the_end == {
        "lines": [],
        "next_cursor": while_running["next_cursor"],
        "has_more": False,
        "complete": True,
    }


def test_a_reading_that_cannot_be_answered_is_refused_with_its_reason(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit('print("one line")')
    supervisor.run_until_idle()
    path = f"/v1/runs/{queued['id']}/logs"
    end = lab.get(path)["next_cursor"]

    both = lab.http.get(path, params={"after": 0, "tail": 5})
    ahead = lab.http.get(path, params={"after": end + 1})
    inside = lab.http.get(path, params={"after": 3})
    stream = lab.http.get(path, params={"stream": "stdin"})
    unknown = lab.http.get(f"/v1/runs/{UNKNOWN_RUN}/logs")

    assert (both.status_code, error_of(both)["code"]) == (422, "VALIDATION_ERROR")
    assert (ahead.status_code, error_of(ahead)["code"]) == (409, "CURSOR_AHEAD")
    assert error_of(ahead)["details"] == {"cursor": end + 1, "size": end}
    assert (inside.status_code, error_of(inside)["code"]) == (422, "VALIDATION_ERROR")
    assert (stream.status_code, error_of(stream)["code"]) == (422, "VALIDATION_ERROR")
    assert (unknown.status_code, error_of(unknown)["code"]) == (404, "NOT_FOUND")


def test_resource_samples_follow_the_program_and_are_summarised_on_the_run(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(
        """
        import time
        block = b"x" * (40 * 1024 * 1024)
        end = time.time() + 1.2
        while time.time() < end:
            sum(range(2000))
        """
    )
    supervisor.run_until_idle()
    path = f"/v1/runs/{queued['id']}/resources"

    page = lab.get(path)
    samples = page["samples"]
    summary = lab.run(queued["id"])["resources"]

    assert (page["complete"], page["has_more"]) == (True, False)
    assert len(samples) >= 3
    assert [sample["elapsed"] for sample in samples] == sorted(s["elapsed"] for s in samples)
    assert max(sample["rss_bytes"] for sample in samples) > 40 * MB
    assert max(sample["cpu_percent"] for sample in samples) > 20
    assert max(sample["processes"] for sample in samples) == 1
    assert {sample["phase"] for sample in samples} == {"program"}
    assert summary["samples"] == len(samples)
    assert summary["max_rss_bytes"] == max(sample["rss_bytes"] for sample in samples)
    assert summary["last"] == samples[-1]
    outcome = lab.run(queued["id"])["outcome"]
    assert outcome["sampled"] == {
        "samples": len(samples),
        "max_rss_bytes": summary["max_rss_bytes"],
    }
    assert outcome["rusage"]["cpu_user_seconds"] > 0.5  # exact, from the system at exit
    assert outcome["rusage"]["max_rss_bytes"] > 40 * MB
    assert lab.get(path, tail=1)["samples"] == samples[-1:]
    assert lab.get(path, after=page["next_cursor"])["samples"] == []


def test_the_events_of_one_run_are_read_apart_from_the_rest_of_the_ledger(
    lab: Lab, supervisor: Worker
) -> None:
    first = lab.submit('print("a")')
    lab.submit('print("b")')
    supervisor.run_until_idle()
    path = f"/v1/runs/{first['id']}/events"

    page = lab.get(path)
    events = page["events"]
    newest = lab.get(path, order="desc", limit=1)["events"]
    later = lab.get(path, after=events[0]["seq"])["events"]
    unknown = lab.http.get(f"/v1/runs/{UNKNOWN_RUN}/events")

    assert [event["type"] for event in events] == ["RUN_QUEUED", "RUN_STARTED", "RUN_FINISHED"]
    assert {event["run_id"] for event in events} == {first["id"]}
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)
    assert page["has_more"] is False
    assert newest == events[-1:]
    assert later == events[1:]
    assert unknown.status_code == 404


def test_artifacts_are_listed_with_checksums_and_served_from_the_run_directory(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    queued = lab.submit(
        """
        import os
        out = os.environ["NUMERICOS_OUTPUT_DIR"]
        os.makedirs(os.path.join(out, "fields"))
        with open(os.path.join(out, "fields", "u.csv"), "w") as handle:
            handle.write("x,u\\n0,1\\n")
        os.symlink("/etc/hosts", os.path.join(out, "hosts"))
        """
    )
    before = lab.artifacts(queued["id"])
    supervisor.run_until_idle()

    artifacts = lab.artifacts(queued["id"])
    table = artifacts["outputs/fields/u.csv"]
    content = lab.http.get(f"/v1/artifacts/{table['id']}/content")
    (layout.run_dir(settings.data_dir, queued["id"]) / "outputs/fields/u.csv").unlink()
    removed = lab.http.get(f"/v1/artifacts/{table['id']}/content")
    unknown = lab.http.get(f"/v1/artifacts/{UNKNOWN_ARTIFACT}/content")

    assert before == {}  # files are registered when the run ends
    assert (table["kind"], table["media_type"], table["size_bytes"]) == ("result", "text/csv", 8)
    assert "outputs/hosts" not in artifacts  # a link out of the run directory is not a result
    assert artifacts["exit.json"]["kind"] == "outcome"
    assert content.content == b"x,u\n0,1\n"
    assert content.headers["content-type"].startswith("text/csv")
    assert (removed.status_code, error_of(removed)["code"]) == (409, "ARTIFACT_MISSING")
    assert (unknown.status_code, error_of(unknown)["code"]) == (404, "NOT_FOUND")


def test_the_api_says_whether_a_supervisor_is_alive_and_what_it_runs(
    lab: Lab, settings: Settings
) -> None:
    nobody = lab.get("/v1/workers")
    worker = Worker(settings, max_parallel=3, poll_interval=0.05)
    worker.start()
    try:
        queued = lab.submit(WAITING)
        drive(worker, lambda: lab.status(queued["id"]) == "running")
        serving = lab.get("/v1/workers")
        lab.cancel(queued["id"])
        worker.run_until_idle()
    finally:
        worker.stop()
    afterwards = lab.get("/v1/workers")

    assert nobody == {"workers": [], "alive": 0}
    assert serving["alive"] == 1
    listed = serving["workers"][0]
    assert (listed["id"], listed["alive"], listed["stopped_at"]) == (worker.id, True, None)
    assert (listed["active_runs"], listed["max_parallel_runs"]) == (1, 3)
    assert afterwards["alive"] == 0
    assert afterwards["workers"][0]["alive"] is False
    assert afterwards["workers"][0]["stopped_at"] is not None
    assert afterwards["workers"][0]["active_runs"] == 0


def test_the_newest_runs_of_a_project_are_listed_across_its_experiments(lab: Lab) -> None:
    one = lab.experiment(lab.program("print(1)"))
    two = lab.experiment(lab.program("print(2)"))
    queued = [lab.queue(one)["id"], lab.queue(two)["id"], lab.queue(one)["id"]]
    path = f"/v1/projects/{lab.project['id']}/runs"

    everything = [run["id"] for run in lab.get(path)["runs"]]
    newest_two = [run["id"] for run in lab.get(path, limit=2)["runs"]]
    unknown = lab.http.get(f"/v1/projects/{UNKNOWN_PROJECT}/runs")

    assert everything == queued[::-1]
    assert newest_two == queued[:0:-1]
    assert unknown.status_code == 404


def test_a_cancel_request_is_validated_like_any_other(lab: Lab) -> None:
    queued = lab.submit('print("x")')
    path = f"/v1/runs/{queued['id']}:cancel"

    too_long = lab.http.post(path, json={"reason": "r" * 301})
    extra = lab.http.post(path, json={"reason": "", "force": True})
    unknown = lab.http.post(f"/v1/runs/{UNKNOWN_RUN}:cancel", json={})
    without_body = lab.http.post(path)

    assert (too_long.status_code, extra.status_code) == (422, 422)
    assert (unknown.status_code, error_of(unknown)["code"]) == (404, "NOT_FOUND")
    assert without_body.status_code == 200
    assert without_body.json()["status"] == "cancelled"


def test_registering_the_same_experiment_again_can_return_the_existing_one(lab: Lab) -> None:
    path = f"/v1/projects/{lab.project['id']}/experiments"
    body = {"name": "Stability against dt", "protocol": factories.protocol()}
    other = {**body, "protocol": factories.protocol(controls={"grid": 64, "steps": 100})}

    first = lab.http.post(path, params={"reuse": "true"}, json=body)
    again = lab.http.post(path, params={"reuse": "true"}, json=body)
    changed = lab.http.post(path, params={"reuse": "true"}, json=other)
    duplicate = lab.http.post(path, json=body)

    assert [r.status_code for r in (first, again, changed, duplicate)] == [201, 200, 201, 201]
    assert again.json() == first.json()
    assert len({r.json()["id"] for r in (first, changed, duplicate)}) == 3
    created = [
        event
        for event in lab.get("/v1/events", project_id=lab.project["id"], limit=1000)["events"]
        if event["type"] == "EXPERIMENT_CREATED"
    ]
    assert len(created) == 3  # the reused one caused no event
