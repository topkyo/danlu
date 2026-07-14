"""Protocol code defaults.

`src/aiwiki/protocol/*` owns runtime code defaults: built-in protocol
descriptors, templates, and schema helpers used when a vault has no stronger
local materialization.

`schema/protocols/*` is the vault-facing override/materialized plane. Treat it
as reviewable configuration output/input for a vault, not a second source for
changing Python defaults. If the two planes drift, code defaults stay the
fallback and the schema plane must be regenerated or explicitly reviewed.
"""

from .library import PROTOCOL_JUDGMENT_EXTRA_FIELDS, PROTOCOL_LIBRARY, protocol_judgment_extra_fields

__all__ = [
    "PROTOCOL_JUDGMENT_EXTRA_FIELDS",
    "PROTOCOL_LIBRARY",
    "protocol_judgment_extra_fields",
]
