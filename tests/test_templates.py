from __future__ import annotations

from devspan.models import EntityType
from devspan.templates import starter_subtopics


def test_starter_subtopics_have_expected_keys() -> None:
    for et in EntityType:
        subs = starter_subtopics(et)
        assert isinstance(subs, dict)
        assert len(subs) > 0
        # Ensure fresh copy each time
        subs2 = starter_subtopics(et)
        assert subs is not subs2

    comp = starter_subtopics(EntityType.COMPONENT)
    assert "overview" in comp and "auth" in comp and "gotchas" in comp

    repo = starter_subtopics(EntityType.REPO)
    assert "testing" in repo and "local-dev" in repo

    task = starter_subtopics(EntityType.TASK)
    assert "goal" in task and "plan" in task

    gov = starter_subtopics(EntityType.GOVERNANCE)
    assert "overview" in gov and "rules" in gov
