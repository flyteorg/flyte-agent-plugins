---
name: flyte-migrate
description: Entry-point orchestrator for porting Flyte 1 (flytekit) code to Flyte 2 (flyte). Explains the v1 to v2 shift, the terminology mapping, a recommended migration strategy, hybrid v1/v2 pipelines, and routes to sibling migration skills. Use when the user wants to migrate, port, or upgrade Flyte 1 (flytekit) code to Flyte 2. Trigger words are migrate, flytekit, v1 to v2, port, upgrade, convert workflow.
---

# Flyte 1 to 2 Migration Skill

This is the entry point for migrating a Flyte 1 (`flytekit`) codebase to Flyte 2 (`flyte`). Flyte 2 is a fundamental shift: there is no `@workflow` decorator, everything is a `@env.task`, orchestration runs as real Python at runtime, and parallelism is expressed with `asyncio`. This skill explains the overall shift, gives a recommended migration strategy, covers hybrid v1/v2 pipelines during the transition, and routes to the sibling skills that handle each theme in depth.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## The overall v1 to v2 shift

Two conceptual shifts motivate almost every change — **pure Python execution** and the **asynchronous model** — after which most migrations come down to a couple of mechanical moves.

- **`flytekit` (package) becomes `flyte`.** Imports change from `import flytekit` to `import flyte`.
- **`pyflyte` (CLI) becomes `flyte`.** The command-line tool was renamed.
- **Everything is a task.** In Flyte 1, `@workflow` functions were constrained to a DSL subset of Python that compiled to a static DAG. In Flyte 2 there is **no `@workflow` decorator**: everything is a `@env.task`, and a "workflow" is simply a task that calls other tasks. Loops, conditionals, and `try`/`except` work anywhere.
- **Async is the parallelism model.** Flyte 2 is built on `asyncio`, with the Flyte orchestrator acting as the event loop, scheduling awaited tasks across distributed infrastructure. `await` signals where a task can be scheduled in parallel, and `asyncio.gather` tells the orchestrator that a set of tasks are independent.

### Simplified API mapping

| Use case | Flyte 1 | Flyte 2 |
| --- | --- | --- |
| Environment management | `N/A` | `TaskEnvironment` |
| Perform basic computation | `@task` | `@env.task` |
| Combine tasks into a workflow | `@workflow` | `@env.task` |
| Create dynamic workflows | `@dynamic` | `@env.task` |
| Fanout parallelism | `flytekit.map` | Python `for` loop with `asyncio.gather` |
| Conditional execution | `flytekit.conditional` | Python `if-elif-else` |
| Catching workflow failures | `@workflow(on_failure=...)` | Python `try-except` |

## Terminology and concept mapping

Several Flyte 1 concepts were renamed or reshaped in Flyte 2. The table below maps the ones you'll meet most often.

| Flyte 1 | Flyte 2 | Notes |
|---|---|---|
| `flytekit` (package) | `flyte` (package) | The Python SDK was renamed; imports change from `import flytekit` to `import flyte`. |
| `pyflyte` (CLI) | `flyte` (CLI) | The command-line tool was renamed. |
| `@task` / `@workflow` / `@dynamic` | `@env.task` | A single task decorator off a `flyte.TaskEnvironment`. Workflows and dynamic tasks are no longer distinct constructs: everything is a task, and orchestration is plain Python. |
| `map_task()` | `flyte.map()` | Plus `asyncio.gather()` for async fan-out. |
| `conditional()` | native `if` / `elif` / `else` | Branching is now ordinary Python control flow, not a DSL. |
| `ImageSpec` | `flyte.Image` | Container image definition. |
| `current_context()` | `flyte.ctx()` | Runtime context access. |
| `FlyteFile` / `FlyteDirectory` | `flyte.io.File` / `flyte.io.Dir` | Offloaded file and directory references. |
| `StructuredDataset` | `flyte.io.DataFrame` | Offloaded tabular data. |
| `LaunchPlan` | `flyte.Trigger` | Scheduling and parameterized entry points. |
| `CronSchedule` | `flyte.Cron` | Cron-based scheduling, used with a `flyte.Trigger`. |
| Decks (`enable_deck=True`) | Reports (`report=True`) | Custom HTML rendered in the UI during/after a run. |

## The two mechanical changes behind (almost) every migration

Most of a migration comes down to two moves.

### 1. Move task configuration into a `TaskEnvironment`

Instead of configuring the image, resources, and caching on each task decorator, configure them once on a `flyte.TaskEnvironment` and share it across tasks:

