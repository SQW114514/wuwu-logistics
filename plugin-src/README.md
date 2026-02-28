## Wuwu Logistics Plugin for Dify

This plugin is for OpenAI-compatible providers that expose a `.../responses` endpoint.

### Included predefined models
- `gpt-5.3-codex`
- `gpt-5.2`

### What this plugin supports
- Responses API non-streaming and true streaming output
- Function/tool calling (including streamed tool call arguments)
- Predefined models and customizable model names
- Performance tier selection (`auto` / `medium` / `high` / `xhigh`)
- Custom performance tier override (`custom_performance_tier`)

### Credentials
- `API Key`
- `API Base` (example: `https://your-host/codex`)

The plugin uses `API Base` exactly as you enter it. If your provider requires `/v1`, include it manually.
