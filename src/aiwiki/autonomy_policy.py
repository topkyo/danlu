"""Autonomy policy: kill switch for runtime side effects (M7.4a).

The policy file lives at ``.aiwiki/state/autonomy-policy.json``::

    {
      "schema_version": 4,
      "autonomy_profile": "agentic",
      "disable_external_llm": false,
      "require_clean_before_hash": true,
      "auto_revert_on_verify_failure": true
    }

Backward-compat by design:

- File missing  → agentic default with automation enabled unless a disable flag is set.
- File malformed/unreadable → fail closed with load_error so CLIs can surface
  why automation is disabled.
- Env override ``AIWIKI_DISABLE_AUTOMATION=1`` sets ``disable_external_llm``
  (blocks LLM client creation). Watcher and nightly keep running.
- Legacy ``auto_adopt_*`` / ``auto_apply_*`` / ``max_l3_apply_per_run`` /
  ``judgment_review_limit`` / ``disable_lane_apply`` / ``disable_alchemy_auto`` /
  ``disable_l3_generate`` keys in old JSON are ignored (no-op after W3/W9/R10).

External LLM gating and governed apply receipts read this module so the local
runtime has one policy source for automation boundaries.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .utils.io import atomic_write_text, runtime_write_operation

POLICY_RELATIVE = Path(".aiwiki") / "state" / "autonomy-policy.json"
POLICY_SCHEMA_VERSION = 4
DEFAULT_AUTONOMY_PROFILE = "agentic"
KNOWN_AUTONOMY_PROFILES = {"strong", "agentic"}

KNOWN_FLAGS = ("disable_external_llm",)

GLOBAL_OVERRIDE_ENV = "AIWIKI_DISABLE_AUTOMATION"
PROFILE_OVERRIDE_ENV = "AIWIKI_AUTONOMY_PROFILE"


@dataclass(frozen=True)
class AutonomyPolicy:
    schema_version: int = POLICY_SCHEMA_VERSION
    autonomy_profile: str = DEFAULT_AUTONOMY_PROFILE
    disable_external_llm: bool = False
    require_clean_before_hash: bool = True
    auto_revert_on_verify_failure: bool = True
    load_error: str | None = None


def policy_path(root: Path) -> Path:
    return root / POLICY_RELATIVE


def load_policy(root: Path, *, env: Mapping[str, str] | None = None) -> AutonomyPolicy:
    """Read the policy file. Missing → default; malformed/unreadable → fail closed."""

    path = policy_path(root)
    try:
        if not path.exists():
            env_profile = _profile_override(env)
            if env_profile is not None:
                if env_profile not in KNOWN_AUTONOMY_PROFILES:
                    return _disabled_policy(f"unsupported {PROFILE_OVERRIDE_ENV}: {env_profile}")
                return _default_policy_for_profile(env_profile)
            return AutonomyPolicy()
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        return _disabled_policy(f"autonomy-policy file unreadable: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        return _disabled_policy(f"autonomy-policy file malformed: {e}")
    if not isinstance(raw, dict):
        return _disabled_policy("autonomy-policy file not a JSON object")
    schema_version = raw.get("schema_version", 1)
    if schema_version not in (1, 2, 3, 4):
        return _disabled_policy(f"unsupported autonomy-policy schema_version: {schema_version}")
    profile = str(_profile_override(env) or raw.get("autonomy_profile") or DEFAULT_AUTONOMY_PROFILE)
    if profile not in KNOWN_AUTONOMY_PROFILES:
        return _disabled_policy(f"unsupported autonomy_profile: {profile}")
    return AutonomyPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        autonomy_profile=profile,
        disable_external_llm=bool(raw.get("disable_external_llm", False)),
        require_clean_before_hash=bool(raw.get("require_clean_before_hash", True)),
        auto_revert_on_verify_failure=bool(raw.get("auto_revert_on_verify_failure", True)),
    )


def _profile_override(env: Mapping[str, str] | None = None) -> str | None:
    source = env if env is not None else os.environ
    value = source.get(PROFILE_OVERRIDE_ENV)
    if value is None:
        return None
    return value.strip().lower()


def _default_policy_for_profile(profile: str) -> AutonomyPolicy:
    return AutonomyPolicy(autonomy_profile=profile)


def _disabled_policy(reason: str) -> AutonomyPolicy:
    return AutonomyPolicy(
        disable_external_llm=True,
        load_error=reason,
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
    policy = load_policy(root, env=env)
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
    policy = load_policy(root, env=env)
    if policy.load_error is not None:
        return f"autonomy-policy fail-closed: {policy.load_error}"
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
    base_policy = AutonomyPolicy() if current.load_error is not None else current
    if current.load_error is not None:
        flags = {name: False for name in KNOWN_FLAGS}
    else:
        flags = {name: getattr(current, name, False) for name in KNOWN_FLAGS}
    flags[flag] = bool(value)
    payload = {**_policy_payload(base_policy), **flags}
    payload["schema_version"] = POLICY_SCHEMA_VERSION
    path = policy_path(root)
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    return AutonomyPolicy(**{**_policy_payload(base_policy), **flags})


def _policy_payload(policy: AutonomyPolicy) -> dict[str, object]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "autonomy_profile": policy.autonomy_profile or DEFAULT_AUTONOMY_PROFILE,
        "disable_external_llm": bool(policy.disable_external_llm),
        "require_clean_before_hash": bool(policy.require_clean_before_hash),
        "auto_revert_on_verify_failure": bool(policy.auto_revert_on_verify_failure),
    }
