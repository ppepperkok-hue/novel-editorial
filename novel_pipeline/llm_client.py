"""LLM 客户端：OpenAI 兼容接口（DeepSeek / OpenAI 等），分档配置 + 重试。

未配置密钥时可用 MockLLMClient 跑测试与演示（脚本化响应）。
"""

import json
import os
import time
import urllib.error
import urllib.request

MODEL_TIERS = ("planning", "writing", "editing", "reviewing", "memory")


class LLMError(RuntimeError):
    pass


def _env_str(name, default=""):
    return os.environ.get(name, default)


class LLMClient:
    def __init__(self, api_key=None, base_url=None, models=None,
                 timeout=120, max_retries=2):
        self.api_key = api_key if api_key is not None else _env_str("LLM_API_KEY")
        self.base_url = (
            base_url if base_url is not None else _env_str("LLM_BASE_URL")
        ).rstrip("/")
        self.models = dict(models or {})
        for tier in MODEL_TIERS:
            self.models.setdefault(tier, _env_str(f"LLM_MODEL_{tier.upper()}"))
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def configured(self):
        return bool(self.api_key and self.base_url)

    def chat(self, system, user, tier="writing", temperature=0.8):
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

    def chat(self, system, user, tier="writing", temperature=0.8):
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
