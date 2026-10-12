"""Keeping comments on their passages when the text they are attached to is rewritten."""

from __future__ import annotations

from numericos.core.anchors import Located, context, locate
from numericos.core.enums import AnchorState, TargetType
from numericos.persistence.engine import utcnow
from numericos.persistence.unit_of_work import UnitOfWork


def reanchor(
    uow: UnitOfWork, target_type: TargetType, target_id: str, markdown: str, version: int
) -> tuple[int, int]:
    """Look for the passage of every comment of a text in its new version. A passage found
    in one clear place moves there; the others are detached, and say so. Returns how many
    stayed attached and how many were detached."""
    attached = detached = 0
    now = utcnow()
    for annotation in uow.annotations.list_for_target(target_type.value, target_id):
        found = locate(markdown, annotation.quote, annotation.prefix, annotation.suffix)
        if isinstance(found, Located):
            annotation.start_offset, annotation.end_offset = found.start, found.end
            annotation.prefix, annotation.suffix = context(markdown, found.start, found.end)
            annotation.anchor_state = AnchorState.ATTACHED.value
            attached += 1
        else:
            annotation.anchor_state = AnchorState.DETACHED.value
            detached += 1
        annotation.target_version = version
        annotation.updated_at = now
    return attached, detached
