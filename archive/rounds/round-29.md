# Round 29 — LLM Worker Boundary + Dogfood Noise Fix

status: 完成
commit: 

Round 29 — LLM Worker Boundary + Dogfood Noise Fix — 完成
- **目的**: 回应 Round 28 暴露的问题：炼丹炉应继续 LLM-first，但常驻 watcher 不应 inline 阻塞跑 LLM；同时修复 Batch/provenance 标签进 concept graph 和 deterministic source 摘要太空的问题
- **实现**:
  - `scripts/run_watch.sh` 默认 `AIWIKI_WATCH_DETERMINISTIC_ONLY=1` 语义；只有显式设置 `AIWIKI_WATCH_DETERMINISTIC_ONLY=0` 才让 watcher inline 跑 LLM
  - `scripts/install_user_service.sh` 新安装 watcher env 默认写 `AIWIKI_WATCH_DETERMINISTIC_ONLY=1`；nightly 默认仍是 `AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0`，保留 scheduled LLM worker 路径
  - deterministic source page Summary 现在保留 `- Pending LLM summary.` enrichment marker，同时追加 2-3 条 `Deterministic preview` bullet，LLM 不可用时不再只有空占位
  - concept noise floor bump 到 6；`batch` / `receipt` 和 timestamp fragment 被过滤，title phrase 构造前去重，避免 `Eva Robot Batch`、`29t13`、`eva robot robot` 等机械噪声进入概念层
- **dogfood 复核**:
  - `/home/tim/danlu/炼丹炉` 重新 compile 后，Batch B 三个 source page 的 concept links 不再包含 `Batch` / `Eva Robot Batch` / `29t13` / `Eva Robot Robot`
  - Batch B source Summary 已出现 deterministic preview，同时仍保留 LLM enrichment marker
  - `aiwiki-watch.service` active，实际命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - 本机 nightly env 已恢复 `AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0`，LLM enrichment 留给 nightly / run-compile / run-ask
- **验证**:
  - focused watcher/service tests 4/4 pass
  - focused content/noise tests 7/7 pass
  - dogfood compile smoke pass；主 metrics 仍保持 provenance/stale/review/proposal/judgment 为 1.0，`output_file_back_rate=0.6667` 继续保留为 skeleton fallback report 的真实证据
  - `bash scripts/verify.sh` exit 0；1508 unit + 13 acceptance；coverage 92%
- **当前评估**: 这不是“炼丹炉不跑 LLM”，而是把 LLM 从常驻 watcher 的同步路径挪到更可控的 enrichment worker 路径；下一步应继续做大上下文 `run-ask` chunked synthesis，而不是让 watcher 承担长耗时推理
