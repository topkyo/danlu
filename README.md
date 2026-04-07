# aiwiki

`aiwiki` 是一个本地优先的知识编译器脚手架。

它把知识库当作可编译产物来看待：

- `raw/` 存放原始材料
- `wiki/` 存放编译后的 markdown 知识层
- `output/` 存放报告、幻灯片、图表 brief 等查询产物

## 当前能力

仓库提供一套 Python CLI，分成 deterministic 主链和可选的 LLM 增强层。

Deterministic 命令：

- `ingest`：把本地文件或 URL stub 登记进 `raw/`
- `compile`：把当前来源库存编译成 `wiki/sources/`、`wiki/concepts/`、`wiki/indexes/`
- `ask`：基于 wiki 和 machine-memory query planning 打包报告/幻灯片/图表 brief
- `file-back`：把高价值 markdown 回流到 `wiki/derived/`、`wiki/decisions/` 或 `wiki/judgments/`
- `review-page`：推进 decision/judgment 页面在审阅流中的状态
- `lint`：检查缺页、坏引用、明显 provenance 缺口
- `nightly`：跑 deterministic compile + lint，并写出 repair backlog 与 nightly health 快照

LLM 增强命令：

- `run-compile`：用 LLM 补来源摘要和概念摘要
- `run-ask`：创建查询 artifact，并让 LLM 把它补成 grounded 内容
- `run-lint`：跑 deterministic lint，再补 semantic lint 报告
- `run-nightly`：跑 compile + semantic lint，并生成 nightly 修复产物
- `llm-check`：查看当前解析到的 LLM backend
- `auto-once`：自动跑一轮 ingest/compile/summary/lint
- `watch`：持续监听 `raw/inbox/` 并自动触发管线

原料入口：

- `drop-url`：抓网页到 `raw/inbox/`，有浏览器时优先渲染后提取正文，并把页面图片落到 `raw/assets/`
- `drop-pdf`：把原 PDF 存到 `raw/assets/`，抽取文字到 `raw/inbox/`
- `drop-image`：把原图存到 `raw/assets/`，把 metadata/OCR/vision note 存到 `raw/inbox/`
- `drop-repo`：把本地或远端 repo 快照成 markdown 来源笔记

deterministic 路径始终是安全基线；LLM runner 是附加层，依赖 prompt 文件和显式文件路径引用。

## 目录结构

```text
raw/
  inbox/        直接丢入或导入的来源文件
  normalized/   预留给未来归一化步骤
  assets/       本地图片和附件
schema/
  index.md      运行时规则总索引
  *.md          ingest/citation/conflict/review/writeback/taxonomy 规则
wiki/
  sources/      每个 raw 输入一页来源页
  concepts/     从多个来源综合出的概念页
  decisions/    显式决策页
  judgments/    显式判断页
  indexes/      总索引、状态页、机器记忆、图谱健康、漂移、修复待办、日志
  derived/      回流后的派生 markdown
output/
  reports/
  slides/
  figures/
  lint/
.aiwiki/
  state/        manifest、machine-memory、history、nightly health
  cache/        graph export 和可重建的机读侧产物
  logs/
prompts/
  compile.md
  ask.md
  lint.md
```

## Obsidian 的角色

Obsidian 是 `aiwiki` 的前端/IDE，不是知识编译器本体。

- `aiwiki` 负责 ingest、compile、query、lint、automation、provenance
- Obsidian 负责浏览 `raw/`、检查 `wiki/`、阅读 `output/`
- 你可以加 Web Clipper、Marp 等插件，但 source of truth 仍然是磁盘上的仓库结构

当前仓库已经带有 repo-local Obsidian 资产：

- `.obsidian/app.json`
- `.obsidian/workspace.json`
- `HOME.md`
- `wiki/indexes/*.md`
- `schema/*.md`
- `.aiwiki/state/machine-memory.json`
- `.aiwiki/state/nightly-health.json`
- `wiki/indexes/review-queue.md`
- `.aiwiki/cache/machine-memory-graph.json`

