from __future__ import annotations

from numericos.core.ids import ID_PATTERN, PREFIXES, is_valid_id, new_id


def test_ids_carry_their_prefix_and_a_ulid() -> None:
    project_id = new_id(PREFIXES["project"])

    assert project_id.startswith("prj_")
    assert ID_PATTERN.match(project_id)
    assert is_valid_id(project_id)


def test_ids_are_unique() -> None:
    assert len({new_id("evt") for _ in range(1000)}) == 1000


def test_malformed_ids_are_rejected() -> None:
    assert not is_valid_id("prj_123")
    assert not is_valid_id("PRJ_01J9W2Z4K7QX8YB3N5M6T0R1S2")
    assert not is_valid_id("01J9W2Z4K7QX8YB3N5M6T0R1S2")
