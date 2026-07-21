"""hermes adapter.

hermes installs skills by repo path and runs headless. We install the skill into
a workspace-local dir and run one non-interactive turn pointed at the GLM
endpoint (OpenAI-compatible base URL via env).

NOTE (spike): hermes was not installed in the dev environment; the exact
headless flag + custom-model config is confirmed in the adapter spike (see plan
Risks). `is_available()` gates it out cleanly until then.
"""

from __future__ import annotations

import pathlib
import shutil

from ..glm import GLMConfig
from ..sandbox import Sandbox
from .base import Runner, sh


class HermesRunner(Runner):
    name = "hermes"

    def is_available(self) -> bool:
        return shutil.which("hermes") is not None

    def skills_dir(self, workspace: pathlib.Path) -> pathlib.Path:
        return workspace / ".hermes" / "skills"

    def _invoke(self, prompt: str, sandbox: Sandbox, glm: GLMConfig):
        env = dict(sandbox.env)
        env["HERMES_SKILLS_DIR"] = str(self.skills_dir(sandbox.workspace))
        env["OPENAI_BASE_URL"] = glm.base_url
        env["OPENAI_API_KEY"] = glm.api_key
        cmd = [
            "hermes", "run",
            "--model", glm.model,
            "--non-interactive",
            prompt,
        ]
        out, code, err = sh(cmd, cwd=sandbox.workspace, env=env)
        return out, code, err
