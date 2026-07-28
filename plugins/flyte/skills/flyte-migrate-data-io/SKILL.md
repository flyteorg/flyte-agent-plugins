---
name: flyte-migrate-data-io
description: Migrates Flyte 1 data types and offloaded I/O to Flyte 2. Use when migrating Flyte 1 data types and I/O (files, directories, dataframes, dataclasses) to Flyte 2, converting FlyteFile, FlyteDirectory, or StructuredDataset to flyte.io.File, flyte.io.Dir, and flyte.io.DataFrame. Trigger words are FlyteFile, FlyteDirectory, StructuredDataset, DataFrame, dataclass, Pydantic, type, I/O, and serialization.
---

# Flyte 1 to 2 Migration: Data Types and I/O

Flyte 2 renames the offloaded-data types and makes their I/O `async`, but the mental model is the same: pass lightweight references to large data between tasks, not the materialized bytes. `FlyteFile`, `FlyteDirectory`, and `StructuredDataset` become `flyte.io.File`, `flyte.io.Dir`, and `flyte.io.DataFrame`. Plain dataclasses and Pydantic `BaseModel`s work directly as task I/O with no JSON mixin.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/data-io/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## Type Mapping

| Flyte 1 | Flyte 2 | Notes |
|---|---|---|
| `flytekit.types.file.FlyteFile` | `flyte.io.File` | I/O is `async` |
| `flytekit.types.directory.FlyteDirectory` | `flyte.io.Dir` | I/O is `async` |
| `flytekit.types.structured.StructuredDataset` | `flyte.io.DataFrame` | build with `from_df`, read with `open(...).all()` |
| `@dataclass_json` + `@dataclass` | plain `@dataclass` | no mixin needed |
| Pydantic `BaseModel` (+ config) | plain Pydantic `BaseModel` | works directly as task I/O |

## Offloaded Data: The Mental Model

`File`, `Dir`, and `DataFrame` are lightweight references (pointers) to data offloaded in blob storage — not the materialized bytes. In Flyte 2 the read/write operations are `async`: upload with `await File.from_local(local_path)`, read with `async with f.open("rb") as fh: await fh.read()`, build a frame with `flyte.io.DataFrame.from_df(df)` (sync constructor), and read it with `await fdf.open(pandas.DataFrame).all()`.

## Files and Directories

`FlyteFile` and `FlyteDirectory` become `flyte.io.File` and `flyte.io.Dir` — the way you pass model artifacts and datasets between tasks. Use `await File.from_local(...)` to upload and `async with file.open(...)` to read.

### Flyte 1

```python
import os

from flytekit import task, workflow, current_context
from flytekit.types.file import FlyteFile

@task
def write_file(content: str) -> FlyteFile:
    path = os.path.join(current_context().working_directory, "out.txt")
    with open(path, "w") as f:
        f.write(content)
    return FlyteFile(path=path)

@task
def read_file(f: FlyteFile) -> str:
    with open(f.download()) as fh:
        return fh.read()

@workflow
def main(content: str) -> str:
    f = write_file(content=content)
    return read_file(f=f)
```

### Flyte 2

```python
import flyte
from flyte.io import File

env = flyte.TaskEnvironment(name="files")

@env.task
async def write_file(content: str) -> File:
    with open("out.txt", "w") as f:
        f.write(content)
    # File.from_local uploads the file to blob storage and returns a reference
    # (a lightweight pointer, not the materialized bytes).
    return await File.from_local("out.txt")

@env.task
async def read_file(f: File) -> str:
    async with f.open("rb") as fh:
        return (await fh.read()).decode("utf-8")

@env.task
async def main(content: str) -> str:
    f = await write_file(content)
    return await read_file(f)
```

