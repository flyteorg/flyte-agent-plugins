---
name: flyte-sdk-ml
description: 'Handles ML workload patterns: model training, hyperparameter optimization, experiment tracking, model evaluation and selection, batch inference, real-time serving, and model monitoring. Use when the user wants to train models, run hyperparameter search, track experiments, evaluate models, do batch or real-time inference, or set up model monitoring. Trigger words: "train", "training", "hyperparameter", "HPO", "experiment", "tracking", "evaluation", "inference", "batch inference", "model serving", "monitoring", "GPU", "PyTorch", "TensorFlow", "scikit-learn", "HuggingFace", "model".'
---

# Flyte 2 SDK ML Skill

Build ML training, HPO, evaluation, and inference pipelines with Flyte 2.

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

## Model Training

### PyTorch Training

```python
import flyte

env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_image("pytorch/pytorch:2.1-cuda12.1-cudnn8-devel").with_pip_packages(
        "transformers", "datasets", "accelerate",
    ),
)

@env.task(
    requests=flyte.Resources(
        cpu="4", memory="16Gi", gpu="1", gpu_model="nvidia-a10g",
    ),
)
async def train(
    train_data: flyte.File,
    val_data: flyte.File,
    hyperparams: dict,
) -> flyte.File:
    """Train a model and save checkpoint."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    # Load data
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModelForSequenceClassification.from_pretrained(
        "bert-base-uncased", num_labels=2
    )

    # Train
    for epoch in range(hyperparams["epochs"]):
        # ... training loop ...
        pass

    # Save checkpoint
    output_path = "/tmp/model_checkpoint"
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)
    return flyte.File(path=output_path)

@env.task
async def main(
    train_uri: str,
    val_uri: str,
    lr: float = 0.001,
    batch_size: int = 32,
    epochs: int = 3,
) -> dict:
    hyperparams = {"lr": lr, "batch_size": batch_size, "epochs": epochs}
    checkpoint = await train(
        train_data=flyte.File(path=train_uri),
        val_data=flyte.File(path=val_uri),
        hyperparams=hyperparams,
    )
    return {"checkpoint": checkpoint, "hyperparams": hyperparams}
```

### scikit-learn Training

```python
import flyte

env = flyte.TaskEnvironment(
    name="sklearn-training",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "scikit-learn", "pandas", "polars", "joblib",
    ),
)

@env.task
async def train_sklearn(
    train_data: flyte.DataFrame,
    val_data: flyte.DataFrame,
    model_type: str = "random_forest",
) -> flyte.File:
    """Train a scikit-learn model."""
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    import joblib

    X_train = train_data.to_polars().drop("label").to_numpy()
    y_train = train_data.to_polars()["label"].to_numpy()
    X_val = val_data.to_polars().drop("label").to_numpy()
    y_val = val_data.to_polars()["label"].to_numpy()

    if model_type == "random_forest":
        model = RandomForestClassifier(n_estimators=100)
    elif model_type == "gbm":
        model = GradientBoostingClassifier(n_estimators=100)
    else:
        model = LogisticRegression()

    model.fit(X_train, y_train)
    accuracy = model.score(X_val, y_val)

    path = f"/tmp/{model_type}_model.joblib"
    joblib.dump(model, path)
    return flyte.File(path=path)
```

### HuggingFace Trainer

```python
import flyte

env = flyte.TaskEnvironment(
    name="hf-training",
    image=flyte.Image.from_image("pytorch/pytorch:2.1-cuda12.1-cudnn8-devel").with_pip_packages(
        "transformers", "datasets", "accelerate", "evaluate",
    ),
)

@env.task(
    requests=flyte.Resources(
        cpu="4", memory="16Gi", gpu="1", gpu_model="nvidia-a10g",
    ),
)
async def train_hf(
    dataset_name: str,
    model_name: str,
    hyperparams: dict,
) -> flyte.File:
    """Train with HuggingFace Trainer."""
    from datasets import load_dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    train_dataset = load_dataset(dataset_name, split="train")
    val_dataset = load_dataset(dataset_name, split="validation")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=2
    )

    def tokenize(examples):
        return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)

    train_dataset = train_dataset.map(tokenize)
    val_dataset = val_dataset.map(tokenize)

    training_args = TrainingArguments(
        output_dir="/tmp/training_output",
        learning_rate=hyperparams.get("lr", 2e-5),
        per_device_train_batch_size=hyperparams.get("batch_size", 16),
        num_train_epochs=hyperparams.get("epochs", 3),
        evaluation_strategy="epoch",
        save_strategy="epoch",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
    )

    trainer.train()
    trainer.save_model("/tmp/final_model")
    tokenizer.save_pretrained("/tmp/final_model")

    return flyte.File(path="/tmp/final_model")
```

