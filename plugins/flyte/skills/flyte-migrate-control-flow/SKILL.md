---
name: flyte-migrate-control-flow
description: "Migrates Flyte 1 branching, dynamic workflows, failure handling, and fan-out to native Flyte 2 Python. Use when migrating Flyte 1 branching, dynamic workflows, failure handling, or map_task/fan-out to Flyte 2. Trigger words: conditional, @dynamic, map_task, on_failure, branching, parallelism, fan-out, flyte.map, asyncio.gather."
---

# Flyte 1 to 2 Migration: Control Flow and Parallelism

Flyte 1 expressed branching, dynamic fan-out, and failure handling through DSL constructs (`conditional()`, `@dynamic`, `@workflow(on_failure=...)`) and `map_task`. In Flyte 2 these are all ordinary Python, because orchestration runs as real Python at runtime. Native `if`/`elif`/`else` replaces the conditional DSL, plain task loops replace `@dynamic`, `try`/`except` replaces `on_failure`, and `flyte.map` / `asyncio.gather` replace `map_task`.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide (Control flow) | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/control-flow/ |
| Migration guide (Parallelism) | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/parallelism/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## Conditional Execution

The `conditional()` DSL becomes ordinary Python `if` / `elif` / `else` — for example, choosing a model based on dataset size.

### Flyte 1

```python
from flytekit import task, workflow, conditional

@task
def train_gradient_boosting(n_rows: int) -> str:
    return f"trained gradient boosting on {n_rows} rows"

@task
def train_logistic_regression(n_rows: int) -> str:
    return f"trained logistic regression on {n_rows} rows"

@workflow
def main(n_rows: int) -> str:
    # Pick the model based on dataset size.
    return (
        conditional("model_choice")
        .if_(n_rows > 10_000)
        .then(train_gradient_boosting(n_rows=n_rows))
        .else_()
        .then(train_logistic_regression(n_rows=n_rows))
    )
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(name="conditional")

@env.task
def train_gradient_boosting(n_rows: int) -> str:
    return f"trained gradient boosting on {n_rows} rows"

@env.task
def train_logistic_regression(n_rows: int) -> str:
    return f"trained logistic regression on {n_rows} rows"

# Branching is now ordinary Python control flow -- no conditional() DSL.
@env.task
def main(n_rows: int) -> str:
    if n_rows > 10_000:
        return train_gradient_boosting(n_rows)
    return train_logistic_regression(n_rows)
```

## Dynamic Workflows

`@dynamic` existed so a task could generate a variable number of subtask calls at runtime (e.g. one per data partition discovered at runtime). In Flyte 2 every task can do this natively, so `@dynamic` simply disappears — loop over runtime data in an ordinary `@env.task`.

### Flyte 1

```python
from flytekit import task, workflow, dynamic

@task
def list_partitions(n: int) -> list[int]:
    return list(range(n))

@task
def process_partition(partition_id: int) -> int:
    # Aggregate one data partition.
    return partition_id * 2

@dynamic
def process_all(partitions: list[int]) -> list[int]:
    results = []
    for partition_id in partitions:
        results.append(process_partition(partition_id=partition_id))
    return results

@workflow
def main(n: int) -> list[int]:
    partitions = list_partitions(n=n)
    return process_all(partitions=partitions)
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(name="dynamic")

@env.task
def process_partition(partition_id: int) -> int:
    # Aggregate one data partition.
    return partition_id * 2

# No @dynamic decorator needed: a plain task can loop over runtime data (e.g. a
# variable number of partitions discovered at runtime) and call other tasks.
@env.task
def main(n: int) -> list[int]:
    return [process_partition(partition_id) for partition_id in range(n)]
```

## Error Handling

Flyte 1's `@workflow(on_failure=...)` handler becomes ordinary Python `try` / `except` — catch a failed training run, run cleanup, and recover or re-raise.

### Flyte 1

```python
from flytekit import task, workflow

@task
def train_fold(max_depth: int) -> float:
    if max_depth <= 0:
        raise ValueError("max_depth must be positive")
    # Return validation accuracy for this hyperparameter.
    return 0.90 + 0.001 * max_depth

@task
def notify_failure() -> None:
    print("training run failed -- sending alert")

# The on_failure handler runs if any node in the workflow fails. There is no
# try/except inside a Flyte 1 workflow.
@workflow(on_failure=notify_failure)
def main(max_depth: int) -> float:
    return train_fold(max_depth=max_depth)
```

### Flyte 2

```python
import flyte

env = flyte.TaskEnvironment(name="error_handling")

@env.task
async def train_fold(max_depth: int) -> float:
    if max_depth <= 0:
        raise ValueError("max_depth must be positive")
    return 0.90 + 0.001 * max_depth

# Failure handling is ordinary Python try/except -- no on_failure handler.
@env.task
async def main(max_depth: int) -> float:
    try:
        return await train_fold(max_depth)
    except ValueError as e:
        print(f"invalid hyperparameter ({e}); falling back to a safe default")
        # Recover with a safe default instead of failing the whole run.
        return await train_fold(max_depth=6)
```

Flyte 2 also exposes typed errors, so you can catch a specific failure and retry with more resources — a common need for memory-hungry training jobs:

```python
try:
    return await train_fold(sample_size)
except flyte.errors.OOMError:
    # Retry the same task with a larger memory request.
    return await train_fold.override(
        resources=flyte.Resources(memory="16Gi")
    )(sample_size)
```

## Fan-out: map_task

