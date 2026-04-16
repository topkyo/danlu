---
id: "rewrite-proposal-a2a-key-concepts"
kind: "rewrite-proposal"
status: "proposed"
title: "A2a Key Concepts"
target_path: "wiki/concepts/a2a-key-concepts.md"
source_signature: "4dce5f60fca63c518922fda267aef53a59fc817cea9d80d511d90dce7fb6997c"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-16T14:24:31+00:00"
---

# Rewrite Proposal · A2a Key Concepts

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
- Target page: `wiki/concepts/a2a-key-concepts.md`
- Source signature: `4dce5f60fca63c518922fda267aef53a59fc817cea9d80d511d90dce7fb6997c`
- Source pages: `wiki/sources/discovered-20260415013529-a2a-key-concepts.md`

## Current Summary Snapshot
A2A 的当前可证实核心概念，是一个围绕 `User`、`A2A Client`、`A2A Server` 三方展开的协议交互模型：用户意图由 client 代理发起，server 通过 HTTP(S) 暴露协议端点并对外表现为黑盒，内部工具、记忆和实现细节不直接暴露给 client。[A2A Key Concepts](../sources/discovered-20260415013529-a2a-key-concepts.md)

这份来源同时把 A2A 描述成一个基于 HTTP(S) 与 JSON-RPC 2.0 的代理间通信协议，并明确支持三类交互模式：同步风格的 request/response（长任务可轮询）、基于 Server-Sent Events 的流式更新，以及面向长时或断连场景的 webhook 推送通知。[A2A Key Concepts](../sources/discovered-20260415013529-a2a-key-concepts.md)

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
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite a2a-key-concepts --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite a2a-key-concepts`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite a2a-key-concepts`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite a2a-key-concepts`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