## Hyperparameter Optimization

### Manual HPO with fan-out

```python
import flyte

env = flyte.TaskEnvironment(
    name="hpo",
    image=flyte.Image.from_image("pytorch/pytorch:2.1-cuda12.1-cudnn8-devel").with_pip_packages(
        "transformers", "datasets",
    ),
)

@env.task(
    requests=flyte.Resources(
        cpu="4", memory="16Gi", gpu="1", gpu_model="nvidia-a10g",
    ),
)
async def train_trial(hyperparams: dict) -> dict:
    """Run a single hyperparameter trial."""
    # hyperparams = {"model": "bert-base", "lr": 2e-5, "batch_size": 16, "epochs": 3}
    checkpoint = await train_hf(
        dataset_name="glue/mnli",
        model_name=hyperparams["model"],
        hyperparams=hyperparams,
    )
    # Evaluate
    metrics = await evaluate(checkpoint, "glue/mnli", split="validation")
    return {
        "hyperparams": hyperparams,
        "accuracy": metrics["accuracy"],
        "checkpoint": checkpoint,
    }

@env.task
async def hpo_search(
    param_grid: list[dict],
) -> dict:
    """Run hyperparameter search with parallel trials."""
    # Fan out all trials in parallel
    results = await flyte.map(train_trial, param_grid)
    best = max(results, key=lambda r: r["accuracy"])
    return best

@env.task
async def main() -> dict:
    param_grid = [
        {"model": "bert-base", "lr": 1e-5, "batch_size": 16, "epochs": 3},
        {"model": "bert-base", "lr": 2e-5, "batch_size": 16, "epochs": 3},
        {"model": "bert-base", "lr": 5e-5, "batch_size": 16, "epochs": 3},
        {"model": "bert-base", "lr": 2e-5, "batch_size": 32, "epochs": 3},
    ]
    return await hpo_search(param_grid)
```

### Grid search pattern

```python
from itertools import product

@env.task
async def grid_search() -> dict:
    """Grid search over hyperparameter combinations."""
    lr_values = [1e-5, 2e-5, 5e-5]
    batch_sizes = [16, 32]
    epochs = [2, 3]

    param_grid = [
        {"model": "bert-base", "lr": lr, "batch_size": bs, "epochs": ep}
        for lr, bs, ep in product(lr_values, batch_sizes, epochs)
    ]

    results = await flyte.map(train_trial, param_grid)
    best = max(results, key=lambda r: r["accuracy"])
    return best
```

## Experiment Tracking

### Manual experiment tracking

```python
import json
import datetime
import flyte

@env.task
async def track_experiment(
    experiment_name: str,
    hyperparams: dict,
    metrics: dict,
    checkpoint: flyte.File,
) -> flyte.File:
    """Track experiment results as a JSON file in remote storage."""
    record = {
        "experiment": experiment_name,
        "timestamp": datetime.datetime.now().isoformat(),
        "hyperparameters": hyperparams,
        "metrics": metrics,
        "checkpoint_uri": checkpoint.path,
    }
    path = f"/tmp/experiments/{experiment_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return flyte.File(path=path)

@env.task
async def compare_experiments(
    experiment_names: list[str],
) -> dict:
    """Compare multiple experiments."""
    reports = []
    for name in experiment_names:
        report = await load_experiment(name)
        reports.append(report)

    # Find best by metric
    best = max(reports, key=lambda r: r["metrics"].get("accuracy", 0))
    return {"best_experiment": best, "all": reports}
```

### Inference result tracking

```python
@env.task
async def track_inference(
    model_uri: str,
    test_data: flyte.File,
    metrics: dict,
) -> flyte.File:
    """Track inference results."""
    record = {
        "model_uri": model_uri,
        "test_data": test_data.path,
        "metrics": metrics,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    path = f"/tmp/inference/{model_uri.split('/')[-1]}_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return flyte.File(path=path)
```

## Model Evaluation and Selection

### Evaluation pipeline

