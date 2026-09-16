from __future__ import annotations

import pytest

from devspan.models import EntityRef, EntityType
from devspan.refs import parse_ref
from devspan.storage import Storage


def test_upsert_get_delete_subtopic(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "c1", scaffold=False)
    ref = EntityRef(type=EntityType.COMPONENT, slug="c1", subtopic="overview")
    sub = storage.upsert_subtopic(ref, "Hello world")
    assert sub.content == "Hello world"
    assert sub.slug == "overview"

    got = storage.get_subtopic(ref)
    assert got is not None and got.content == "Hello world"

    existed = storage.delete_subtopic(ref)
    assert existed is True
    assert storage.get_subtopic(ref) is None


def test_append_creates_or_appends(storage: Storage) -> None:
    storage.create_entity(EntityType.TASK, "t1", scaffold=False)
    ref = parse_ref("task:t1/goal")
    s1 = storage.append_subtopic(ref, "first")
    assert "first" in s1.content

    s2 = storage.append_subtopic(ref, "second")
    assert "first" in s2.content and "second" in s2.content


def test_upsert_requires_existing_entity(storage: Storage) -> None:
    ref = EntityRef(type=EntityType.REPO, slug="nope", subtopic="x")
    with pytest.raises(KeyError):
        storage.upsert_subtopic(ref, "content")


def test_import_content_tracks_source(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "c", scaffold=False)
    ref = parse_ref("component:c/confluence-page")
    sub = storage.upsert_subtopic(
        ref,
        "imported body",
        source_url="https://ex/confluence/123",
        source_name="confluence",
        source_fetched_at="2026-01-01T00:00:00+00:00",
    )
    assert sub.source_url == "https://ex/confluence/123"
    assert sub.source_name == "confluence"

    got = storage.get_subtopic(ref)
    assert got and got.source_url.startswith("https")
