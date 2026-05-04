#!/usr/bin/env python3
"""Audit contract Stop Lines against changed files.

This helper is intentionally stdlib-only and is invoked by
scripts/stop_line_audit.sh. Unknown Stop Line phrases are warnings, not
failures: the first version only enforces explicit whitelist patterns.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# Whitelist maps Stop Line keywords (substring, case-insensitive) to glob
# patterns. Patterns must reflect actual repo paths; non-existent paths cause
# silent misses.
STOP_LINE_PATTERNS: dict[str, list[str]] = {
    "shell-summary contract": ["src/aiwiki/render/**"],
    "runtime schema": ["src/aiwiki/schemas/**"],
    "review/apply/audit 边界": [
        "src/aiwiki/runner/auto_adopt.py",
        "src/aiwiki/execution/review.py",
        "src/aiwiki/execution/audit_preview.py",
        "src/aiwiki/execution/lifecycle.py",
        "src/aiwiki/execution/machine_memory_actions.py",
        "src/aiwiki/execution/l3_proposals.py",
    ],
    "review/apply/audit": [
        "src/aiwiki/runner/auto_adopt.py",
        "src/aiwiki/execution/review.py",
        "src/aiwiki/execution/audit_preview.py",
        "src/aiwiki/execution/lifecycle.py",
        "src/aiwiki/execution/machine_memory_actions.py",
        "src/aiwiki/execution/l3_proposals.py",
    ],
    "npm 依赖": [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "node_modules/**",
        "*/package.json",
        "*/package-lock.json",
        "*/yarn.lock",
        "*/pnpm-lock.yaml",
        "*/node_modules/**",
        "**/package.json",
        "**/package-lock.json",
        "**/yarn.lock",
        "**/pnpm-lock.yaml",
        "**/node_modules/**",
    ],
    "npm dependencies": [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "node_modules/**",
        "*/package.json",
        "*/package-lock.json",
        "*/yarn.lock",
        "*/pnpm-lock.yaml",
        "*/node_modules/**",
        "**/package.json",
        "**/package-lock.json",
        "**/yarn.lock",
        "**/pnpm-lock.yaml",
        "**/node_modules/**",
    ],
    "installer 默认值": ["src/aiwiki/installer/**"],
    "installer defaults": ["src/aiwiki/installer/**"],
    "acceptance fixture": ["tests/fixtures/acceptance/**"],
    "expected goldens": ["tests/expected/**"],
    "expected/*.golden": ["tests/expected/**"],
    "_build_ask_prompt": ["src/aiwiki/runner/prompts.py"],
    "ReplayBackend": ["tests/acceptance/llm_replay.py"],
    "compute_prompt_hash": ["tests/acceptance/llm_replay.py"],
    "verify.sh 默认链路": ["scripts/verify.sh"],
    "receipt schema": ["src/aiwiki/schemas/**", "src/aiwiki/runner/receipts.py"],
    "产品代码": ["src/aiwiki/**"],
    "src/aiwiki": ["src/aiwiki/**"],
    "fixture": ["tests/fixtures/**"],
}


@dataclass(frozen=True)
class StopLineResult:
    phrase: str
    status: str
    keywords: list[str]
    patterns: list[str]
    violations: list[str]


class ContractNotFoundError(FileNotFoundError):
    """Raised when the requested contract path does not exist."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--baseline-label", required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--diff-list", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_contract(path: Path) -> str:
    if not path.is_file():
        raise ContractNotFoundError(f"ContractNotFound: contract file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def normalize_phrase(raw: str) -> str:
    phrase = raw.strip()
    phrase = re.sub(r"^[-*]\s+", "", phrase)
    phrase = re.sub(r"^\[[ xX]\]\s+", "", phrase)
    phrase = re.sub(r"^`?0`?\s+", "", phrase)
    phrase = phrase.strip(" `\t")
    return phrase


def parse_inline_stop_lines(text: str) -> list[str]:
    phrases: list[str] = []
    for line in text.splitlines():
        match = re.match(
            r"^\s*(?:[-*]\s+)?(?:\*\*)?Stop Lines?(?:\*\*)?\s*:\s*(.+)$",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        body = match.group(1).strip()
        for part in re.split(r"\s*(?:/|,)\s*", body):
            phrase = normalize_phrase(part)
            if phrase:
                phrases.append(phrase)
    return phrases


def parse_out_of_scope_bullets(text: str) -> list[str]:
    phrases: list[str] = []
    in_out_of_scope = False
    for line in text.splitlines():
        heading = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip().lower()
            if level == 2 and title == "out of scope":
                in_out_of_scope = True
                continue
            if in_out_of_scope and level <= 2:
                break
        if not in_out_of_scope:
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if bullet:
            phrase = normalize_phrase(bullet.group(1))
            if phrase:
                phrases.append(phrase)
    return phrases


def parse_stop_lines(text: str) -> list[str]:
    phrases = parse_inline_stop_lines(text)
    if phrases:
        return dedupe(phrases)
    return dedupe(parse_out_of_scope_bullets(text))


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def load_diff_files(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def matching_patterns(phrase: str) -> tuple[list[str], list[str]]:
    phrase_key = phrase.casefold()
    keywords: list[str] = []
    patterns: list[str] = []
    for keyword, keyword_patterns in STOP_LINE_PATTERNS.items():
        if keyword.casefold() not in phrase_key:
            continue
        keywords.append(keyword)
        patterns.extend(keyword_patterns)
    return keywords, dedupe(patterns)


def path_matches(path: str, pattern: str) -> bool:
    normalized = path.lstrip("./")
    normalized_pattern = pattern.lstrip("./")
    return fnmatch.fnmatchcase(normalized, normalized_pattern)


def audit(phrases: list[str], diff_files: list[str]) -> list[StopLineResult]:
    results: list[StopLineResult] = []
    for phrase in phrases:
        keywords, patterns = matching_patterns(phrase)
        if not keywords:
            results.append(StopLineResult(phrase, "unrecognized", [], [], []))
            continue
        if not patterns:
            results.append(StopLineResult(phrase, "no-pattern", keywords, [], []))
            continue
        violations = [
            file_path
            for file_path in diff_files
            if any(path_matches(file_path, pattern) for pattern in patterns)
        ]
        results.append(StopLineResult(phrase, "matched", keywords, patterns, violations))
    return results


def as_jsonable(results: list[StopLineResult]) -> list[dict[str, object]]:
    return [
        {
            "phrase": result.phrase,
            "status": result.status,
            "keywords": result.keywords,
            "patterns": result.patterns,
            "violations": result.violations,
        }
        for result in results
    ]


def render_human(
    *,
    contract: str,
    baseline_label: str,
    baseline_sha: str,
    diff_files: list[str],
    results: list[StopLineResult],
) -> str:
    lines: list[str] = [
        "stop_line_audit",
        f"  contract: {contract}",
        f"  baseline: {baseline_label} ({baseline_sha})",
        "",
        f"Stop Lines parsed: {len(results)}",
    ]
    if not results:
        lines.append("  [no-pattern]   no machine-parseable Stop Lines found")
    for result in results:
        if result.patterns:
            target = ", ".join(result.patterns)
            lines.append(f"  [{result.status:<12}] {result.phrase} → {target}")
        elif result.status == "unrecognized":
            lines.append(
                f"  [{result.status:<12}] {result.phrase}                    "
                "(no whitelist entry, skipped)"
            )
        else:
            lines.append(f"  [{result.status:<12}] {result.phrase}                    (no path pattern, skipped)")

    lines.extend(["", f"Diff scope: {len(diff_files)} files"])
    for file_path in diff_files:
        lines.append(f"  {file_path}")

    violation_count = sum(len(result.violations) for result in results)
    lines.extend(["", f"Violations: {violation_count}"])
    for result in results:
        if not result.violations:
            continue
        lines.append(f"  {result.phrase}")
        for file_path in result.violations:
            lines.append(f"    - {file_path}")

    lines.extend(["", "FAIL" if violation_count else "PASS"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        contract_text = read_contract(Path(args.contract))
        diff_files = load_diff_files(Path(args.diff_list))
    except ContractNotFoundError as exc:
        print(f"stop_line_audit error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"stop_line_audit error: FileReadError: {exc}", file=sys.stderr)
        return 2

    phrases = parse_stop_lines(contract_text)
    results = audit(phrases, diff_files)
    violation_count = sum(len(result.violations) for result in results)

    if args.json:
        print(
            json.dumps(
                {
                    "contract": args.contract,
                    "baseline": args.baseline_label,
                    "baseline_sha": args.baseline_sha,
                    "stop_lines_parsed": len(results),
                    "diff_scope": diff_files,
                    "results": as_jsonable(results),
                    "violations": violation_count,
                    "ok": violation_count == 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            render_human(
                contract=args.contract,
                baseline_label=args.baseline_label,
                baseline_sha=args.baseline_sha,
                diff_files=diff_files,
                results=results,
            )
        )

    return 1 if violation_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
