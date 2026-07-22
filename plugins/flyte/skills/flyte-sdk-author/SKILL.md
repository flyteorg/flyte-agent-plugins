---
name: flyte-sdk-author
description: 'Creates Flyte 2 project scaffolds (tasks, workflows, launch plans, apps), selects patterns (map tasks, traces, dynamic workflows, conditions), and generates code from templates aligned to the user''s constraints. Use when the user wants to create or scaffold Flyte workflows, tasks, or apps from scratch — "write a Flyte workflow", "create a task", "scaffold a Flyte project", "build a Flyte pipeline". Trigger words: "author", "create", "scaffold", "write a workflow", "write a task", "Flyte project structure".'
---

# Flyte 2 SDK Author Skill

Create Flyte 2 workflows, tasks, and apps from scratch using pure Python — no DSL.

## Grounding References

| Resource | URL |
|---|---|
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server (task runs, image builds, app management) |

## Tool Priority

1. **Flyte MCP** — if the agent harness has access to `flyte-mcp`, prefer its tools for:
   - `flyte_mcp_get_task` — inspect a registered task's spec
   - `flyte_mcp_list_tasks` — discover registered tasks
   - `flyte_mcp_list_runs` — list past runs
   - `flyte_mcp_get_run` / `flyte_mcp_wait_for_run` / `flyte_mcp_get_run_io` — interact with runs
   - `flyte_mcp_run_task` — execute a task remotely
   - `flyte_mcp_get_app` / `flyte_mcp_activate_app` / `flyte_mcp_deactivate_app` — manage apps
   - `flyte_mcp_activate_trigger` / `flyte_mcp_deactivate_trigger` — manage triggers
   - `flyte_mcp_build_image` — build container images
   - `flyte_mcp_search_flyte_docs_examples` — search docs and SDK examples
2. **`flyte` CLI** — for local commands: `flyte run`, `flyte deploy`, `flyte serve`, `flyte create config`, `flyte start devbox`
3. **Python SDK** — for anything the CLI/MCP can't do (custom task environments, type transformers, dynamic workflows, programmatic run control)

## Core Patterns

### TaskEnvironment + @env.task (recommended)

```python
import flyte

env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "pandas", "torch", "transformers",
    ),
)

@env.task(retries=2, cache="auto")
async def preprocess(data: list[str]) -> flyte.File:
    # ETL: clean + write to remote storage
    ...
    return flyte.File(path="/tmp/output.parquet")

@env.task
async def train(data_path: flyte.File) -> flyte.File:
    # ML: model training
    ...
    return flyte.File(path="/tmp/model.pt")

@env.task
async def evaluate(model_path: flyte.File) -> dict:
    # ML: evaluation
    return {"accuracy": 0.95, "f1": 0.92}

@env.task
async def main(data: list[str]) -> dict:
    path = await preprocess(data)
    model = await train(path)
    return await evaluate(model)

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(main(["a", "b", "c"]))
    print(result)
```

### Map tasks (parallel fan-out)

```python
@env.task
async def process_image(url: str) -> flyte.File:
    return flyte.File(path=f"/tmp/{url.split('/')[-1]}.png")

@env.task
async def main(urls: list[str]) -> list:
    # Parallel execution — each URL processed in a separate container
    results = await flyte.map(process_image, urls)
    return results
```

### Traces (lightweight parallelism, no container overhead)

```python
@env.task
async def fetch_page(url: str) -> str:
    ...

@env.task
async def main(urls: list[str]) -> list:
    # Traces run in-process (no container spin-up) — use for lightweight ops
    results = await flyte.trace(fetch_page, urls)
    return results
```

### Dynamic workflows (runtime-dependent branching)

```python
@env.task
async def classify(text: str) -> str:
    ...

@env.task
async def main(texts: list[str]) -> list:
    results = []
    for text in texts:
        label = await classify(text)
        if label == "urgent":
            results.append(await flag_urgent(text))
        else:
            results.append(await archive(text))
    return results
```

