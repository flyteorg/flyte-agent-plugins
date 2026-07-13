---
name: flyte-sdk-eval
description: 'Builds minimal evaluation harnesses (unit tests + small-run workflows) and suggests ways to validate correctness and performance early. Use when the user wants to test Flyte tasks, validate pipeline outputs, set up evaluation pipelines, or write unit tests for ML/data workflows. Trigger words: "test", "evaluate", "validation", "unit test", "verify", "assert", "data quality", "metrics", "benchmark".'
---

# Flyte 2 SDK Eval Skill

Build evaluation harnesses, unit tests, and validation pipelines for Flyte 2 workflows.

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

## Testing Patterns

### Direct Task Invocation (unit testing)

Test task logic directly without remote execution:

```python
import pytest
from pipeline import preprocess, train, evaluate

def test_preprocess():
    """Test preprocessing logic in isolation."""
    result = preprocess(["a", "b", "c"])
    assert result is not None
    assert len(result) == 3

def test_train():
    """Test training with a small dataset."""
    import flyte
    data = flyte.DataFrame(polars.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}))
    model = train(data)
    assert model is not None

def test_evaluate():
    """Test evaluation metrics."""
    import flyte
    model = flyte.File(path="/tmp/mock_model.pt")
    metrics = evaluate(model)
    assert "accuracy" in metrics
    assert 0 <= metrics["accuracy"] <= 1
```

### Using flyte.run() for Integration Testing

Test the full workflow execution locally:

```python
import pytest
import flyte
from pipeline import main

def test_full_pipeline():
    """Run the full pipeline locally with test data."""
    result = flyte.run(main, inputs={"data": ["test1", "test2"]})
    assert result is not None
    assert "accuracy" in result.outputs

def test_full_pipeline_with_inputs():
    """Test with specific inputs via flyte.run()."""
    result = flyte.run(
        main,
        inputs={"data": ["a", "b", "c"]},
    )
    assert result.status == "SUCCEEDED"
```

### Testing Async Tasks

```python
import asyncio
import pytest

def test_async_task():
    """Test async task by running in event loop."""
    result = asyncio.run(preprocess(["a", "b"]))
    assert result is not None

@pytest.mark.asyncio
async def test_async_task_mark():
    """Test async task with pytest-asyncio."""
    result = await preprocess(["a", "b"])
    assert len(result) == 2
```

## Evaluation Pipeline Patterns

### ML Model Evaluation

```python
import flyte

env = flyte.TaskEnvironment(
    name="eval",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "scikit-learn", "scipy", "pandas", "matplotlib",
    ),
)

@env.task
async def load_test_data() -> flyte.DataFrame:
    """Load ground truth test data."""
    ...
    return flyte.DataFrame(df)

@env.task
async def load_model(model_uri: str) -> object:
    """Load a trained model."""
    ...

@env.task
async def predict(model: object, data: flyte.DataFrame) -> flyte.DataFrame:
    """Run model predictions on test data."""
    ...

@env.task
async def compute_metrics(
    predictions: flyte.DataFrame,
    ground_truth: flyte.DataFrame,
) -> dict:
    """Compute evaluation metrics."""
    from sklearn.metrics import (
        accuracy_score, f1_score, precision_score, recall_score,
        roc_auc_score, mean_squared_error,
    )
    y_true = ground_truth.to_polars()["label"].to_list()
    y_pred = predictions.to_polars()["prediction"].to_list()
    y_prob = predictions.to_polars()["probability"].to_list()

    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred),
        "recall": recall_score(y_true, y_pred),
        "auc": roc_auc_score(y_true, y_prob),
    }

@env.task
async def generate_report(metrics: dict) -> flyte.File:
    """Generate an evaluation report."""
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    # Confusion matrix, ROC curve, etc.
    path = "/tmp/eval_report.png"
    fig.savefig(path)
    return flyte.File(path=path)

@env.task
async def evaluate_pipeline(
    model_uri: str,
    test_data_uri: str,
) -> dict:
    """Full evaluation pipeline."""
    data = await load_test_data()
    model = await load_model(model_uri)
    preds = await predict(model, data)
    metrics = await compute_metrics(preds, data)
    report = await generate_report(metrics)
    return {"metrics": metrics, "report": report}
```

### A/B Model Comparison

```python
@env.task
async def compare_models(
    model_a_uri: str,
    model_b_uri: str,
    test_data: flyte.DataFrame,
) -> dict:
    """Compare two models on the same test data."""
    model_a = await load_model(model_a_uri)
    model_b = await load_model(model_b_uri)
    preds_a = await predict(model_a, test_data)
    preds_b = await predict(model_b, test_data)
    metrics_a = await compute_metrics(preds_a, test_data)
    metrics_b = await compute_metrics(preds_b, test_data)

    winner = "A" if metrics_a["accuracy"] > metrics_b["accuracy"] else "B"
    return {
        "model_a_metrics": metrics_a,
        "model_b_metrics": metrics_b,
        "winner": winner,
        "improvement": metrics_a["accuracy"] - metrics_b["accuracy"],
    }
```

### Data Quality Validation

