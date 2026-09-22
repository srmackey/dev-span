from __future__ import annotations

from pathlib import Path

from devspan.config import Config


def test_config_defaults_and_persist(tmp_path: Path) -> None:
    cfg = Config(tmp_path)
    assert cfg.always_include == []
    assert cfg.workspaces == {}

    cfg.add_always_include("governance:security-policy")
    assert "governance:security-policy" in cfg.always_include

    # Reload from disk
    cfg2 = Config(tmp_path)
    assert "governance:security-policy" in cfg2.always_include

    cfg.remove_always_include("governance:security-policy")
    cfg3 = Config(tmp_path)
    assert cfg3.always_include == []


def test_workspace_bind_lookup(tmp_path: Path) -> None:
    cfg = Config(tmp_path)
    p = str((tmp_path / "myproj").resolve())
    cfg.bind_workspace(p, "ui-repo")
    assert cfg.lookup_workspace(p) == "ui-repo"

    cfg.unbind_workspace(p)
    assert cfg.lookup_workspace(p) is None

    d = cfg.as_dict()
    assert "always_include" in d and "workspaces" in d


def test_config_bad_json_is_tolerated(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    cfg = Config(tmp_path)
    # Should fall back to defaults without crashing
    assert cfg.always_include == []
