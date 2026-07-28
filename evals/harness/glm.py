"""Client config for the union-hosted GLM endpoint (the LLM under test + judge).

The endpoint is OpenAI-compatible but auth-gated. Everything downstream (runner
adapters + judge) reads its connection details from here so there is exactly one
place to fix once the auth/schema spike is resolved.

Environment variables (never hardcode creds):
  GLM_BASE_URL   default: the demo.hosted GLM app, with /v1 appended if missing
  GLM_API_KEY    bearer token / api key for the endpoint (required for live calls)
  GLM_MODEL      model name to request (default: glm-5.2)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://glm-5-2-llm-service-development.apps.demo.hosted.unionai.cloud/v1"
DEFAULT_MODEL = "glm-5.2"


@dataclass(frozen=True)
class GLMConfig:
    base_url: str
    api_key: str
    model: str

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def from_env() -> "GLMConfig":
        base = os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        return GLMConfig(
            base_url=base,
            api_key=os.environ.get("GLM_API_KEY", ""),
            model=os.environ.get("GLM_MODEL", DEFAULT_MODEL),
        )


def chat_completion(cfg: GLMConfig, messages: list[dict], *, temperature: float = 0.0,
                    max_tokens: int = 2048, timeout: int = 120) -> str:
    """Minimal OpenAI-compatible chat call. Returns the assistant text.

    Kept dependency-light (requests) and isolated so the exact route/auth header
    can be adjusted in one place after the endpoint spike.
    """
    import requests

    if not cfg.has_key:
        raise RuntimeError(
            "GLM_API_KEY is not set — cannot call the GLM endpoint. "
            "Export a valid token/api key for the demo.hosted GLM app."
        )
    resp = requests.post(
        f"{cfg.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json={
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
