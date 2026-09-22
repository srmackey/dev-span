from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from devspan.storage import Storage


@pytest.fixture
def tmp_home(tmp_path: Path) -> Path:
    """Isolated DEVSPAN_HOME for a test."""
    home = tmp_path / "cfhome"
    home.mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture
def storage(tmp_home: Path) -> Generator[Storage, None, None]:
    """Provide a Storage instance isolated to tmp_home.

    Uses context manager protocol so per-thread conn is closed on exit.
    """
    st = Storage(root=tmp_home)
    try:
        yield st
    finally:
        st.close()


@pytest.fixture
def storage_no_scaffold(tmp_home: Path) -> Generator[Storage, None, None]:
    """Storage that does not scaffold starter subtopics by default.

    Useful when tests want to control exact subtopics.
    (Scaffolding is controlled per create_entity call.)
    """
    st = Storage(root=tmp_home)
    try:
        yield st
    finally:
        st.close()