`map_task()` becomes `flyte.map()`, a near drop-in replacement. The one catch: `flyte.map` returns a generator, so wrap it in `list()`. For new code, the idiomatic approach is Python `async`/`await` with `asyncio.gather()`, which gives finer control over concurrency and error handling.

### Flyte 1

```python
from functools import partial

from flytekit import task, workflow, map_task

@task
def get_shards(n: int) -> list[int]:
    return list(range(n))

@task
def score_shard(shard_id: int, model_version: int) -> int:
    # Score one shard of records with the given model version.
    return shard_id * model_version

@workflow
def main(n: int, model_version: int) -> list[int]:
    shards = get_shards(n=n)
    return map_task(
        partial(score_shard, model_version=model_version),
        concurrency=10,
    )(shard_id=shards)
```

### Flyte 2 (flyte.map)

```python
import flyte
from functools import partial

env = flyte.TaskEnvironment(name="map_task")

@env.task
def score_shard(shard_id: int, model_version: int) -> int:
    # Score one shard of records with the given model version.
    return shard_id * model_version

@env.task
def main(n: int, model_version: int) -> list[int]:
    bound = partial(score_shard, model_version=model_version)
    # flyte.map is a drop-in for map_task, but it returns a generator, so wrap
    # it in list() to materialize the results.
    return list(flyte.map(bound, range(n), concurrency=10))
```

### Flyte 2 (asyncio.gather)

```python
import asyncio

import flyte

env = flyte.TaskEnvironment(name="map_task")

@env.task
async def score_shard_async(shard_id: int, model_version: int) -> int:
    return shard_id * model_version

@env.task
async def main_async(n: int, model_version: int) -> list[int]:
    # asyncio.gather is the idiomatic Flyte 2 way to fan out.
    coros = [score_shard_async(i, model_version) for i in range(n)]
    return list(await asyncio.gather(*coros))
```

### Choosing flyte.map vs asyncio.gather

| Feature | `flyte.map` (sync) | `asyncio.gather` (async) |
|---|---|---|
| Syntax | `list(flyte.map(fn, items))` | `await asyncio.gather(*tasks)` |
| Concurrency limit | Built-in `concurrency=N` | Use `asyncio.Semaphore` |
| Streaming / as-completed | No | Yes, via `asyncio.as_completed()` |
| Error handling | `return_exceptions=True` | Check return type |

Use `flyte.map` for the smallest change from Flyte 1 `map_task`, or when stuck in synchronous code. Use `asyncio.gather` for new code where you want streaming results or fine-grained concurrency control.

### Concurrency Control and Error Handling

`map_task`'s `concurrency` and `min_success_ratio` become an `asyncio.Semaphore` and `return_exceptions=True`:

```python
import asyncio

@env.task
async def main(items: list[int], max_concurrent: int = 5) -> list[str]:
    sem = asyncio.Semaphore(max_concurrent)

    async def process_with_limit(item: int) -> str:
        async with sem:
            return await process_item(item)

    tasks = [process_with_limit(i) for i in items]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in results if not isinstance(r, Exception)]
```

## Data Backfills

Reprocessing a range of dates is a textbook `@dynamic` use case in Flyte 1, because the number of days is only known at runtime. In Flyte 2 it's a plain task that builds the date range and fans the days out with `asyncio.gather`.

### Flyte 1

```python
from datetime import date, timedelta

from flytekit import task, workflow, dynamic

@task
def process_day(day: str) -> int:
    # Reprocess a single day's partition; return the row count.
    return len(day)

# @dynamic is needed because the number of days is only known at runtime.
@dynamic
def backfill(start: str, days: int) -> list[int]:
    base = date.fromisoformat(start)
    results = []
    for i in range(days):
        day = (base + timedelta(days=i)).isoformat()
        results.append(process_day(day=day))
    return results

@workflow
def main(start: str, days: int) -> list[int]:
    return backfill(start=start, days=days)
```

### Flyte 2

```python
import asyncio
from datetime import date, timedelta

import flyte

env = flyte.TaskEnvironment(name="data_backfill")

@env.task
async def process_day(day: str) -> int:
    # Reprocess a single day's partition; return the row count.
    return len(day)

# A plain task builds the date range at runtime and fans the days out in
# parallel with asyncio.gather -- no @dynamic and no map_task needed.
@env.task
async def main(start: str, days: int) -> list[int]:
    base = date.fromisoformat(start)
    coros = [
        process_day((base + timedelta(days=i)).isoformat())
        for i in range(days)
    ]
    return list(await asyncio.gather(*coros))
```

## Anti-Patterns

1. **Don't import `conditional`, `dynamic`, or `map_task` from `flytekit`** — none exist in Flyte 2. Branching is native `if`/`elif`/`else`, dynamic fan-out is a plain task loop, and `map_task` becomes `flyte.map`.
2. **Don't keep the `conditional().if_().then().else_()` DSL** — rewrite it as ordinary Python control flow inside an `@env.task`.
3. **Don't reach for `@dynamic`** — every Flyte 2 task can loop over runtime data and call other tasks, so drop the decorator entirely.
4. **Don't pass `on_failure=...` to `@workflow`** — there is no workflow decorator in Flyte 2; handle failures with ordinary `try`/`except` inside a task.
5. **Don't forget to `list()` a `flyte.map` result** — it returns a generator, not a materialized list.
6. **Don't forget to `await` async fan-out** — `asyncio.gather(*coros)` returns a coroutine; without `await` you get a coroutine object instead of results.
7. **Don't drop concurrency limits** — port `concurrency=N` to `flyte.map(..., concurrency=N)` or an `asyncio.Semaphore`, and `min_success_ratio` to `return_exceptions=True` with filtering.
8. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
