---
name: flyte-migrate-tasks-workflows
description: >-
  Migrates Flyte 1 tasks and workflows to Flyte 2, where the @task, @workflow,
  and @dynamic decorators collapse into a single @env.task on a
  flyte.TaskEnvironment and a workflow becomes a task that calls other tasks.
  Use when the user is migrating Flyte 1 tasks/workflows to Flyte 2. Trigger
  words: migrate task, migrate workflow, @task, @workflow, @dynamic,
  TaskEnvironment, env.task.
---

# Flyte 1 to 2 Migration: Tasks and Workflows

The biggest structural change in Flyte 2 is that everything is a task. The Flyte 1 `@task`, `@workflow`, and `@dynamic` decorators all collapse into a single `@env.task` on a `flyte.TaskEnvironment`, and a "workflow" is now just a task that calls other tasks. This skill covers the structural shift, sequential ordering without the `>>` operator, nested subworkflows, TaskEnvironment configuration basics, and the full `@task` parameter mapping.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/tasks-and-workflows/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## The Structural Shift

In Flyte 1 you decorated units of work with `@task`, composed them with `@workflow`, and used `@dynamic` for runtime-generated graphs. In Flyte 2 you create one `flyte.TaskEnvironment` that carries the configuration, then decorate every function — leaf tasks and orchestrating "workflows" alike — with `@env.task`. There is no separate `@workflow` decorator: the entrypoint is just a task that calls other tasks.

## Hello World: Tasks and Workflows

A `@task` plus `@workflow` becomes two `@env.task`s, where the entrypoint task calls the others. Sequential calls are naturally ordered — no `>>` operator required.

### Flyte 1

```python
import flytekit

@flytekit.task
def say_hello(name: str) -> str:
    return f"Hello, {name}!"

@flytekit.task
def to_upper(greeting: str) -> str:
    return greeting.upper()

@flytekit.workflow
def main(name: str) -> str:
    greeting = say_hello(name=name)
    return to_upper(greeting=greeting)
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(name="hello_world")

@env.task
def say_hello(name: str) -> str:
    return f"Hello, {name}!"

@env.task
def to_upper(greeting: str) -> str:
    return greeting.upper()

# The "workflow" is now just a task that calls other tasks.
@env.task
def main(name: str) -> str:
    greeting = say_hello(name)
    return to_upper(greeting)
```

Note that Flyte 2 task calls pass arguments positionally (`say_hello(name)`) rather than requiring keyword arguments as in Flyte 1 (`say_hello(name=name)`).

## Chaining and Ordering

In Flyte 1 you sometimes used `>>` to force ordering between tasks with no data dependency. In Flyte 2, sequential (synchronous) calls run in the order they are written, and `await`ing async tasks in sequence does the same. The `>>` operator is gone.

### Flyte 1

```python
from flytekit import task, workflow

@task
def clear_staging_table() -> None:
    # Side effect only: truncate the staging table.
    print("cleared staging table")

@task
def load_into_staging() -> None:
    # Side effect only: load fresh rows into staging.
    print("loaded staging table")

@task
def publish_to_prod() -> None:
    # Side effect only: swap staging into the production table.
    print("published to prod")

@workflow
def main() -> None:
    clear = clear_staging_table()
    load = load_into_staging()
    publish = publish_to_prod()

    # These tasks pass no data between them, so use the >> operator to force
    # ordering: clear must finish before load, which must finish before publish.
    clear >> load >> publish
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(name="staging_publish")

@env.task
def clear_staging_table() -> None:
    print("cleared staging table")

@env.task
def load_into_staging() -> None:
    print("loaded staging table")

@env.task
def publish_to_prod() -> None:
    print("published to prod")

# Sequential (synchronous) calls run in the order they're written, even when no
# data flows between them. The Flyte 1 `>>` ordering operator is gone.
@env.task
def main() -> None:
    clear_staging_table()
    load_into_staging()
    publish_to_prod()
```

## Subworkflows

