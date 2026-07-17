from __future__ import annotations

import pytest

from contextforge.refs import is_slug, parse_ref, slugify
from contextforge.models import EntityRef, EntityType


class TestParseRef:
    def test_parse_entity(self) -> None:
        ref = parse_ref("component:api-gateway")
        assert ref.type == EntityType.COMPONENT
        assert ref.slug == "api-gateway"
        assert ref.subtopic is None
        assert str(ref) == "component:api-gateway"

    def test_parse_subtopic(self) -> None:
        ref = parse_ref("repo:ui-repo/testing")
        assert ref.type == EntityType.REPO
        assert ref.slug == "ui-repo"
        assert ref.subtopic == "testing"
        assert str(ref) == "repo:ui-repo/testing"

    def test_parse_all_types(self) -> None:
        for t in ("component", "repo", "task", "governance"):
            ref = parse_ref(f"{t}:foo-bar")
            assert ref.type.value == t
            assert ref.slug == "foo-bar"

    def test_invalid_raises(self) -> None:
        bad = [
            "foo:bar",
            "component:BadSlug",
            "component:api gateway",
            "component:api_gateway",
            "component:api/gateway/extra",
            "component:",
            ":slug",
            "component:slug/",
            "component:slug/Upper",
        ]
        for b in bad:
            with pytest.raises(ValueError):
                parse_ref(b)

    def test_whitespace_trimmed(self) -> None:
        ref = parse_ref("  task:fix-login  ")
        assert str(ref) == "task:fix-login"


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("API Gateway") == "api-gateway"
        assert slugify("My Service!") == "my-service"

    def test_already_good(self) -> None:
        assert slugify("foo-bar-123") == "foo-bar-123"

    def test_invalid_after_slugify(self) -> None:
        with pytest.raises(ValueError):
            slugify("!!!")  # becomes empty after strip
        with pytest.raises(ValueError):
            slugify("   ")  # empty

    def test_leading_trailing_hyphen_stripped(self) -> None:
        assert slugify("-foo-") == "foo"
        assert slugify(" foo bar ") == "foo-bar"


class TestIsSlug:
    def test_valid(self) -> None:
        assert is_slug("a")
        assert is_slug("foo-bar")
        assert is_slug("x1-y2")

    def test_invalid(self) -> None:
        assert not is_slug("Foo")
        assert not is_slug("foo_bar")
        assert not is_slug("foo bar")
        assert is_slug("1foo")  # digits are allowed as start per slug RE
        assert not is_slug("")
        # Note: current slug RE allows trailing hyphen (slugify strips them)
        assert is_slug("foo-")
