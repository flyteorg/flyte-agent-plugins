---
name: flyte-migrate-ml
description: Migrates Flyte 1 machine learning code to Flyte 2 and unlocks net-new v2 patterns. Use when migrating Flyte 1 ML workloads (training, HPO, GPU/deep learning, batch inference) to Flyte 2, specifying GPU resources, or building the end-to-end pipeline pattern. Trigger words - migrate training, HPO, GPU, deep learning, batch inference, model serving, pytorch.
---

# Flyte 1 to Flyte 2 ML Migration Skill

Migrate existing Flyte 1 ML workloads — small-model training, hyperparameter optimization, deep learning on GPUs, and batch inference — to Flyte 2, then take advantage of patterns that were not possible in Flyte 1 (real-time serving, apps, sandboxed execution).

This skill is specifically about **migrating existing v1 ML code**. For greenfield authoring in Flyte 2, use the companion skills:

- `flyte-sdk-ml` — writing new ML training / inference tasks in Flyte 2.
- `flyte-sdk-app` — writing new apps and serving endpoints.
- `flyte-sdk-agent` — writing new agents and sandboxed / code-mode workloads.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide (ML workloads) | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/ml-workloads/ |
| Migration guide (New in Flyte 2) | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/new-in-flyte-2/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## Migration Cheat Sheet

| Flyte 1 | Flyte 2 |
|---|---|
| `ImageSpec(name=..., packages=[...])` | `flyte.Image.from_debian_base().with_pip_packages(...)` |
| `@task(container_image=..., requests=..., cache=...)` | Set `image`, `resources`, `cache` once on `flyte.TaskEnvironment`, then `@env.task` |
| `Resources(cpu=..., mem=...)` | `flyte.Resources(cpu=..., memory=...)` (note `mem` becomes `memory`) |
| `Resources(gpu="1")` + `accelerator=T4` | `flyte.Resources(gpu="T4:1")` |
| `FlyteFile` / `FlyteFile(path=...)` | `flyte.io.File` / `await File.from_local(...)` |
| `model_file.download()` | `await model_file.download()` |
| `current_context().working_directory` | `os.getcwd()` |
| `@workflow` | An orchestrating `@env.task` (plain `async` Python) |
| `map_task(fn)(x=xs)` | `await asyncio.gather(*[fn(x) for x in xs])` |
| A "pick the best" task | Plain Python after `gather` |

## Small model training (scikit-learn / XGBoost)

Train a model, persist it as a `File`, and evaluate it. Image, resources, and caching move to the `TaskEnvironment`; `FlyteFile` becomes `flyte.io.File`.

### Flyte 1

```python
import os

import joblib
from flytekit import task, workflow, ImageSpec, Resources, current_context
from flytekit.types.file import FlyteFile
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

image = ImageSpec(
    name="xgb-image",
    packages=["xgboost", "scikit-learn", "joblib"],
)

@task(container_image=image, requests=Resources(cpu="2", mem="4Gi"))
def train_model(n_estimators: int, max_depth: int) -> FlyteFile:
    data = load_breast_cancer()
    X_train, _, y_train, _ = train_test_split(data.data, data.target, random_state=42)
    model = XGBClassifier(n_estimators=n_estimators, max_depth=max_depth)
    model.fit(X_train, y_train)

    model_path = os.path.join(current_context().working_directory, "model.json")
    joblib.dump(model, model_path)
    return FlyteFile(path=model_path)

@task(container_image=image)
def evaluate(model_file: FlyteFile) -> float:
    model = joblib.load(model_file.download())
    data = load_breast_cancer()
    _, X_test, _, y_test = train_test_split(data.data, data.target, random_state=42)
    return float(model.score(X_test, y_test))

@workflow
def main(n_estimators: int, max_depth: int) -> float:
    model = train_model(n_estimators=n_estimators, max_depth=max_depth)
    return evaluate(model_file=model)
```

### Flyte 2