现在系统已经具备：

- `run-compile` 同时维护 `wiki/sources/` 和 `wiki/concepts/`
- `ask` / `run-ask` 先读编译层，再用 machine-memory 和 graph edges 做 source/concept bias
- `file-back --kind decision|judgment` 让高阶沉淀不再都挤进 `wiki/derived/`
- `review-page` 让 decision / judgment 进入显式 review workflow
- `nightly` / `run-nightly` 聚合 compile、lint、drift、repair queue 到 `wiki/indexes/repair-backlog.md`
- `graph-health.md` 汇总 connected components、isolated sources、singleton concepts、overloaded concepts
- `install_user_service.sh` 会同时安装 inbox watcher 和 nightly `systemd --user` timer

炼丹炉产品架构文档在 [wiki/indexes/Alchemy Furnace.md](/home/tim/ai-wiki/wiki/indexes/Alchemy%20Furnace.md)。

## LLM 配置

当前支持三类 backend：

- `codex-cli`：调用本地 `codex exec`
- `claude-cli`：调用本地 `claude --print`
- `openai-api`：调用 OpenAI-compatible `/chat/completions`

解析顺序：

1. 如果显式设置了 `AIWIKI_LLM_BACKEND`，优先用它
2. 否则自动解析：
3. 有 model + API key 时用 `openai-api`
4. 否则如果本机有 `codex`，用 `codex-cli`
5. 否则如果本机有 `claude`，用 `claude-cli`

常用变量：

```bash
export AIWIKI_LLM_BACKEND="codex-cli"                    # optional: auto | codex-cli | claude-cli | openai-api
export AIWIKI_LLM_MODEL="gpt-4.1-mini"                  # optional for CLI backends, required for openai-api
export AIWIKI_LLM_TIMEOUT="120"                         # optional
export AIWIKI_LLM_TEMPERATURE="0.2"                     # optional; only used by openai-api
export AIWIKI_LLM_MAX_CONTEXT_CHARS="24000"             # optional
```

CLI 相关：

```bash
export AIWIKI_CODEX_COMMAND="codex"
export AIWIKI_CLAUDE_COMMAND="claude"
```

OpenAI-compatible API：

```bash
export AIWIKI_LLM_BACKEND="openai-api"
export AIWIKI_LLM_MODEL="gpt-4.1-mini"
export AIWIKI_LLM_API_KEY="..."
export AIWIKI_LLM_BASE_URL="https://api.openai.com/v1"
```

`OPENAI_MODEL`、`OPENAI_API_KEY`、`OPENAI_BASE_URL` 也可作为 fallback。

`llm-check` 会输出：

- 当前解析到的 backend
- 认证方式是 `api-key` 还是 `cli-session`
- 当前 backend 是否支持 `drop-image` 的图像理解

## 使用方式

如果想装成 shell 命令：

```bash
pip install -e .
```

