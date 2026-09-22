from __future__ import annotations

from devspan.models import EntityRef, EntityType
from devspan.storage import Storage


def test_context_manager_closes_conn(tmp_home) -> None:
    with Storage(root=tmp_home) as st:
        st.create_entity(EntityType.TASK, "cm-test")
        assert st.entity_exists(EntityType.TASK, "cm-test")
    # After exit, the thread-local conn should be cleared
    # We cannot easily peek private, but re-using should work without locked state.
    st2 = Storage(root=tmp_home)
    assert st2.entity_exists(EntityType.TASK, "cm-test")
    st2.close()


def test_list_stale_sources(storage: Storage) -> None:
    storage.create_entity(EntityType.COMPONENT, "srcy", scaffold=False)
    ref = EntityRef(type=EntityType.COMPONENT, slug="srcy", subtopic="old-doc")
    storage.upsert_subtopic(
        ref,
        "old content",
        source_url="https://old",
        source_name="wiki",
        source_fetched_at="2020-01-01T00:00:00+00:00",
    )

    # Cutoff after the fetch date => reported as stale
    stale = storage.list_stale_sources("2025-01-01T00:00:00+00:00")
    assert any(s["subtopic"] == "old-doc" for s in stale)

    # Cutoff before the fetch date => not considered stale
    not_stale = storage.list_stale_sources("2010-01-01T00:00:00+00:00")
    assert all(s["subtopic"] != "old-doc" for s in not_stale)


def test_tail_logs_smoke(storage: Storage) -> None:
    # Just ensure it doesn't blow up; logs may or may not exist in the tmp home.
    lines = storage.tail_logs(10)
    assert isinstance(lines, list)