```python
import os

import joblib
import flyte
from flyte.io import File
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

env = flyte.TaskEnvironment(
    name="train_xgboost",
    image=flyte.Image.from_debian_base().with_pip_packages(
        "xgboost", "scikit-learn", "joblib"
    ),
    resources=flyte.Resources(cpu="2", memory="4Gi"),
)

@env.task
async def train_model(n_estimators: int, max_depth: int) -> File:
    data = load_breast_cancer()
    X_train, _, y_train, _ = train_test_split(data.data, data.target, random_state=42)
    model = XGBClassifier(n_estimators=n_estimators, max_depth=max_depth)
    model.fit(X_train, y_train)

    model_path = os.path.join(os.getcwd(), "model.json")
    joblib.dump(model, model_path)
    return await File.from_local(model_path)

@env.task
async def evaluate(model_file: File) -> float:
    local_path = await model_file.download()
    model = joblib.load(local_path)
    data = load_breast_cancer()
    _, X_test, _, y_test = train_test_split(data.data, data.target, random_state=42)
    return float(model.score(X_test, y_test))

@env.task
async def main(n_estimators: int, max_depth: int) -> float:
    model = await train_model(n_estimators, max_depth)
    return await evaluate(model)
```

## Hyperparameter optimization

Fan out one training run per hyperparameter, then pick the best. In Flyte 1 the grid search runs through `map_task` and the "pick the best" step must itself be a task. In Flyte 2 you `gather` the runs and select the winner in plain Python.

### Flyte 1

```python
from flytekit import task, workflow, map_task
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

@task
def get_grid() -> list[int]:
    return [2, 4, 8, 16]

@task
def train_eval(max_depth: int) -> float:
    data = load_iris()
    model = RandomForestClassifier(max_depth=max_depth, random_state=42)
    scores = cross_val_score(model, data.data, data.target, cv=3)
    return float(scores.mean())

@task
def best_score(scores: list[float]) -> float:
    return max(scores)

@workflow
def main() -> float:
    grid = get_grid()
    # Fan out one training run per hyperparameter value.
    scores = map_task(train_eval)(max_depth=grid)
    return best_score(scores=scores)
```

### Flyte 2

```python
import asyncio

import flyte
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

env = flyte.TaskEnvironment(
    name="hpo",
    image=flyte.Image.from_debian_base().with_pip_packages("scikit-learn"),
)

@env.task
async def train_eval(max_depth: int) -> float:
    data = load_iris()
    model = RandomForestClassifier(max_depth=max_depth, random_state=42)
    scores = cross_val_score(model, data.data, data.target, cv=3)
    return float(scores.mean())

@env.task
async def main() -> dict:
    grid = [2, 4, 8, 16]
    # Fan out one training run per hyperparameter value...
    scores = await asyncio.gather(*[train_eval(d) for d in grid])
    # ...then pick the best in plain Python (impossible in a Flyte 1 workflow).
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    return {"best_max_depth": grid[best_idx], "best_score": scores[best_idx]}
```

## Large model training (deep learning)

GPU configuration moves to the `TaskEnvironment`: the Flyte 1 `Resources(gpu="1")` plus a separate `accelerator=T4` become a single `gpu="T4:1"` string on `flyte.Resources`.

### Flyte 1

```python
from flytekit import task, workflow, ImageSpec, Resources
from flytekit.extras.accelerators import T4
import torch
import torch.nn as nn

image = ImageSpec(
    name="dl-image",
    packages=["torch"],
)

@task(
    container_image=image,
    requests=Resources(cpu="4", mem="16Gi", gpu="1"),
    accelerator=T4,
)
def train(epochs: int) -> float:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = nn.Linear(10, 1).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()

    X = torch.randn(128, 10, device=device)
    y = torch.randn(128, 1, device=device)

    loss = torch.tensor(0.0)
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(X), y)
        loss.backward()
        optimizer.step()
    return float(loss.item())

@workflow
def main(epochs: int) -> float:
    return train(epochs=epochs)
```

### Flyte 2

