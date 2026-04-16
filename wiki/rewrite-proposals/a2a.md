---
id: "rewrite-proposal-a2a"
kind: "rewrite-proposal"
status: "proposed"
title: "A2a"
target_path: "wiki/concepts/a2a.md"
source_signature: "f66159b548a84cbe56482d260ff4f84fdd37494b1947c479af11671c2a626f17"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-16T14:24:31+00:00"
---

# Rewrite Proposal · A2a

## Proposal Status
- Status: `待审提案`
- Priority: `high`
- Score: `6`
- Quality score: `76`
- Quality band: `stable`
- Apply ready: `False`
- First proposed: `2026-04-15T01:37:58+00:00`
- Last proposed: `2026-04-16T14:24:31+00:00`
- Reviewed at: `none`
- Applied at: `none`
- Reverted at: `none`

## Target
- Target page: `wiki/concepts/a2a.md`
- Source signature: `f66159b548a84cbe56482d260ff4f84fdd37494b1947c479af11671c2a626f17`
- Source pages: `wiki/sources/discovered-20260415013529-a2a-key-concepts.md`

## Current Summary Snapshot
A2A 在当前证据里可被落实为一个面向 agent 间互操作的协议外部契约：`User` 提供意图，`A2A Client` 代表用户发起交互，`A2A Server` 通过 HTTP(S) 端点暴露协议能力，但其内部工具、记忆和执行方式对 client 保持黑盒。[A2A Key Concepts](../sources/discovered-20260415013529-a2a-key-concepts.md)

这意味着 A2A 的核心不在 server 内部如何实现 agent，而在不同系统之间如何以统一发现、消息封装和任务执行语义互通；现有来源同时把该协议锚定在 HTTP(S) 传输和 JSON-RPC 2.0 负载之上。[A2A Key Concepts](../sources/discovered-20260415013529-a2a-key-concepts.md)

## Rewrite Strategy
- Issues: `soft-hardness, single-source, evidence-gap, merge-boundary`
- Strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。

## Verification
- Status: `not-run`
- Checked at: `none`
- Summary: Verification has not run yet.
- Issues: `none`

## Rollback
- Previous snapshot available: `False`
- Last applied at: `none`
- Revert note: none

## Commands
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite a2a --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite a2a`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite a2a`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite a2a`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
