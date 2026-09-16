from __future__ import annotations

from devspan.models import EntityRef, EntityType
from devspan.storage import Storage


def test_search_basic_fts(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "searchy", description="Search target")
    storage.upsert_subtopic(
        EntityRef(type=EntityType.COMPONENT, slug="searchy", subtopic="overview"),
        "This component contains the special token ZORBLAX for testing FTS.",
    )

    hits = storage.search("ZORBLAX", limit=5)
    assert len(hits) >= 1
    assert any(h["entity_slug"] == "searchy" for h in hits)

    # Type filter
    filtered = storage.search("ZORBLAX", entity_type=EntityType.COMPONENT)
    assert all(h["entity_type"] == "component" for h in filtered)
