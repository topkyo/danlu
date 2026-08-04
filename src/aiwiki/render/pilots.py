"""Domain-pilot scorecard lookup (炼丹炉 render layer).

Only ``protocol_scorecard`` survives here: the domain-pilot build machinery
(``build_domain_pilots*`` and helpers) was retired when the surface was cut
to an always-empty scorecard list (W4 surface cut), and the dead stubs were
removed in the 2026-08 audit remediation.
"""

from __future__ import annotations

from typing import Any


def protocol_scorecard(domain_pilots: dict[str, Any], protocol: str) -> dict[str, Any]:
    for scorecard in domain_pilots.get("scorecards", []):
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "") == protocol:
            return scorecard
    return {}
