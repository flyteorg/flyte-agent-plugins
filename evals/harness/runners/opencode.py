"""opencode adapter.

Config strategy:
  - skills discovered from `<workspace>/.opencode/skills/<name>/`
  - a project `opencode.json` registers the GLM endpoint as an OpenAI-compatible
    custom provider `glm`, so `--model glm/<model>` routes there
  - headless run: `opencode run --model glm/<model> --format json --auto "<prompt>"`
"""

from __future__ import annotations

import json
import pathlib
import shutil

from ..glm import GLMConfig
from ..sandbox import Sandbox
from .base import Runner, sh


class OpenCodeRunner(Runner):
    name = "opencode"

    def is_available(self) -> bool:
        return shutil.which("opencode") is not None

    def skills_dir(self, workspace: pathlib.Path) -> pathlib.Path:
        return workspace / ".opencode" / "skills"

    def _write_config(self, workspace: pathlib.Path, glm: GLMConfig) -> None:
        cfg = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "glm": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "GLM (union-hosted)",
                    "options": {"baseURL": glm.base_url, "apiKey": glm.api_key},
                    "models": {glm.model: {"name": glm.model}},
                }
            },
        }
        (workspace / "opencode.json").write_text(json.dumps(cfg, indent=2))

    def _invoke(self, prompt: str, sandbox: Sandbox, glm: GLMConfig):
        self._write_config(sandbox.workspace, glm)
        cmd = [
            "opencode", "run",
            "--model", f"glm/{glm.model}",
            "--format", "json",
            "--auto",
            "--dir", str(sandbox.workspace),
            prompt,
        ]
        out, code, err = sh(cmd, cwd=sandbox.workspace, env=sandbox.env)
        return out, code, err
