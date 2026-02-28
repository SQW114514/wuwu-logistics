# 🐹 呜呜物流（Wuwu Logistics）Dify 插件

一只会搬运 API 的仓鼠插件 🐹🚚  
用于在 Dify 中接入 **OpenAI 兼容中转 API（Responses）**。

## ✨ 主要能力

- 支持 `responses` 接口（流式 / 非流式）
- 支持工具调用（tool call）
- 支持手动填写新模型名（customizable model）
- 支持性能档位：`medium` / `high` / `xhigh`
- 支持自定义性能档位字段（可填未来新档位）
- 仓鼠 emoji 图标 🐹

## 📦 仓库结构

- `plugin-src/`：插件源码（用于二次开发）
- `releases/wuwu-logistics-plugin-v0.0.11.difypkg`：可直接上传到 Dify 的安装包

## 🚀 在 Dify 中安装

1. 进入 Dify 插件管理页面
2. 选择“上传本地插件包”
3. 上传 `releases/wuwu-logistics-plugin-v0.0.11.difypkg`
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

## ⚠️ 说明

- 本插件走 OpenAI 兼容风格；是否可用取决于你的中转服务是否兼容对应字段。
- 若 Dify 页面未立即更新图标/文案，通常是前端缓存，刷新页面或重装插件即可。

---

如果你愿意，仓鼠还可以继续进化：自动测速、按模型路由、失败重试等 🐹💨