Directories follow the same pattern: import `Dir` from `flyte.io` and use its `async` upload/read methods in place of `FlyteDirectory`. See [Files and directories](https://www.union.ai/docs/v2/flyte/user-guide/task-programming/files-and-directories) for more.

## DataFrames

`StructuredDataset` becomes `flyte.io.DataFrame`. Construct one with `flyte.io.DataFrame.from_df(df)` and read it back with `await df.open(pandas.DataFrame).all()`.

### Flyte 1

```python
import pandas as pd
from flytekit import task, workflow
from flytekit.types.structured import StructuredDataset

@task
def make_df() -> StructuredDataset:
    df = pd.DataFrame({"employee_id": [1, 2, 3], "salary": [50000, 60000, 70000]})
    return StructuredDataset(dataframe=df)

@task
def total_payroll(sd: StructuredDataset) -> float:
    df = sd.open(pd.DataFrame).all()
    return float(df["salary"].sum())

@workflow
def main() -> float:
    return total_payroll(sd=make_df())
```

### Flyte 2

```python
import pandas as pd
import flyte
import flyte.io

env = flyte.TaskEnvironment(
    name="dataframe",
    image=flyte.Image.from_debian_base().with_pip_packages("pandas", "pyarrow"),
)

@env.task
async def make_df() -> flyte.io.DataFrame:
    df = pd.DataFrame({"employee_id": [1, 2, 3], "salary": [50000, 60000, 70000]})
    # StructuredDataset becomes flyte.io.DataFrame.
    return flyte.io.DataFrame.from_df(df)

@env.task
async def total_payroll(fdf: flyte.io.DataFrame) -> float:
    df = await fdf.open(pd.DataFrame).all()
    return float(df["salary"].sum())

@env.task
async def main() -> float:
    return await total_payroll(await make_df())
```

Add the dataframe dependencies (for example `pandas` and `pyarrow`) to the `TaskEnvironment` image. See [DataFrames](https://www.union.ai/docs/v2/flyte/user-guide/task-programming/dataframes) for more.

## Dataclasses and Structured Types

Flyte 1 required a `@dataclass_json` mixin for dataclass I/O. In Flyte 2, plain dataclasses (and Pydantic `BaseModel`s) work directly as task inputs and outputs — handy for passing around a training config.

### Flyte 1

```python
from dataclasses import dataclass

from dataclasses_json import dataclass_json
from flytekit import task, workflow

@dataclass_json
@dataclass
class TrainingConfig:
    learning_rate: float
    n_estimators: int
    max_depth: int = 6

@task
def make_config(learning_rate: float, n_estimators: int) -> TrainingConfig:
    return TrainingConfig(learning_rate=learning_rate, n_estimators=n_estimators)

@task
def train(config: TrainingConfig) -> str:
    return (
        f"trained with lr={config.learning_rate}, "
        f"n_estimators={config.n_estimators}, max_depth={config.max_depth}"
    )

@workflow
def main(learning_rate: float, n_estimators: int) -> str:
    config = make_config(learning_rate=learning_rate, n_estimators=n_estimators)
    return train(config=config)
```

### Flyte 2

```python
from dataclasses import dataclass

import flyte

env = flyte.TaskEnvironment(name="dataclasses")

# Plain dataclasses work directly as task I/O -- no @dataclass_json mixin needed.
# Pydantic BaseModels work the same way.
@dataclass
class TrainingConfig:
    learning_rate: float
    n_estimators: int
    max_depth: int = 6

@env.task
def make_config(learning_rate: float, n_estimators: int) -> TrainingConfig:
    return TrainingConfig(learning_rate=learning_rate, n_estimators=n_estimators)

@env.task
def train(config: TrainingConfig) -> str:
    return (
        f"trained with lr={config.learning_rate}, "
        f"n_estimators={config.n_estimators}, max_depth={config.max_depth}"
    )

@env.task
def main(learning_rate: float, n_estimators: int) -> str:
    config = make_config(learning_rate, n_estimators)
    return train(config)
```

## Data ETL: Putting It Together

Extract, clean, aggregate, and write out a feature table. `StructuredDataset` becomes `flyte.io.DataFrame`, and the tasks become `async`.

### Flyte 1

```python
import pandas as pd
from flytekit import task, workflow
from flytekit.types.structured import StructuredDataset

@task
def extract() -> pd.DataFrame:
    # Read raw transaction records (stand-in for a real source).
    return pd.DataFrame(
        {
            "user_id": [1, 1, 2, 3, 3, 3],
            "amount": [10.0, 5.0, 20.0, 7.5, 2.5, 1.0],
        }
    )

@task
def transform(df: pd.DataFrame) -> StructuredDataset:
    # Clean and aggregate into a per-user feature table.
    df = df[df["amount"] > 0]
    agg = df.groupby("user_id", as_index=False)["amount"].sum()
    return StructuredDataset(dataframe=agg)

@task
def load(sd: StructuredDataset) -> int:
    df = sd.open(pd.DataFrame).all()
    return len(df)

@workflow
def main() -> int:
    raw = extract()
    features = transform(df=raw)
    return load(sd=features)
```

### Flyte 2

```python
import pandas as pd
import flyte
import flyte.io

env = flyte.TaskEnvironment(
    name="data_etl",
    image=flyte.Image.from_debian_base().with_pip_packages("pandas", "pyarrow"),
)

@env.task
async def extract() -> pd.DataFrame:
    # Read raw transaction records (stand-in for a real source).
    return pd.DataFrame(
        {
            "user_id": [1, 1, 2, 3, 3, 3],
            "amount": [10.0, 5.0, 20.0, 7.5, 2.5, 1.0],
        }
    )

@env.task
async def transform(df: pd.DataFrame) -> flyte.io.DataFrame:
    # Clean and aggregate into a per-user feature table.
    df = df[df["amount"] > 0]
    agg = df.groupby("user_id", as_index=False)["amount"].sum()
    # StructuredDataset becomes flyte.io.DataFrame.
    return flyte.io.DataFrame.from_df(agg)

@env.task
async def load(sd: flyte.io.DataFrame) -> int:
    df = await sd.open(pd.DataFrame).all()
    return len(df)

@env.task
async def main() -> int:
    raw = await extract()
    features = await transform(raw)
    return await load(features)
```

## Anti-Patterns

1. **Don't call the offloaded-data I/O synchronously** — `File.from_local`, `file.open(...).read()`, and `DataFrame.open(...).all()` are `async` in Flyte 2; `await` them inside `async` tasks.
2. **Don't keep the `@dataclass_json` mixin** — plain `@dataclass` and Pydantic `BaseModel`s serialize as task I/O directly; drop `dataclasses_json`.
3. **Don't return `StructuredDataset(dataframe=df)`** — use `flyte.io.DataFrame.from_df(df)` instead.
4. **Don't materialize large data into task outputs** — return `File`, `Dir`, or `DataFrame` references, not the raw bytes or full frames.
5. **Don't forget the dataframe dependencies** — add `pandas` and `pyarrow` (or your engine) to the `TaskEnvironment` image so DataFrame I/O works remotely.
6. **Don't import from `flytekit.types.*`** — import `File` and `Dir` from `flyte.io`, and use `flyte.io.DataFrame`.