```python
import flyte
import torch
import torch.nn as nn

# GPU type and count go in a single "T4:1"-style string. For multi-node
# distributed training, wrap the training task with the torch elastic plugin.
env = flyte.TaskEnvironment(
    name="train_deep_learning",
    image=flyte.Image.from_debian_base().with_pip_packages("torch"),
    resources=flyte.Resources(cpu="4", memory="16Gi", gpu="T4:1"),
)

@env.task
async def train(epochs: int) -> float:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = nn.Linear(10, 1).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()

    X = torch.randn(128, 10, device=device)
    y = torch.randn(128, 1, device=device)

    loss = torch.tensor(0.0)
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(X), y)
        loss.backward()
        optimizer.step()
    return float(loss.item())

@env.task
async def main(epochs: int) -> float:
    return await train(epochs)
```

For multi-node distributed training (PyTorch elastic, etc.), wrap the training task with the torch elastic plugin. See the Resources docs and plugin integrations at https://www.union.ai/docs/v2/flyte/user-guide/task-configuration/resources.

## Batch inference

Load a trained model once and score many batches in parallel. `map_task` with a `partial`-bound model becomes `asyncio.gather` over the batches, reusing the same model reference.

### Flyte 1

```python
import os
from functools import partial

import joblib
from flytekit import task, workflow, map_task, ImageSpec, current_context
from flytekit.types.file import FlyteFile
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

image = ImageSpec(name="inference-image", packages=["scikit-learn", "joblib"])

@task(container_image=image)
def train_model() -> FlyteFile:
    data = load_iris()
    model = RandomForestClassifier().fit(data.data, data.target)
    model_path = os.path.join(current_context().working_directory, "model.joblib")
    joblib.dump(model, model_path)
    return FlyteFile(path=model_path)

@task(container_image=image)
def get_batches() -> list[list[list[float]]]:
    data = load_iris()
    rows = data.data.tolist()
    # Split the rows into batches of 30.
    return [rows[i : i + 30] for i in range(0, len(rows), 30)]

@task(container_image=image)
def score_batch(model_file: FlyteFile, batch: list[list[float]]) -> list[int]:
    model = joblib.load(model_file.download())
    return [int(p) for p in model.predict(batch)]

@workflow
def main() -> list[list[int]]:
    model = train_model()
    batches = get_batches()
    return map_task(partial(score_batch, model_file=model))(batch=batches)
```

### Flyte 2

```python
import asyncio
import os

import joblib
import flyte
from flyte.io import File
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

env = flyte.TaskEnvironment(
    name="batch_inference",
    image=flyte.Image.from_debian_base().with_pip_packages("scikit-learn", "joblib"),
)

@env.task
async def train_model() -> File:
    data = load_iris()
    model = RandomForestClassifier().fit(data.data, data.target)
    model_path = os.path.join(os.getcwd(), "model.joblib")
    joblib.dump(model, model_path)
    return await File.from_local(model_path)

@env.task
async def score_batch(model_file: File, batch: list[list[float]]) -> list[int]:
    local_path = await model_file.download()
    model = joblib.load(local_path)
    return [int(p) for p in model.predict(batch)]

@env.task
async def main() -> list[list[int]]:
    model = await train_model()
    rows = load_iris().data.tolist()
    batches = [rows[i : i + 30] for i in range(0, len(rows), 30)]
    # Score every batch in parallel, reusing the same model reference.
    coros = [score_batch(model, batch) for batch in batches]
    return list(await asyncio.gather(*coros))
```

## A complete example: end-to-end ML pipeline

Putting it together — a load / train / evaluate pipeline shows the image, resources, caching, file I/O, and orchestration changes in one place. Image, resources, and cache are set **once** on the `TaskEnvironment`, and the "workflow" is just an orchestrating task.

### Flyte 1