```python
@env.task
async def validate_data(df: flyte.DataFrame) -> dict:
    """Run data quality checks."""
    inner = df.to_polars()
    checks = {}

    # Row count check
    row_count = len(inner)
    checks["row_count"] = row_count
    if row_count == 0:
        raise ValueError("Dataset is empty")

    # Null check
    null_counts = inner.null_count().to_dict()
    checks["null_counts"] = null_counts
    for col, count in null_counts.items():
        if count > 0 and count / row_count > 0.5:
            raise ValueError(f"Column {col} has >50% nulls")

    # Type check
    checks["dtypes"] = {str(k): str(v) for k, v in inner.schema.items()}

    # Value range check
    for col in inner.columns:
        if inner[col].dtype.is_float64():
            min_val = inner[col].min()
            max_val = inner[col].max()
            if min_val < 0 or max_val > 1:
                checks[f"range_{col}"] = {"min": min_val, "max": max_val}

    return {"passed": True, "checks": checks}

@env.task
async def data_quality_gate(
    data: flyte.DataFrame,
    threshold: float = 0.9,
) -> bool:
    """Pass/fail gate based on data quality score."""
    result = await validate_data(data)
    score = result["checks"].get("quality_score", 1.0)
    if score < threshold:
        raise ValueError(f"Data quality gate failed: {score} < {threshold}")
    return True
```

### Pipeline Output Validation

```python
@env.task
async def validate_output(
    model_path: flyte.File,
    metrics: dict,
    min_accuracy: float = 0.8,
) -> dict:
    """Validate that pipeline outputs meet quality thresholds."""
    validation = {
        "model_exists": model_path is not None,
        "metrics_valid": all(v >= 0 and v <= 1 for v in metrics.values()),
        "accuracy_threshold": metrics.get("accuracy", 0) >= min_accuracy,
    }

    if not validation["accuracy_threshold"]:
        raise ValueError(
            f"Model accuracy {metrics['accuracy']} below threshold {min_accuracy}"
        )

    return validation
```

## Experiment Tracking

### Manual Experiment Tracking

```python
import json
import datetime
import flyte

@env.task
async def track_experiment(
    experiment_name: str,
    hyperparams: dict,
    metrics: dict,
) -> flyte.File:
    """Track experiment results as a JSON file."""
    record = {
        "experiment": experiment_name,
        "timestamp": datetime.datetime.now().isoformat(),
        "hyperparameters": hyperparams,
        "metrics": metrics,
    }
    path = f"/tmp/experiments/{experiment_name}.json"
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return flyte.File(path=path)

@env.task
async def run_experiment(
    config: dict,
    data: flyte.DataFrame,
) -> dict:
    """Run a single experiment and track results."""
    model = await train(data, config)
    metrics = await evaluate(model, data)
    await track_experiment(config["name"], config, metrics)
    return metrics
```

### Hyperparameter Search with Tracking

```python
@env.task
async def hpo_search(
    param_grid: list[dict],
    data: flyte.DataFrame,
) -> dict:
    """Run hyperparameter search with experiment tracking."""
    results = await flyte.map(
        lambda cfg: run_experiment(cfg, data),
        param_grid,
    )
    best = max(results, key=lambda r: r["accuracy"])
    return best
```

## Performance Benchmarking

### Task-level Benchmarking

```python
import time
import flyte

@env.task
async def benchmark_task(
    task_fn,
    inputs: dict,
    num_runs: int = 5,
) -> dict:
    """Benchmark a task's performance."""
    durations = []
    for _ in range(num_runs):
        start = time.time()
        await task_fn(**inputs)
        durations.append(time.time() - start)

    return {
        "mean_ms": sum(durations) / len(durations) * 1000,
        "min_ms": min(durations) * 1000,
        "max_ms": max(durations) * 1000,
        "p95_ms": sorted(durations)[int(len(durations) * 0.95)] * 1000,
    }
```

### Throughput Testing

```python
@env.task
async def throughput_test(
    batch_sizes: list[int],
) -> dict:
    """Test throughput at different batch sizes."""
    results = {}
    for size in batch_sizes:
        data = create_batch(size)
        start = time.time()
        await process_batch(data)
        elapsed = time.time() - start
        results[size] = {
            "throughput": size / elapsed if elapsed > 0 else 0,
            "latency_ms": elapsed * 1000 / size,
        }
    return results
```

## Testing with Flyte MCP

### Inspecting past run outputs

```
Use flyte_mcp_get_run_io(name="<run_name>")
to check the inputs and outputs of a past run for validation.
```

### Listing runs for comparison

```
Use flyte_mcp_list_runs(task_name="<task_name>", limit=10)
to find recent runs for comparison.
```

### Watching a run complete

```
Use flyte_mcp_wait_for_run(name="<run_name>")
to block until a run finishes, then check its status.
```

## pytest Configuration

```ini
# pytest.ini
[pytest]
testpaths = tests
asyncio_mode = auto
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
]
```

## Test Structure

```
tests/
  __init__.py
  test_preprocess.py     # unit tests for preprocessing
  test_train.py           # unit tests for training
  test_evaluate.py        # unit tests for evaluation
  test_integration.py     # integration tests (flyte.run)
  test_data_quality.py    # data quality validation
  conftest.py             # shared fixtures
```

## Anti-Patterns

1. **Don't test against remote runs in unit tests** — use direct function invocation for unit tests. Reserve `flyte.run()` for integration tests.
2. **Don't hardcode test data paths** — use `flyte.File(path="/tmp/test_data")` with temp directories.
3. **Don't skip data quality gates** — always validate data before and after transformations.
4. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
5. **Don't test ML models with random data** — use representative test datasets that match production distribution.
