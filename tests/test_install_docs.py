from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_reads_platforms_yaml() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manual = (ROOT / "install" / "README.md").read_text(encoding="utf-8")
    assert "platforms.yaml" in readme
    assert "platforms.yaml" in manual
    assert "devspan-router.mdc" in manual
    assert "do not edit user-global" in manual.lower()
    for doc in (readme, manual):
        assert "~/.cursor/" not in doc
        assert "~/.claude" not in doc
        assert "~/.grok" not in doc
