---
name: flyte-migrate-config
description: Migrates Flyte 1 task configuration, container images, resources, caching, secrets, scheduling, and CLI/config-file usage to Flyte 2 equivalents. Use when migrating Flyte 1 task configuration, images, resources, secrets, scheduling, or CLI/config-file usage to Flyte 2. Trigger words include resources, ImageSpec, cache_version, secrets, LaunchPlan, CronSchedule, pyflyte, config, register, and deploy.
---

# Flyte 1 to Flyte 2 Migration: Task Configuration and CLI/Config

In Flyte 1, image, resources, caching, secrets, and scheduling were configured per-task on the `@task` decorator or per-workflow on a `LaunchPlan`. In Flyte 2 most of this moves to the `flyte.TaskEnvironment`, so it is declared once and shared. The CLI is renamed from `pyflyte` to `flyte` and the config file is trimmed down. This skill covers migrating those settings and commands.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide (Task configuration) | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/configuration/ |
| Migration guide (CLI) | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/cli-and-configuration/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| Example code | https://github.com/unionai/unionai-examples |

## Image, resources, and caching move to the TaskEnvironment

Image, resources, and caching move from the `@task` decorator to the `TaskEnvironment`. Per-task settings like `retries` and `timeout` stay on `@env.task`. Note that `mem` is renamed to `memory`, and there are no separate `requests`/`limits` — a single `Resources` value serves as both.

### Flyte 1

```python
from datetime import timedelta

import flytekit
from flytekit import Resources

image = flytekit.ImageSpec(
    name="training-image",
    packages=["scikit-learn", "pandas"],
)

@flytekit.task(
    container_image=image,
    requests=Resources(cpu="2", mem="4Gi"),
    limits=Resources(cpu="4", mem="8Gi"),
    cache=True,
    cache_version="1.0",
    retries=3,
    timeout=timedelta(minutes=30),
)
def train_epoch(step: int) -> float:
    # A stand-in for a training step that returns the current loss.
    return 1.0 / (step + 1)

@flytekit.workflow
def main(step: int) -> float:
    return train_epoch(step=step)
```

### Flyte 2

```python
from datetime import timedelta

import flyte

# Image, resources, and caching move to the TaskEnvironment, so they are declared
# once and shared by every task in the environment.
env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_debian_base().with_pip_packages("scikit-learn", "pandas"),
    resources=flyte.Resources(cpu="2", memory="4Gi"),  # "memory", not "mem"
    cache="auto",
)

# retries and timeout stay on the task decorator.
@env.task(retries=3, timeout=timedelta(minutes=30))
def train_epoch(step: int) -> float:
    # A stand-in for a training step that returns the current loss.
    return 1.0 / (step + 1)

@env.task
def main(step: int) -> float:
    return train_epoch(step)
```

## Container images: ImageSpec to flyte.Image

Flyte 1's `ImageSpec` is replaced by Flyte 2's `flyte.Image` with a fluent builder API. Instead of one constructor with many arguments, you start from a base and chain builder methods.

```python
from flyte import Image

image = (
    Image.from_debian_base(name="my-image", registry="ghcr.io/myorg", python_version=(3, 11))
    .with_pip_packages("pandas", "numpy")
    .with_apt_packages("curl", "git")
    .with_env_vars({"MY_VAR": "value"})
)
```

| Constructor | Use case |
|---|---|
| `Image.from_debian_base()` | Most common; includes the Flyte SDK |
| `Image.from_base(image_uri)` | Start from any existing image |
| `Image.from_dockerfile(path)` | Complex custom builds |
| `Image.from_uv_script(path)` | UV-based projects |

Common chainable builder methods: `.with_pip_packages(...)`, `.with_requirements(path)`, `.with_uv_project(path)`, `.with_apt_packages(...)`, `.with_commands([...])`, `.with_source_file(path, dst=...)`, `.with_source_folder(path, dst=...)`, `.with_env_vars({...})`, and `.with_workdir(...)`.

