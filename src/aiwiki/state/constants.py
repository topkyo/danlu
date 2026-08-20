"""Global state constants extracted from the legacy app_state hub."""

from __future__ import annotations

DEFAULT_PROTOCOL = "general"


KNOWLEDGE_LIFECYCLE_KINDS = ("concept", "decision", "judgment")


KNOWLEDGE_LIFECYCLE_STATES = ("active", "review", "deferred", "retired", "revisit")


JUDGMENT_LIFECYCLE_STATES = ("formed", "active", "under-review", "revised", "retired")