```python
import flyte

env = flyte.TaskEnvironment(
    name="evaluation",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "scikit-learn", "scipy", "pandas", "matplotlib", "seaborn",
    ),
)

@env.task
async def evaluate_model(
    model_path: flyte.File,
    test_data: flyte.DataFrame,
) -> dict:
    """Evaluate a model and return metrics."""
    import joblib
    from sklearn.metrics import (
        accuracy_score, f1_score, precision_score, recall_score,
        roc_auc_score, confusion_matrix, classification_report,
    )

    model = joblib.load(model_path.path)
    X_test = test_data.to_polars().drop("label").to_numpy()
    y_test = test_data.to_polars()["label"].to_numpy()

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else y_pred

    return {
        "accuracy": accuracy_score(y_test, y_pred),
        "f1": f1_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "auc": roc_auc_score(y_test, y_prob),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "report": classification_report(y_test, y_pred, output_dict=True),
    }

@env.task
async def select_best_model(
    candidate_models: list[flyte.File],
    test_data: flyte.DataFrame,
) -> dict:
    """Evaluate all candidates and select the best."""
    evaluations = await flyte.map(
        lambda m: evaluate_model(m, test_data),
        candidate_models,
    )
    best = max(evaluations, key=lambda e: e["accuracy"])
    return {"best_metrics": best, "all_evaluations": evaluations}
```

### Model comparison report

```python
@env.task
async def generate_comparison_report(
    evaluations: list[dict],
    model_names: list[str],
) -> flyte.File:
    """Generate a model comparison report."""
    import matplotlib.pyplot as plt
    import pandas as pd

    df = pd.DataFrame({
        "model": model_names,
        "accuracy": [e["accuracy"] for e in evaluations],
        "f1": [e["f1"] for e in evaluations],
        "precision": [e["precision"] for e in evaluations],
        "recall": [e["recall"] for e in evaluations],
        "auc": [e["auc"] for e in evaluations],
    })

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    metrics = ["accuracy", "f1", "precision", "recall", "auc"]
    for i, metric in enumerate(metrics[:3]):
        axes[i].bar(df["model"], df[metric])
        axes[i].set_title(metric)
        axes[i].tick_params(axis="x", rotation=45)

    path = "/tmp/model_comparison.png"
    fig.savefig(path, bbox_inches="tight")
    return flyte.File(path=path)
```

## Batch Inference

### Large-scale batch inference

```python
import flyte

env = flyte.TaskEnvironment(
    name="batch-inference",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "torch", "transformers", "pandas", "polars", "boto3",
    ),
)

@env.task(
    requests=flyte.Resources(
        cpu="4", memory="16Gi", gpu="1", gpu_model="nvidia-a10g",
    ),
)
async def load_model(model_uri: str) -> object:
    """Load model into memory."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_uri)
    model = AutoModelForSequenceClassification.from_pretrained(model_uri)
    model.eval()
    return {"model": model, "tokenizer": tokenizer}

@env.task(
    requests=flyte.Resources(
        cpu="2", memory="8Gi", gpu="1", gpu_model="nvidia-a10g",
    ),
)
async def batch_predict(
    model_ctx: object,
    data_file: flyte.File,
    batch_size: int = 32,
) -> flyte.File:
    """Run inference on a batch of data."""
    import torch
    import polars as pl

    model = model_ctx["model"]
    tokenizer = model_ctx["tokenizer"]

    df = pl.read_parquet(data_file.path)
    texts = df["text"].to_list()

    all_preds = []
    all_probs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        inputs = tokenizer(batch, padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)
        preds = torch.argmax(probs, dim=1)
        all_preds.extend(preds.tolist())
        all_probs.extend(probs.tolist())

    results = pl.DataFrame({"prediction": all_preds, "probability": all_probs})
    path = f"/tmp/predictions_{data_file.path.split('/')[-1]}"
    results.write_parquet(path)
    return flyte.File(path=path)

@env.task
async def batch_inference(
    model_uri: str,
    data_files: list[str],
) -> list:
    """Run batch inference on multiple data files."""
    model_ctx = await load_model(model_uri)
    # Fan out inference across files
    results = await flyte.map(
        lambda f: batch_predict(model_ctx, flyte.File(path=f)),
        data_files,
    )
    return results
```

### GPU batch inference optimization

```python
@env.task
async def optimized_batch_inference(
    model_uri: str,
    data_files: list[str],
) -> list:
    """Optimized batch inference with dynamic batching."""
    # Use dynamic batcher for better GPU utilization
    # Combine small batches and shard large ones
    ...
```

## Real-time Model Serving

### FastAPI model serving (covered in flyte-sdk-app)

