from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("devspan.config")


_DEFAULT: dict[str, Any] = {
    "always_include": [],   # list of refs auto-included in every task pack
    "workspaces": {},       # map of absolute workspace path -> repo slug
}


class Config:
    """Simple JSON-backed config at <home>/config.json.

    Why JSON: Python stdlib can both read and write it. TOML reads via stdlib
    tomllib but writing requires a third-party lib; avoiding that for one file.
    """

    def __init__(self, home: Path):
        self.home = home
        self.path = home / "config.json"
        self._data: dict[str, Any] = dict(_DEFAULT)
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                loaded = {}
            self._data = {**_DEFAULT, **loaded}
        else:
            self._data = dict(_DEFAULT)

    def save(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # ---------- always_include ----------

    @property
    def always_include(self) -> list[str]:
        return list(self._data.get("always_include", []))

    def add_always_include(self, ref: str) -> list[str]:
        with self._lock:
            refs = self.always_include
            if ref not in refs:
                refs.append(ref)
            self._data["always_include"] = refs
            self.save()
            logger.info("always_include:added ref=%s total=%d", ref, len(refs))
            return refs

    def remove_always_include(self, ref: str) -> list[str]:
        with self._lock:
            refs = [r for r in self.always_include if r != ref]
            self._data["always_include"] = refs
            self.save()
            logger.info("always_include:removed ref=%s total=%d", ref, len(refs))
            return refs

    # ---------- workspace bindings ----------

    @property
    def workspaces(self) -> dict[str, str]:
        return dict(self._data.get("workspaces", {}))

    def bind_workspace(self, path: str, repo_slug: str) -> dict[str, str]:
        with self._lock:
            ws = self.workspaces
            ws[str(Path(path).resolve())] = repo_slug
            self._data["workspaces"] = ws
            self.save()
            logger.info("workspace:bound path=%s repo=%s", path, repo_slug)
            return ws

    def unbind_workspace(self, path: str) -> dict[str, str]:
        with self._lock:
            ws = self.workspaces
            ws.pop(str(Path(path).resolve()), None)
            self._data["workspaces"] = ws
            self.save()
            logger.info("workspace:unbound path=%s", path)
            return ws

    def lookup_workspace(self, path: str) -> str | None:
        return self.workspaces.get(str(Path(path).resolve()))

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
