from __future__ import annotations

import re

from .models import EntityRef, EntityType

_REF_RE = re.compile(
    r"^(component|repo|task|governance):"
    r"([a-z0-9][a-z0-9\-]*)"
    r"(?:/([a-z0-9][a-z0-9\-]*))?$"
)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def parse_ref(s: str) -> EntityRef:
    m = _REF_RE.match(s.strip())
    if not m:
        raise ValueError(
            f"Invalid ref {s!r}. Expected 'type:slug' or 'type:slug/subtopic' "
            "(type in component|repo|task|governance; slug/subtopic are lowercase a-z0-9-)."
        )
    type_, slug, subtopic = m.groups()
    return EntityRef(type=EntityType(type_), slug=slug, subtopic=subtopic)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not _SLUG_RE.match(s):
        raise ValueError(f"Cannot derive a slug from {name!r}")
    return s


def is_slug(s: str) -> bool:
    return bool(_SLUG_RE.match(s))
