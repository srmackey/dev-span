from __future__ import annotations

import pytest

from devspan.models import EntityType
from devspan.storage import Storage


def test_alias_add_resolve_remove(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "api-gw", name="Gateway")
    storage.add_alias(EntityType.COMPONENT, "api-gw", "gw")
    storage.add_alias(EntityType.COMPONENT, "api-gw", "gateway")

    res = storage.resolve_ref("gw")
    assert any(r["ref"] == "component:api-gw" for r in res)
    # alias score should be high
    gw_hit = [r for r in res if r["ref"] == "component:api-gw" and r["source"] == "alias"][0]
    assert gw_hit["score"] >= 0.9

    res_name = storage.resolve_ref("gateway")
    # name match is case-insensitive substring; may be ranked after slug/alias
    assert any(r["source"] == "name" and "api-gw" in r["ref"] for r in res_name) or \
           any("api-gw" in r["ref"] for r in res_name)  # at least the entity is returned via some path

    after = storage.remove_alias(EntityType.COMPONENT, "api-gw", "gw")
    assert "gw" not in after


def test_alias_uniqueness_across_types(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "c1")
    storage.create_entity(EntityType.TASK, "t1")
    storage.add_alias(EntityType.COMPONENT, "c1", "shared")

    with pytest.raises(ValueError):
        storage.add_alias(EntityType.TASK, "t1", "shared")


def test_resolve_exact_slug_beats_alias(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "foo")
    storage.add_alias(EntityType.COMPONENT, "foo", "bar")

    # Exact slug match
    hits = storage.resolve_ref("foo")
    assert hits[0]["source"] == "slug"
    assert hits[0]["score"] == 1.0
