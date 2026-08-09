"""Shared DeepSeek chat helper used by meeting/diary tools."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def load_env():
    env = {}
    env_file = Path.home() / ".n8n" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("DEEPSEEK_API_KEY",):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def chat(model, system, user, temperature=0.5, max_tokens=1600):
    """Call DeepSeek chat completions; returns dict or raises."""
    env = load_env()
    key = env.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY missing")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    choice = data["choices"][0]["message"]
    text = choice.get("content") or choice.get("reasoning_content") or ""
    return {
        "text": text,
        "usage": data.get("usage", {}),
        "model": model,
    }
