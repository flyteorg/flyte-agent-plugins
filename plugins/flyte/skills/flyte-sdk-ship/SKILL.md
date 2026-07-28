---
name: flyte-sdk-ship
description: 'Generates flyte.Image specs, Dockerfiles, dependency management, image tagging strategy, and reproducible build instructions for Flyte tasks. Use when the user needs to build container images for Flyte tasks, configure custom images, manage dependencies, or set up reproducible builds. Trigger words: "image", "Docker", "build", "dependency", "pip package", "debian base", "image builder", "push image", "container", "Dockerfile", "uv", "requirements".'
---

# Flyte 2 SDK Ship Skill

Generate images, Dockerfiles, and dependency configurations for Flyte 2 tasks.

## Grounding References

| Resource | URL |
|---|---|
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via the `flyte-cluster` and `flyte-docs` MCP servers |

**Ground unfamiliar APIs in real examples.** When unsure of a current Flyte 2 API, or for a pattern not shown below, and the `flyte-docs` search tools are available, search them first — by exact symbol (`TaskEnvironment`, `flyte.io.File`, `map_task`), since matching is literal substring, not semantic — then adapt a real example rather than inventing one, and cite the file or section you pulled it from. (Flyte 2 is not `flytekit`; priors are often wrong.)

## flyte.Image — Programmatic Image Definition

Use `flyte.Image` to define task container images in Python. Flyte builds and pushes them automatically.

### From Debian Base

```python
import flyte

env = flyte.TaskEnvironment(
    name="etl-pipeline",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "pandas", "polars", "pyarrow", "boto3",
    ).with_system_packages(
        "git", "curl", "wget",
    ),
)
```

### From Existing Image

```python
env = flyte.TaskEnvironment(
    name="ml-training",
    image=flyte.Image.from_base(
        "ghcr.io/flyteorg/flyte:py3.12-v2",  # base image
    ).with_pip_packages(
        "torch", "transformers", "datasets",
    ),
)
```

### Image from uv Script Metadata

When using a `# /// script` header, Flyte can derive the image from the script's dependencies:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pandas",
#   "polars",
# ]
# ///

# Flyte reads the script metadata and builds the image automatically
```

## Image Configuration Methods

### with_pip_packages

```python
image = flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
    "pandas",           # latest version
    "torch>=2.0",       # version constraint
    "transformers==4.40",  # pinned version
)
```

### with_system_packages

```python
image = image.with_system_packages(
    "git", "curl", "wget", "jq", "ffmpeg",
)
```

### with_commands (apt-get run)

```python
image = image.with_commands(
    "apt-get update && apt-get install -y libgl1-mesa-glx",  # for OpenCV
    "pip install --upgrade pip",
)
```

### with_env_vars

```python
image = image.with_env_vars({
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
})
```

### with_local_rs_controller

```python
# For development: bake the Rust controller wheel into the image
image = image.with_local_rs_controller()
```

## Custom Dockerfile

For complex builds, use a custom `Dockerfile`:

```dockerfile
# Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch \
    transformers \
    datasets

WORKDIR /app
COPY . /app

ENV HF_HUB_DISABLE_TELEMETRY=1
```

```python
env = flyte.TaskEnvironment(
    name="ml-training",
    image=flyte.Image.from_dockerfile("Dockerfile"),
)
```

## Image Builder Configuration

### Local builder (default for development)

```yaml
# .flyte/config.yaml
image:
  builder: local
```

Builds images locally using Docker. Fast iteration, requires Docker installed.

### Remote builder (CI/production)

```yaml
# .flyte/config.yaml
image:
  builder: remote
  registry: "ghcr.io/myorg"
  repository: "flyte-tasks"
```

Builds images in a remote Docker build service. No local Docker needed.

### Push to registry

```python
# Programmatically configure the builder
env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_debian_base(python_version=(3, 12)),
)
# Set registry via config or CLI
```

## Image Tagging Strategy

### Version tags (recommended for production)

```bash
# Tag with git sha for reproducibility
VERSION=$(git rev-parse --short HEAD)
flyte deploy --version $VERSION
```

### Semantic versioning

```bash
# Tag with semver
flyte deploy --version 1.2.3
```

### Auto versioning (development)

```bash
# Flyte auto-generates a version based on code hash
flyte deploy --version auto
```

## Dependency Management Patterns

### Using pyproject.toml

```toml
[project]
name = "my-flyte-pipeline"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pandas",
    "polars",
    "flyte",
]