```python
env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_debian_base().with_pip_packages("scikit-learn", "pandas"),
    resources=flyte.Resources(cpu="2", memory="4Gi"),
    cache="auto",
)
```

### 2. Replace `@task` / `@workflow` / `@dynamic` with `@env.task`

Every decorated function becomes an `@env.task`. There is no separate workflow or dynamic construct: a "workflow" is simply a task that calls other tasks, and orchestration is plain Python. The `env` in `@env.task` is just the variable you assigned your `TaskEnvironment` to — name it whatever you like.

## Package imports

The package is renamed from `flytekit` to `flyte`, and the workflow/dynamic/map_task imports disappear.

### Flyte 1

```python
import flytekit
from flytekit import task, workflow, dynamic, map_task
from flytekit import ImageSpec, Resources, Secret
from flytekit import current_context, LaunchPlan, CronSchedule
```

### Flyte 2

```python
import flyte
from flyte import TaskEnvironment, Resources, Secret
from flyte import Image, Trigger, Cron
```

## Before and after: pure Python execution

### Flyte 1

```python
import flytekit

image = flytekit.ImageSpec(
    name="hello-world-image",
    packages=["requests"],
)

@flytekit.task(container_image=image)
def mean(data: list[float]) -> float:
    return sum(list) / len(list)

@flytekit.workflow
def main(data: list[float]) -> float:
    output = mean(data)

    # ❌ performing trivial operations in a workflow is not allowed
    # output = output / 100

    # ❌ if/else is not allowed
    # if output < 0:
    #     raise ValueError("Output cannot be negative")

    return output
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(
    "hello_world",
    image=flyte.Image.from_debian_base().with_pip_packages("requests"),
)

@env.task
def mean(data: list[float]) -> float:
    return sum(data) / len(data)

@env.task
def main(data: list[float]) -> float:
    output = mean(data)

    # ✅ performing trivial operations in a workflow is allowed
    output = output / 100

    # ✅ if/else is allowed
    if output < 0:
        raise ValueError("Output cannot be negative")

    return output
```

## Quick reference: minimal Flyte 2 module

```python
import asyncio
import flyte

# 1. Define an image
image = (
    flyte.Image.from_debian_base(python_version=(3, 11))
    .with_pip_packages("pandas", "numpy")
)

# 2. Create a TaskEnvironment
env = flyte.TaskEnvironment(
    name="my_env",
    image=image,
    resources=flyte.Resources(cpu="1", memory="2Gi"),
)

# 3. Define tasks
@env.task
async def process(x: int) -> int:
    return x * 2

# 4. Define the entrypoint task
@env.task
async def main(items: list[int]) -> list[int]:
    results = await asyncio.gather(*[process(x) for x in items])
    return list(results)

# 5. Run it
if __name__ == "__main__":
    flyte.init_from_config()
    run = flyte.run(main, items=[1, 2, 3, 4, 5])
    print(run.url)
    run.wait()
```

```bash
# CLI
flyte run my_module.py main --items '[1,2,3,4,5]'   # remote (default)
flyte run --local my_module.py main --items '[1,2,3,4,5]'
flyte deploy my_module.py my_env
```

## Recommended migration strategy

Migrations rarely happen all at once. Work incrementally and lean on hybrid pipelines while the transition is in progress.

1. **Assess the codebase.** Inventory every `@task`, `@workflow`, `@dynamic`, and `map_task`; the images (`ImageSpec`), resources, and secrets; the control-flow constructs (`conditional`, `on_failure`, `>>`); the data types (`FlyteFile`, `FlyteDirectory`, `StructuredDataset`); and any schedules (`LaunchPlan`, `CronSchedule`).
2. **Establish the `TaskEnvironment`(s).** Group tasks by their image/resource/cache needs and define a `flyte.TaskEnvironment` for each group. This is mechanical change #1 and unblocks everything else.
3. **Port leaf tasks first, then orchestration.** Convert atomic compute tasks (`@task` → `@env.task`), then rebuild the `@workflow`/`@dynamic` orchestration as plain-Python driver tasks that call them.
4. **Migrate control flow and I/O.** Replace `conditional()` with `if`/`elif`/`else`, `on_failure` with `try`/`except`, `map_task` with `flyte.map` / `asyncio.gather`, and the `FlyteFile`/`FlyteDirectory`/`StructuredDataset` types with their `flyte.io` equivalents.
5. **Update config, CLI, and schedules.** Swap `pyflyte` for `flyte`, migrate config files, and convert `LaunchPlan`/`CronSchedule` to `flyte.Trigger`/`flyte.Cron`.
6. **Run hybrid during the transition.** Keep unported v1 workflows callable via bridge tasks (see below) until every piece is on v2.

