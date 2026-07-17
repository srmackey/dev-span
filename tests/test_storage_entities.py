from __future__ import annotations

import pytest

from contextforge.models import ComponentKind, EntityRef, EntityType
from contextforge.storage import Storage


def test_create_and_get_component(storage: Storage) -> None:
    e = storage.create_entity(
        EntityType.COMPONENT,
        "api-gateway",
        name="API Gateway",
        description="Edge proxy",
        kind=ComponentKind.SYSTEM,
        aliases=["gw"],
    )
    assert e.slug == "api-gateway"
    assert e.meta.kind == ComponentKind.SYSTEM
    assert "gw" in e.meta.aliases

    got = storage.get_entity(EntityType.COMPONENT, "api-gateway")
    assert got.meta.description == "Edge proxy"


def test_create_repo_with_parent(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "backend", kind=ComponentKind.SERVICE)
    r = storage.create_entity(
        EntityType.REPO,
        "svc-repo",
        description="Service code",
        component_parent="backend",
    )
    assert r.meta.component == "backend"

    # Invalid parent should fail at create time
    with pytest.raises(KeyError):
        storage.create_entity(
            EntityType.REPO, "bad-repo", component_parent="no-such-comp"
        )


def test_component_kind_only_for_components(storage: Storage) -> None:
    with pytest.raises(ValueError):
        storage.create_entity(EntityType.TASK, "t1", kind=ComponentKind.API)

    with pytest.raises(ValueError):
        storage.create_entity(EntityType.REPO, "r1", kind=ComponentKind.LIBRARY)


def test_list_and_delete(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "c1")
    storage.create_entity(EntityType.COMPONENT, "c2")
    lst = storage.list_entities(EntityType.COMPONENT)
    slugs = {x["slug"] for x in lst}
    assert {"c1", "c2"} <= slugs

    storage.delete_entity(EntityType.COMPONENT, "c1")
    assert not storage.entity_exists(EntityType.COMPONENT, "c1")
    assert storage.entity_exists(EntityType.COMPONENT, "c2")


def test_governance_cannot_reference_other_governance(storage: Storage) -> None:
    storage.create_entity(EntityType.GOVERNANCE, "sec")
    with pytest.raises(ValueError):
        storage.create_entity(
            EntityType.GOVERNANCE, "other", governance=["governance:sec"]
        )

    # add_governance also guards
    gov_ref = EntityRef(type=EntityType.GOVERNANCE, slug="sec")
    with pytest.raises(ValueError):
        storage.add_governance(gov_ref, "governance:sec")
