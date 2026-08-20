# 贡献指南

本仓库是炼丹炉 / `aiwiki` 的**定期导出展示树**：可克隆、可阅读、可按 AGPL 使用。开发在私有真源进行。

**不接受外部 Pull Request。** 安全问题见 [SECURITY.md](SECURITY.md)，不要在公开页面贴密钥。

## 开始

```bash
git clone https://github.com/topkyo/danlu.git aiwiki
cd aiwiki
pip install -e ".[dev]" --break-system-packages   # 无 PEP 668 可去掉 flag
bash scripts/verify.sh python-static smoke
```

确定性路径（`new-vault` / `compile` / `today` / `lint`）不需要 API key。Ask 和万能 `drop` planner 需要，见 `.env.example` 与 [docs/INSTALL.md](docs/INSTALL.md)。

| 角色 | 名字 |
|------|------|
| 对外产品名 | 炼丹炉 / Furnace |
| 包 / CLI | `aiwiki` |
| 本 GitHub 展示仓 | `topkyo/danlu` |
| Obsidian 插件 | `furnace-product-shell` |

## 验证

- `bash scripts/verify.sh [target]`
- 日常最小：`scripts` + `python-static` + `smoke`

## 许可

默认 [AGPL-3.0](LICENSE)。商业使用见 [docs/commercial/BOUNDARIES.md](docs/commercial/BOUNDARIES.md)。
