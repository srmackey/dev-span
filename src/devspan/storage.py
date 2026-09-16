from __future__ import annotations

import logging
import logging.handlers
import os
import re
import shutil
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("devspan.storage")

import frontmatter

from .config import Config
from .models import (
    ComponentKind,
    Entity,
    EntityMeta,
    EntityRef,
    EntityType,
    ExternalRef,
    Subtopic,
    TaskPack,
)
from .refs import parse_ref
from .templates import starter_subtopics


_META_FILE = "_meta.md"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
  type             TEXT NOT NULL,
  slug             TEXT NOT NULL,
  name             TEXT,
  description      TEXT,
  kind             TEXT,          -- component kind; NULL for other types
  component_parent TEXT,          -- for repos; NULL for others
  created_at       TEXT,
  updated_at       TEXT,
  PRIMARY KEY (type, slug)
);

CREATE TABLE IF NOT EXISTS aliases (
  alias       TEXT NOT NULL PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_slug TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aliases_entity
  ON aliases(entity_type, entity_slug);

CREATE TABLE IF NOT EXISTS subtopics (
  entity_type        TEXT NOT NULL,
  entity_slug        TEXT NOT NULL,
  subtopic           TEXT NOT NULL,
  content            TEXT NOT NULL,
  source_url         TEXT,
  source_name        TEXT,
  source_fetched_at  TEXT,
  updated_at         TEXT,
  PRIMARY KEY (entity_type, entity_slug, subtopic)
);

CREATE TABLE IF NOT EXISTS task_links (
  task_slug TEXT NOT NULL,
  ref       TEXT NOT NULL,
  PRIMARY KEY (task_slug, ref)
);

CREATE TABLE IF NOT EXISTS governance_links (
  entity_type     TEXT NOT NULL,
  entity_slug     TEXT NOT NULL,
  governance_ref  TEXT NOT NULL,
  PRIMARY KEY (entity_type, entity_slug, governance_ref)
);

CREATE TABLE IF NOT EXISTS uses_edges (
  from_component TEXT NOT NULL,
  to_component   TEXT NOT NULL,
  PRIMARY KEY (from_component, to_component)
);

CREATE TABLE IF NOT EXISTS task_external_refs (
  task_slug  TEXT NOT NULL,
  ext_system TEXT NOT NULL,
  ext_id     TEXT NOT NULL,
  url        TEXT,
  PRIMARY KEY (task_slug, ext_system, ext_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS context_fts USING fts5(
  entity_type, entity_slug, subtopic, content,
  tokenize = 'porter unicode61'
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_home() -> Path:
    override = os.environ.get("DEVSPAN_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".devspan"


def _fts_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _fts_or_query(text: str, max_terms: int = 50) -> str:
    """Tokenize free text into an FTS5 OR-of-quoted-terms query.

    Phrase-only queries (the default elsewhere) are too restrictive for
    long task descriptions. Each token is quoted so FTS5 keywords
    (NEAR/AND/OR/NOT) can't break the parse.
    """
    tokens = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break
    return " OR ".join(f'"{t}"' for t in out)


def _attach_rotating_file_handler(path: Path, level: int = logging.INFO) -> None:
    """Attach a rotating file handler for an exact log path (idempotent).

    Used for both the standard home-based log and any additional dev / repo-local
    logs specified via environment variables.
    """
    root_logger = logging.getLogger("devspan")
    resolved = path.resolve()
    for h in list(root_logger.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):
            try:
                if Path(getattr(h, "baseFilename", "")).resolve() == resolved:
                    return  # already attached for this exact file
            except Exception:
                pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        str(path),
        maxBytes=5_000_000,  # ~5 MB
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    fh.setLevel(level)
    root_logger.addHandler(fh)


def _ensure_persistent_log_handler(root: Path) -> None:
    """Attach the standard rotating log under the DevSpan home directory.

    Writes to <root>/logs/devspan.log. This is the normal user-facing
    persistent log. Additional locations can be added via setup_extra_logging().
    """
    log_path = root / "logs" / "devspan.log"
    _attach_rotating_file_handler(log_path)


def setup_extra_logging() -> None:
    """Attach extra log destination(s) driven by environment variables.

    This is the mechanism for making logs "travel with the repo" during
    development and trials without changing the normal user data location.

    Supported variables:
      DEVSPAN_LOG_FILE     Full path to an additional log file.
      DEVSPAN_DEV_LOG_DIR  Directory; "devspan.log" will be created inside it.

      Example (for this repo's dev logs so they travel with the checkout):
        DEVSPAN_DEV_LOG_DIR=/path/to/dev-span/.system/usage-logs
        # or
        DEVSPAN_LOG_FILE=/path/to/dev-span/.system/usage-logs/devspan.log

    When set, the same structured events are written to both the normal home log
    (if any) *and* the extra location(s). Safe to use for "both places for a while".

    Call is idempotent and harmless if the variable is unset.
    """
    extra_file = os.environ.get("DEVSPAN_LOG_FILE")
    if extra_file:
        _attach_rotating_file_handler(Path(extra_file))

    # Alternative convenience for dev: point at a directory
    extra_dir = os.environ.get("DEVSPAN_DEV_LOG_DIR")
    if extra_dir:
        _attach_rotating_file_handler(Path(extra_dir) / "devspan.log")


def _dir_for(type_: EntityType) -> str:
    # Plural subdir names for a comfortable FS layout.
    return {
        EntityType.COMPONENT: "components",
        EntityType.REPO: "repos",
        EntityType.TASK: "tasks",
        EntityType.GOVERNANCE: "governance",
    }[type_]


class Storage:
    def __init__(self, root: Path | None = None, config: Config | None = None):
        self.root = root or default_home()
        self._init_dirs()
        _ensure_persistent_log_handler(self.root)
        setup_extra_logging()
        self.db_path = self.root / ".index" / "devspan.db"
        self._local = threading.local()
        # Apply schema on the creating thread (main thread at server import time).
        # The CREATE ... IF NOT EXISTS statements are idempotent, so per-thread
        # connections created later in _connect() automatically see the schema
        # from the on-disk DB file. This is intentional and documented in
        # evolution.md Round 7.
        conn = self._conn
        conn.executescript(_SCHEMA)
        conn.commit()
        self.config = config or Config(self.root)

    def _connect(self) -> sqlite3.Connection:
        """One SQLite connection per thread (FastMCP dispatches tools across threads)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode=WAL")
            # WAL gives concurrent readers + one writer, but writer-vs-writer
            # contention across worker threads otherwise raises "database is
            # locked" immediately. Wait instead of failing on brief overlaps.
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._connect()

    # ---------- paths ----------

    def _init_dirs(self) -> None:
        for t in EntityType:
            (self.root / _dir_for(t)).mkdir(parents=True, exist_ok=True)
        (self.root / ".index").mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(parents=True, exist_ok=True)

    def _entity_dir(self, type_: EntityType, slug: str) -> Path:
        return self.root / _dir_for(type_) / slug

    def _meta_path(self, type_: EntityType, slug: str) -> Path:
        return self._entity_dir(type_, slug) / _META_FILE

    def _sub_path(self, type_: EntityType, slug: str, subtopic: str) -> Path:
        return self._entity_dir(type_, slug) / f"{subtopic}.md"

    # ---------- entity CRUD ----------

    def entity_exists(self, type_: EntityType, slug: str) -> bool:
        return self._meta_path(type_, slug).exists()

    def create_entity(
        self,
        type_: EntityType,
        slug: str,
        name: str | None = None,
        description: str = "",
        *,
        kind: ComponentKind | None = None,
        component_parent: str | None = None,
        aliases: list[str] | None = None,
        uses: list[str] | None = None,
        governance: list[str] | None = None,
        scaffold: bool = True,
    ) -> Entity:
        if self.entity_exists(type_, slug):
            raise ValueError(f"{type_.value}:{slug} already exists")
        if type_ == EntityType.COMPONENT and kind is None:
            kind = ComponentKind.SYSTEM
        if type_ != EntityType.COMPONENT and kind is not None:
            raise ValueError("kind is only valid for components")
        if type_ != EntityType.REPO and component_parent is not None:
            raise ValueError("component_parent is only valid for repos")
        if component_parent and not self.entity_exists(EntityType.COMPONENT, component_parent):
            raise KeyError(f"component:{component_parent} not found (parent must exist)")
        if type_ == EntityType.GOVERNANCE and governance:
            raise ValueError("governance entities cannot reference other governance entities")

        now = _now()
        meta = EntityMeta(
            name=name or slug,
            description=description,
            created_at=now,
            updated_at=now,
            aliases=aliases or [],
            kind=kind,
            uses=uses or [],
            component=component_parent,
            governance=governance or [],
        )
        self._entity_dir(type_, slug).mkdir(parents=True, exist_ok=True)
        self._write_meta(type_, slug, meta)
        self._conn.execute(
            "INSERT INTO entities(type, slug, name, description, kind,"
            " component_parent, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                type_.value,
                slug,
                meta.name,
                meta.description,
                kind.value if kind else None,
                component_parent,
                now,
                now,
            ),
        )
        self._write_aliases(type_, slug, meta.aliases)
        if type_ == EntityType.COMPONENT:
            self._write_uses(slug, meta.uses)
        if governance:
            for gref in governance:
                self._add_governance_link(type_, slug, gref)
        self._conn.commit()

        if scaffold:
            for sub_name, body in starter_subtopics(type_).items():
                ref = EntityRef(type=type_, slug=slug, subtopic=sub_name)
                self.upsert_subtopic(ref, body, _touch=False)
            self._touch_entity(type_, slug)
            self._conn.commit()

        logger.info(
            "entity:created type=%s slug=%s kind=%s parent=%s aliases=%d governance=%d",
            type_.value, slug, (kind.value if kind else ""), component_parent or "",
            len(meta.aliases or []), len(governance or []),
        )
        return self.get_entity(type_, slug)

    def get_entity(self, type_: EntityType, slug: str) -> Entity:
        if not self.entity_exists(type_, slug):
            raise KeyError(f"{type_.value}:{slug} not found")
        meta = self._read_meta(type_, slug)
        subtopics = self._read_all_subtopics(type_, slug)
        return Entity(type=type_, slug=slug, meta=meta, subtopics=subtopics)

    def get_repo_component(self, slug: str) -> str | None:
        """Return the parent component slug for a repo (if any).

        Lightweight accessor that avoids loading full subtopics. Used by
        get_current_workspace and avoids leaking the private _read_meta.
        """
        if not self.entity_exists(EntityType.REPO, slug):
            return None
        meta = self._read_meta(EntityType.REPO, slug)
        return meta.component

    def list_entities(self, type_: EntityType, kind: ComponentKind | None = None) -> list[dict]:
        sql = (
            "SELECT slug, name, description, kind, component_parent,"
            " created_at, updated_at FROM entities WHERE type = ?"
        )
        params: list = [type_.value]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind.value)
        sql += " ORDER BY updated_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def delete_entity(self, type_: EntityType, slug: str) -> None:
        d = self._entity_dir(type_, slug)
        if d.exists():
            shutil.rmtree(d)
        self._conn.execute(
            "DELETE FROM entities WHERE type = ? AND slug = ?",
            (type_.value, slug),
        )
        self._conn.execute(
            "DELETE FROM subtopics WHERE entity_type = ? AND entity_slug = ?",
            (type_.value, slug),
        )
        self._conn.execute(
            "DELETE FROM context_fts WHERE entity_type = ? AND entity_slug = ?",
            (type_.value, slug),
        )
        self._conn.execute(
            "DELETE FROM aliases WHERE entity_type = ? AND entity_slug = ?",
            (type_.value, slug),
        )
        self._conn.execute(
            "DELETE FROM governance_links WHERE entity_type = ? AND entity_slug = ?",
            (type_.value, slug),
        )
        prefix = f"{type_.value}:{slug}"
        affected_tasks: list[str] = []
        if type_ == EntityType.TASK:
            self._conn.execute("DELETE FROM task_links WHERE task_slug = ?", (slug,))
            self._conn.execute("DELETE FROM task_external_refs WHERE task_slug = ?", (slug,))
        else:
            affected_tasks = [
                r["task_slug"]
                for r in self._conn.execute(
                    "SELECT DISTINCT task_slug FROM task_links WHERE ref = ? OR ref LIKE ?",
                    (prefix, f"{prefix}/%"),
                ).fetchall()
            ]
            self._conn.execute(
                "DELETE FROM task_links WHERE ref = ? OR ref LIKE ?",
                (prefix, f"{prefix}/%"),
            )
            # Orphan cleanup for governance references from other entities.
            if type_ == EntityType.GOVERNANCE:
                # Capture owners so we can rewrite their markdown governance lists
                owners = [
                    (r["entity_type"], r["entity_slug"])
                    for r in self._conn.execute(
                        "SELECT entity_type, entity_slug FROM governance_links"
                        " WHERE governance_ref = ? OR governance_ref LIKE ?",
                        (prefix, f"{prefix}/%"),
                    ).fetchall()
                ]
                self._conn.execute(
                    "DELETE FROM governance_links WHERE governance_ref = ?"
                    " OR governance_ref LIKE ?",
                    (prefix, f"{prefix}/%"),
                )
                for et, es in owners:
                    try:
                        etype = EntityType(et)
                        self._sync_governance_meta(etype, es)
                    except Exception:
                        pass  # best effort; reindex will also heal
            if type_ == EntityType.COMPONENT:
                self._conn.execute(
                    "DELETE FROM uses_edges WHERE from_component = ? OR to_component = ?",
                    (slug, slug),
                )
                # Capture children before nulling so we can sync their markdown truth
                child_repos = [
                    r["slug"]
                    for r in self._conn.execute(
                        "SELECT slug FROM entities WHERE type = 'repo' AND component_parent = ?",
                        (slug,),
                    ).fetchall()
                ]
                self._conn.execute(
                    "UPDATE entities SET component_parent = NULL WHERE component_parent = ?",
                    (slug,),
                )
                for rslug in child_repos:
                    if self.entity_exists(EntityType.REPO, rslug):
                        meta = self._read_meta(EntityType.REPO, rslug)
                        meta.component = None
                        self._write_meta(EntityType.REPO, rslug, meta)
        self._conn.commit()
        for task_slug in affected_tasks:
            if self.entity_exists(EntityType.TASK, task_slug):
                self._sync_task_links_meta(task_slug)
        self._conn.commit()

    # ---------- aliases ----------

    def add_alias(self, type_: EntityType, slug: str, alias: str) -> list[str]:
        if not self.entity_exists(type_, slug):
            raise KeyError(f"{type_.value}:{slug} not found")
        existing = self._conn.execute(
            "SELECT entity_type, entity_slug FROM aliases WHERE alias = ?",
            (alias,),
        ).fetchone()
        if existing and (existing["entity_type"], existing["entity_slug"]) != (type_.value, slug):
            raise ValueError(
                f"alias {alias!r} is already taken by "
                f"{existing['entity_type']}:{existing['entity_slug']}"
            )
        self._conn.execute(
            "INSERT OR IGNORE INTO aliases(alias, entity_type, entity_slug) VALUES (?,?,?)",
            (alias, type_.value, slug),
        )
        self._conn.commit()
        return self._sync_aliases_meta(type_, slug)

    def remove_alias(self, type_: EntityType, slug: str, alias: str) -> list[str]:
        self._conn.execute(
            "DELETE FROM aliases WHERE alias = ? AND entity_type = ? AND entity_slug = ?",
            (alias, type_.value, slug),
        )
        self._conn.commit()
        return self._sync_aliases_meta(type_, slug)

    def resolve_ref(self, query: str, type_filter: EntityType | None = None) -> list[dict]:
        """Resolve a free-form query to candidate entity refs.

        Looks at: exact slug match, exact alias match, name (case-insensitive
        substring). Returns [{ref, source, score}] sorted by confidence.
        """
        q = query.strip().lower()
        results: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def _add(t: str, s: str, source: str, score: float):
            key = (t, s)
            if key in seen:
                return
            seen.add(key)
            results.append({"ref": f"{t}:{s}", "source": source, "score": score})

        sql = "SELECT type, slug FROM entities WHERE slug = ?"
        params: list = [q]
        if type_filter:
            sql += " AND type = ?"
            params.append(type_filter.value)
        for r in self._conn.execute(sql, params).fetchall():
            _add(r["type"], r["slug"], "slug", 1.0)

        sql = "SELECT entity_type, entity_slug FROM aliases WHERE alias = ?"
        params = [q]
        if type_filter:
            sql += " AND entity_type = ?"
            params.append(type_filter.value)
        for r in self._conn.execute(sql, params).fetchall():
            _add(r["entity_type"], r["entity_slug"], "alias", 0.95)

        sql = "SELECT type, slug, name FROM entities WHERE LOWER(name) LIKE ?"
        params = [f"%{q}%"]
        if type_filter:
            sql += " AND type = ?"
            params.append(type_filter.value)
        for r in self._conn.execute(sql, params).fetchall():
            name = (r["name"] or "").lower()
            score = 0.8 if name == q else 0.5
            _add(r["type"], r["slug"], "name", score)

        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info("ref:resolved query=%r hits=%d filter=%s", query, len(results), type_filter.value if type_filter else "")
        return results

    # ---------- subtopic CRUD ----------

    def get_subtopic(self, ref: EntityRef) -> Subtopic | None:
        if not ref.subtopic:
            raise ValueError("get_subtopic requires a subtopic in the ref")
        p = self._sub_path(ref.type, ref.slug, ref.subtopic)
        if not p.exists():
            return None
        post = frontmatter.load(p)
        return Subtopic(
            slug=ref.subtopic,
            content=post.content,
            updated_at=post.metadata.get("updated_at", ""),
            source_url=post.metadata.get("source_url", "") or "",
            source_name=post.metadata.get("source_name", "") or "",
            source_fetched_at=post.metadata.get("source_fetched_at", "") or "",
        )

    def upsert_subtopic(
        self,
        ref: EntityRef,
        content: str,
        *,
        source_url: str | None = None,
        source_name: str | None = None,
        source_fetched_at: str | None = None,
        _touch: bool = True,
    ) -> Subtopic:
        if not ref.subtopic:
            raise ValueError("upsert_subtopic requires a subtopic in the ref")
        if not self.entity_exists(ref.type, ref.slug):
            raise KeyError(f"{ref.type.value}:{ref.slug} not found — create it first")
        now = _now()
        fm: dict = {"updated_at": now}
        if source_url is not None:
            fm["source_url"] = source_url
        if source_name is not None:
            fm["source_name"] = source_name
        if source_fetched_at is not None:
            fm["source_fetched_at"] = source_fetched_at
        # Preserve prior source_* fields unless explicitly overridden.
        p = self._sub_path(ref.type, ref.slug, ref.subtopic)
        if p.exists():
            prior = frontmatter.load(p)
            for k in ("source_url", "source_name", "source_fetched_at"):
                if k not in fm and prior.metadata.get(k):
                    fm[k] = prior.metadata[k]
        post = frontmatter.Post(content, **fm)
        p.write_text(frontmatter.dumps(post), encoding="utf-8")
        self._conn.execute(
            "INSERT INTO subtopics(entity_type, entity_slug, subtopic, content,"
            " source_url, source_name, source_fetched_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(entity_type, entity_slug, subtopic)"
            " DO UPDATE SET content=excluded.content,"
            " source_url=excluded.source_url,"
            " source_name=excluded.source_name,"
            " source_fetched_at=excluded.source_fetched_at,"
            " updated_at=excluded.updated_at",
            (
                ref.type.value,
                ref.slug,
                ref.subtopic,
                content,
                fm.get("source_url"),
                fm.get("source_name"),
                fm.get("source_fetched_at"),
                now,
            ),
        )
        self._conn.execute(
            "DELETE FROM context_fts WHERE entity_type=? AND entity_slug=? AND subtopic=?",
            (ref.type.value, ref.slug, ref.subtopic),
        )
        self._conn.execute(
            "INSERT INTO context_fts(entity_type, entity_slug, subtopic, content)"
            " VALUES (?,?,?,?)",
            (ref.type.value, ref.slug, ref.subtopic, content),
        )
        if _touch:
            self._touch_entity(ref.type, ref.slug)
            self._conn.commit()
        logger.info("context:upsert ref=%s len=%d source=%s", ref, len(content), "external" if source_url else "local")
        return Subtopic(
            slug=ref.subtopic,
            content=content,
            updated_at=now,
            source_url=fm.get("source_url", "") or "",
            source_name=fm.get("source_name", "") or "",
            source_fetched_at=fm.get("source_fetched_at", "") or "",
        )

    def append_subtopic(self, ref: EntityRef, content: str) -> Subtopic:
        existing = self.get_subtopic(ref)
        if existing is None:
            return self.upsert_subtopic(ref, content)
        merged = existing.content.rstrip() + "\n\n" + content.strip()
        sub = self.upsert_subtopic(ref, merged)
        logger.info("context:append ref=%s added=%d total=%d", ref, len(content), len(merged))
        return sub

    def delete_subtopic(self, ref: EntityRef) -> bool:
        if not ref.subtopic:
            raise ValueError("delete_subtopic requires a subtopic in the ref")
        p = self._sub_path(ref.type, ref.slug, ref.subtopic)
        existed = p.exists()
        if existed:
            p.unlink()
        self._conn.execute(
            "DELETE FROM subtopics WHERE entity_type=? AND entity_slug=? AND subtopic=?",
            (ref.type.value, ref.slug, ref.subtopic),
        )
        self._conn.execute(
            "DELETE FROM context_fts WHERE entity_type=? AND entity_slug=? AND subtopic=?",
            (ref.type.value, ref.slug, ref.subtopic),
        )
        if self.entity_exists(ref.type, ref.slug):
            self._touch_entity(ref.type, ref.slug)
        self._conn.commit()
        logger.info("context:deleted ref=%s existed=%s", ref, existed)
        return existed

    # ---------- task links ----------

    def link_task(self, task_slug: str, refs: list[str]) -> list[str]:
        if not self.entity_exists(EntityType.TASK, task_slug):
            raise KeyError(f"task:{task_slug} not found")
        for r in refs:
            parsed = parse_ref(r)
            if parsed.type == EntityType.TASK:
                raise ValueError(f"Tasks cannot link to other tasks: {r}")
            self._conn.execute(
                "INSERT OR IGNORE INTO task_links(task_slug, ref) VALUES (?,?)",
                (task_slug, str(parsed)),
            )
        self._sync_task_links_meta(task_slug)
        self._conn.commit()
        logger.info("task:linked task=%s added=%d total=%d", task_slug, len(refs), len(self.list_task_links(task_slug)))
        return self.list_task_links(task_slug)

    def unlink_task(self, task_slug: str, refs: list[str]) -> list[str]:
        for r in refs:
            parsed = parse_ref(r)
            self._conn.execute(
                "DELETE FROM task_links WHERE task_slug = ? AND ref = ?",
                (task_slug, str(parsed)),
            )
        self._sync_task_links_meta(task_slug)
        self._conn.commit()
        logger.info("task:unlinked task=%s removed=%d total=%d", task_slug, len(refs), len(self.list_task_links(task_slug)))
        return self.list_task_links(task_slug)

    def list_task_links(self, task_slug: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT ref FROM task_links WHERE task_slug = ? ORDER BY ref",
            (task_slug,),
        ).fetchall()
        return [r["ref"] for r in rows]

    # ---------- governance links ----------

    def add_governance(self, entity_ref: EntityRef, governance_ref: str) -> list[str]:
        if entity_ref.subtopic:
            raise ValueError("governance is attached to entities, not subtopics")
        if not self.entity_exists(entity_ref.type, entity_ref.slug):
            raise KeyError(f"{entity_ref} not found")
        if entity_ref.type == EntityType.GOVERNANCE:
            raise ValueError("governance entities cannot reference other governance entities")
        parsed = parse_ref(governance_ref)
        if parsed.type != EntityType.GOVERNANCE:
            raise ValueError(f"{governance_ref} is not a governance ref")
        self._add_governance_link(entity_ref.type, entity_ref.slug, str(parsed))
        self._sync_governance_meta(entity_ref.type, entity_ref.slug)
        self._conn.commit()
        logger.info("governance:attached to=%s:%s gov=%s", entity_ref.type.value, entity_ref.slug, governance_ref)
        return self.list_governance(entity_ref)

    def remove_governance(self, entity_ref: EntityRef, governance_ref: str) -> list[str]:
        if entity_ref.subtopic:
            raise ValueError("governance is attached to entities, not subtopics")
        parsed = parse_ref(governance_ref)
        self._conn.execute(
            "DELETE FROM governance_links"
            " WHERE entity_type = ? AND entity_slug = ? AND governance_ref = ?",
            (entity_ref.type.value, entity_ref.slug, str(parsed)),
        )
        self._sync_governance_meta(entity_ref.type, entity_ref.slug)
        self._conn.commit()
        logger.info("governance:removed from=%s:%s gov=%s", entity_ref.type.value, entity_ref.slug, governance_ref)
        return self.list_governance(entity_ref)

    def list_governance(self, entity_ref: EntityRef) -> list[str]:
        rows = self._conn.execute(
            "SELECT governance_ref FROM governance_links"
            " WHERE entity_type = ? AND entity_slug = ? ORDER BY governance_ref",
            (entity_ref.type.value, entity_ref.slug),
        ).fetchall()
        return [r["governance_ref"] for r in rows]

    # ---------- task external refs ----------

    def add_external_ref(self, task_slug: str, ext: ExternalRef) -> list[ExternalRef]:
        if not self.entity_exists(EntityType.TASK, task_slug):
            raise KeyError(f"task:{task_slug} not found")
        self._conn.execute(
            "INSERT OR REPLACE INTO task_external_refs"
            "(task_slug, ext_system, ext_id, url) VALUES (?,?,?,?)",
            (task_slug, ext.system, ext.id, ext.url),
        )
        self._sync_external_refs_meta(task_slug)
        self._conn.commit()
        logger.info("external_ref:added task=%s system=%s id=%s", task_slug, ext.system, ext.id)
        return self.list_external_refs(task_slug)

    def remove_external_ref(self, task_slug: str, system: str, ext_id: str) -> list[ExternalRef]:
        self._conn.execute(
            "DELETE FROM task_external_refs"
            " WHERE task_slug = ? AND ext_system = ? AND ext_id = ?",
            (task_slug, system, ext_id),
        )
        self._sync_external_refs_meta(task_slug)
        self._conn.commit()
        logger.info("external_ref:removed task=%s system=%s id=%s", task_slug, system, ext_id)
        return self.list_external_refs(task_slug)

    def list_external_refs(self, task_slug: str) -> list[ExternalRef]:
        rows = self._conn.execute(
            "SELECT ext_system, ext_id, url FROM task_external_refs"
            " WHERE task_slug = ? ORDER BY ext_system, ext_id",
            (task_slug,),
        ).fetchall()
        return [
            ExternalRef(system=r["ext_system"], id=r["ext_id"], url=r["url"] or "")
            for r in rows
        ]

    # ---------- task pack ----------

    def get_task_pack(
        self,
        task_slug: str,
        *,
        include_always: bool = True,
        focus: bool = True,
        per_entity_top_k: int = 3,
        min_score: float | None = None,
    ) -> TaskPack:
        t0 = time.perf_counter()
        task = self.get_entity(EntityType.TASK, task_slug)
        links = self.list_task_links(task_slug)

        # Build the focus query from task description + own subtopic content.
        # If focus is off or the task has nothing to query against, narrowing
        # is skipped and entity-level refs resolve to all subtopics (legacy).
        query: str | None = None
        if focus:
            text = " ".join(
                [task.meta.description or ""] + [s.content for s in task.subtopics]
            )
            q = _fts_or_query(text)
            query = q or None

        term_count = len(query.split(" OR ")) if query else 0
        logger.info(
            "pack:start task=%s links=%d focus=%s terms=%d top_k=%d",
            task_slug, len(links), focus, term_count, per_entity_top_k,
        )

        narrow_kwargs = dict(
            query=query,
            top_k=per_entity_top_k if focus else None,
            min_score=min_score if focus else None,
        )

        resolved_links: list[tuple[str, str]] = []
        dropped: list[str] = []
        governance_refs: list[str] = list(self.list_governance(
            EntityRef(type=EntityType.TASK, slug=task_slug)
        ))

        for ref_str in links:
            ref = parse_ref(ref_str)
            content, drops = self._resolve_ref_content(ref, **narrow_kwargs)
            resolved_links.append((ref_str, content))
            dropped.extend(drops)
            # Governance cascade: gather governance attached to linked entities
            # (and to parent components of linked repos).
            if ref.type != EntityType.GOVERNANCE:
                owner = EntityRef(type=ref.type, slug=ref.slug)
                for gref in self.list_governance(owner):
                    if gref not in governance_refs:
                        governance_refs.append(gref)
                if ref.type == EntityType.REPO and self.entity_exists(ref.type, ref.slug):
                    parent = self._read_meta(ref.type, ref.slug).component
                    if parent and self.entity_exists(EntityType.COMPONENT, parent):
                        parent_ref = EntityRef(type=EntityType.COMPONENT, slug=parent)
                        for gref in self.list_governance(parent_ref):
                            if gref not in governance_refs:
                                governance_refs.append(gref)

        if include_always:
            for r in self.config.always_include:
                try:
                    parsed = parse_ref(r)
                except ValueError:
                    logger.warning("pack:bad_always_include ref=%r task=%s", r, task_slug)
                    continue
                if r not in governance_refs and r not in (x for x, _ in resolved_links):
                    # Always-included refs join whichever bucket fits their type.
                    if r.startswith("governance:"):
                        governance_refs.append(r)
                    else:
                        content, drops = self._resolve_ref_content(parsed, **narrow_kwargs)
                        resolved_links.append((r, content))
                        dropped.extend(drops)

        resolved_governance: list[tuple[str, str]] = []
        for gref in governance_refs:
            try:
                ref = parse_ref(gref)
            except ValueError:
                logger.warning("pack:bad_governance_ref ref=%r task=%s", gref, task_slug)
                continue
            content, drops = self._resolve_ref_content(ref, **narrow_kwargs)
            resolved_governance.append((gref, content))
            dropped.extend(drops)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_chars = sum(len(c) for _, c in resolved_links) + sum(len(c) for _, c in resolved_governance)
        logger.info(
            "pack:done task=%s linked=%d governance=%d dropped=%d total_chars=%d elapsed_ms=%.1f",
            task_slug, len(resolved_links), len(resolved_governance),
            len(dropped), total_chars, elapsed_ms,
        )

        return TaskPack(
            task=task,
            linked=resolved_links,
            governance=resolved_governance,
            dropped=dropped,
        )

    def _resolve_ref_content(
        self,
        ref: EntityRef,
        *,
        query: str | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> tuple[str, list[str]]:
        """Render a ref's content. Returns (content, dropped_subtopic_refs).

        Subtopic-level refs always return their content verbatim (explicit
        selection wins). Entity-level refs return the full entity unless a
        focus query is supplied AND the entity has more than top_k subtopics,
        in which case its subtopics are FTS-ranked against the query and only
        the top-K are concatenated. The entity's `_meta` description is always
        included as the overview.
        """
        if ref.subtopic:
            sub = self.get_subtopic(ref)
            if sub is None:
                logger.error("resolve:missing_subtopic ref=%s", ref)
                return f"(missing subtopic: {ref})", []
            return sub.content, []
        if not self.entity_exists(ref.type, ref.slug):
            logger.error("resolve:missing_entity ref=%s", ref)
            return f"(missing entity: {ref})", []
        ent = self.get_entity(ref.type, ref.slug)
        head = (ent.meta.description.strip() + "\n\n") if ent.meta.description else ""

        can_narrow = (
            query is not None
            and top_k is not None
            and len(ent.subtopics) > top_k
        )
        if not can_narrow:
            body = "\n\n".join(
                f"### {s.slug}\n{s.content}".rstrip() for s in ent.subtopics
            )
            return ((head + body).strip() or f"(empty entity: {ref})"), []

        # Fetch ALL FTS matches without LIMIT so we capture scores for every
        # matched subtopic — both selected and would-be-dropped. This powers
        # the optimization log below and costs little at typical subtopic counts.
        all_rows = self._conn.execute(
            "SELECT subtopic, -bm25(context_fts) AS score"
            " FROM context_fts"
            " WHERE context_fts MATCH ? AND entity_type = ? AND entity_slug = ?"
            " ORDER BY score DESC",
            (query, ref.type.value, ref.slug),
        ).fetchall()
        if min_score is not None:
            all_rows = [r for r in all_rows if r["score"] >= min_score]

        rows = all_rows[:top_k]

        if not rows:
            # No FTS signal — fall back to full content rather than silently
            # dropping every subtopic. Narrowing earns its keep only with signal.
            logger.debug(
                "resolve:no_signal ref=%s subtopics=%d — returning full entity",
                ref, len(ent.subtopics),
            )
            body = "\n\n".join(
                f"### {s.slug}\n{s.content}".rstrip() for s in ent.subtopics
            )
            return ((head + body).strip() or f"(empty entity: {ref})"), []

        selected_slugs = {r["subtopic"] for r in rows}
        scored_slugs = {r["subtopic"]: r["score"] for r in all_rows}
        by_slug = {s.slug: s for s in ent.subtopics}
        selected = [by_slug[r["subtopic"]] for r in rows if r["subtopic"] in by_slug]

        # Build dropped list: matched-but-not-selected (have a score) + no-match
        dropped_with_score = [
            (r["subtopic"], r["score"]) for r in all_rows[top_k:]
        ]
        no_match = [s.slug for s in ent.subtopics if s.slug not in scored_slugs]
        dropped_refs = [
            f"{ref.type.value}:{ref.slug}/{slug}"
            for slug, _ in dropped_with_score
        ] + [
            f"{ref.type.value}:{ref.slug}/{slug}"
            for slug in no_match
        ]

        # Debug log: full scoring breakdown for optimizer use
        selected_summary = " ".join(
            f"{r['subtopic']}={r['score']:.2f}" for r in rows
        )
        dropped_score_summary = " ".join(
            f"{slug}={score:.2f}" for slug, score in dropped_with_score
        )
        logger.debug(
            "resolve:narrowed ref=%s subtopics=%d->%d | "
            "selected=[%s] | dropped_low=[%s] | dropped_no_match=[%s]",
            ref, len(ent.subtopics), len(selected),
            selected_summary,
            dropped_score_summary,
            " ".join(no_match),
        )

        body = "\n\n".join(
            f"### {s.slug}\n{s.content}".rstrip() for s in selected
        )
        return ((head + body).strip() or f"(empty entity: {ref})"), dropped_refs

    # ---------- search ----------

    def search(
        self,
        query: str,
        entity_type: EntityType | None = None,
        limit: int = 20,
    ) -> list[dict]:
        sql = (
            "SELECT entity_type, entity_slug, subtopic,"
            " snippet(context_fts, 3, '[', ']', '…', 12) AS snippet"
            " FROM context_fts WHERE context_fts MATCH ?"
        )
        params: list = [_fts_phrase(query)]
        if entity_type is not None:
            sql += " AND entity_type = ?"
            params.append(entity_type.value)
        sql += " LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ---------- graph + suggestions ----------

    def traverse_uses(self, start_components: list[str], depth: int = 3) -> list[str]:
        """BFS over the uses-edges graph. Returns component slugs within `depth` hops."""
        visited: dict[str, int] = {c: 0 for c in start_components}
        q: deque[str] = deque(start_components)
        while q:
            cur = q.popleft()
            if visited[cur] >= depth:
                continue
            rows = self._conn.execute(
                "SELECT to_component FROM uses_edges WHERE from_component = ?",
                (cur,),
            ).fetchall()
            for r in rows:
                nxt = r["to_component"]
                if nxt not in visited:
                    visited[nxt] = visited[cur] + 1
                    q.append(nxt)
        return list(visited.keys())

    def suggest_task_links(
        self,
        task_slug: str,
        anchors: list[str] | None = None,
        depth: int = 3,
        top_k: int = 10,
    ) -> list[dict]:
        """Suggest candidate links for a task.

        Walks the uses-graph from the anchors (or from the task's current links
        if anchors is None), collects components within `depth`, and
        FTS-scores each candidate's subtopics against the task's description +
        own subtopics. Returns [{ref, score, why}].
        """
        if not self.entity_exists(EntityType.TASK, task_slug):
            raise KeyError(f"task:{task_slug} not found")
        task = self.get_entity(EntityType.TASK, task_slug)

        # Anchor components: from supplied anchors or derived from existing links.
        anchor_components: list[str] = []
        sources = anchors if anchors else self.list_task_links(task_slug)
        for r in sources:
            try:
                parsed = parse_ref(r)
            except ValueError:
                continue
            if parsed.type == EntityType.COMPONENT:
                anchor_components.append(parsed.slug)
            elif parsed.type == EntityType.REPO and self.entity_exists(parsed.type, parsed.slug):
                parent = self._read_meta(parsed.type, parsed.slug).component
                if parent:
                    anchor_components.append(parent)

        reachable = self.traverse_uses(list(set(anchor_components)), depth=depth) if anchor_components else []

        # Build a query from the task's description + subtopic content.
        query_parts = [task.meta.description]
        query_parts.extend(s.content for s in task.subtopics)
        query = " ".join(p for p in query_parts if p).strip()
        if not query:
            return []

        # Score subtopics via FTS, restricted to reachable components + any repo.
        hits = self.search(query, limit=top_k * 4)
        existing = set(self.list_task_links(task_slug))
        suggestions: list[dict] = []
        for h in hits:
            ref_str = (
                f"{h['entity_type']}:{h['entity_slug']}/{h['subtopic']}"
                if h.get("subtopic") else f"{h['entity_type']}:{h['entity_slug']}"
            )
            if ref_str in existing:
                continue
            if h["entity_type"] == "task":
                continue
            # If we have anchors, only surface reachable components; repos always welcome.
            if reachable and h["entity_type"] == "component" and h["entity_slug"] not in reachable:
                continue
            suggestions.append({
                "ref": ref_str,
                "why": h.get("snippet", ""),
            })
            if len(suggestions) >= top_k:
                break
        logger.info("suggest:links task=%s anchors=%d depth=%d returned=%d", task_slug, len(anchor_components), depth, len(suggestions))
        return suggestions

    # ---------- maintenance ----------

    def list_stale_sources(self, older_than_iso: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT entity_type, entity_slug, subtopic, source_url, source_name,"
            " source_fetched_at FROM subtopics"
            " WHERE source_url IS NOT NULL AND source_url != ''"
            " AND (source_fetched_at IS NULL OR source_fetched_at < ?)"
            " ORDER BY source_fetched_at",
            (older_than_iso,),
        ).fetchall()
        return [dict(r) for r in rows]

    def tail_logs(self, n: int = 50) -> list[str]:
        """Return the last n lines from the persistent log file (most recent last).

        Useful for inspecting real usage during trials without leaving the MCP
        environment. Returns [] if no log file exists yet.
        """
        log_path = self.root / "logs" / "devspan.log"
        if not log_path.exists():
            return []
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                # Efficient enough for small rotating logs
                lines = f.readlines()
            return [line.rstrip("\n") for line in lines[-max(1, int(n)):]]
        except Exception as e:
            logger.warning("tail_logs: failed to read %s: %s", log_path, e)
            return []

    def reindex(self) -> dict:
        """Rebuild SQLite + FTS from filesystem (disaster recovery)."""
        self._conn.execute("DELETE FROM entities")
        self._conn.execute("DELETE FROM subtopics")
        self._conn.execute("DELETE FROM context_fts")
        self._conn.execute("DELETE FROM task_links")
        self._conn.execute("DELETE FROM task_external_refs")
        self._conn.execute("DELETE FROM aliases")
        self._conn.execute("DELETE FROM governance_links")
        self._conn.execute("DELETE FROM uses_edges")
        counts = {"entities": 0, "subtopics": 0, "task_links": 0, "governance_links": 0}
        for type_ in EntityType:
            base = self.root / _dir_for(type_)
            if not base.exists():
                continue
            for entity_dir in base.iterdir():
                if not entity_dir.is_dir() or not (entity_dir / _META_FILE).exists():
                    continue
                slug = entity_dir.name
                meta = self._read_meta(type_, slug)
                self._conn.execute(
                    "INSERT INTO entities(type, slug, name, description, kind,"
                    " component_parent, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        type_.value,
                        slug,
                        meta.name,
                        meta.description,
                        meta.kind.value if meta.kind else None,
                        meta.component,
                        meta.created_at,
                        meta.updated_at,
                    ),
                )
                counts["entities"] += 1
                for alias in meta.aliases:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO aliases(alias, entity_type, entity_slug)"
                        " VALUES (?,?,?)",
                        (alias, type_.value, slug),
                    )
                for gref in meta.governance:
                    self._add_governance_link(type_, slug, gref)
                    counts["governance_links"] += 1
                if type_ == EntityType.COMPONENT:
                    self._write_uses(slug, meta.uses)
                if type_ == EntityType.TASK:
                    for link in meta.links:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO task_links(task_slug, ref) VALUES (?,?)",
                            (slug, link),
                        )
                        counts["task_links"] += 1
                    for ext in meta.external_refs:
                        self._conn.execute(
                            "INSERT OR REPLACE INTO task_external_refs"
                            "(task_slug, ext_system, ext_id, url) VALUES (?,?,?,?)",
                            (slug, ext.system, ext.id, ext.url),
                        )
                for sub in self._read_all_subtopics(type_, slug):
                    self._conn.execute(
                        "INSERT INTO subtopics(entity_type, entity_slug, subtopic, content,"
                        " source_url, source_name, source_fetched_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (
                            type_.value,
                            slug,
                            sub.slug,
                            sub.content,
                            sub.source_url or None,
                            sub.source_name or None,
                            sub.source_fetched_at or None,
                            sub.updated_at,
                        ),
                    )
                    self._conn.execute(
                        "INSERT INTO context_fts(entity_type, entity_slug, subtopic, content)"
                        " VALUES (?,?,?,?)",
                        (type_.value, slug, sub.slug, sub.content),
                    )
                    counts["subtopics"] += 1
        self._conn.commit()
        return counts

    def close(self) -> None:
        """Close the SQLite connection (if any) for the *calling* thread only.

        Because we use one connection per thread (threading.local), this only
        affects the current thread's connection. In normal stdio usage the
        process exit cleans up remaining connections, but explicit close is
        provided for tests, context managers, or graceful shutdown.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def __enter__(self) -> Storage:
        """Support the context manager protocol.

        Allows clean usage such as:

            with Storage() as storage:
                storage.create_component(...)
                # connection is closed automatically on exit
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close the current thread's connection when exiting the context."""
        self.close()

    # ---------- internals ----------

    def _write_meta(self, type_: EntityType, slug: str, meta: EntityMeta) -> None:
        fm: dict = {
            "name": meta.name,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
        }
        if meta.aliases:
            fm["aliases"] = list(meta.aliases)
        if type_ == EntityType.COMPONENT:
            fm["kind"] = (meta.kind or ComponentKind.SYSTEM).value
            if meta.uses:
                fm["uses"] = list(meta.uses)
        if type_ == EntityType.REPO and meta.component:
            fm["component"] = meta.component
        if type_ == EntityType.TASK:
            fm["links"] = list(meta.links)
            if meta.external_refs:
                fm["external_refs"] = [e.model_dump() for e in meta.external_refs]
        if type_ != EntityType.GOVERNANCE and meta.governance:
            fm["governance"] = list(meta.governance)
        post = frontmatter.Post(meta.description, **fm)
        self._meta_path(type_, slug).write_text(
            frontmatter.dumps(post), encoding="utf-8"
        )

    def _read_meta(self, type_: EntityType, slug: str) -> EntityMeta:
        post = frontmatter.load(self._meta_path(type_, slug))
        kind_value = post.metadata.get("kind")
        kind = ComponentKind(kind_value) if kind_value else None
        ext_list = post.metadata.get("external_refs") or []
        external = [ExternalRef(**e) if isinstance(e, dict) else ExternalRef(system=str(e), id="") for e in ext_list]
        return EntityMeta(
            name=post.metadata.get("name", slug),
            description=post.content,
            created_at=post.metadata.get("created_at", ""),
            updated_at=post.metadata.get("updated_at", ""),
            aliases=list(post.metadata.get("aliases") or []),
            kind=kind if type_ == EntityType.COMPONENT else None,
            uses=list(post.metadata.get("uses") or []),
            component=post.metadata.get("component") if type_ == EntityType.REPO else None,
            links=list(post.metadata.get("links") or []),
            external_refs=external,
            governance=list(post.metadata.get("governance") or []),
        )

    def _read_all_subtopics(self, type_: EntityType, slug: str) -> list[Subtopic]:
        d = self._entity_dir(type_, slug)
        if not d.exists():
            return []
        out: list[Subtopic] = []
        for p in sorted(d.glob("*.md")):
            if p.name == _META_FILE:
                continue
            post = frontmatter.load(p)
            out.append(
                Subtopic(
                    slug=p.stem,
                    content=post.content,
                    updated_at=post.metadata.get("updated_at", ""),
                    source_url=post.metadata.get("source_url", "") or "",
                    source_name=post.metadata.get("source_name", "") or "",
                    source_fetched_at=post.metadata.get("source_fetched_at", "") or "",
                )
            )
        return out

    def _touch_entity(self, type_: EntityType, slug: str) -> None:
        now = _now()
        post = frontmatter.load(self._meta_path(type_, slug))
        post.metadata["updated_at"] = now
        self._meta_path(type_, slug).write_text(
            frontmatter.dumps(post), encoding="utf-8"
        )
        self._conn.execute(
            "UPDATE entities SET updated_at = ? WHERE type = ? AND slug = ?",
            (now, type_.value, slug),
        )

    def _sync_task_links_meta(self, task_slug: str) -> None:
        links = self.list_task_links(task_slug)
        path = self._meta_path(EntityType.TASK, task_slug)
        if not path.exists():
            return
        post = frontmatter.load(path)
        post.metadata["links"] = links
        post.metadata["updated_at"] = _now()
        path.write_text(frontmatter.dumps(post), encoding="utf-8")
        self._conn.execute(
            "UPDATE entities SET updated_at = ? WHERE type = 'task' AND slug = ?",
            (post.metadata["updated_at"], task_slug),
        )

    def _sync_external_refs_meta(self, task_slug: str) -> None:
        refs = self.list_external_refs(task_slug)
        path = self._meta_path(EntityType.TASK, task_slug)
        if not path.exists():
            return
        post = frontmatter.load(path)
        post.metadata["external_refs"] = [r.model_dump() for r in refs]
        post.metadata["updated_at"] = _now()
        path.write_text(frontmatter.dumps(post), encoding="utf-8")

    def _sync_governance_meta(self, type_: EntityType, slug: str) -> None:
        path = self._meta_path(type_, slug)
        if not path.exists():
            return
        refs = self.list_governance(EntityRef(type=type_, slug=slug))
        post = frontmatter.load(path)
        post.metadata["governance"] = refs
        post.metadata["updated_at"] = _now()
        path.write_text(frontmatter.dumps(post), encoding="utf-8")

    def _sync_aliases_meta(self, type_: EntityType, slug: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT alias FROM aliases WHERE entity_type = ? AND entity_slug = ?"
            " ORDER BY alias",
            (type_.value, slug),
        ).fetchall()
        aliases = [r["alias"] for r in rows]
        path = self._meta_path(type_, slug)
        if path.exists():
            post = frontmatter.load(path)
            post.metadata["aliases"] = aliases
            post.metadata["updated_at"] = _now()
            path.write_text(frontmatter.dumps(post), encoding="utf-8")
        return aliases

    def _write_aliases(self, type_: EntityType, slug: str, aliases: list[str]) -> None:
        for alias in aliases:
            existing = self._conn.execute(
                "SELECT entity_type, entity_slug FROM aliases WHERE alias = ?",
                (alias,),
            ).fetchone()
            if existing and (existing["entity_type"], existing["entity_slug"]) != (type_.value, slug):
                raise ValueError(
                    f"alias {alias!r} is already taken by "
                    f"{existing['entity_type']}:{existing['entity_slug']}"
                )
            self._conn.execute(
                "INSERT OR IGNORE INTO aliases(alias, entity_type, entity_slug)"
                " VALUES (?,?,?)",
                (alias, type_.value, slug),
            )

    def _write_uses(self, component_slug: str, uses: list[str]) -> None:
        self._conn.execute(
            "DELETE FROM uses_edges WHERE from_component = ?", (component_slug,)
        )
        for target in uses:
            # Accept either a bare slug or a component:<slug> ref; normalize to slug.
            if ":" in target:
                try:
                    parsed = parse_ref(target)
                    if parsed.type != EntityType.COMPONENT or parsed.subtopic:
                        continue
                    target_slug = parsed.slug
                except ValueError:
                    continue
            else:
                target_slug = target
            self._conn.execute(
                "INSERT OR IGNORE INTO uses_edges(from_component, to_component) VALUES (?,?)",
                (component_slug, target_slug),
            )

    def _add_governance_link(self, entity_type: EntityType, slug: str, gref: str) -> None:
        parsed = parse_ref(gref)
        if parsed.type != EntityType.GOVERNANCE:
            raise ValueError(f"{gref} is not a governance ref")
        self._conn.execute(
            "INSERT OR IGNORE INTO governance_links"
            "(entity_type, entity_slug, governance_ref) VALUES (?,?,?)",
            (entity_type.value, slug, str(parsed)),
        )