### Sibling skills to route to

Migrate by theme. Start with tasks and workflows, then jump to whatever the workload needs:

- **`flyte-migrate-tasks-workflows`** — the structural shift: `@task`/`@workflow` → `@env.task`, sequential ordering, nested "subworkflows", and the `@task` → `TaskEnvironment` parameter mapping.
- **`flyte-migrate-config`** — moving image/resources/cache to the `TaskEnvironment`, GPUs, secrets, caching, scheduling with triggers, and the `pyflyte` → `flyte` command/config-file changes.
- **`flyte-migrate-control-flow`** — `conditional()` and `@dynamic` become plain Python `if`/loops, `on_failure` becomes `try`/`except`, and `map_task` → `flyte.map` / `asyncio.gather`.
- **`flyte-migrate-data-io`** — `FlyteFile`/`FlyteDirectory` → `flyte.io.File`/`Dir`, `StructuredDataset` → `flyte.io.DataFrame`, dataclasses, and ETL patterns.
- **`flyte-migrate-ml`** — small-model training, hyperparameter optimization, deep learning, batch inference, and end-to-end pipelines.
- **`flyte-migrate-slurm`** — Slurm/HPC workloads: `#SBATCH` directives → `TaskEnvironment` resources, job arrays → `flyte.map`, multi-node `srun` training → clustered environments.

## Hybrid v1 and v2 pipelines

For a while you'll have Flyte 1 and Flyte 2 workloads running side by side, and you'll want them to call each other: a Flyte 1 workflow that kicks off a newly ported Flyte 2 task, or a Flyte 2 task that triggers a workflow that hasn't been migrated yet.

You can bridge the two in both directions. The idea is the same each way: one task installs **both** SDKs, authenticates to the **other** control plane, fetches the entity it wants to run, and launches it. Keep the bridging task lightweight and focused on orchestration.

### Running a Flyte 2 task from a Flyte 1 workflow

The bridge is a single Flyte 1 task that runs the Flyte 2 client. Give it an image with **both** `flytekit` and `flyte` installed, provide a Flyte 2 API key as a secret, authenticate inside the task with `flyte.init_from_api_key()`, fetch the deployed task with `flyte.remote.Task.get(...)`, and run it.

```python
import flytekit
from flytekit import task, workflow, ImageSpec, Secret, current_context

# The bridge image needs BOTH the v1 (flytekit) and v2 (flyte) SDKs.
bridge_image = ImageSpec(
    name="v1-to-v2-bridge",
    packages=["flytekit", "flyte"],
)

@task(
    container_image=bridge_image,
    secret_requests=[Secret(group="flyte", key="flyte_api_key")],
)
def launch_v2_from_v1(x: int) -> str:
    import flyte
    import flyte.remote

    # Authenticate to the Flyte 2 control plane with the API key.
    # Option A: read the mounted secret and pass it explicitly.
    api_key = current_context().secrets.get(group="flyte", key="flyte_api_key")
    flyte.init_from_api_key(api_key=api_key)

    # Option B: if FLYTE_API_KEY is set as an env var, no argument is needed:
    #     flyte.init_from_api_key()

    # Fetch the deployed Flyte 2 task and run it.
    remote_v2_task = flyte.remote.Task.get(
        "my_v2_env.process",
        auto_version="latest",
    )
    run = flyte.run(remote_v2_task, x=x)
    run.wait()  # optional: block until the v2 run finishes
    return run.url

@workflow
def main(x: int) -> str:
    return launch_v2_from_v1(x=x)
```

The referenced Flyte 2 task (`my_v2_env.process` above) must be **deployed** before the bridge runs. Use `flyte.init_from_api_key()` here — do **not** use `flyte.init_from_config()`, which reads a `config.yaml` that has no API-key field.

### Running a Flyte 1 workflow from a Flyte 2 task

The reverse works the same way: a Flyte 2 task installs the Flyte 1 client and uses `FlyteRemote` to launch a Flyte 1 workflow.

