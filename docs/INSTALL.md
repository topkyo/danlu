# 炼丹炉安装指南

本指南面向普通用户，目标是让你从零开始跑起一个可用的炼丹炉 vault。不需要先读代码结构或模块边界图。

## 前置条件

- **Python 3.10+**（macOS 和 Linux 通常自带；Windows 暂未正式支持）
- **Obsidian Desktop**（macOS / Linux），用于日常 Product Shell 工作台
- 一个愿意用来存放 vault 的本地目录（建议 SSD，因为会频繁读写 markdown / JSON）

> 注意：炼丹炉是 local-first 系统，你的原料、wiki、输出和审计 receipt 全部落在本地文件里。LLM 调用、网页抓取、通知等才走网络。

## 安装方式

### 方式一：源码安装（完整 Product Shell，当前推荐）

适合要跑 Obsidian Product Shell 的用户。需要克隆本仓库作为 **runtime root**（插件模板与 vault 脚手架仍从 checkout 同步）。

```bash
# 1. 克隆仓库
git clone https://github.com/topkyo/danlu.git aiwiki
cd aiwiki

# 2. 确认 Python 版本
python3 --version   # 需要 3.10 及以上

# 3. 可选：editable 安装，获得 `aiwiki` console script（与方式二预览一致）
pip install -e ".[dev]" --break-system-packages   # 若无 PEP 668，可去掉 --break-system-packages
```

后续可用 `aiwiki ...`，或继续用 `PYTHONPATH=src python3 -m aiwiki.cli ...` / vault 内 `scripts/aiwiki-launcher.sh`。

### 方式二：pip 预览安装（CLI 主路径已可用；PyPI 正式发布待定）

**边界（诚实预览）**：

- **可用**：在克隆仓库根执行 `pip install -e .`（或 `pip install .`）后，用 `aiwiki` 做 `new-vault` / `advanced compile` / `today` / `drop` 等 CLI。
- **仍依赖 checkout**：创建带 Product Shell 的 vault 需要本仓库里的 `.obsidian/plugins/furnace-product-shell/` 三件套；**尚未**发布到 PyPI 的 `pip install aiwiki` 一键包。
- 版本与 CHANGELOG AgentOS gate 对齐为 **0.4.0**（见 `pyproject.toml` / `src/aiwiki/__init__.py`）。

```bash
git clone https://github.com/topkyo/danlu.git aiwiki
cd aiwiki
pip install -e . --break-system-packages   # 预览；正式 PyPI 名待发布后改为 pip install aiwiki
aiwiki --help
```

干净机最小验收（在仓库根执行；`--root` 指向 **runtime checkout**，vault 路径是 `new-vault` 参数）：

```bash
aiwiki advanced new-vault /tmp/furnace-preview-vault
aiwiki --root /tmp/furnace-preview-vault advanced compile
aiwiki --root /tmp/furnace-preview-vault today
```

> 若你的环境已有 `aiwiki` console script，vault 内 `scripts/aiwiki-launcher.sh` 会优先调用它；否则回退到 `PYTHONPATH=src python3 -m aiwiki.cli`。

## 首次创建 vault

vault 是你的炼丹炉工作区，里面包含 `raw/`、`wiki/`、`output/`、`.aiwiki/` 状态目录和 Obsidian 配置。

```bash
# 在已安装 `aiwiki` 或源码目录下执行（推荐 console script）
aiwiki --root . advanced new-vault /path/to/your-vault
# 等价：PYTHONPATH=src python3 -m aiwiki.cli --root . advanced new-vault /path/to/your-vault
```

把 `/path/to/your-vault` 换成你想要的路径，例如 `~/炼丹炉` 或 `~/Documents/furnace-vault`。

创建完成后进入 vault：

```bash
cd /path/to/your-vault
```

你会看到：

- `raw/`：放原料
- `wiki/`：炼化后的知识
- `output/`：报告、仪表盘、审计 receipt
- `.aiwiki/`：状态、缓存、机器记忆
- `HOME.md`：Obsidian 首页
- `scripts/aiwiki-launcher.sh`：vault 内调用 runtime 的启动器
- `.obsidian/`：Obsidian 配置和 Furnace Product Shell 插件

## 启动 Obsidian 与 launcher

1. 用 Obsidian 打开你的 vault 目录。
2. 在 Obsidian 左侧边栏找到 **Furnace Product Shell**，这是日常极简工作台。
3. 同时也可以在终端里用 launcher 执行命令：

```bash
./scripts/aiwiki-launcher.sh advanced shell-status
./scripts/aiwiki-launcher.sh advanced compile
./scripts/aiwiki-launcher.sh today
```

> 规则：同一个 vault 同时只能有一个写入命令在跑（`single writer, many readers`）。不要在 Obsidian Product Shell 和终端两边同时执行 `compile`、`nightly`、`file-back` 等写入型命令。

## 配置 LLM 后端

炼丹炉的确定性链路（投料、编译、本地 lint、nightly）可以离线跑；只有 `run-ask` 等显式 LLM 命令需要后端配置。

当前支持的后端：