| Flyte 1 `ImageSpec` | Flyte 2 `Image` | Notes |
|---|---|---|
| `name` | `name` (constructor) | Same |
| `registry` | `registry` (constructor) | Same |
| `python_version` | `python_version` (tuple) | `"3.11"` becomes `(3, 11)` |
| `packages` | `.with_pip_packages()` | Method instead of param |
| `apt_packages` | `.with_apt_packages()` | Method instead of param |
| `requirements` | `.with_requirements()` | Supports txt, poetry.lock, uv.lock |
| `env` | `.with_env_vars()` | Method instead of param |
| `commands` | `.with_commands()` | Method instead of param |
| `copy` / `source_root` | `.with_source_file()` / `.with_source_folder()` | More explicit methods |
| `base_image` | `Image.from_base()` | Different constructor |
| `builder` | Config file or `flyte.init()` | Global setting |
| `platform` | `platform` (constructor) | Tuple: `("linux/amd64", "linux/arm64")` |

For a private registry, create an image-pull secret and reference it:

```bash
flyte create secret --type image_pull my-registry-secret --from-file ~/.docker/config.json
```

```python
image = Image.from_debian_base(
    registry="private.registry.com",
    name="my-image",
    registry_secret="my-registry-secret",
)
```

## Resources and GPUs

A single `flyte.Resources` value serves as both request and limit — there are no separate `requests`/`limits`. Several parameters were renamed.

| Flyte 1 | Flyte 2 | Notes |
|---|---|---|
| `cpu="1"` | `cpu="1"` | Same |
| `mem="2Gi"` | `memory="2Gi"` | Renamed |
| `gpu="1"` | `gpu="A100:1"` | `Type:count` format |
| `ephemeral_storage="10Gi"` | `disk="10Gi"` | Renamed |
| N/A | `shm="auto"` | New: shared memory |

GPU type and count are combined into one string, replacing the separate Flyte 1 `accelerator=` argument:

```python
env = flyte.TaskEnvironment(
    name="gpu_env",
    resources=flyte.Resources(
        cpu="4",
        memory="32Gi",
        gpu="A100:2",              # Type:count
        # gpu="A100 80G:1"         # 80GB variant
        # gpu=flyte.GPU("A100", count=1, partition="1g.5gb")   # MIG partition
    ),
)
```

Supported GPU types include A10, A10G, A100, A100 80G, B200, H100, H200, L4, L40s, T4, V100, RTX PRO 6000, and GB10.

## Caching: cache_version to cache="auto" / CachePolicy

Caching is enabled at the env level with `cache="auto"` (or per-task on `@env.task`). The explicit `cache_version` string moves into a `flyte.Cache` object.

| Behavior | Description |
|---|---|
| `"auto"` | Cache results and reuse if available |
| `"override"` | Always execute and overwrite the cache |
| `"disable"` | No caching (default for a `TaskEnvironment`) |

```python
# Flyte 1: @task(cache=True, cache_version="1.0")
# Flyte 2:
@env.task(cache="auto")
def cached_task(x: int) -> int:
    return x * 2

# Advanced control (replaces cache_version, serialize, ignored_inputs, ...)
@env.task(cache=flyte.Cache(
    behavior="auto",
    version_override="v1.0",
    serialize=True,
    ignored_inputs=("debug",),
))
def advanced(x: int, debug: bool = False) -> int:
    return x * 2
```

## Secrets: current_context().secrets to env vars

Secrets move from `secret_requests` on the task to `secrets` on the `TaskEnvironment`, and you read them from environment variables instead of `current_context().secrets` — for example, an API key for a model registry or hosted LLM.

### Flyte 1

```python
from flytekit import task, workflow, Secret, current_context

@task(secret_requests=[Secret(group="openai", key="api_key")])
def call_api() -> str:
    token = current_context().secrets.get(group="openai", key="api_key")
    return f"token has {len(token)} chars"

@workflow
def main() -> str:
    return call_api()
```

### Flyte 2

```python
import os

import flyte

# Secrets are declared on the TaskEnvironment and injected as environment
# variables (instead of read through current_context().secrets).
env = flyte.TaskEnvironment(
    name="secrets",
    secrets=[flyte.Secret(key="openai_api_key", as_env_var="OPENAI_API_KEY")],
)

@env.task
def call_api() -> str:
    token = os.getenv("OPENAI_API_KEY", "")
    return f"token has {len(token)} chars"

@env.task
def main() -> str:
    return call_api()
```