```python
import os

import joblib
import pandas as pd
from flytekit import task, workflow, ImageSpec, Resources, current_context
from flytekit.types.file import FlyteFile
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

image = ImageSpec(
    name="ml-image",
    packages=["pandas", "scikit-learn", "joblib"],
)

@task(
    container_image=image,
    requests=Resources(cpu="2", mem="4Gi"),
    cache=True,
    cache_version="1.0",
)
def load_data() -> pd.DataFrame:
    data = load_iris(as_frame=True)
    df = data.frame
    df["species"] = data.target
    return df

@task(container_image=image)
def train_model(data: pd.DataFrame) -> FlyteFile:
    model = RandomForestClassifier()
    X = data.drop("species", axis=1)
    y = data["species"]
    model.fit(X, y)

    model_path = os.path.join(current_context().working_directory, "model.joblib")
    joblib.dump(model, model_path)
    return FlyteFile(path=model_path)

@task(container_image=image)
def evaluate(model_file: FlyteFile, data: pd.DataFrame) -> float:
    model = joblib.load(model_file.download())
    X = data.drop("species", axis=1)
    y = data["species"]
    return float(model.score(X, y))

@workflow
def main() -> float:
    data = load_data()
    model = train_model(data=data)
    return evaluate(model_file=model, data=data)
```

### Flyte 2

```python
import os

import joblib
import pandas as pd
import flyte
from flyte.io import File
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

# Image, resources, and cache are set once on the TaskEnvironment.
env = flyte.TaskEnvironment(
    name="ml_pipeline",
    image=flyte.Image.from_debian_base().with_pip_packages(
        "pandas", "scikit-learn", "joblib"
    ),
    resources=flyte.Resources(cpu="2", memory="4Gi"),
    cache="auto",
)

@env.task
async def load_data() -> pd.DataFrame:
    data = load_iris(as_frame=True)
    df = data.frame
    df["species"] = data.target
    return df

@env.task
async def train_model(data: pd.DataFrame) -> File:
    model = RandomForestClassifier()
    X = data.drop("species", axis=1)
    y = data["species"]
    model.fit(X, y)

    model_path = os.path.join(os.getcwd(), "model.joblib")
    joblib.dump(model, model_path)
    return await File.from_local(model_path)

@env.task
async def evaluate(model_file: File, data: pd.DataFrame) -> float:
    local_path = await model_file.download()
    model = joblib.load(local_path)
    X = data.drop("species", axis=1)
    y = data["species"]
    return float(model.score(X, y))

# The "workflow" is just an orchestrating task.
@env.task
async def main() -> float:
    data = await load_data()
    model = await train_model(data)
    return await evaluate(model, data)
```

## New in Flyte 2

Flyte 1 was a batch orchestration system: everything ran as a finite DAG that started, did work, and finished. Flyte 2 keeps all of that and adds long-running services, high-throughput batch inference, and sandboxed code execution — so the same project that trains your model can also serve it, host a dashboard, saturate a GPU, or safely run LLM-generated code. There is no v1 counterpart to migrate here; these are net-new capabilities that your migrated training code unlocks. For greenfield authoring of these, see the `flyte-sdk-app` and `flyte-sdk-agent` skills.

### Real-time inference and model serving

Instead of scoring a batch and exiting, you can stand up an always-on REST endpoint from a `FastAPIAppEnvironment` and deploy it with `flyte.deploy`. The app can load a model artifact produced by one of your migrated training tasks.

```python
app = FastAPI(title="ML Model API")

# Define request/response models
class PredictionRequest(BaseModel):
    feature1: float
    feature2: float
    feature3: float

class PredictionResponse(BaseModel):
    prediction: float
    probability: float

# Load model (you would typically load this from storage)
model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    model_path = os.getenv("MODEL_PATH", "/app/models/model.joblib")
    # In production, load from your storage
    if os.path.exists(model_path):
        with open(model_path, "rb") as f:
            model = joblib.load(f)
    yield

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    # Make prediction
    # prediction = model.predict([[request.feature1, request.feature2, request.feature3]])

    # Dummy prediction for demo
    prediction = 0.85
    probability = 0.92

    return PredictionResponse(
        prediction=prediction,
        probability=probability,
    )

env = FastAPIAppEnvironment(
    name="ml-model-api",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi",
        "uvicorn",
        "scikit-learn",
        "pydantic",
        "joblib",
    ),
    parameters=[
        flyte.app.Parameter(
            name="model_file",
            value=flyte.io.File.from_existing_remote("s3://bucket/models/model.joblib"),
            mount="/app/models",
            env_var="MODEL_PATH",
        ),
    ],
    resources=flyte.Resources(cpu=2, memory="2Gi"),
    requires_auth=False,
)
```