- `deepseek-api`
- `opencode-api`（**产品默认**主路由，模型 `deepseek-v4-pro`）
- `openai-api`（兼容 OpenAI 协议）
- `anthropic-api`

### 产品默认 LLM 路由（product lock）

炼丹炉产品面只锁定一条默认 LLM 路由：`opencode-api` + `deepseek-v4-pro`。Product Shell、CLI、`llm-check` 与 systemd/launchd 安装脚本均以此为准；**不会**在 `run-ask` 中自动 fallback 到其他 backend。`nightly` / watcher 默认只做确定性 `compile` + `lint`。

`deepseek-api`、`openai-api`、`anthropic-api` 仍作为开发者/专家 escape hatch 保留在代码中，需显式设置 `AIWIKI_LLM_BACKEND` 切换；这不属于默认产品路径。

最简配置示例：

```bash
# 使用 OpenCode（推荐）
export AIWIKI_LLM_BACKEND=opencode-api
export AIWIKI_OPENCODE_API_KEY=opencode-...

# 或使用 DeepSeek
export AIWIKI_LLM_BACKEND=deepseek-api
export AIWIKI_DEEPSEEK_API_KEY=sk-...
```

检查配置是否生效：

```bash
./scripts/aiwiki-launcher.sh advanced llm-check
```

加 `--probe` 会发一个极小真实请求，验证账号是否真的能跑：

```bash
./scripts/aiwiki-launcher.sh advanced llm-check --probe
```

**安全提示**：不要把 key 写进 git 跟踪的文件。Product Shell 里填写的 key 只保存在本机未跟踪的插件 `data.json` 中；CLI 使用推荐放到 `~/.aiwiki-secrets/<provider>.env`（文件权限 600，目录权限 700）。

## 安装自动化服务（可选）

如果你希望炼丹炉在后台自动处理投料和 nightly 巡检，可以安装 systemd（Linux）或 launchd（macOS）服务。

### systemd（Linux）

```bash
# 必须显式指定 vault 路径
AIWIKI_VAULT=/path/to/your-vault scripts/install_user_service.sh
```

安装后会创建两条服务：

- `aiwiki-watch.service`：常驻等待投料
- `aiwiki-nightly.timer`：每晚自动炼化

### launchd（macOS）

```bash
AIWIKI_VAULT=/path/to/your-vault scripts/install_launchd_service.sh
```

卸载：

```bash
scripts/uninstall_user_service.sh
# 或 macOS
scripts/uninstall_launchd_service.sh
```

> 默认服务只跑确定性链路，不会自动执行 LLM 或无人值守修改核心策略。需要开启更高自治级别时，请阅读 `docs/Furnace Runtime Operations.md` 中的 autonomy 配置说明。

## 5 分钟验证

按顺序执行下面命令，确认炼丹炉基本链路可用：

```bash
cd /path/to/your-vault

# 1. 投料：丢一段 markdown 进 raw/inbox/
./scripts/aiwiki-launcher.sh drop markdown --title "验证材料" --text "这是一段用于验证的原材料。"

# 2. 编译：把原料炼化成 wiki
./scripts/aiwiki-launcher.sh advanced compile

# 3. 看今日简报
./scripts/aiwiki-launcher.sh today

# 4. 提问（需要 LLM 配置）
./scripts/aiwiki-launcher.sh advanced run-ask "总结今天投入的材料" --format report

# 5. 回流高价值结论到 wiki
./scripts/aiwiki-launcher.sh advanced file-back output/reports/<刚才生成的报告>.md
```

如果前 3 步都能跑通，说明离线确定性链路没问题。第 4 步失败通常只是 LLM key 没配或网络不通，不会破坏 vault。

## 常见问题

### 没有 Python 环境怎么办？

macOS 和大多数 Linux 发行版都自带 Python 3。如果提示没有，建议用系统包管理器安装：

```bash
# macOS（Homebrew）
brew install python@3.12

# Ubuntu / Debian
sudo apt update && sudo apt install python3 python3-pip
```

### 没有 API key 能跑吗？

可以。投料、编译、本地 lint、today 简报、nightly 等确定性链路完全离线可用。只有 `run-ask` 等显式 LLM 命令需要后端配置。

### Obsidian 打不开 vault？

1. 确认你打开的是 vault 目录本身，而不是 `aiwiki` 源码目录。
2. 首次打开后，在 Obsidian 设置 → 社区插件 → 打开 `Furnace Product Shell`。
3. 如果界面显示异常，尝试重新加载 Obsidian（`Cmd/Ctrl + P` → `Reload app without saving`）。

### 怎么升级炼丹炉？

当前方式：在 `aiwiki` 源码目录 `git pull` 即可。vault 数据与源码分离，升级不会覆盖你的 `raw/`、`wiki/`、`output/`。

```bash
cd /path/to/aiwiki
git pull
```

### 遇到问题怎么排查？

1. 先看 `output/control/shell-summary.json` 里的状态摘要。
2. 再跑 `./scripts/aiwiki-launcher.sh advanced lint`，看是否有健康度问题。
3. 最后看 `.aiwiki/state/execution-receipts/` 下的 receipt，定位最近失败的命令。
