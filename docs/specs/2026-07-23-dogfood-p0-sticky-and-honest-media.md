# Dogfood P0：材料粘性 + 图片诚实失败（Slice 1）

**Date:** 2026-07-23  
**Status:** Approved (chat)  
**Owner:** Product Shell + ask runtime  
**Packaging:** 三片顺序之 **Slice 1 = 全部 P0**；Slice 2 = P1；Slice 3 = P2 观察清单  
**Related:** dogfood 调研（2026-07-21~22）：追问丢 `material_refs`；图片 ask 假成功

## Goal

修好 dogfood 暴露的两处信任缺口：

1. **追问继承刚投材料**（Shell 本地短期粘性，持久化到插件 data）。
2. **图片/不可读材料诚实失败**：有 `material_refs` 但读不出内容时，禁止用无关 wiki 冒充「分析了该材料」。

## Decisions

1. **打包 = A**：本 spec 只覆盖 P0；P1（图片 hash 去重、概念门槛、探针失踪）与 P2（观察项）另开。
2. **粘性实现 = Shell 本地（方案 1）**：插件状态 `stickyMaterialRefs`；**Runtime 会话文件 = 长期升级路径，本片不做**。
3. **持久化 = P1**：写入插件 `data.json`（经现有 savePluginState）；Obsidian 重启仍在；**新 drop 成功则整组替换**；不设短 TTL。
4. **图片 = 方案 X**：收紧诚实暴露；**不加**新 vision；drop Notice + ask 短答诚实降级。
5. **弱命中**：不确定性必须放在答案**首段**；粘性落地后「有什么区别」类应优先靠 sticky 修复。
6. **实现路径 = ①**：Shell 粘性注入 + runtime 对「有 refs、无可读上下文」分支收紧；不只改 prompt 拼接。

## Design

### Architecture

```text
drop success → stickyMaterialRefs = { paths, updatedAt, source:"drop" }
        │
追问 ask（无显式 materials）
        │
        ▼
Shell: buildAutoAskQuestion(q, sticky.paths) → run-ask
        │
        ▼
runtime: parse material_refs → _read_material_context
        │
        ├─ 有可读文本 → 正常合成
        └─ refs 非空但上下文空（如仅 jpeg）→ 诚实降级短答，不灌无关 wiki 主答案
```

### Components

| Area | Change |
|------|--------|
| Shell state | `stickyMaterialRefs` 读写；load/save 随 plugin state |
| Shell ask/drop | drop 成功替换 sticky；追问注入；显式 materials 不叠旧 sticky |
| Shell Notice | image drop 无可用摘要时提示「仅存档」 |
| `workflows_ask*` / context | 「有 material_refs、无可读 context」→ 诚实降级分支 |
| Tests | Jest sticky + llm-integration/mock 诚实降级 |

### Data shape

```json
{
  "stickyMaterialRefs": {
    "paths": ["raw/inbox/codex-goal.md", "raw/inbox/codex-goal-sm.md"],
    "updatedAt": "2026-07-22T08:49:22+00:00",
    "source": "drop"
  }
}
```

- `paths`：vault 相对路径，去重保序。
- `source`：`"drop" | "ask" | "explicit-@"`。
- 清除：仅由新 drop 替换（或显式 `@` 新集合替换）；本片不强制 Advanced 清除按钮。

### Behavior detail

**粘性写入**

- drop 成功且 `materialPaths` 非空 → 替换 sticky。
- ask 本轮实际使用了 materials（注入或显式）→ 可刷新 `updatedAt`；若路径集合变化则更新 `paths`。
- 用户输入显式另一批材料提示 → 替换。

**粘性读取**

- 追问无显式 materials → 把 sticky `paths` 注入 ask 问题（复用现有「请优先使用本次投喂材料回答；材料路径…」句式，见 `buildAutoAskQuestion`）。
- 本轮已有显式 materials → **不**叠加 sticky。

**图片 / 不可读材料**

- 根因：`_read_material_context` 仅读 `.md`/`.txt`；jpeg 静默跳过。
- 当 `material_refs` 非空且可读 context 为空（或仅 pending/preview-unavailable 占位）：
  - 报告**首段**诚实说明：材料已登记，当前无法读取内容。
  - **短答降级**；不得用无关检索 wiki 充当主分析。
  - 标记为 degraded / 非「假装 deliverable 已理解附件」语义（具体字段与现有 ask degraded 标记对齐，实现时选已有约定）。
- Shell：image drop 完成且无可用视觉摘要 → Notice「图片已存档，暂不能内容分析」。

**弱命中（文本）**

- prompt / 后处理约束：若必须承认不确定，**首段**说出；禁止先写长替代故事再在文末小声承认。

### Error handling

- sticky 损坏 / 非数组 → 视为空并在下次 save 纠正。
- 粘性路径已不存在 → 仍注入路径；runtime 读失败走诚实/弱上下文路径，不崩溃。
- 诚实降级仍写报告文件（用户可见），不静默吞掉。

### Testing

- Jest：sticky 写入/替换/注入/不叠显式 materials；hydrate 后仍在；image Notice 契约。
- llm-integration 或等价：仅 jpeg `material_refs` → 诚实降级（mock LLM），断言不走「无关 wiki 长综述」主路径。
- Verify：`bash scripts/verify.sh product-shell-static` + `llm-integration`（或 `verify_target_rules.sh`）。
- 可选 dogfood：复现「干嘛的 → 有什么区别」应带 sticky；纯图 ask 应诚实。

## Success criteria

- 连续追问在未新 drop、未换材料时，ask 携带上一轮材料路径。
- 纯不可读图材料的 ask：首段诚实，无「分析了图」式假成功长文。
- `product-shell-static` + 相关 llm-integration PASS。

## Out of scope

- Runtime vault session 文件（长期方案 2）。
- 新 vision / OCR 能力。
- 图片 content-hash 去重、概念抽取门槛、探针报告失踪排查（Slice 2）。
- Webhook dogfood 验证、Ask 进度机改造（Slice 3）。
- 修改 dogfood vault 历史报告内容。

## Open questions

(none)

## Follow-on slices (pointer only)

- **Slice 2 (P1):** 图片 sha256 去重；概念最小信息量门槛；调查探针 md 失踪。
- **Slice 3 (P2):** 15s 软提示观察；notify 未跑过记为未验证。
