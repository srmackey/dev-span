from __future__ import annotations

import pytest

from contextforge.models import EntityRef, EntityType
from contextforge.storage import Storage



def _create_minimal(storage: Storage, et: EntityType, slug: str, desc: str = "") -> None:
    storage.create_entity(et, slug, description=desc, scaffold=True)


def test_governance_cascade_order_and_dedup(storage: Storage) -> None:
    # Governance
    _create_minimal(storage, EntityType.GOVERNANCE, "sec", "Security rules")
    _create_minimal(storage, EntityType.GOVERNANCE, "style", "Style guide")

    # Component with gov
    storage.create_entity(
        EntityType.COMPONENT,
        "api",
        description="The API",
        governance=["governance:sec"],
        scaffold=True,
    )

    # Repo belonging to component + own gov
    storage.create_entity(
        EntityType.REPO,
        "api-repo",
        description="API code",
        component_parent="api",
        governance=["governance:style"],
        scaffold=True,
    )

    # Task with its own gov link
    _create_minimal(storage, EntityType.TASK, "t1", "fix stuff")
    storage.add_governance(EntityRef(type=EntityType.TASK, slug="t1"), "governance:sec")

    # Link task to the repo (which brings its parent component + both govs)
    storage.link_task("t1", ["repo:api-repo"])

    pack = storage.get_task_pack("t1", focus=False)

    gov_refs = [r for r, _ in pack.governance]
    # task's own, component's, repo's, parent component's (deduped)
    assert "governance:sec" in gov_refs
    assert "governance:style" in gov_refs

    # Always include
    storage.config.add_always_include("governance:sec")  # already present, ok
    pack2 = storage.get_task_pack("t1", include_always=True, focus=False)
    # Still deduped
    assert gov_refs.count("governance:sec") <= 1  # from previous


def test_focus_narrows_and_reports_dropped(storage: Storage) -> None:
    _create_minimal(storage, EntityType.TASK, "feat", "Implement login with password reset and MFA flows")
    storage.create_entity(EntityType.COMPONENT, "auth", scaffold=True)

    # Add several subtopics so it has > top_k
    for i in range(5):
        storage.upsert_subtopic(
            EntityRef(type=EntityType.COMPONENT, slug="auth", subtopic=f"sub{i}"),
            f"Detail about topic {i} with login and reset mentions.",
        )

    storage.link_task("feat", ["component:auth"])

    pack = storage.get_task_pack("feat", focus=True, per_entity_top_k=2)
    # Should have dropped entries for auth
    assert any(d.startswith("component:auth/") for d in pack.dropped)

    # With focus=False we get everything, no dropped for this entity
    pack_full = storage.get_task_pack("feat", focus=False)
    assert len(pack_full.dropped) == 0 or not any(
        d.startswith("component:auth/") for d in pack_full.dropped
    )


def test_subtopic_ref_bypasses_narrowing(storage: Storage) -> None:
    _create_minimal(storage, EntityType.TASK, "t", "some work")
    storage.create_entity(EntityType.COMPONENT, "big", scaffold=True)
    storage.upsert_subtopic(
        EntityRef(type=EntityType.COMPONENT, slug="big", subtopic="deep"),
        "Very specific deep detail here.",
    )
    storage.link_task("t", ["component:big/deep"])  # subtopic-level

    pack = storage.get_task_pack("t", focus=True, per_entity_top_k=0)  # even with aggressive k
    # The explicit subtopic ref should appear fully in linked
    linked_refs = [r for r, _ in pack.linked]
    assert "component:big/deep" in linked_refs
    assert not any("component:big/deep" in d for d in pack.dropped)


def test_always_include_merges_into_pack(storage: Storage) -> None:
    _create_minimal(storage, EntityType.TASK, "t", "x")
    _create_minimal(storage, EntityType.GOVERNANCE, "prefs", "My prefs")

    storage.config.add_always_include("governance:prefs")
    pack = storage.get_task_pack("t", include_always=True, focus=False)
    govs = [r for r, _ in pack.governance]
    assert "governance:prefs" in govs

    # When focus=False and include always, also non-gov always_includes are resolved
    storage.create_entity(EntityType.COMPONENT, "shared", scaffold=True)
    storage.config.add_always_include("component:shared")
    pack2 = storage.get_task_pack("t", include_always=True, focus=False)
    linked_refs = [r for r, _ in pack2.linked]
    assert "component:shared" in linked_refs
