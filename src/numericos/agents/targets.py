"""The texts a comment can be attached to: an answer of the agent, or a document it wrote."""

from __future__ import annotations

from dataclasses import dataclass

from numericos.agents import pipeline
from numericos.core.enums import (
    DocumentKind,
    MessageRole,
    MessageStatus,
    TargetType,
)
from numericos.persistence.unit_of_work import UnitOfWork

WHAT = {
    DocumentKind.THEORY.value: "the theory of this project",
    DocumentKind.PLAN.value: "the notes of the plan of this project",
    DocumentKind.PIPELINE.value: (
        "the pipeline of this project: what happens when the program runs, part by part"
    ),
}


@dataclass(frozen=True)
class Target:
    type: TargetType
    id: str
    project_id: str
    markdown: str
    #: Counts how many times the text was written; an answer is written once.
    version: int
    #: What the text is, in words for the agent: "the theory of this project".
    what: str
    title: str
    #: For an answer: the question it answered.
    question: str | None
    #: The text is final: a turn that is still writing it cannot be commented.
    ready: bool
    #: The text can be rewritten in place (a document), or is a record (an answer).
    rewritable: bool
    #: For a text that is drawn as a diagram (a pipeline): its boxes and arrows, in words.
    outline: str | None = None


def load(uow: UnitOfWork, target_type: TargetType, target_id: str) -> Target | None:
    if target_type is TargetType.MESSAGE:
        message = uow.messages.get(target_id)
        if message is None or message.role != MessageRole.ASSISTANT.value:
            return None
        prompt = (
            uow.messages.get(message.prompt_message_id)
            if message.prompt_message_id is not None
            else None
        )
        return Target(
            type=target_type,
            id=message.id,
            project_id=message.project_id,
            markdown=message.markdown,
            version=1,
            what="an answer you gave in a conversation about this project",
            title="answer",
            question=prompt.markdown if prompt is not None else None,
            ready=message.status == MessageStatus.FINAL.value,
            rewritable=False,
        )
    document = uow.documents.get(target_id)
    if document is None:
        return None
    what = WHAT.get(document.kind, f"the description of the file `{document.key}`")
    return Target(
        type=target_type,
        id=document.id,
        project_id=document.project_id,
        markdown=document.markdown,
        version=document.version,
        what=what,
        title=document.title or document.key,
        question=None,
        ready=document.version > 0,
        rewritable=True,
        outline=(
            pipeline.outline(document.pipeline)
            if document.kind == DocumentKind.PIPELINE.value
            else None
        ),
    )