A `@workflow` invoked by another `@workflow` (for example, a reusable preprocessing pipeline) becomes a task that calls other tasks — nest them as deeply as you like.

### Flyte 1

```python
from flytekit import task, workflow

@task
def impute(value: float) -> float:
    # Replace missing/negative sentinel values with 0.
    return value if value >= 0 else 0.0

@task
def scale(value: float) -> float:
    return value / 100.0

@workflow
def preprocess(value: float) -> float:
    imputed = impute(value=value)
    return scale(value=imputed)

@workflow
def main(raw_value: float) -> float:
    return preprocess(value=raw_value)
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(name="subworkflow")

@env.task
def impute(value: float) -> float:
    # Replace missing/negative sentinel values with 0.
    return value if value >= 0 else 0.0

@env.task
def scale(value: float) -> float:
    return value / 100.0

# A preprocessing "subworkflow" is just a task that calls other tasks.
@env.task
def preprocess(value: float) -> float:
    imputed = impute(value)
    return scale(imputed)

@env.task
def main(raw_value: float) -> float:
    return preprocess(raw_value)
```

## TaskEnvironment Configuration

The `TaskEnvironment` holds the configuration that Flyte 1 spread across the `@task` decorator. The task decorator can still override a few settings per-task.

```python
import flyte

env = flyte.TaskEnvironment(
    name="my_env",                           # Required: unique name
    image=flyte.Image.from_debian_base(),    # Or a string, or "auto"
    resources=flyte.Resources(
        cpu="2",
        memory="4Gi",
        gpu="A100:1",
        disk="10Gi",
    ),
    env_vars={"LOG_LEVEL": "INFO"},
    secrets=[flyte.Secret(key="api-key", as_env_var="API_KEY")],
    cache="auto",                            # "auto", "override", "disable", or a Cache object
    reusable=flyte.ReusePolicy(replicas=5, idle_ttl=60),
    interruptible=True,
)

# The task decorator can override some settings:
@env.task(
    short_name="my_task",   # Display name
    cache="disable",        # Override cache
    retries=3,              # Retry count
    timeout=3600,           # Seconds or a timedelta
    report=True,            # Generate an HTML report
)
def my_task(x: int) -> int:
    return x
```

### Calling tasks in another environment: `depends_on`

In Flyte 1 each `@task` could set its own `container_image`, and a workflow could mix them freely. In Flyte 2, tasks with different images live in different `TaskEnvironment`s, and the environment of the calling task must declare the environments it calls in `depends_on`. Without it, the call fails at runtime with `Environment 'mindmeld' not found in image cache ... declare that dependency using 'depends_on=[...]'`: the callee's image was never resolved for the run. (Environments that share the same image object may happen to work without it; declare the dependency anyway.)

```python
# Flyte 1: @task(container_image=sklearn_image) def get_data(): ...
mindmeld = flyte.TaskEnvironment(
    name="mindmeld",
    image=flyte.Image.from_debian_base().with_pip_packages("scikit-learn", "numpy"),
)

borebuster = flyte.TaskEnvironment(
    name="borebuster",
    image=flyte.Image.from_debian_base().with_pip_packages("numpy"),
    depends_on=[mindmeld],  # the entrypoint below calls get_data, which runs in mindmeld
)

@mindmeld.task
def get_data() -> list[float]:
    ...

@borebuster.task
def main() -> list[float]:
    return get_data()
```

The same applies to tasks not created with an `@env.task` decorator, such as plugin tasks (see `flyte-migrate-plugins`) and shell tasks: wrap them in an environment with `flyte.TaskEnvironment.from_task("name", task_a, task_b)` and add that environment to `depends_on`.

**`depends_on` must not form a cycle.** If the driver environment depends on a worker environment and the worker also calls back into a task in the driver environment (`driver.depends_on=[worker]` plus `worker.add_dependency(driver)`), `flyte run` fails at submit with `maximum recursion depth exceeded`. Move the shared task into a third environment that both depend on:

```python
helpers = flyte.TaskEnvironment(name="helpers")                 # stringify() lives here
worker = flyte.TaskEnvironment(name="worker", depends_on=[helpers])
driver = flyte.TaskEnvironment(name="driver", depends_on=[worker, helpers])
```

**The caller's image must be able to deserialize what it receives.** A calling task materializes every sub-task output. If a task in another environment returns a value that falls back to pickle, such as a scikit-learn model, the caller's image needs that library too. Otherwise the caller fails with `Error converting input ... No module named sklearn`. This holds even when `depends_on` is correct. Add the library to the caller's image, or return a `File` (for example a saved model) instead of the object.

### Mixing sync and async tasks

Flyte 1 tasks were all called the same way. In Flyte 2, a task is sync or async depending on its `def`, and the call must match:

| Caller | Callee | How to call |
|---|---|---|
| sync | sync | `result = t(x)` |
| async | async | `result = await t(x)` |
| async | sync (including plugin tasks like `NotebookTask`) | `result = await t.aio(x)`. A plain `t(x)` fails with `Sync task '...' was called in a blocking way from async code ... Use await t.aio(...)` |
| sync | async | Don't. The call returns an un-awaited coroutine, and the caller fails later with `Expected value of type <class 'str'> but got '<coroutine object ...>'`. Make the caller `async`, or the callee sync |

A literal port of a Flyte 1 workflow is sync throughout, so the simplest rule is: keep a migrated pipeline all sync or all async, and use `.aio()` at the boundary when an async driver calls a sync task.

## Parameter Mapping: `@task` to `TaskEnvironment` + `@env.task`

| Flyte 1 `@task` parameter | Flyte 2 location | Notes |
|---|---|---|
| `container_image` | `TaskEnvironment(image=...)` | Env-level only |
| `requests` | `TaskEnvironment(resources=...)` | Env-level only |
| `limits` | `TaskEnvironment(resources=...)` | Combined with requests (single value) |
| `environment` | `TaskEnvironment(env_vars=...)` | Env-level only |
| `secret_requests` | `TaskEnvironment(secrets=...)` | Env-level only |
| `cache` | Both | Can override at task level |
| `cache_version` | `flyte.Cache(behavior="override", version_override=...)` | In a `Cache` object |
| `retries` | `@env.task(retries=...)` | Task-level only |
| `timeout` | `@env.task(timeout=...)` | Task-level only |
| `interruptible` | Both | Can override at task level |
| `pod_template` | Both | Can override at task level |
| `deprecated` | N/A | Not in Flyte 2 |
| `docs` | `@env.task(docs=...)` | Task-level only |

For image, resource, secret, and caching detail, see the Task configuration migration page.

## Anti-Patterns

1. **Don't reach for `>>`** — the ordering operator is gone. Sequential synchronous calls already run in written order; `await` async tasks in sequence for the same effect.
2. **Don't look for a `@workflow` decorator** — there isn't one. The orchestrating entrypoint is just another `@env.task` that calls other tasks.
3. **Don't look for a `@dynamic` decorator** — dynamic graphs also collapse into ordinary `@env.task` functions that call other tasks at runtime.
4. **Don't put heavy compute in the orchestrating task** — keep the entrypoint task focused on calling other tasks; push CPU/GPU/memory-intensive work into leaf tasks whose resources you can tune per environment.
5. **Don't set image, resources, or secrets on the `@env.task` decorator** — those are env-level and belong on `TaskEnvironment`. Only per-task overrides like `retries`, `timeout`, `cache`, and `short_name` go on `@env.task`.
6. **Don't keep passing every argument by keyword** — Flyte 2 task calls accept positional arguments (`say_hello(name)`).
7. **Don't call a task in another `TaskEnvironment` without `depends_on`** — the caller's environment must list the callee's environment, or the run fails with `Environment '...' not found in image cache`.
8. **Don't make `depends_on` circular** — when two environments call each other, move the shared tasks into a third environment that both depend on.
9. **Don't call an async task from a sync task** — it returns a coroutine instead of a result. From an async task, call sync tasks with `await t.aio(...)`.