或直接在仓库里运行：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . ingest /path/to/paper.md
PYTHONPATH=src python3 -m aiwiki.cli --root . ingest https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png --no-vision
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-repo https://github.com/user/repo.git
PYTHONPATH=src python3 -m aiwiki.cli --root . compile
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
AIWIKI_LLM_BACKEND=claude-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare A and B" --format report
AIWIKI_LLM_BACKEND=openai-api PYTHONPATH=src python3 -m aiwiki.cli --root . run-lint
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare A and B" --format report
PYTHONPATH=src python3 -m aiwiki.cli --root . file-back output/reports/20260405-120000-compare-a-and-b.md
PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260405-example.md --status approved --note "Approved after source review."
PYTHONPATH=src python3 -m aiwiki.cli --root . lint
PYTHONPATH=src python3 -m aiwiki.cli --root . run-lint
PYTHONPATH=src python3 -m aiwiki.cli --root . nightly
PYTHONPATH=src python3 -m aiwiki.cli --root . run-nightly
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
```

## 全自动模式

如果你想要 Karpathy 风格的“只投原料”，直接用自动化入口。

单次自动处理：

```bash
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . auto-once
```

常驻 watcher：

```bash
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . watch --interval 5
```

`watch` 运行后，预期链路是：

- 你往 `raw/inbox/` 丢文件
- 或用 `drop-url`、`drop-pdf`、`drop-image`、`drop-repo`
- `aiwiki` 自动发现新材料
- 在 `wiki/sources/` 下编译来源页
- 在 `wiki/concepts/` 和 `wiki/indexes/` 下刷新概念页和索引页
- 在 `wiki/indexes/review-queue.md` 下刷新 decision/judgment 审阅队列
- 在 `.aiwiki/` 与 `wiki/indexes/` 下刷新 machine-memory、drift、graph-health
- LLM 自动补摘要
- `output/lint/` 自动刷新 lint 结果

如果要安静/离线模式，可加 `--deterministic-only`。

nightly 健康巡检：

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . nightly
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-nightly
```

## 原料投喂方式

`drop-url`

- 适合文章、博客、文档页、newsletter
- 有 Playwright Chromium 时优先抓渲染后的 DOM，再抽 `article` / `main` 正文
- 页面图片会下载到 `raw/assets/` 并在 note frontmatter 里登记
- 没有浏览器能力时会回退到 HTTP + BeautifulSoup

可选浏览器支持：

```bash
python3 -m pip install --user playwright
python3 -m playwright install chromium
```

`drop-pdf`

- 原 PDF 落到 `raw/assets/`
- 正文抽取结果落到 `raw/inbox/`
- 适合论文、白皮书、导出的长文档

`drop-image`

- 原图落到 `raw/assets/`
- metadata / OCR / vision note 落到 `raw/inbox/`
- 本机有 `tesseract` 时会自动 OCR
- 当前支持图像理解的 backend 是 `codex-cli` 和 `openai-api`

`drop-repo`

- 把本地或远程 repo snapshot 成 markdown 来源笔记
- 适合把 README、目录结构、关键文件摘要纳入炼丹炉

## 用户级服务

如果希望 watcher 和 nightly repair loop 随用户会话自动启动，可以安装 `systemd --user` 单元：

```bash
bash scripts/install_user_service.sh
```

安装后会生成：

- `~/.config/systemd/user/aiwiki-watch.service`
- `~/.config/aiwiki/aiwiki-watch.env`
- `~/.config/systemd/user/aiwiki-nightly.service`
- `~/.config/systemd/user/aiwiki-nightly.timer`
- `~/.config/aiwiki/aiwiki-nightly.env`

默认 env 使用 `codex-cli`。如果要换成 `claude-cli` 或 `openai-api`，改 env 文件后重启对应 unit：

```bash
systemctl --user restart aiwiki-watch.service
systemctl --user status --no-pager aiwiki-watch.service
journalctl --user -u aiwiki-watch.service -n 100 --no-pager
systemctl --user status --no-pager aiwiki-nightly.timer
journalctl --user -u aiwiki-nightly.service -n 100 --no-pager
```

## 本地闭环

仓库带了本地闭环脚本：

```bash
bash scripts/finalize_task.sh
bash scripts/finalize_task.sh --message "your commit message"
```

它会：

1. 运行 `closed_loop.sh --require-contract`
2. stage 所有未忽略变更
3. 创建一次本地 commit

不会自动 `push`。

## 验证

```bash
bash scripts/verify.sh
```

当前覆盖：

- CLI 和核心主链回归测试
- watch / nightly 脚本语法校验
- systemd 模板存在性检查
- Obsidian workspace / dashboard 存在性检查

## 开发备注

- `.codex/` 和 `open-harness` 只用于本仓库开发治理，不属于 `aiwiki` runtime
- 产品/runtime 主体是 `src/aiwiki/`、`schema/`、`raw/`、`wiki/`、`output/`
