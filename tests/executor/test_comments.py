"""Comments on what the agent wrote, and what Clarify and Resolve make of them, under a real
supervisor with the stand-in as the agent."""

from __future__ import annotations

import json

from numericos.agents import layout
from numericos.config import Settings
from numericos.executor.worker import Worker
from tests.lab import Json, Lab, drive

SOLVER = "examples/heat2d-python/heat2d.py"


def theory(lab: Lab, supervisor: Worker, instructions: str = f"READ {SOLVER}") -> Json:
    lab.generate("theory", instructions)
    written: Json = drive(supervisor, lambda: _settled(lab.single("theory")))
    return written


def _settled(document: Json | None) -> Json | None:
    return document if document and document["pending_message_id"] is None else None


def answered(lab: Lab, target: Json) -> Json | None:
    """The comments of a text once no turn is answering any of them."""
    listed = lab.comments(target)
    return listed if listed["pending_message_id"] is None else None


def prompt_of(lab: Lab, session_id: str, turn: int = 0) -> str:
    messages = lab.get(f"/v1/agent-sessions/{session_id}/messages")["messages"]
    return str([m for m in messages if m["role"] == "user"][turn]["markdown"])


def refused(lab: Lab, body: Json) -> Json:
    response = lab.http.post("/v1/annotations", json=body)
    assert response.status_code == 422, response.text
    error: Json = response.json()["error"]["details"]["errors"][0]
    return error


def test_a_comment_is_attached_to_an_exact_passage_or_not_at_all(
    lab: Lab, supervisor: Worker
) -> None:
    document = theory(lab, supervisor)
    text = document["markdown"]
    target = {"target_type": "document", "target_id": document["id"]}

    by_quote = lab.comment(document, "clarification", "homogeneous Dirichlet", "Why homogeneous?")
    start = text.index("central differences")
    by_offsets = lab.comment(
        document,
        "change",
        "central differences",
        "Use a 9-point stencil.",
        start_offset=start,
        end_offset=start + len("central differences"),
    )
    note = lab.comment(document, "note", "Forward Euler")
    listed = lab.comments(document)

    assert by_quote["status"] == "open" and by_quote["anchor_state"] == "attached"
    assert text[by_quote["start_offset"] : by_quote["end_offset"]] == "homogeneous Dirichlet"
    assert by_quote["prefix"].endswith("with ") and by_quote["suffix"].startswith(" boundary")
    assert by_quote["target_version"] == 1
    assert (note["kind"], note["body"]) == ("note", "")
    # In the order of their passages in the text, not of their creation.
    assert [item["id"] for item in listed["annotations"]] == [
        by_quote["id"],
        note["id"],
        by_offsets["id"],
    ]
    assert listed["target_version"] == 1 and listed["pending_message_id"] is None

    wrong_place = {
        **target,
        "kind": "note",
        "quote": "Forward Euler",
        "start_offset": 0,
        "end_offset": 13,
    }
    assert refused(lab, wrong_place)["type"] == "anchor_mismatch"
    assert refused(lab, {**target, "kind": "note", "quote": "(1)"})["type"] == "quote_ambiguous"
    assert refused(lab, {**target, "kind": "note", "quote": "not in it"})["type"] == "quote_missing"
    empty = lab.http.post(
        "/v1/annotations", json={**target, "kind": "clarification", "quote": "Forward Euler"}
    )
    assert empty.status_code == 422  # a request must say what it asks
    unknown = lab.http.post(
        "/v1/annotations",
        json={
            "target_type": "document",
            "target_id": "doc_01J9W2Z4K7QX8YB3N5M6T0R1S2",
            "kind": "note",
            "quote": "x",
        },
    )
    assert unknown.status_code == 404


def test_an_open_comment_is_reworded_or_withdrawn(lab: Lab, supervisor: Worker) -> None:
    document = theory(lab, supervisor)
    comment = lab.comment(document, "clarification", "Forward Euler", "Why?")

    reworded = lab.http.patch(
        f"/v1/annotations/{comment['id']}",
        json={"version": 1, "body": "Why not implicit?", "kind": "change"},
    ).json()
    stale = lab.http.patch(f"/v1/annotations/{comment['id']}", json={"version": 1, "body": "x"})
    dismissed = lab.http.post(f"/v1/annotations/{comment['id']}:dismiss").json()
    after = lab.http.patch(f"/v1/annotations/{comment['id']}", json={"version": 3, "body": "y"})

    assert (reworded["body"], reworded["kind"], reworded["version"]) == (
        "Why not implicit?",
        "change",
        2,
    )
    assert stale.status_code == 409
    assert dismissed["status"] == "dismissed"
    assert after.status_code == 422  # only an open comment can be changed
    kinds = [
        e["type"] for e in lab.get("/v1/events", project_id=lab.project["id"], limit=1000)["events"]
    ]
    assert kinds.count("ANNOTATION_CREATED") == 1 and kinds.count("ANNOTATION_UPDATED") == 2


