"""Autonomy policy: kill switch for runtime side effects (M7.4a).

The policy file lives at ``.aiwiki/state/autonomy-policy.json``::

    {
      "schema_version": 2,
      "autonomy_profile": "strong",
      "disable_lane_apply": false,
      "disable_alchemy_auto": false,
      "disable_l3_generate": false,
      "disable_external_llm": false,
      "auto_apply_light": true,
      "auto_adopt_l1": true,
      "auto_adopt_l2": true,
      "auto_adopt_l3": true,
      "auto_adopt_judgments": true,
      "max_l3_apply_per_run": 1,
      "judgment_review_limit": 5,
      "require_clean_before_hash": true,
      "auto_revert_on_verify_failure": true
    }

Backward-compat by design:

- File missing  → all flags False (identical to today's behavior).
- File malformed/unreadable → all flags True (fail closed) with load_error so
  CLIs can surface why automation is disabled.
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
POLICY_SCHEMA_VERSION = 2
DEFAULT_AUTONOMY_PROFILE = "strong"

KNOWN_FLAGS = (
    "disable_lane_apply",
    "disable_alchemy_auto",
    "disable_l3_generate",
    "disable_external_llm",
)

GLOBAL_OVERRIDE_ENV = "AIWIKI_DISABLE_AUTOMATION"


@dataclass(frozen=True)
class AutonomyPolicy:
    schema_version: int = POLICY_SCHEMA_VERSION
    autonomy_profile: str = DEFAULT_AUTONOMY_PROFILE
    disable_lane_apply: bool = False
    disable_alchemy_auto: bool = False
    disable_l3_generate: bool = False
    disable_external_llm: bool = False
    auto_apply_light: bool = True
    auto_adopt_l1: bool = True
    auto_adopt_l2: bool = True
    auto_adopt_l3: bool = True
    auto_adopt_judgments: bool = True
    max_l3_apply_per_run: int = 1
    judgment_review_limit: int = 5
    require_clean_before_hash: bool = True
    auto_revert_on_verify_failure: bool = True
    load_error: str | None = None


def policy_path(root: Path) -> Path:
    return root / POLICY_RELATIVE


def load_policy(root: Path) -> AutonomyPolicy:
    """Read the policy file. Missing → default; malformed/unreadable → fail closed."""

    path = policy_path(root)
    try:
        if not path.exists():
            return AutonomyPolicy()
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        return _disabled_policy(f"autonomy-policy file unreadable: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        return _disabled_policy(f"autonomy-policy file malformed: {e}")
    if not isinstance(raw, dict):
        return _disabled_policy("autonomy-policy file not a JSON object")
    schema_version = raw.get("schema_version", 1)
    if schema_version not in (1, 2):
        return _disabled_policy(f"unsupported autonomy-policy schema_version: {schema_version}")
    return AutonomyPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        autonomy_profile=str(raw.get("autonomy_profile") or DEFAULT_AUTONOMY_PROFILE),
        disable_lane_apply=bool(raw.get("disable_lane_apply", False)),
        disable_alchemy_auto=bool(raw.get("disable_alchemy_auto", False)),
        disable_l3_generate=bool(raw.get("disable_l3_generate", False)),
        disable_external_llm=bool(raw.get("disable_external_llm", False)),
        auto_apply_light=bool(raw.get("auto_apply_light", True)),
        auto_adopt_l1=bool(raw.get("auto_adopt_l1", True)),
        auto_adopt_l2=bool(raw.get("auto_adopt_l2", True)),
        auto_adopt_l3=bool(raw.get("auto_adopt_l3", True)),
        auto_adopt_judgments=bool(raw.get("auto_adopt_judgments", True)),
        max_l3_apply_per_run=_positive_int(raw.get("max_l3_apply_per_run"), 1),
        judgment_review_limit=_positive_int(raw.get("judgment_review_limit"), 5),
        require_clean_before_hash=bool(raw.get("require_clean_before_hash", True)),
        auto_revert_on_verify_failure=bool(raw.get("auto_revert_on_verify_failure", True)),
    )


def _disabled_policy(reason: str) -> AutonomyPolicy:
    return AutonomyPolicy(
        auto_apply_light=False,
        auto_adopt_l1=False,
        auto_adopt_l2=False,
        auto_adopt_l3=False,
        auto_adopt_judgments=False,
        disable_lane_apply=True,
        disable_alchemy_auto=True,
        disable_l3_generate=True,
        disable_external_llm=True,
        load_error=reason,
    )


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(str(value).strip()) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return AutonomyPolicy(**{**_policy_payload(base_policy), **flags})


def _policy_payload(policy: AutonomyPolicy) -> dict[str, object]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "autonomy_profile": policy.autonomy_profile or DEFAULT_AUTONOMY_PROFILE,
        "disable_lane_apply": bool(policy.disable_lane_apply),
        "disable_alchemy_auto": bool(policy.disable_alchemy_auto),
        "disable_l3_generate": bool(policy.disable_l3_generate),
        "disable_external_llm": bool(policy.disable_external_llm),
        "auto_apply_light": bool(policy.auto_apply_light),
        "auto_adopt_l1": bool(policy.auto_adopt_l1),
        "auto_adopt_l2": bool(policy.auto_adopt_l2),
        "auto_adopt_l3": bool(policy.auto_adopt_l3),
        "auto_adopt_judgments": bool(policy.auto_adopt_judgments),
        "max_l3_apply_per_run": int(policy.max_l3_apply_per_run),
        "judgment_review_limit": int(policy.judgment_review_limit),
        "require_clean_before_hash": bool(policy.require_clean_before_hash),
        "auto_revert_on_verify_failure": bool(policy.auto_revert_on_verify_failure),
    }


def _env_flag_value(name: str, env: Mapping[str, str] | None) -> bool | None:
    source = env if env is not None else os.environ
    if name not in source:
        return None
    return source.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def nightly_autonomy_flags(root: Path, *, env: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Effective default-autonomy flags for run-nightly.

    Env variables remain explicit overrides. Missing env values fall back to the
    v2 policy profile, whose default is strong autonomy. Corrupt policy or the
    global kill switch fail closed.
    """

    policy = load_policy(root)
    globally_disabled = _env_global_override(env) or policy.load_error is not None
    defaults = {
        "auto_apply_light": bool(policy.auto_apply_light),
        "auto_adopt_l1": bool(policy.auto_adopt_l1),
        "auto_adopt_l2": bool(policy.auto_adopt_l2),
        "auto_adopt_l3": bool(policy.auto_adopt_l3),
        "auto_adopt_judgments": bool(policy.auto_adopt_judgments),
    }
    env_names = {
        "auto_apply_light": "AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT",
        "auto_adopt_l1": "AIWIKI_NIGHTLY_AUTO_ADOPT_L1",
        "auto_adopt_l2": "AIWIKI_NIGHTLY_AUTO_ADOPT_L2",
        "auto_adopt_l3": "AIWIKI_NIGHTLY_AUTO_ADOPT_L3",
        "auto_adopt_judgments": "AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS",
    }
    effective: dict[str, bool] = {}
    for key, env_name in env_names.items():
        override = _env_flag_value(env_name, env)
        effective[key] = defaults[key] if override is None else override
    if globally_disabled or policy.disable_lane_apply:
        effective["auto_apply_light"] = False
    if globally_disabled or policy.disable_alchemy_auto:
        effective["auto_apply_light"] = False
        effective["auto_adopt_l1"] = False
        effective["auto_adopt_l2"] = False
        effective["auto_adopt_l3"] = False
        effective["auto_adopt_judgments"] = False
    if globally_disabled or policy.disable_l3_generate:
        effective["auto_adopt_l3"] = False
    if globally_disabled or policy.disable_external_llm:
        effective["auto_adopt_judgments"] = False
    return effective


def policy_status(root: Path, *, env: Mapping[str, str] | None = None) -> dict:
    """M7.4c: aggregate state for the autonomy-status CLI.

    Shape (stable):
        {
          "policy_path": "<absolute>",
          "policy_file_exists": bool,
          "policy_load_error": str|None,
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
        "policy_load_error": file_policy.load_error,
        "global_override_env": GLOBAL_OVERRIDE_ENV,
        "global_override_active": override,
        "flags": flags,
    }
