from __future__ import annotations

from devspan.models import EntityRef, EntityType
from devspan.storage import Storage


def test_reindex_restores_from_markdown(tmp_home) -> None:
    # Create a storage, write data, close it, then reindex from a fresh instance.
    st1 = Storage(root=tmp_home)
    st1.create_entity(EntityType.COMPONENT, "reidx", description="To be reindexed")
    st1.upsert_subtopic(
        EntityRef(type=EntityType.COMPONENT, slug="reidx", subtopic="overview"),
        "Important fact about reindexing.",
    )
    st1.create_entity(EntityType.TASK, "t-re")
    st1.link_task("t-re", ["component:reidx"])
    st1.add_alias(EntityType.COMPONENT, "reidx", "reidx-alias")
    st1.close()

    # Fresh storage on same root; index may be empty-ish or stale in theory.
    st2 = Storage(root=tmp_home)
    counts = st2.reindex()
    assert counts["entities"] >= 2  # component + task at least
    assert counts["subtopics"] >= 1

    # Data should be queryable
    ent = st2.get_entity(EntityType.COMPONENT, "reidx")
    assert ent.meta.description == "To be reindexed"
    assert any(a == "reidx-alias" for a in ent.meta.aliases)

    links = st2.list_task_links("t-re")
    assert "component:reidx" in links

    st2.close()
