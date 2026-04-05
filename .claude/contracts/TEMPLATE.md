# Sprint Contract

## Goal

[一句话说明本轮要交付什么]

## Problem / Context

- [当前问题、触发背景、相关上下文]

## Success Criteria

- [ ] [具体可验证的完成条件]

## Constraints / Dependencies

- [限制条件、依赖、前置条件]

## Questions / Assumptions

- [待确认问题；若先按假设推进，明确写出假设]

## Chosen Approach

- [本轮采用的方案；说明核心思路与原因]

## Alternatives Rejected

- [备选方案 + 为什么这轮不选]

## Execution Plan

1. [第一步]
2. [第二步]

## In Scope

- [本轮明确要做的项]

## Out Of Scope

- [本轮明确不做的项]

## Affected Files / Modules

- [路径或模块名]

## Gate Requirements

- `verify`: required
- `qa-review`: required | not-required
- `qa-runtime`: required | not-required

## Gate Artifacts

- `qa-review`: `.claude/gates/qa-review.md`（或其他 `.claude/gates/*.md` 路径）
- `qa-runtime`: `.claude/gates/qa-runtime.md`（或其他 `.claude/gates/*.md` 路径）

本节路径会被脚本实际读取，不只是文档；请保持在 `.claude/gates/` 下，避免 `worktree_fingerprint` 自指失效。

## Gate Artifact Headers

- `status`: `pass | fail | blocked | not-required`
- `checked_at`: `YYYY-MM-DD`
- `contract_sha`: 当前 `.claude/contracts/active.md` 的 sha256
- `worktree_fingerprint`: 当前工作区状态指纹
- `summary`: 一句话摘要
- `qa-review` 在 `status: pass` 时必填: `reviewer_mode`
- 若 `reviewer_mode: same-context`，必填: `reviewer_fallback_reason`
- `qa-review` 推荐追加: `reviewer_identity`、`reviewer_scope`
- `qa-runtime` 在 `status: pass` 时必填: `runtime_mode`; 推荐追加: `runtime_identity`

## Verification Plan

- `verify`:
- `qa-review`: 优先隔离 reviewer；若退化为同 context 自审，需写明触发条件
- `qa-runtime`: 写明 runtime layer 与实际检查入口

## Fail Gate

- [什么情况视为未完成，不能 deploy]

## Residual Risks

- [即使通过也仍然存在的风险]
