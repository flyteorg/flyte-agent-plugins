"""flyte.Image specs for the eval tasks.

The eval task image needs: python + flyte + the harness CLIs (opencode, pi via
npm; hermes via its installer) + the harness package itself + judge deps. The
harness CLIs are node-based, so we install node and the npm globals in the image.

Only the SDK/trajectory tiers run on Flyte. The kind DinD smoke runs on a
privileged GitHub Actions runner, not here (privileged pods aren't assumed on
the demo cluster) — so no Docker-in-Docker layer is baked in.
"""

from __future__ import annotations

import flyte

# Base: flyte + eval harness python deps.
eval_image = (
    flyte.Image.from_debian_base()
    .with_apt_packages("git", "curl", "ca-certificates")
    # Node.js for the node-based agent harnesses (opencode, pi).
    .with_commands([
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
        "apt-get install -y nodejs",
        "npm install -g opencode-ai @mieszko/pi || true",
    ])
    .with_pip_packages("pyyaml", "requests", "flyte>=2.5.0")
    # Ship the eval package + the skills so tasks can install/lint them.
    .with_source_folder("evals", "/root/evals")
    .with_source_folder("plugins", "/root/plugins")
    .with_env_vars({"PYTHONPATH": "/root"})
)
