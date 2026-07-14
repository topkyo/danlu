# Round 41 — Dogfood Batch Adoption Run

status: 完成
commit: 

Round 41 — Dogfood Batch Adoption Run — 完成
- **目的**: 在 dogfood vault 上跑通 review-action 批量入口完整状态机（proposed → accepted → resolved），验证 Round 40 终局对比表中"批量入口 CLI 已存在"的判断
- **提交基线**:
  - `5dbfdef`（Round 40 baseline；本轮纯运行测试，无代码变更，并入 Round 42 提交）
- **实测过程**:
  - 停 `aiwiki-watch.service`（避免 lock 冲突）
  - baseline：review-queue total=40；machine_memory_actions=19；concept_backlog=11；revisit_concepts=10；lint=0/91
  - 跑 `review-action --all-pending --kind monitor-bridge-concept --status accepted`：5 个 review-first proposed bridge concept（vlm/robot/eva/navigation/imu）一次性写出 `operation=action-review-batch` 内置 batch receipt，从 proposed → accepted
  - 接着 5 次单条 `review-action <id> --status resolved`（`--all-pending` 仅支持 proposed→accepted，不支持 accepted→resolved），全部成功
  - 复跑 `review-queue` / `today` / `metrics` / `lint`
- **dogfood 净变化（baseline → after closure）**:
  - review-queue total: 40 → 35（净 −5）
  - machine_memory_actions: 19 → 14（−5；5 个 review-first 关闭）
  - concept_backlog: 11 → 1（−10；review ack 推进 concept lifecycle）
  - revisit_concepts: 10 → 1（−9）
  - lint: 91 → 91（不变；review ack 不写 maintenance note，符合 contract「不静默采纳语义」）
  - metrics: provenance/stale/closure/proposal/revisit/file_back 全保持稳定
  - knowledge_stats: concept_nodes=30 / source_nodes=32 / judgment_nodes=9 不变
- **验证结论**:
  - ✅ `review-action --all-pending --kind <kind>` 批量 review-state 写入工作正常，写 `action-review-batch` operation receipt
  - ✅ 完整 candidate 状态机 `proposed → accepted → resolved` 端到端通畅
  - ✅ 5 个 ack 触发派生 bucket 大幅收敛（concept_backlog 与 revisit_concepts 净减 19）
  - ⚠️ `apply-action --all-accepted-low-risk --dry-run` 当前 dogfood 上返回 "No accepted low-risk actions are ready for batch apply"——因为 `monitor-bridge-concept` policy 为 manual-repair（不进 low-risk apply 集合）；split-overloaded-concept accepted 也不在该集合
  - 下一步要让 lint warnings 真正下降，仍需人工/外部 model 写 maintenance note 与 judgment metadata，不能靠 batch ack
- **结论**: Round 40 终局对比表中"批量 CLI 已存在"判断成立；剩余短板是「批量入口未 surface 到 today」（已在 Round 42 收口）与「lint 语义债收敛」（需 quota 恢复 + 多周自然运行）
- **监控**: 闭环结束后恢复 `aiwiki-watch.service` active
