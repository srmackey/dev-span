from __future__ import annotations

from .models import EntityType


_SUBTOPIC_TEMPLATES: dict[EntityType, dict[str, str]] = {
    EntityType.COMPONENT: {
        "overview": "# Overview\n\n_What this component is and why it exists._\n",
        "auth": "# Auth\n\n_How authentication/authorization works with this component._\n",
        "integration": "# Integration\n\n_How other things talk to this — endpoints, protocols, data shapes._\n",
        "gotchas": "# Gotchas\n\n_Non-obvious behaviors, pitfalls, known issues._\n",
    },
    EntityType.REPO: {
        "overview": "# Overview\n\n_What this repo contains and how it's organized._\n",
        "style": "# Style\n\n_Code style, naming conventions, import rules, preferred patterns._\n",
        "testing": "# Testing\n\n_Test framework, how to run tests, coverage expectations._\n",
        "local-dev": "# Local Dev\n\n_How to run this locally — dependencies, env vars, setup steps._\n",
    },
    EntityType.TASK: {
        "goal": "# Goal\n\n_What this task is trying to accomplish, success criteria._\n",
        "plan": "# Plan\n\n_Steps, decisions, open questions._\n",
        "notes": "# Notes\n\n_Ongoing scratchpad._\n",
    },
    EntityType.GOVERNANCE: {
        "overview": "# Overview\n\n_What this guideline covers and who it applies to._\n",
        "rules": "# Rules\n\n_The actual guidelines._\n",
    },
}


def starter_subtopics(entity_type: EntityType) -> dict[str, str]:
    """Return a fresh copy of the starter subtopic templates for an entity type."""
    return dict(_SUBTOPIC_TEMPLATES.get(entity_type, {}))