### Conditions (external gates)

```python
@env.task
async def main() -> None:
    result = await flyte.condition(
        "human-approval",
        description="Wait for human approval before proceeding",
        timeout="24h",
    )
    if result.approved:
        await deploy_pipeline()
    else:
        await notify_rejected()
```

### Apps (serving)

```python
from flyte.app.extras import FastAPIAppEnvironment
from fastapi import FastAPI

app = FastAPI()
env = FastAPIAppEnvironment(
    name="model-serving",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn", "torch",
    ),
)

@app.get("/predict")
async def predict(x: float) -> dict:
    return {"result": x * 2 + 5}

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

## Project Structure Patterns

### Single-file (quick scripts)

```
pipeline.py          # all tasks + entrypoint in one file
```

### Multi-file (production)

```
src/
  tasks/
    preprocess.py     # @env.task functions
    train.py
    evaluate.py
  workflows/
    __init__.py
    training.py       # @env.task main() entrypoint
  models/
    metrics.py
flyte.config.yaml     # project config
pyproject.toml
```

### Monorepo with uv

```
pyproject.toml              # shared lockfile
src/
  pipeline/
    tasks/
    workflows/
examples/
  quickstart.py
```

See: https://www.union.ai/docs/v2/flyte/user-guide/project-patterns/monorepo-with-uv/

## Code Generation Checklist

When scaffolding a new Flyte project:

1. **Choose the right environment type**:
   - `TaskEnvironment` for tasks/workflows
   - `FastAPIAppEnvironment` for REST APIs
   - `StreamlitAppEnvironment` for dashboards
   - `vLLMAppEnvironment` for LLM serving
   - `SGLangAppEnvironment` for structured generation

2. **Select the right parallelism pattern**:
   - `flyte.map` — parallel container execution (fan-out)
   - `flyte.trace` — lightweight in-process parallelism
   - `asyncio.gather` — sequential task chaining with parallel fan-out
   - Dynamic workflows — runtime-dependent branching

3. **Add durability**:
   - `retries=N` on tasks that may fail transiently
   - `cache="auto"` for idempotent tasks (ETL, embedding, etc.)
   - `cache="disable"` for tasks that must always run

4. **Set resources appropriately**:
   - CPU/memory for standard tasks (500m-4 CPU, 1-8Gi)
   - GPU for training/inference tasks (`gpu: "1"`, `gpu_model: "nvidia-a10g"`)
   - Larger resources for data processing (8+ CPU, 16+ Gi)

5. **Add secrets if needed**:
   - API keys, database credentials
   - Use `flyte.Secret` for literal strings or file-based secrets

## Domain-Specific Patterns

### ETL / Data Processing

```python
@env.task(retries=3, cache="auto")
async def extract(source: str) -> flyte.DataFrame:
    """Extract data from a source (CSV, Parquet, database)."""
    ...

@env.task(retries=2, cache="auto")
async def transform(df: flyte.DataFrame) -> flyte.DataFrame:
    """Clean, normalize, join data."""
    return df.dropna()

@env.task(cache="auto")
async def load(df: flyte.DataFrame, destination: str) -> None:
    """Write to Parquet, database, or data lake."""
    ...
```

### Model Training

```python
@env.task
async def train(
    train_data: flyte.DataFrame,
    val_data: flyte.DataFrame,
    hyperparams: dict,
) -> flyte.File:
    """Train a model and save checkpoint."""
    ...
    return flyte.File(path="/tmp/checkpoint.pt")

@env.task
async def evaluate(
    model_path: flyte.File,
    test_data: flyte.DataFrame,
) -> dict:
    """Evaluate model and return metrics."""
    return {"accuracy": 0.95, "f1": 0.92, "auc": 0.97}
