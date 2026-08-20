# 安全披露

炼丹炉是 local-first runtime：vault 内容默认不离开本机。请把**可被利用的缺陷**私下发给维护者，不要开公开 issue。

## 联系

邮件：`topkyoxp@gmail.com`  
主题请写 `SECURITY: <一句话>`。

请尽量附上：

1. 受影响版本（`aiwiki --version` 或 git commit）
2. 复现步骤（可脱敏路径）
3. 影响（任意文件写入、SSRF、密钥泄漏、receipt 被绕过等）
4. 是否已有公开讨论或 CVE

## 范围

**请报：**

- 路径穿越、symlink 逃出 vault
- `drop url` / fetch 的 SSRF 或开放重定向绕过
- 密钥被写入 git 跟踪文件、日志或 receipt
- LLM 失败被标成确定性成功
- 插件 spawn 可注入任意 argv / 环境

**请勿当安全漏洞报：**

- 需要用户主动把 API key 配给第三方 LLM provider（这是产品设计）
- AGPL 合规咨询
- 未配置 key 时 Ask 失败（fail-closed）

## 支持的版本

当前维护 `0.4.x`（`main`）。更早 tag 仅作历史基线，不承诺回移植。

## 密钥存放

不要把 key 写进 README、fixture、`.envrc.dogfood` 或任何 git 跟踪文件。推荐：

- Product Shell：vault 内未跟踪的 `data.json`
- CLI：`~/.aiwiki-secrets/<provider>.env`（目录 `700`，文件 `600`）

模板见 `.env.example`。