A `flyte.Secret` can be mounted as an environment variable or as a file, and the access convention changes:

```python
flyte.Secret(key="openai-key", as_env_var="OPENAI_API_KEY")   # mount as env var
flyte.Secret(key="access-key", group="aws")                    # env var: AWS_ACCESS_KEY
flyte.Secret(key="ssl-cert", mount="/etc/flyte/secrets")       # mount as a file
```

| Flyte 1 pattern | Flyte 2 pattern |
|---|---|
| `ctx.secrets.get(key="mykey", group="mygroup")` | `os.environ["MYGROUP_MYKEY"]` (auto-named) |
| `ctx.secrets.get(key="mykey")` | `os.environ["MY_SECRET"]` (with `as_env_var="MY_SECRET"`) |

Create and manage secrets from the CLI:

```bash
flyte create secret MY_SECRET_KEY --value my_secret_value
flyte create secret MY_SECRET_KEY --from-file /path/to/secret
flyte get secret
flyte delete secret MY_SECRET_KEY
```

## Scheduling: LaunchPlan + CronSchedule to flyte.Trigger + flyte.Cron

A `LaunchPlan` with a `CronSchedule` (say, a nightly retraining job) becomes a `flyte.Trigger` attached directly to the task. Use `flyte.TriggerTime` to bind the scheduled fire time to an input, and deploy the trigger with `flyte deploy`.

### Flyte 1

```python
from flytekit import task, workflow, LaunchPlan, CronSchedule

@task
def retrain(kickoff_time: str) -> str:
    return f"retrained model at {kickoff_time}"

@workflow
def main(kickoff_time: str) -> str:
    return retrain(kickoff_time=kickoff_time)

# A LaunchPlan attaches a schedule (and default inputs) to a workflow.
nightly_retrain = LaunchPlan.get_or_create(
    workflow=main,
    name="nightly_retrain",
    schedule=CronSchedule(
        schedule="0 2 * * *",  # 2 AM daily
        kickoff_time_input_arg="kickoff_time",
    ),
)
```

### Flyte 2

```python
from datetime import datetime

import flyte

env = flyte.TaskEnvironment(name="scheduling")

# A Trigger replaces LaunchPlan + CronSchedule. It is attached directly to the
# task and deployed with it (flyte deploy). flyte.TriggerTime binds the
# scheduled fire time to a task input.
nightly_retrain = flyte.Trigger(
    name="nightly_retrain",
    automation=flyte.Cron("0 2 * * *"),  # 2 AM daily
    inputs={"trigger_time": flyte.TriggerTime},
    auto_activate=True,
)

@env.task(triggers=nightly_retrain)
def main(trigger_time: datetime = datetime(2024, 1, 1, 2, 0)) -> str:
    return f"retrained model at {trigger_time.isoformat()}"
```

Triggers support `flyte.Cron("0 9 * * *", timezone="America/New_York")` and `flyte.FixedRate(timedelta(hours=1))` as automations, plus convenience constructors like `flyte.Trigger.hourly()` and `flyte.Trigger.daily()`.

## CLI command mapping: pyflyte to flyte

The command-line tool is renamed from `pyflyte` to `flyte`, and remote is now the default.

| Flyte 1 | Flyte 2 | Notes |
|---|---|---|
| `pyflyte run` | `flyte run` | Similar, different flags |
| `pyflyte run --remote` | `flyte run` | Remote is the default in Flyte 2 |
| `pyflyte run` (local) | `flyte run --local` | Local execution is now explicit |
| `pyflyte register` | `flyte deploy` | Different concept |
| `pyflyte package` | N/A | Not needed in Flyte 2 |
| `pyflyte serialize` | N/A | Not needed in Flyte 2 |

### Running tasks — Flyte 1

```bash
# Local
pyflyte run my_module.py my_workflow --arg1 value1

# Remote
pyflyte --config config.yaml run --remote my_module.py my_workflow --arg1 value1
```

### Running tasks — Flyte 2