[project.optional-dependencies]
ml = ["torch", "transformers", "datasets"]
dev = ["pytest", "ruff"]
```

### Using requirements.txt

```
pandas>=2.0
polars>=0.20
pyarrow>=14.0
boto3>=1.34
flyte
```

### uv pyproject.toml (monorepo)

```toml
[project]
name = "flyte-monorepo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["flyte"]

[tool.uv.sources]
# Pin flyte to local path during development
flyte = { workspace = true }
```

## BYOI (Bring Your Own Image) Pattern

For multi-team setups where each team manages their own images:

```python
# team-a/pipeline.py
import flyte

# Reference an externally-built image
env = flyte.TaskEnvironment(
    name="team-a-task",
    image=flyte.Image.from_base("ghcr.io/team-a/base:v1.2.3"),
)

@env.task
async def process(data: str) -> str:
    ...
```

```python
# team-b/pipeline.py
import flyte
import flyte.io

env = flyte.TaskEnvironment(
    name="team-b-task",
    image=flyte.Image.from_base("ghcr.io/team-b/base:v2.0.0"),
)

@env.task
async def train(model_path: flyte.io.File) -> dict:
    ...
```

## Common Image Recipes

### Data Engineering

```python
env = flyte.TaskEnvironment(
    name="etl",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "pandas", "polars", "pyarrow", "boto3", "sqlalchemy",
        "db-dtypes",  # for BigQuery
        "google-cloud-bigquery",
    ).with_system_packages("git", "curl"),
)
```

### ML Training (GPU)

```python
env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_base("nvidia/cuda:12.1-py3").with_pip_packages(
        "torch", "torchvision", "transformers", "datasets",
        "accelerate", "peft",
    ),
)
```

### LLM Inference

```python
env = flyte.TaskEnvironment(
    name="inference",
    image=flyte.Image.from_base("python:3.12-slim").with_pip_packages(
        "fastapi", "uvicorn", "torch", "transformers",
        "bitsandbytes", "vllm",
    ),
)
```

### Data Quality

```python
env = flyte.TaskEnvironment(
    name="data-quality",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "pandas", "polars", "pyarrow",
        "great-expectations",  # or "pandera"
        "soda-core",
        "boto3",
    ),
)
```

## Build and Deploy Workflow

### Build locally

```bash
# Deploy will auto-build the image
flyte deploy pipeline.py

# Dry-run to see what would be built
flyte deploy --dry-run pipeline.py
```

### Build with remote builder

```bash
# Use remote builder (no Docker needed locally)
flyte deploy --image-builder remote pipeline.py
```

### Push image manually

```bash
# If using a custom registry
docker build -t ghcr.io/myorg/my-task:v1 .
docker push ghcr.io/myorg/my-task:v1
```

### Image caching

Flyte caches built images by content hash. If the image source hasn't changed, it reuses the cached image.

## Troubleshooting

| Issue | Fix |
|---|---|
| `Docker not found` | Install Docker, or use `builder: remote` in config |
| `Permission denied` on Docker socket | Add user to `docker` group: `sudo usermod -aG docker $USER` |
| `Image build failed` | Check Dockerfile syntax, apt package names, pip requirements |
| `Registry push failed` | Verify registry credentials, network connectivity |
| `CUDA not found in container` | Use `nvidia/cuda` base image or install CUDA toolkit in Dockerfile |
| `pip install fails for torch` | Use the correct CUDA index: `--extra-index-url https://download.pytorch.org/whl/cu121` |
| `Image too large` | Use slim base images, multi-stage builds, `.dockerignore` |

## Anti-Patterns

1. **Don't bake secrets into images** — use Flyte secrets instead (`flyte.Secret`).
2. **Don't use `latest` tags in production** — pin to specific versions or git SHAs.
3. **Don't install unnecessary system packages** — they increase image size and build time.
4. **Don't forget `.dockerignore`** — exclude `.git`, `__pycache__`, `.venv`, etc.
5. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
