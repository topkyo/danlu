# M6.1b acceptance fixtures

这些 fixtures 用于 deterministic acceptance replay tests：测试通过 `backend_responses/*.json` 回放 LLM 输出，不调用真实 LLM，并用 `prompt_hash` 确认运行时 prompt 与录制时一致。

## 什么时候会漂移

任何会被 `_build_ask_prompt` 拼入 prompt 的内容或结构变化，都可能导致 `prompt_hash` 漂移，包括：

- prompt builder 逻辑改动
- schema / protocol 页面改动
- index 页面改动
- source / concept / machine memory 上下文改动

## 刷新方式

```bash
python3 scripts/refresh_acceptance_fixture.py --case M6.1b/<case_name>
```

脚本只重算 `prompt_hash` 并重命名 `backend_responses/000N-<hash>.json`，保留既有 `response_text`、`response_id`、`usage`、`backend`、`model`，并保留 backend-failure fixture 的 `failure` 字段。

## Review 重点

- `prompt_hash` 改动应伴随 prompt 上下文的预期变更。
- 如果只有 hash 改动但 `response_text` 也变了，需要更深 review；这可能不是普通 prompt drift，而是刷新流程或 runtime bug。

## 已知约束

`_build_ask_prompt` 必须 deterministic；不要引入随机数、时间戳或其他非确定性输入，否则 replay fixture 无法稳定。
