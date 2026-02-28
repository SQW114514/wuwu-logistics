## Remote model discovery helper

If your Dify build rejects provider plugins that declare `fetch-from-remote`, you can still
discover usable model ids quickly by querying your gateway directly, then paste the model id
into Dify via "customizable model".

### List remote model ids

```bash
export CODEX_API_KEY='YOUR_KEY'
python3 scripts/remote_models.py --api-base 'https://your-host/v1' list
```

Filter by substring:

```bash
python3 scripts/remote_models.py --api-base 'https://your-host/v1' list --contains gpt-5
```

### Probe a model id via /responses

```bash
python3 scripts/remote_models.py --api-base 'https://your-host/v1' probe --model gpt-5.3-codex-xhigh
```

### Probe tier suffix candidates (xhigh vs extra-high, etc.)

```bash
python3 scripts/remote_models.py --api-base 'https://your-host/v1' probe-tiers --base-model gpt-5.3-codex
```
