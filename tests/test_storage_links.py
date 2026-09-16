from __future__ import annotations

import pytest

from devspan.models import EntityRef, EntityType, ExternalRef
from devspan.storage import Storage


def test_link_unlink_and_meta_sync(storage: Storage) -> None:
    storage.create_entity(EntityType.TASK, "t")
    storage.create_entity(EntityType.COMPONENT, "c1")
    storage.create_entity(EntityType.REPO, "r1")

    links = storage.link_task("t", ["component:c1", "repo:r1"])
    assert "component:c1" in links and "repo:r1" in links

    # Meta on disk should reflect links
    meta = storage.get_entity(EntityType.TASK, "t").meta
    assert "component:c1" in meta.links

    after = storage.unlink_task("t", ["repo:r1"])
    assert "repo:r1" not in after


def test_cannot_link_task_to_task(storage: Storage) -> None:
    storage.create_entity(EntityType.TASK, "t1")
    storage.create_entity(EntityType.TASK, "t2")
    with pytest.raises(ValueError):
        storage.link_task("t1", ["task:t2"])


def test_governance_attach_list_remove(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "c")
    storage.create_entity(EntityType.GOVERNANCE, "g")

    refs = storage.add_governance(EntityRef(type=EntityType.COMPONENT, slug="c"), "governance:g")
    assert "governance:g" in refs

    listed = storage.list_governance(EntityRef(type=EntityType.COMPONENT, slug="c"))
    assert listed == ["governance:g"]

    after = storage.remove_governance(EntityRef(type=EntityType.COMPONENT, slug="c"), "governance:g")
    assert after == []


def test_task_external_refs(storage: Storage) -> None:
    storage.create_entity(EntityType.TASK, "bug")
    refs = storage.add_external_ref("bug", ExternalRef(system="jira", id="BUG-42", url="https://j/BUG-42"))
    assert len(refs) == 1
    assert refs[0].id == "BUG-42"

    listed = storage.list_external_refs("bug")
    assert any(e.id == "BUG-42" for e in listed)

    after = storage.remove_external_ref("bug", "jira", "BUG-42")
    assert after == []