```python
from fastapi import FastAPI
import flyte
from flyte.app.extras import FastAPIAppEnvironment

app = FastAPI()
model = None

@app.on_event("startup")
async def load_model():
    global model
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    model = AutoModelForSequenceClassification.from_pretrained("model-checkpoint")
    model.tokenizer = AutoTokenizer.from_pretrained("model-checkpoint")

@app.get("/predict")
async def predict(text: str) -> dict:
    inputs = model.tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    probs = torch.softmax(outputs.logits, dim=1)
    return {
        "prediction": int(torch.argmax(probs, dim=1)[0]),
        "confidence": float(probs.max().item()),
    }

env = FastAPIAppEnvironment(
    name="model-serving",
    app=app,
    image=flyte.Image.from_image("pytorch/pytorch:2.1-cuda12.1-cudnn8-devel").with_pip_packages(
        "fastapi", "uvicorn", "torch", "transformers",
    ),
    resources=flyte.Resources(cpu="4", memory="16Gi", gpu="1", gpu_model="nvidia-a10g"),
)
```

## Model Monitoring

### Drift detection

```python
@env.task(cache="auto")
async def detect_drift(
    baseline_data: flyte.DataFrame,
    current_data: flyte.DataFrame,
) -> dict:
    """Detect data drift between baseline and current distributions."""
    import scipy.stats as stats

    drift_results = {}
    baseline_df = baseline_data.to_polars()
    current_df = current_data.to_polars()

    for col in baseline_df.columns:
        if baseline_df[col].dtype.is_float64():
            # Kolmogorov-Smirnov test
            stat, p_value = stats.ks_2samp(
                baseline_df[col].to_list(),
                current_df[col].to_list(),
            )
            drift_results[col] = {
                "statistic": stat,
                "p_value": p_value,
                "drift_detected": p_value < 0.05,
            }

    return drift_results

@env.task
async def monitor_model(
    model_uri: str,
    baseline_data: flyte.DataFrame,
    current_data: flyte.DataFrame,
    predictions: flyte.DataFrame,
) -> dict:
    """Monitor model health: drift, performance, prediction distribution."""
    drift = await detect_drift(baseline_data, current_data)

    # Prediction distribution analysis
    pred_dist = predictions.to_polars()["prediction"].value_counts().to_dict()

    # Confidence distribution
    conf_stats = {
        "mean": float(predictions.to_polars()["probability"].mean()),
        "std": float(predictions.to_polars()["probability"].std()),
        "min": float(predictions.to_polars()["probability"].min()),
        "max": float(predictions.to_polars()["probability"].max()),
    }

    return {
        "drift": drift,
        "prediction_distribution": pred_dist,
        "confidence_stats": conf_stats,
        "alert": any(d["drift_detected"] for d in drift.values()),
    }
```

### Prediction quality monitoring

```python
@env.task
async def monitor_prediction_quality(
    predictions: flyte.DataFrame,
    ground_truth: flyte.DataFrame,
) -> dict:
    """Monitor prediction quality over time."""
    merged = predictions.to_polars().join(ground_truth.to_polars(), on="id")
    accuracy = (merged["prediction"] == merged["label"]).mean()

    # Per-class performance
    per_class = {}
    for label in merged["label"].unique():
        mask = merged["label"] == label
        per_class[int(label)] = {
            "count": int(mask.sum()),
            "accuracy": int(merged[mask]["prediction"] == merged[mask]["label"]).mean(),
        }

    return {"accuracy": float(accuracy), "per_class": per_class}
```

## ML Resource Recommendations

| ML Workload | CPU | Memory | GPU |
|---|---|---|---|
| scikit-learn (small data) | 2-4 | 4-8 Gi | none |
| scikit-learn (large data) | 4-8 | 16-32 Gi | none |
| PyTorch training (small model) | 4 | 16 Gi | 1x A10G |
| PyTorch training (large model) | 8 | 32+ Gi | 4-8x A100 |
| HuggingFace fine-tuning | 4-8 | 16-32 Gi | 1-4x A10G/A100 |
| Batch inference (CPU) | 4-8 | 16-32 Gi | none |
| Batch inference (GPU) | 4 | 16 Gi | 1-4x A10G/A100 |
| LLM serving | 8-16 | 32-64 Gi | 1-8x A100/H100 |

## ML Anti-Patterns

1. **Don't train without experiment tracking** — always log hyperparams, metrics, and model artifacts.
2. **Don't skip evaluation** — always evaluate on held-out test data with multiple metrics.
3. **Don't over-provision GPUs** — start with 1x A10G for most fine-tuning, scale only when needed.
4. **Don't do batch inference one-by-one** — use `flyte.map` for parallel file-level inference.
5. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
6. **Don't forget to set `cache="auto"`** on evaluation tasks — same model + same data = same result.