def test_clarify_answers_every_clarification_together_and_leaves_the_text_alone(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    document = theory(lab, supervisor)
    first = lab.comment(document, "clarification", "homogeneous Dirichlet", "Why homogeneous?")
    second = lab.comment(document, "clarification", "stable when", 'Derive the "bound".\nPlease.')
    change = lab.comment(document, "change", "central differences", "Use a 9-point stencil.")
    lab.comment(document, "note", "Forward Euler", "check this")

    sent = lab.send_comments("clarify", document, instructions="Rispondi in italiano.")
    waiting = lab.comments(document)
    listed = drive(supervisor, lambda: answered(lab, document))

    assert sent["queued"] == 2
    assert waiting["pending_message_id"] == sent["message_id"]
    assert {a["status"] for a in waiting["annotations"] if a["kind"] == "clarification"} == {
        "pending"
    }
    by_id = {item["id"]: item for item in listed["annotations"]}
    assert by_id[first["id"]]["status"] == "answered"
    assert by_id[first["id"]]["response_markdown"].startswith(
        'About "homogeneous Dirichlet": the bound'
    )
    assert by_id[first["id"]]["message_id"] == sent["message_id"]
    assert by_id[first["id"]]["responded_at"] is not None
    assert by_id[second["id"]]["status"] == "answered"
    assert by_id[change["id"]]["status"] == "open"  # Clarify sends clarifications only
    after = lab.single("theory")
    assert after is not None
    assert (after["version"], after["markdown"]) == (1, document["markdown"])  # untouched

    # One turn, in a session of its own, read-only, with the text and both requests.
    session = lab.get(f"/v1/agent-sessions/{sent['session_id']}")
    assert (session["task"], session["permission_mode"]) == ("clarify", "read_only")
    prompt = prompt_of(lab, sent["session_id"])
    assert prompt.startswith("[NumericOS task: clarify]")
    assert "A researcher is reading the theory of this project" in prompt
    assert "--- document start ---\n# Explicit scheme" in prompt
    assert f'1. id: {first["id"]}\n   passage: "homogeneous Dirichlet"' in prompt
    assert "[[homogeneous Dirichlet]] boundary conditions" in prompt
    assert '   request: "Derive the \\"bound\\".\\nPlease."' in prompt  # one line per request
    assert "9-point stencil" not in prompt
    assert prompt.rstrip().endswith("Rispondi in italiano.")
    spec = json.loads(
        (layout.turn_dir(settings.data_dir, sent["message_id"]) / layout.SPEC).read_text()
    )
    assert "--json-schema" in spec["argv"]
    events = [
        e["type"] for e in lab.turn_events(sent["message_id"]) if e["type"].startswith("ANNOT")
    ]
    assert events == ["ANNOTATIONS_SENT", "ANNOTATIONS_ANSWERED"]


def test_a_later_clarify_continues_the_same_session_without_repeating_the_text(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    document = theory(lab, supervisor)
    lab.comment(document, "clarification", "homogeneous Dirichlet", "Why homogeneous?")
    first = lab.send_comments("clarify", document)
    lab.comment(document, "clarification", "stable when", "Derive it.")
    busy = lab.http.post(
        "/v1/annotations:clarify", json={"target_type": "document", "target_id": document["id"]}
    )
    drive(supervisor, lambda: answered(lab, document))
    second = lab.send_comments("clarify", document)
    drive(supervisor, lambda: answered(lab, document))
    nothing = lab.http.post(
        "/v1/annotations:clarify", json={"target_type": "document", "target_id": document["id"]}
    )

    assert busy.status_code == 409 and busy.json()["error"]["code"] == "SESSION_BUSY"
    assert second["session_id"] == first["session_id"]
    later = prompt_of(lab, second["session_id"], turn=1)
    assert later.startswith("[NumericOS task: clarify]\nMore requests about the same text")
    assert "--- document start ---" not in later and "Derive it." in later
    spec = json.loads(
        (layout.turn_dir(settings.data_dir, second["message_id"]) / layout.SPEC).read_text()
    )
    assert spec["resume"] is True
    assert nothing.status_code == 422
    assert nothing.json()["error"]["details"]["errors"][0]["type"] == "nothing_to_send"
    assert all(a["status"] == "answered" for a in lab.comments(document)["annotations"])


def test_a_request_the_turn_did_not_answer_is_open_again_and_says_why(
    lab: Lab, supervisor: Worker
) -> None:
    document = theory(lab, supervisor)
    kept = lab.comment(document, "clarification", "homogeneous Dirichlet", "Why?")
    left_out = lab.comment(document, "clarification", "stable when", "Derive it.")

    lab.send_comments("clarify", document, instructions=f"OMIT {left_out['id']}")
    drive(supervisor, lambda: answered(lab, document))
    partly = {a["id"]: a for a in lab.comments(document)["annotations"]}
    lab.send_comments("clarify", document, instructions="FAIL the model refused")
    drive(supervisor, lambda: answered(lab, document))
    failed = lab.comment_by_id(document, left_out["id"])
    queued = lab.send_comments("clarify", document, instructions="")
    lab.cancel_turn(queued["message_id"], "changed my mind")
    cancelled = lab.comment_by_id(document, left_out["id"])

    assert partly[kept["id"]]["status"] == "answered"
    assert (partly[left_out["id"]]["status"], partly[left_out["id"]]["status_reason"]) == (
        "open",
        "the agent gave no answer to this request",
    )
    assert failed["status"] == "open"
    assert failed["status_reason"] == (
        "the agent's turn ended failed: error_during_execution: the model refused"
    )
    # A turn cancelled before any supervisor took it is ended by the API, which tells the comments.
    assert (cancelled["status"], cancelled["pending_message_id"]) == ("open", None)
    assert cancelled["status_reason"] == "the agent's turn ended cancelled: changed my mind"


def test_resolve_edits_the_files_decides_per_request_and_rewrites_the_text(
    lab: Lab, supervisor: Worker
) -> None:
    document = theory(lab, supervisor)
    applied = lab.comment(document, "change", "Forward Euler", "Make the scheme implicit.")
    declined = lab.comment(document, "change", "homogeneous Dirichlet", "Rewrite it in Fortran.")
    survives = lab.comment(document, "note", "central differences", "second order")
    lost = lab.comment(
        document, "clarification", "explicit\nfinite-difference scheme", "Which one?"
    )

    read_only = lab.http.post(
        "/v1/annotations:resolve",
        json={
            "target_type": "document",
            "target_id": document["id"],
            "permission_mode": "read_only",
        },
    )
    sent = lab.send_comments(
        "resolve",
        document,
        instructions=(
            f"WRITE {SOLVER}::print('implicit now')\n"
            f"DECLINE {declined['id']}::A rewrite in Fortran is a different project.\n"
            "REPLACE explicit=>implicit\nREPLACE Forward Euler=>Backward Euler"
        ),
    )
    listed = drive(supervisor, lambda: answered(lab, document))
    by_id = {item["id"]: item for item in listed["annotations"]}
    after = lab.single("theory")
    turn = lab.message(sent["message_id"])

    assert read_only.status_code == 422
    assert sent["queued"] == 2
    assert lab.get(f"/v1/agent-sessions/{sent['session_id']}")["permission_mode"] == "edit"
    assert by_id[applied["id"]]["status"] == "resolved"
    assert (
        by_id[applied["id"]]["response_markdown"]
        == 'Changed what "Forward Euler" says, in `heat2d.py`.'
    )
    assert (by_id[declined["id"]]["status"], by_id[declined["id"]]["response_markdown"]) == (
        "declined",
        "A rewrite in Fortran is a different project.",
    )
    # The agent edited the file of the project directly.
    assert (lab.repo.root / SOLVER).read_text() == "print('implicit now')"
    assert turn["files_written"] == [SOLVER]
    # Its revised text is the new version of the document, current with the file as it is now.
    assert after is not None
    assert after["version"] == 2
    assert (
        "Backward Euler in time" in after["markdown"] and "Forward Euler" not in after["markdown"]
    )
    # "Explicit" in the title is capitalised: the replacement of "explicit" leaves it.
    assert after["title"] == "Explicit scheme for the 2D heat equation"
    assert after["sources"] == [{"path": SOLVER, "sha": lab.repo.git("hash-object", SOLVER)}]
    assert after["stale"] is False
    assert after["message_id"] == sent["message_id"]
    # Every comment was looked for again in the new text.
    moved = by_id[survives["id"]]
    assert (moved["anchor_state"], moved["target_version"]) == ("attached", 2)
    assert after["markdown"][moved["start_offset"] : moved["end_offset"]] == "central differences"
    assert by_id[lost["id"]]["anchor_state"] == "detached"  # its passage was rewritten
    assert by_id[applied["id"]]["anchor_state"] == "detached"
    prompt = prompt_of(lab, sent["session_id"])
    assert prompt.startswith("[NumericOS task: resolve]")
    assert "give the complete revised text in `document`" in prompt
    assert "second order" not in prompt and "Which one?" not in prompt  # change requests only
    finished = [
        e for e in lab.turn_events(sent["message_id"]) if e["type"] == "ANNOTATIONS_ANSWERED"
    ]
    assert finished[0]["payload"]["applied"] == 1 and finished[0]["payload"]["declined"] == 1
    assert finished[0]["payload"]["document_version"] == 2
    assert finished[0]["payload"]["comments_detached"] == 2


def test_an_answer_of_a_conversation_is_commented_but_never_rewritten(
    lab: Lab, supervisor: Worker
) -> None:
    session = lab.open_session()
    turn = lab.ask(session, "Is it stable?")
    drive(supervisor, lambda: lab.turn_status(turn["id"]) == "final")
    answer = lab.message(turn["id"])
    question = lab.comment(answer, "clarification", "explicit scheme", "Which scheme exactly?")
    change = lab.comment(
        answer, "change", "is stable when", "Add a check of this bound to the code."
    )

    clarified = lab.send_comments("clarify", answer)
    drive(supervisor, lambda: answered(lab, answer))
    resolved = lab.send_comments(
        "resolve", answer, permission_mode="full", instructions="REPLACE explicit=>implicit"
    )
    drive(supervisor, lambda: answered(lab, answer))

    assert lab.comment_by_id(answer, question["id"])["status"] == "answered"
    assert lab.comment_by_id(answer, change["id"])["status"] == "resolved"
    assert lab.message(turn["id"])["markdown"] == answer["markdown"]  # a record
    assert lab.comment_by_id(answer, question["id"])["anchor_state"] == "attached"
    # Neither grew the conversation: each has a session of its own for this answer.
    messages = lab.get(f"/v1/agent-sessions/{session['id']}/messages")["messages"]
    assert len(messages) == 2
    assert len({session["id"], clarified["session_id"], resolved["session_id"]}) == 3
    prompt = prompt_of(lab, resolved["session_id"])
    assert "--- question start ---\nIs it stable?" in prompt
    assert "it is a record and is not\nrewritten" in prompt or "is not rewritten" in prompt
    assert lab.get(f"/v1/agent-sessions/{resolved['session_id']}")["permission_mode"] == "full"
    pending = lab.http.post(
        "/v1/annotations",
        json={
            "target_type": "message",
            "target_id": lab.ask(session, "SLEEP 30")["id"],
            "kind": "note",
            "quote": "x",
        },
    )
    assert pending.status_code == 422  # an answer that is still being written


def test_a_text_written_again_keeps_the_comments_whose_passage_is_still_in_it(
    lab: Lab, supervisor: Worker
) -> None:
    document = theory(lab, supervisor)
    kept = lab.comment(document, "note", "Forward Euler", "keep")

    same = theory(lab, supervisor)  # the stand-in writes the same text again
    kept_after = lab.comment_by_id(same, kept["id"])
    other = theory(lab, supervisor, "ECHO # Another text entirely")
    lost = lab.comment_by_id(other, kept["id"])

    assert (same["version"], kept_after["anchor_state"], kept_after["target_version"]) == (
        2,
        "attached",
        2,
    )
    assert (other["version"], lost["anchor_state"], lost["target_version"]) == (3, "detached", 3)
    assert lost["quote"] == "Forward Euler"  # what it was about is kept
