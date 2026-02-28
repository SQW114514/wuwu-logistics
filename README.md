# 🐹 呜呜物流（Wuwu Logistics）Dify 插件

一只会搬运 API 的仓鼠插件 🐹🚚  
用于在 Dify 中接入 **OpenAI 兼容中转 API（Responses）**。

## ✨ 主要能力

- 支持 `responses` 接口（流式 / 非流式）
- 支持工具调用（tool call）
- 支持手动填写新模型名（customizable model）
- 支持性能档位：`medium` / `high` / `xhigh`（若你的网关支持新档位，可用 `custom_performance_tier` 手动填写）
- 支持自定义性能档位字段（可填未来新档位）
- 仓鼠 emoji 图标 🐹

## 📦 仓库结构

- `plugin-src/`：插件源码（用于二次开发）
- `releases/codex-responses-plugin-v0.0.17.difypkg`：可直接上传到 Dify 的安装包（最新）

## 🚀 在 Dify 中安装

1. 进入 Dify 插件管理页面
2. 选择“上传本地插件包”
3. 上传 `releases/codex-responses-plugin-v0.0.17.difypkg`
4. 配置：
   - `API Key`
   - `API Base`（按你的中转服务要求填写，是否带 `/v1` 以服务商为准）

## 🧪 模型与档位建议

- 模型名建议填基础名，例如：`gpt-5.3-codex`
- 常用性能档位用 `performance_tier`
- 如果有新档位，填 `custom_performance_tier`（优先级更高）
- `reasoning_effort` 可手动选（含 `high` / `xhigh`）

## 🛠 开发与重新打包

在 WSL 里执行：

```bash
./dify-plugin-linux-amd64 plugin package ./plugin-src -o ./releases/wuwu-logistics-plugin-v0.0.11.difypkg
```

## 🔎 远端模型列表（绕过 Dify 不支持远程拉取）

如果你们当前的 Dify 安装插件时提示“不支持远程/remote”（即不支持 `fetch-from-remote`），仍然可以用脚本直接请求你的中转服务的 `/models` 与 `/responses` 来快速拿到可用模型名，然后在 Dify 里用“自定义模型名（customizable model）”粘贴使用：

```bash
export CODEX_API_KEY='YOUR_KEY'
python3 scripts/remote_models.py --api-base 'https://your-host/v1' list --contains gpt
python3 scripts/remote_models.py --api-base 'https://your-host/v1' probe-tiers --base-model gpt-5.3-codex
```

## ⚠️ 说明

- 本插件走 OpenAI 兼容风格；是否可用取决于你的中转服务是否兼容对应字段。
- 若 Dify 页面未立即更新图标/文案，通常是前端缓存，刷新页面或重装插件即可。

---

如果你愿意，仓鼠还可以继续进化：自动测速、按模型路由、失败重试等 🐹💨