For serving large language models, the `flyteplugins-vllm` integration gives you a production-grade vLLM server (with autoscaling to zero) via `VLLMAppEnvironment`. Any web app — a Streamlit dashboard, a Gradio demo, a Flask backend — runs as a `flyte.app.AppEnvironment` that you configure with image, resources, port, autoscaling, and a custom subdomain, then `flyte.serve`.

### Dynamic batching for GPU inference

For in-process batch inference, `DynamicBatcher` from `flyte.extras` keeps an expensive GPU saturated: async producers load and preprocess data concurrently while a single consumer feeds the model in optimally-sized batches, with built-in backpressure. This replaces the Flyte 1 pattern of standing up a separate inference server just to get request batching.

```python
import asyncio
from flyte.extras import DynamicBatcher

async with DynamicBatcher(
    process_fn=run_inference,   # takes a batch, returns results in the same order
    target_batch_cost=1000,     # cost budget per batch
    max_batch_size=64,          # hard cap on records per batch
    batch_timeout_s=0.05,       # max wait before dispatching a partial batch
) as batcher:
    futures = [await batcher.submit(record) for record in records]
    results = await asyncio.gather(*futures)
```

`submit()` is non-blocking and returns a `Future`; when the queue is full it applies backpressure automatically. See the batch inference docs for `TokenBatcher` (token-aware LLM batching).

### Sandboxed code execution

`flyte.sandbox.create()` runs arbitrary Python code or shell commands inside an ephemeral, single-use Docker container — built on demand from declared dependencies, executed once, then discarded. Only declared inputs go in and only declared outputs come back, which makes it the safe way to run untrusted code, most importantly code generated by an LLM.

```python
# sandbox_environment provides the base runtime for code sandboxes.
# Include it in depends_on so the sandbox runtime is available when tasks execute.
env = flyte.TaskEnvironment(
    name="sandbox-demo",
    image=flyte.Image.from_debian_base(name="sandbox-demo"),
    depends_on=[sandbox_environment],
)

# Auto-IO mode: pure computation. The code string runs in an isolated sandbox;
# only the declared inputs go in and only the declared outputs come back.
sum_sandbox = flyte.sandbox.create(
    name="sum-to-n",
    code="total = sum(range(n + 1)) if conditional else 0",
    inputs={"n": int, "conditional": bool},
    outputs={"total": int},
)
```

Call it from a task with `await sum_sandbox.run.aio(n=10, conditional=True)`. This also powers **code mode** (programmatic tool calling), where an agent writes a whole program instead of emitting one tool call at a time.

## Anti-Patterns

1. **Don't keep `@task` / `@workflow` per-task config** — move `image`, `resources`, and `cache` onto a single `flyte.TaskEnvironment` and decorate with `@env.task`.
2. **Don't leave a separate "pick the best" task** — after `asyncio.gather`, select the winner in plain Python inside the orchestrating task.
3. **Don't carry `map_task` + `partial` into v2** — fan out with `asyncio.gather` over coroutines, reusing the same model reference.
4. **Don't split GPU type and count** — replace `Resources(gpu="1")` + `accelerator=T4` with a single `gpu="T4:1"` string on `flyte.Resources`.
5. **Don't use `mem=` or `current_context().working_directory`** — use `memory=` on `flyte.Resources` and `os.getcwd()` for local paths.
6. **Don't forget `await`** — `File.from_local`, `download`, and task calls are all async in v2.
7. **Don't hand-roll a serving container or a request-batching server** — use a `FastAPIAppEnvironment` / `AppEnvironment` for serving and `DynamicBatcher` for GPU batching.
8. **Don't run untrusted or LLM-generated code inline** — use `flyte.sandbox.create()` with `sandbox_environment` in `depends_on`.
