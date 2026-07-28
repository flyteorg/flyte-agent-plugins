"""pi adapter.

pi discovers nested SKILL.md folders under its agent skills dir. We install the
skill into a workspace-local skills dir and run pi non-interactively pointed at
the GLM endpoint (OpenAI-compatible base URL via env).

NOTE (spike): the exact non-interactive flag + custom-model config for pi is
confirmed in the adapter spike (see plan Risks). The invocation below is the
current best-effort; adjust `_invoke`/`skills_dir` once verified — everything
else in the harness is agnostic to it.
"""

from __future__ import annotations

import pathlib
import shutil

from ..glm import GLMConfig
from ..sandbox import Sandbox
from .base import Runner, sh


class PiRunner(Runner):
    name = "pi"

    def is_available(self) -> bool:
        return shutil.which("pi") is not None

    def skills_dir(self, workspace: pathlib.Path) -> pathlib.Path:
        # Workspace-local skills dir; PI_SKILLS_DIR points pi at it (set below).
        return workspace / ".pi" / "skills"

    def _invoke(self, prompt: str, sandbox: Sandbox, glm: GLMConfig):
        env = dict(sandbox.env)
        # Point pi's skill discovery + OpenAI-compatible model at our config.
        env["PI_SKILLS_DIR"] = str(self.skills_dir(sandbox.workspace))
        env["OPENAI_BASE_URL"] = glm.base_url
        env["OPENAI_API_KEY"] = glm.api_key
        cmd = [
            "pi", "run",
            "--model", glm.model,
            "--yes",
            prompt,
        ]
        out, code, err = sh(cmd, cwd=sandbox.workspace, env=env)
        return out, code, err
