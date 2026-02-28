#!/usr/bin/env python3
"""
List and probe OpenAI-compatible model ids via the /models and /responses endpoints.

This is a practical workaround when your Dify build doesn't support "fetch-from-remote"
for model provider plugins: you can still discover usable model ids quickly and then
paste them into Dify's "customizable model" field.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _join(base: str, path: str) -> str:
    base = (base or "").strip()
    if not base:
        raise ValueError("api_base is required")
    return urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _http_json(method: str, url: str, *, api_key: str, payload: dict | None = None, timeout: int = 30) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "wuwu-logistics-dify-plugin-remote-models/0.1",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        # Some OpenAI-compatible gateways may return SSE even when stream=false.
        if "event:" in text and "\ndata:" in text:
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    return json.loads(data)
                except Exception:
                    continue
        raise RuntimeError(f"Non-JSON response from {url}: {raw[:200]!r}")


def list_models(api_base: str, api_key: str, timeout: int) -> list[str]:
    url = _join(api_base, "/models")
    try:
        data = _http_json("GET", url, api_key=api_key, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(
                f"/models not found at {url} (your gateway may not implement the Models API)"
            ) from e
        raise

    items = data.get("data")
    if isinstance(items, list):
        model_ids = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                model_ids.append(item["id"])
        return model_ids

    # Some gateways may return {"models": [...]} or plain list.
    if isinstance(data, list):
        return [m.get("id") for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]
    if isinstance(data.get("models"), list):
        return [m.get("id") for m in data["models"] if isinstance(m, dict) and isinstance(m.get("id"), str)]

    raise RuntimeError(f"Unrecognized /models payload shape: keys={sorted(data.keys())}")


def probe_model(api_base: str, api_key: str, model: str, timeout: int) -> tuple[bool, str]:
    url = _join(api_base, "/responses")
    payload = {
        "model": model,
        "input": "ping",
        "max_output_tokens": 16,
        "stream": False,
    }
    try:
        _http_json("POST", url, api_key=api_key, payload=payload, timeout=timeout)
        return True, "ok"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"http {e.code}: {body[:300]}".strip()
    except Exception as e:
        return False, str(e)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--api-base", required=True, help="API base URL, e.g. https://your-host/v1")
    p.add_argument("--api-key", default="", help="API key (Bearer token). If omitted, read from env.")
    p.add_argument(
        "--api-key-env",
        default="CODEX_API_KEY",
        help="Env var name to read API key from when --api-key is omitted (default: CODEX_API_KEY)",
    )
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default: 30)")

    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List model ids from /models")
    p_list.add_argument("--contains", default="", help="Only print ids containing this substring")

    p_probe = sub.add_parser("probe", help="Probe a model id by calling /responses")
    p_probe.add_argument("--model", required=True, help="Model id to probe, e.g. gpt-5.3-codex-xhigh")

    p_tiers = sub.add_parser("probe-tiers", help="Probe tier suffixes for a base model")
    p_tiers.add_argument("--base-model", required=True, help="Base model id without tier suffix")
    p_tiers.add_argument(
        "--tiers",
        nargs="*",
        default=["xhigh", "extra-high", "extra_high", "exhigh"],
        help="Tier suffix candidates (default: xhigh extra-high extra_high exhigh)",
    )

    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    api_key = (args.api_key or "").strip()
    if not api_key:
        api_key = (getattr(__import__("os"), "environ").get(args.api_key_env, "") or "").strip()
    if not api_key:
        # Common fallback for OpenAI-compatible gateways.
        api_key = (getattr(__import__("os"), "environ").get("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        print(
            f"ERROR: API key not provided. Pass --api-key or set ${args.api_key_env} (or $OPENAI_API_KEY).",
            file=sys.stderr,
        )
        return 2

    if args.cmd == "list":
        try:
            ids = list_models(args.api_base, api_key, args.timeout)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

        filt = (args.contains or "").strip()
        for mid in ids:
            if not filt or filt in mid:
                print(mid)
        return 0

    if args.cmd == "probe":
        ok, detail = probe_model(args.api_base, api_key, args.model, args.timeout)
        print(json.dumps({"model": args.model, "ok": ok, "detail": detail}, ensure_ascii=False))
        return 0 if ok else 1

    if args.cmd == "probe-tiers":
        results = []
        for tier in args.tiers:
            candidate = f"{args.base_model}-{tier}".rstrip("-")
            started = time.time()
            ok, detail = probe_model(args.api_base, api_key, candidate, args.timeout)
            results.append(
                {
                    "model": candidate,
                    "ok": ok,
                    "detail": detail,
                    "elapsed_ms": int((time.time() - started) * 1000),
                }
            )
        print(json.dumps({"base_model": args.base_model, "results": results}, ensure_ascii=False))
        return 0 if any(r["ok"] for r in results) else 1

    raise RuntimeError(f"unknown cmd: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
