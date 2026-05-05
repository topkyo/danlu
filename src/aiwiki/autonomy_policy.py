"""Autonomy policy: kill switch for runtime side effects (M7.4a).

The policy file lives at ``.aiwiki/state/autonomy-policy.json``::

    {
      "schema_version": 1,
      "disable_lane_apply": false,
      "disable_alchemy_auto": false,
      "disable_l3_generate": false,
      "disable_external_llm": false
    }

Backward-compat by design:

- File missing  → all flags False (identical to today's behavior).
- File malformed → all flags False (refuse to ever silently disable on parse
  error; user can fix the file). We emit no warning here; CLIs may surface it.
- Env override ``AIWIKI_DISABLE_AUTOMATION=1`` forces every flag to True
  regardless of the file. Designed as a "panic button" knob.

In M7.4a only one hook point reads this module: external LLM (i.e.
``aiwiki.llm.create_backend_client``). Lane apply / alchemy auto / l3 generate
are wired in M7.4b.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .app_utils import runtime_write_operation

POLICY_RELATIVE = Path(".aiwiki") / "state" / "autonomy-policy.json"

KNOWN_FLAGS = (
    "disable_lane_apply",
    "disable_alchemy_auto",
    "disable_l3_generate",
    "disable_external_llm",
)

GLOBAL_OVERRIDE_ENV = "AIWIKI_DISABLE_AUTOMATION"


@dataclass(frozen=True)
class AutonomyPolicy:
    disable_lane_apply: bool = False
    disable_alchemy_auto: bool = False
    disable_l3_generate: bool = False
    disable_external_llm: bool = False


def policy_path(root: Path) -> Path:
    return root / POLICY_RELATIVE


def load_policy(root: Path) -> AutonomyPolicy:
    """Read the policy file. Missing/malformed → default (all False)."""

    path = policy_path(root)
    if not path.exists():
        return AutonomyPolicy()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return AutonomyPolicy()
    if not isinstance(raw, dict):
        return AutonomyPolicy()
    return AutonomyPolicy(
        disable_lane_apply=bool(raw.get("disable_lane_apply", False)),
        disable_alchemy_auto=bool(raw.get("disable_alchemy_auto", False)),
        disable_l3_generate=bool(raw.get("disable_l3_generate", False)),
        disable_external_llm=bool(raw.get("disable_external_llm", False)),
    )


def _env_global_override(env: Mapping[str, str] | None) -> bool:
    source = env if env is not None else os.environ
    return source.get(GLOBAL_OVERRIDE_ENV, "") == "1"


def is_disabled(
    root: Path,
    flag: str,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    """True iff the flag is disabled either by env override or by file."""

    if flag not in KNOWN_FLAGS:
        return False
    if _env_global_override(env):
        return True
    policy = load_policy(root)
    return bool(getattr(policy, flag, False))


def disabled_reason(
    root: Path,
    flag: str,
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Human-readable reason or None when not disabled."""

    if flag not in KNOWN_FLAGS:
        return None
    if _env_global_override(env):
        return f"{GLOBAL_OVERRIDE_ENV}=1 (global kill switch active)"
    policy = load_policy(root)
    if bool(getattr(policy, flag, False)):
        return f"autonomy-policy.{flag}=true"
    return None


@runtime_write_operation
def set_flag(root: Path, flag: str, value: bool) -> AutonomyPolicy:
    """M7.4c: write a single flag to the policy file. Atomic, idempotent.

    Unknown flag → ValueError. Missing parent dir → created. Malformed file
    → overwritten with a clean policy preserving the new flag value (we don't
    silently inherit corrupt fields).
    """

    if flag not in KNOWN_FLAGS:
        raise ValueError(f"Unknown autonomy flag: {flag}. Known: {', '.join(KNOWN_FLAGS)}")
    current = load_policy(root)
    flags = {name: getattr(current, name, False) for name in KNOWN_FLAGS}
    flags[flag] = bool(value)
    payload = {"schema_version": 1, **flags}
    path = policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return AutonomyPolicy(**flags)


def policy_status(root: Path, *, env: Mapping[str, str] | None = None) -> dict:
    """M7.4c: aggregate state for the autonomy-status CLI.

    Shape (stable):
        {
          "policy_path": "<absolute>",
          "policy_file_exists": bool,
          "global_override_env": "AIWIKI_DISABLE_AUTOMATION",
          "global_override_active": bool,
          "flags": {
            "<flag>": {"file_value": bool, "effective": bool, "reason": str|None}
          }
        }
    """

    path = policy_path(root)
    file_policy = load_policy(root)
    override = _env_global_override(env)
    flags: dict[str, dict] = {}
    for name in KNOWN_FLAGS:
        file_value = bool(getattr(file_policy, name, False))
        reason = disabled_reason(root, name, env=env)
        flags[name] = {
            "file_value": file_value,
            "effective": reason is not None,
            "reason": reason,
        }
    return {
        "policy_path": str(path),
        "policy_file_exists": path.exists(),
        "global_override_env": GLOBAL_OVERRIDE_ENV,
        "global_override_active": override,
        "flags": flags,
    }