```bash
# Remote (default)
flyte run my_module.py my_task --arg1 value1

# Local
flyte run --local my_module.py my_task --arg1 value1

# With an explicit config file
flyte --config config.yaml run my_module.py my_task --arg1 value1
```

### Deploying (register to deploy)

In Flyte 1 you registered a module; in Flyte 2 you deploy task environments.

#### Flyte 1

```bash
pyflyte register my_module.py -p my-project -d development
```

#### Flyte 2

```bash
# Deploy a task environment
flyte deploy my_module.py my_env --project my-project --domain development

# Deploy all environments in a file
flyte deploy --all my_module.py

# Deploy with an explicit version, or recursively
flyte deploy --version v1.0.0 my_module.py my_env
flyte deploy --recursive --all ./src
```

### Key flag differences

| Flyte 1 flag | Flyte 2 flag | Notes |
|---|---|---|
| `--remote` | (default) | Remote is the default |
| `--copy-all` | `--copy-style all` | File copying |
| N/A | `--copy-style loaded_modules` | Default: only imported modules |
| `-p, --project` | `--project` | Same |
| `-d, --domain` | `--domain` | Same |
| `-i, --image` | `--image` | Same format |
| N/A | `--follow, -f` | Follow execution logs |

## Configuration files

The config file lives in the same place (`~/.flyte/config.yaml`), but the environment variable changes from `FLYTECTL_CONFIG` to `FLYTE_CONFIG`, and the format is simpler.

### Flyte 1

```yaml
admin:
  endpoint: dns:///your-cluster.hosted.unionai.cloud
  insecure: false
  authType: Pkce
```

### Flyte 2

```yaml
admin:
  endpoint: dns:///your-cluster.hosted.unionai.cloud

image:
  builder: remote  # or "local"

task:
  domain: development
  org: your-org
  project: your-project
```

| Setting | Flyte 1 | Flyte 2 |
|---|---|---|
| Endpoint | `admin.endpoint` | `admin.endpoint` |
| Auth type | `admin.authType` | Auto-detected (PKCE default) |
| Project | CLI flag `-p` | `task.project` (default) |
| Domain | CLI flag `-d` | `task.domain` (default) |
| Organization | CLI flag `--org` | `task.org` (default) |
| Image builder | N/A | `image.builder` (`local` or `remote`) |

### Configuring in code

```python
import flyte

# From a config file (auto-discovers, or pass a path)
flyte.init_from_config()
flyte.init_from_config("path/to/config.yaml")

# Programmatically
flyte.init(
    endpoint="flyte.example.com",
    project="my-project",
    domain="development",
)
```

For API-key authentication in non-interactive environments, use `flyte.init_from_api_key()`.

## Anti-Patterns

1. **Don't keep `image`, `resources`, and `cache` on `@env.task`** — move them onto the shared `flyte.TaskEnvironment`; only per-task settings like `retries` and `timeout` stay on `@env.task`.
2. **Don't use `mem`, `ephemeral_storage`, or separate `requests`/`limits`** — use `memory`, `disk`, and a single `flyte.Resources` value that serves as both.
3. **Don't pass GPUs with `gpu="1"` plus `accelerator=`** — combine type and count into one `Type:count` string like `gpu="A100:2"`.
4. **Don't rebuild `ImageSpec`'s many constructor args** — start from a base (`Image.from_debian_base()`) and chain `.with_*` builder methods.
5. **Don't keep `cache_version="1.0"`** — use `cache="auto"` for the common case, or `flyte.Cache(version_override=...)` for advanced control.
6. **Don't read secrets via `current_context().secrets.get(...)`** — declare them on the `TaskEnvironment` and read the injected environment variable with `os.environ` / `os.getenv`.
7. **Don't recreate `LaunchPlan` + `CronSchedule`** — use `flyte.Trigger` with `flyte.Cron` attached to the task, and deploy it with `flyte deploy`.
8. **Don't run `pyflyte ... --remote`** — `flyte run` is remote by default; add `--local` explicitly for in-process runs.
9. **Don't use `pyflyte register`** — use `flyte deploy` to deploy task environments.
10. **Don't set `FLYTECTL_CONFIG` or rely on `admin.authType`** — use `FLYTE_CONFIG` and the simpler config format with auto-detected auth.
