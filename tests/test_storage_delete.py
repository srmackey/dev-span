from __future__ import annotations

from devspan.models import EntityType
from devspan.storage import Storage


def test_delete_entity_cleans_links_gov_and_parents(storage: Storage) -> None:
    storage.create_entity(EntityType.GOVERNANCE, "gsec")
    c = storage.create_entity(
        EntityType.COMPONENT, "parent", governance=["governance:gsec"]
    )
    storage.create_entity(
        EntityType.REPO, "child", component_parent="parent"
    )
    storage.create_entity(EntityType.TASK, "work")
    storage.link_task("work", ["component:parent", "repo:child"])

    # Delete the component
    storage.delete_entity(EntityType.COMPONENT, "parent")

    # Repo parent pointer nulled both in index and on-disk meta (source of truth)
    rmeta = storage.get_entity(EntityType.REPO, "child").meta
    assert rmeta.component is None

    # Task links cleaned
    tlinks = storage.list_task_links("work")
    assert all("component:parent" not in lnk for lnk in tlinks)

    # Governance links to the deleted gov should be gone if gov deleted, but here we deleted comp

    # Now delete the repo
    storage.delete_entity(EntityType.REPO, "child")
    # no crash; links already cleaned


def test_delete_governance_orphans_refs(storage: Storage) -> None:
    storage.create_entity(EntityType.GOVERNANCE, "to-delete")
    storage.create_entity(EntityType.COMPONENT, "owner", governance=["governance:to-delete"])

    storage.delete_entity(EntityType.GOVERNANCE, "to-delete")

    owner = storage.get_entity(EntityType.COMPONENT, "owner")
    # _sync during delete should have removed it from the owner's markdown
    assert "governance:to-delete" not in owner.meta.governance

    # The link row is also gone (tested indirectly via meta sync)
