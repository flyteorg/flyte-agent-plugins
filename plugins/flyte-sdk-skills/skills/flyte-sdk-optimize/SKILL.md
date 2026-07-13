---
name: flyte-sdk-optimize
description: 'Suggests performance improvements (task granularity, caching, resource requests, data format changes) using observed run metadata when available. Use when the user wants to optimize workflow performance, debug slow tasks, configure caching, tune resources, or improve throughput. Trigger words: "optimize", "performance", "slow", "cache", "caching", "resource", "throughput", "latency", "speed up", "bottleneck", "profiling", "metadata".'
---

# Flyte 2 SDK Optimize Skill

Optimize Flyte 2 workflows for performance, cost, and reliability.

## Grounding References

| Resource | URL |
|---|---|
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## Optimization Strategy Overview

Performance optimization in Flyte follows a hierarchy:

1. **Reduce container overhead** — use traces for lightweight ops
2. **Parallelize work** — use `flyte.map` for fan-out
3. **Cache results** — use `cache="auto"` for idempotent tasks
4. **Tune resources** — set appropriate CPU/memory/GPU
5. **Optimize data transfer** — choose efficient formats, reduce inline I/O
6. **Use reusable containers** — shared environments reduce image pull time

## Caching

### Enable automatic caching

```python
@env.task(cache="auto")  # versioned by function body + inputs
async def preprocess(data: list[str]) -> flyte.File:
    ...
```

### Cache key strategies

```python
@env.task(cache="auto")  # default: function body + inputs
async def task_a(data: str) -> flyte.File:
    ...

@env.task(cache="override", salt="v2")  # add salt for cache key variation
async def task_b(data: str) -> flyte.File:
    ...

@env.task(cache="disable")  # always re-run
async def task_c(data: str) -> flyte.File:
    ...
```

### Content-based caching for DataFrames

```python
@env.task(cache="auto")
async def transform(df: flyte.DataFrame) -> flyte.DataFrame:
    """Cache key includes DataFrame content hash."""
    ...
```

### Ignoring specific inputs in cache key

```python
@env.task(cache="auto", cache_ignore_inputs=["api_key"])
async def fetch_data(api_key: str, url: str) -> flyte.File:
    """Don't include api_key in cache key."""
    ...
```

### Cache policies

```python
@env.task(cache="auto", cache_policy=flyte.CachePolicy(min_cached_age="1h"))
async def cached_task(data: str) -> flyte.File:
    """Only use cache if result is at least 1 hour old."""
    ...
```

## Resource Tuning

### Setting task resources

```python
@env.task(
    requests=flyte.Resources(cpu="500m", memory="1Gi"),
    limits=flyte.Resources(cpu="2", memory="4Gi"),
)
async def light_task(data: str) -> str:
    """Lightweight task — small resources."""
    ...

@env.task(
    requests=flyte.Resources(cpu="4", memory="16Gi"),
    limits=flyte.Resources(cpu="8", memory="32Gi"),
)
async def heavy_task(data: flyte.DataFrame) -> flyte.DataFrame:
    """Heavy data processing — large resources."""
    ...

@env.task(
    requests=flyte.Resources(cpu="1", memory="4Gi", gpu="1", gpu_model="nvidia-a10g"),
    limits=flyte.Resources(cpu="2", memory="8Gi", gpu="1", gpu_model="nvidia-a10g"),
)
async def train_model(data: flyte.File) -> flyte.File:
    """GPU training task."""
    ...
```

### GPU resource configuration

```python
@env.task(
    requests=flyte.Resources(
        cpu="2",
        memory="8Gi",
        gpu="1",
        gpu_model="nvidia-a10g",  # or "nvidia-a100", "nvidia-h100"
    ),
)
async def inference(batch: flyte.DataFrame) -> flyte.DataFrame:
    ...
```

### Resource recommendations by workload

| Workload | CPU | Memory | GPU |
|---|---|---|---|
| Light ETL | 500m-1 | 1-2 Gi | none |
| Data processing | 2-4 | 8-16 Gi | none |
| Embedding | 2-4 | 8-16 Gi | none |
| Model training | 4-8 | 16-32 Gi | 1-8 |
| Batch inference | 2-4 | 8-16 Gi | 1-4 |
| LLM serving | 8-16 | 32-64 Gi | 1-8 |
| Data quality | 1-2 | 4-8 Gi | none |

## Parallelization Patterns

### flyte.map for parallel execution

```python
@env.task
async def process_item(item: dict) -> dict:
    """Process a single item."""
    ...

@env.task
async def main(items: list[dict]) -> list:
    """Fan out processing in parallel."""
    results = await flyte.map(process_item, items)
    return results
```