```

### Hyperparameter Optimization (manual — fan out trials)

```python
@env.task
async def train_trial(hp_config: dict) -> dict:
    """Run a single hyperparameter trial."""
    lr = hp_config["lr"]
    batch_size = hp_config["batch_size"]
    # ... train with these hyperparams ...
    return {"loss": 0.12, "accuracy": 0.94, "hp_config": hp_config}

@env.task
async def hpo(trial_configs: list[dict]) -> dict:
    """Fan out trials in parallel, return best."""
    results = await flyte.map(train_trial, trial_configs)
    best = max(results, key=lambda r: r["accuracy"])
    return best
```

### Batch Inference

```python
@env.task
async def load_model(model_path: flyte.File):
    """Load model into memory (called once per container)."""
    ...

@env.task
async def predict(model: object, batch: flyte.DataFrame) -> flyte.DataFrame:
    """Run inference on a batch of data."""
    ...

@env.task
async def batch_inference(
    model_path: flyte.File,
    data_files: list[str],
) -> list:
    """Process data files in parallel batches."""
    model = await load_model(model_path)
    # Use flyte.map for parallel batch inference
    results = await flyte.map(predict, [(model, f) for f in data_files])
    return results
```

### Data Quality Checks

```python
@env.task(cache="auto")
async def validate(df: flyte.DataFrame) -> dict:
    """Run data quality checks."""
    checks = {
        "null_counts": df.isna().sum().to_dict(),
        "column_types": {c: str(t) for c, t in df.dtypes.items()},
        "row_count": len(df),
    }
    # Fail if quality thresholds are exceeded
    if checks["row_count"] == 0:
        raise ValueError("Empty dataset after validation")
    return checks
```

## Running and Deploying

### Local execution

```bash
# Run locally (in-process, no remote)
python pipeline.py

# Run with flyte CLI (local mode)
flyte run --local pipeline.py main --data '[1,2,3]'

# Run with TUI
flyte run --tui --local pipeline.py main --data '[1,2,3]'
```

### Run remotely

```bash
# Create config for remote backend
flyte create config \
    --endpoint <host> \
    --project flytesnacks \
    --domain development \
    --builder local \
    --insecure

# Run on remote backend
flyte run pipeline.py main --data '[1,2,3]'

# Deploy task for repeated use
flyte deploy pipeline.py
```

### Devbox

```bash
# Start local dev environment (docker + k3s)
flyte start devbox

# Run on devbox
flyte run pipeline.py main --data '[1,2,3]'
```

## MCP Tool Usage Patterns

### Discovering registered tasks

```
Use flyte_mcp_list_tasks(project="flytesnacks", domain="development")
to find tasks available for re-use or inspection.
```

### Running a task remotely

```
Use flyte_mcp_run_task(project="flytesnacks", domain="development",
    name="task_name", version="auto", inputs={"x": 5})
to execute a registered task.
```

### Inspecting run results

```
Use flyte_mcp_get_run_io(name="<run_name>")
to get inputs/outputs of a run.
Use flyte_mcp_wait_for_run(name="<run_name>")
to poll until a run completes.
```

### Building images

```
Use flyte_mcp_build_image(path="./", requirements_txt="requirements.txt")
to build a container image for task deployment.
```

## Anti-Patterns to Avoid

1. **Don't use Flyte 1.x syntax** — no `@task`, no `@workflow`, no `PythonFunctionTask`. Flyte 2 uses `@env.task` and `async` functions.
2. **Don't hardcode paths** — use `flyte.File` for data that flows between tasks. Files are uploaded to the metadata bucket automatically.
3. **Don't skip type hints** — Flyte 2 requires them for serialization. Use `flyte.DataFrame` for Polars, `flyte.File` for files, `flyte.Directory` for directories.
4. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs. Write code that works on open-source Flyte v2.
5. **Don't use `asyncio.gather` for heavy workloads** — use `flyte.map` for parallel container execution. `asyncio.gather` is for light fan-out within a single task.
6. **Don't forget `flyte.init_from_config()`** — required before `flyte.serve()` for apps.
