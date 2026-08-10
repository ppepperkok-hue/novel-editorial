"""LLM 客户端：OpenAI 兼容接口（DeepSeek / OpenAI 等），分档配置 + 重试。

未配置密钥时可用 MockLLMClient 跑测试与演示（脚本化响应）。
"""

import json
import os
import time
import urllib.error
import urllib.request

from novel_pipeline import config  # noqa: E402

MODEL_TIERS = ("planning", "writing", "editing", "reviewing", "memory")
_ENV_CACHE = {"ts": 0.0, "env": {}}


class LLMError(RuntimeError):
    pass


def _env_str(name, default=""):
    return os.environ.get(name, default)


def cached_env(ttl=5.0):
    """Environment snapshot with a short TTL to avoid per-call file IO."""
    now = time.time()
    if now - _ENV_CACHE["ts"] > ttl:
        _ENV_CACHE["env"] = config.load_env()
        _ENV_CACHE["ts"] = now
    return _ENV_CACHE["env"]


def estimate_cost(model, usage, env=None):
    """Estimate RMB cost for a model+usage pair using per-1k-token rates."""
    env = env if env is not None else cached_env()
    is_flash = "flash" in str(model or "")
    try:
        rate = float(env.get("COST_FLASH_PER_1K") or 0.002) if is_flash else float(
            env.get("COST_PRO_PER_1K") or 0.01
        )
    except (TypeError, ValueError):
        rate = 0.002 if is_flash else 0.01
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    return round(pt / 1000.0 * rate + ct / 1000.0 * rate, 6)


class LLMClient:
    def __init__(self, api_key=None, base_url=None, models=None,
                 timeout=120, max_retries=2):
        env = config.load_env()
        self.api_key = (
            api_key
            if api_key is not None
            else (
                _env_str("LLM_API_KEY")
                or env.get("LLM_API_KEY")
                or env.get("DEEPSEEK_API_KEY")
            )
        )
        self.base_url = (
            base_url
            if base_url is not None
            else (_env_str("LLM_BASE_URL") or env.get("LLM_BASE_URL") or "https://api.deepseek.com")
        ).rstrip("/")
        self.models = dict(models or {})
        for tier in MODEL_TIERS:
            self.models.setdefault(
                tier,
                _env_str(f"LLM_MODEL_{tier.upper()}")
                or env.get(f"LLM_MODEL_{tier.upper()}")
                or "",
            )
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def configured(self):
        return bool(self.api_key and self.base_url)

    def chat(self, system, user, tier="writing", temperature=0.8, max_tokens=2000):
        if not self.configured:
            raise LLMError(
                "未配置 LLM_API_KEY / LLM_BASE_URL；"
                "请设置环境变量，或使用 MockLLMClient 跑测试与演示"
            )
        model = self.models.get(tier) or self.models.get("writing")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self.base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504):
                    raise LLMError(f"LLM 调用被拒：HTTP {exc.code}") from exc
                last_err = exc
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
            except (urllib.error.URLError, KeyError, ValueError) as exc:
                last_err = exc
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
        raise LLMError(f"LLM 调用失败：{last_err}")


class MockLLMClient(LLMClient):
    """脚本化响应：按 tier 返回固定内容，用于测试与无密钥演示。"""

    def __init__(self, responses=None, **kwargs):
        super().__init__(api_key="mock", base_url="mock://local", **kwargs)
        self.responses = dict(responses or {})
        self.calls = []

    def chat(self, system, user, tier="writing", temperature=0.8, max_tokens=None):
        self.calls.append({"tier": tier, "system": system, "user": user})
        resp = self.responses.get(tier)
        if callable(resp):
            return resp(tier, system, user)
        if isinstance(resp, list):
            if not resp:
                return f"[mock:{tier}]"
            value = resp.pop(0)
            if callable(value):
                return value(tier, system, user)
            return value
        if resp is not None:
            return resp
        return f"[mock:{tier}]"


def chat_deepseek(model, system, user, temperature=0.5, max_tokens=1600,
                  messages=None, tools=None):
    """Direct DeepSeek chat call used by meeting/diary tools.

    Reads DEEPSEEK_API_KEY from ~/.n8n/.env or process env. Returns
    {text, usage, model, tool_calls}. `messages` overrides the system/user
    pair (used by the agent tool loop for multi-turn tool calls); `tools`
    enables native function calling. `tool_choice` is intentionally omitted:
    DeepSeek V4 thinking mode rejects forced tool_choice with HTTP 400.
    """
    env = config.load_env()
    key = env.get("DEEPSEEK_API_KEY") or env.get("LLM_API_KEY") or ""
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY / LLM_API_KEY missing")
    base_url = (env.get("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    msgs = messages if messages is not None else [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body = {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
    else:
        body["response_format"] = {"type": "json_object"}
    last_err = None
    data = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                base_url + "/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + key,
                },
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            choice = data["choices"][0]["message"]
            text = choice.get("content") or ""
            tool_calls = choice.get("tool_calls") or []
            if text or tool_calls:
                break
            # Empty content with no tool calls: transient model behavior,
            # retry instead of failing the whole meeting/workflow.
            last_err = RuntimeError("DeepSeek 返回空 content")
        except (urllib.error.URLError, ValueError, KeyError) as exc:
            last_err = exc
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    if data is None:
        raise RuntimeError(f"DeepSeek 调用失败：{last_err}")
    if not text and not tool_calls:
        raise RuntimeError(f"DeepSeek 连续返回空 content：{last_err}")
    return {
        "text": text,
        "usage": data.get("usage", {}),
        "model": model,
        "tool_calls": tool_calls,
    }