```python
import flyte

env = flyte.TaskEnvironment(
    name="v2_to_v1_bridge",
    # The image needs the Flyte 1 client installed.
    image=flyte.Image.from_debian_base().with_pip_packages("flytekit"),
    # Supply credentials for the Flyte 1 control plane (config or API key).
    secrets=[flyte.Secret(key="v1_client_secret", as_env_var="V1_CLIENT_SECRET")],
)

@env.task
async def launch_v1_from_v2(x: int) -> str:
    from flytekit.remote import FlyteRemote
    from flytekit.configuration import Config

    # Point the client at your Flyte 1 cluster.
    remote = FlyteRemote(
        config=Config.for_endpoint(endpoint="my-v1-cluster.example.com"),
        default_project="flytesnacks",
        default_domain="development",
    )

    # Fetch the deployed Flyte 1 workflow and execute it.
    wf = remote.fetch_workflow(name="my_v1_module.main", version="v1.2.3")
    execution = remote.execute(wf, inputs={"x": x}, wait=True)
    return execution.id.name
```

### Hybrid considerations

- **Both SDKs in one image.** The bridging task installs `flytekit` and `flyte` together. Pin versions and watch for dependency conflicts; keep the bridge image minimal.
- **Deploy the callee first.** For v1→v2, the Flyte 2 task must be deployed (`flyte deploy`) before `flyte.remote.Task.get()` can resolve it. For v2→v1, the Flyte 1 workflow must be registered on its cluster.
- **Wait vs. fire-and-forget.** Both `run.wait()` (v2) and `execute(..., wait=True)` (v1) block until the launched run finishes. Omit them to launch and return immediately.
- **Credentials cross a boundary.** The bridge authenticates to a *different* control plane than the one it runs on. Store the API key or client credentials as a secret — never hard-code them.
- **Keep the bridge lightweight.** Like any orchestrating task, it should mostly launch and assemble results rather than do heavy compute.

## Gotchas

Flyte 2 lets each Python task act as its own engine, launching sub-tasks and assembling their outputs. That flexibility warrants some caveats.

### Common gotchas

- **`flyte.map` returns a generator.** Wrap it in `list()` to materialize results, unlike `map_task` which returned a list directly.
- **`memory`, not `mem`.** The `Resources` parameter was renamed, and there are no separate `requests`/`limits` — a single value serves as both.
- **GPUs use a `"T4:1"` string.** Type and count are combined; the separate `accelerator=` argument is gone.
- **Image, resources, and cache live on the `TaskEnvironment`.** Set them once at the env level instead of repeating them on every task decorator.
- **`current_context()` is gone.** Read secrets from environment variables and use `flyte.ctx()` for runtime context.
- **The `>>` ordering operator is gone.** Sequential (sync) calls and sequential `await`s are naturally ordered.
- **Retries no longer have a platform cap.** In Flyte 1 the control plane capped attempts at 3; in Flyte 2 total attempts equal `retries + 1`. Audit any large `retries` values before deploying.
- **You can only `await` async tasks.** Call a sync task from an async context with `.aio()`.
- **Pick an entrypoint task name.** There's no `@workflow`, so the top-level task is just a task (commonly `main`); run it with `flyte run module.py main`.
- **Type annotations are more lenient.** Flyte 2 will pickle untyped I/O rather than rejecting it at registration.
- **Keep orchestration lightweight.** A task that calls other tasks acts as a driver pod. Avoid heavy CPU work in it.

## Anti-Patterns

1. **Don't introduce non-determinism into orchestration.** When a task launches another task, a new Action ID is determined as a hash of the inputs and task definition — consistent hashing is what makes recovery and replay work. Branching on `datetime.now()` or other non-deterministic values breaks that guarantee: on retry, a *different* downstream task may get kicked off. If non-determinism is unavoidable, decorate sub-task functions with `@trace` for fine-grained checkpointing and observability.
2. **Don't do heavy compute in a driver task.** When a task runs other tasks and assembles their outputs, it becomes a driver pod (work that Flyte Propeller did in v1). A CPU-bound function between two `await`s makes the driver pod hang and slows downstream kickoff. Keep parent tasks focused on orchestration:

```python
@env.task
async def t_main():
    await t1()
    local_cpu_intensive_function()  # ❌ blocks the driver pod between t1 and t2
    await t2()
```

3. **Don't rely on global state across tasks.** Each task runs in its own isolated container; globals are not carried across task containers. Any state that must persist has to be reconstructable through repeated deterministic execution.
4. **Don't materialize huge in-memory I/O between tasks.** Outputs are materialized in the parent pod's memory, so passing a 1 GB `list[float]` requires the pod to hold all of it, risking OOM. Use `flyte.io.File`, `flyte.io.Dir`, and `flyte.io.DataFrame` — they're materialized only as pointers to offloaded data, so their memory footprint stays low.
5. **Don't skip type hints at the "workflow" level.** The top-level task now runs at runtime, so the system can't guarantee type safety across the DAG the way the v1 DSL did. Use Python type hints and a type checker like `mypy` at all levels, including the top-most task.