### flyte.trace for lightweight parallelism

```python
@env.task
async def fetch_url(url: str) -> str:
    """Lightweight HTTP fetch — use trace (no container overhead)."""
    ...

@env.task
async def main(urls: list[str]) -> list:
    """Use trace for light ops (no container spin-up cost)."""
    results = await flyte.trace(fetch_url, urls)
    return results
```

### asyncio.gather for sequential fan-out

```python
@env.task
async def main(data: list[str]) -> dict:
    """Chain tasks with parallel fan-out at each step."""
    # Step 1: parallel preprocessing
    preprocessed = await asyncio.gather(*(preprocess(d) for d in data))

    # Step 2: sequential aggregation
    aggregated = aggregate(preprocessed)

    # Step 3: parallel evaluation
    metrics = await asyncio.gather(*(evaluate(p) for p in preprocessed))

    return {"aggregated": aggregated, "metrics": metrics}
```

### Controlling concurrency

```python
@env.task
async def main(urls: list[str]) -> list:
    """Limit concurrency with asyncio.Semaphore."""
    import asyncio
    sem = asyncio.Semaphore(10)  # max 10 concurrent

    async def bounded(item):
        async with sem:
            return await process_item(item)

    return await asyncio.gather(*(bounded(u) for u in urls))
```

## Data Format Optimization

### Choosing efficient formats

| Use case | Recommended format | Why |
|---|---|---|
| Tabular data | Parquet | Columnar, compressed, fast |
| JSON data | JSONL | Line-delimited, streaming |
| Images | PNG/WebP | Lossless/lossy compression |
| Audio | WAV/FLAC | Lossless |
| Model checkpoints | .pt/.safetensors | Native framework format |
| Embeddings | .npy/.npz | NumPy binary format |

### Reducing inline I/O

```python
# Bad: large dict passed inline (JSON serialization overhead)
@env.task
async def process(large_data: dict) -> dict:
    ...

# Good: pass by reference
@env.task
async def process(data_file: flyte.File) -> flyte.File:
    ...

# Good: set inline output limit
@env.task(inline_output_limit="5MB")
async def process(data: dict) -> dict:
    ...
```

## Run Metadata Inspection

### Using MCP to inspect runs

```
Use flyte_mcp_list_runs(task_name="<task_name>", limit=50)
to find runs for performance analysis.

Use flyte_mcp_get_run(name="<run_name>")
to get run metadata (status, duration, etc.).

Use flyte_mcp_get_run_io(name="<run_name>")
to get inputs/outputs of a run for validation.
```

### Performance analysis checklist

1. **Check run duration** — use `flyte_mcp_get_run` to see `durationMs`
2. **Check cache status** — `CACHE_HIT` vs `CACHE_MISS` in run metadata
3. **Check resource utilization** — compare requested vs actual usage
4. **Check data transfer** — large inline I/O indicates format issues
5. **Check retry count** — frequent retries indicate instability

## Retry and Timeout Configuration

### Retries for resilience

```python
@env.task(retries=3)  # retry up to 3 times on failure
async def flaky_task(data: str) -> str:
    """Task that may fail transiently."""
    ...

@env.task(retries=3, retry_policy=flyte.RetryPolicy(min_attempts=3))
async def critical_task(data: str) -> str:
    """Always retry, never fail fast."""
    ...
```

### Timeouts for bounding execution

```python
@env.task(max_runtime="1h")  # bound single attempt
async def long_task(data: str) -> str:
    ...

@env.task(max_queued_time="30m")  # fail fast if no capacity
async def urgent_task(data: str) -> str:
    ...

@env.task(deadline="2h")  # bound total wall-clock (all attempts)
async def deadline_task(data: str) -> str:
    ...
```

## Interruptible Tasks (Spot Instances)

```python
@env.task(interruptible=True)  # can be preempted, falls back to on-demand
async def spot_task(data: str) -> str:
    """Cost-effective for fault-tolerant workloads."""
    ...
```

## Optimization Anti-Patterns

1. **Don't over-cache** — avoid `cache="auto"` on tasks with side effects or non-deterministic outputs
2. **Don't set resources too high** — over-provisioning wastes money; too low causes OOM
3. **Don't use `asyncio.gather` for heavy workloads** — use `flyte.map` for parallel container execution
4. **Don't skip caching on ETL** — idempotent data transforms should always cache
5. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs
6. **Don't ignore run metadata** — always check `durationMs` and cache status when debugging performance
