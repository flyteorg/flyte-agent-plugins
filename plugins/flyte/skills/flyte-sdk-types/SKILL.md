---
name: flyte-sdk-types
description: 'Guides correct types, I/O, and serialization for common data (Pandas, Arrow, Parquet, images, audio, HF datasets), including data locality and storage best practices. Use when the user needs help with type annotations, data serialization, file I/O between tasks, custom type transformers, DataFrame handling, or choosing the right Flyte type for their data. Trigger words: "type", "serialize", "deserialize", "DataFrame", "File", "Directory", "custom type", "data format", "Parquet", "Arrow", "Pandas", "type transformer".'
---

# Flyte 2 SDK Types Skill

Guide correct type annotations, I/O patterns, and serialization for Flyte 2 workflows.

## Grounding References

| Resource | URL |
|---|---|
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via the `flyte-cluster` and `flyte-docs` MCP servers |

**Ground unfamiliar APIs in real examples.** When unsure of a current Flyte 2 API, or for a pattern not shown below, and the `flyte-docs` search tools are available, search them first — by exact symbol (`TaskEnvironment`, `flyte.io.File`, `map_task`), since matching is literal substring, not semantic — then adapt a real example rather than inventing one, and cite the file or section you pulled it from. (Flyte 2 is not `flytekit`; priors are often wrong.)

## Type System Overview

Flyte 2 uses **Python type hints** for serialization. Every task input/output must have a type annotation. Flyte's type transformer system handles conversion between Python types and remote storage (S3, GCS, etc.).

### Supported Native Types

| Python Type | Flyte Type | Remote Transport |
|---|---|---|
| `int`, `float`, `bool`, `str` | Literal | Inline (JSON) |
| `list[T]`, `dict[K, V]` | Collection / Map | Inline (JSON) for small, blob for large |
| `flyte.io.File` | Blob | Uploaded to metadata bucket |
| `flyte.io.Dir` | Blob (directory) | Uploaded to metadata bucket |
| `flyte.io.DataFrame` | DataFrame | Parquet in metadata bucket |
| `dataclass` | Struct | JSON in metadata bucket |
| `pydantic.BaseModel` | Struct | JSON in metadata bucket |
| `datetime`, `timedelta` | DateTime / Duration | Inline |

## Offloaded types: flyte.io.File and flyte.io.Dir

`flyte.io.File` and `flyte.io.Dir` are the **offloaded types**. A variable of an offloaded type holds a *reference* to data, not the data itself. The bytes live in the internal blob store; they are uploaded when first created and only downloaded when a task actually accesses them. This lets very large objects (videos, DNA datasets, model weights) move between tasks without transferring bytes.

Use `flyte.io.File` for a single file and `flyte.io.Dir` for a directory of files.

```python
import tempfile
from pathlib import Path
import flyte
from flyte.io import Dir, File

env = flyte.TaskEnvironment(name="files-and-dirs")

@env.task
async def write_file(name: str) -> File:
    with open("test.txt", "w") as fh:
        fh.write(f"hello world {name}")
    # Upload the local file to the blob store and return the reference.
    return await File.from_local("test.txt")

@env.task
async def check_dir(my_dir: Dir):
    # Stream each file out of the directory without downloading it whole.
    async for file in my_dir.walk():
        async with file.open("rb") as fh:
            print(file.name, await fh.read())

@env.task
async def main():
    f = await write_file("Alice")
    temp_dir = tempfile.mkdtemp()
    async with f.open("rb") as fh:
        (Path(temp_dir) / f.name).write_bytes(await fh.read())
    my_dir = await Dir.from_local(temp_dir)
    await check_dir(my_dir=my_dir)
```

### Synchronous and asynchronous APIs

Every I/O operation on `File`/`Dir` has an async form (used in `async def` tasks) and a `_sync` form (used in plain `def` tasks). Pick the one matching how your task is defined:

- **Async task** (`async def`): `await File.from_local(...)`, `async with file.open(...)`, `async for f in dir.walk()`, `await file.download()`, `await file.exists()`.
- **Sync task** (`def`): `File.from_local_sync(...)`, `with file.open_sync(...)`, `for f in dir.walk_sync()`, `file.download_sync()`, `file.exists_sync()`.

Constructors like `File.new_remote()` and `File.from_existing_remote(uri)` do no I/O, so a single form works from either kind of task.

#### File methods

| Async (in `async def`) | Sync (in `def`) | Purpose |
|---|---|---|
| `await File.from_local(path)` | `File.from_local_sync(path)` | Upload a local file to the blob store |
| `File.new_remote()` | `File.new_remote()` | Allocate a new remote file to stream into |
| `File.from_existing_remote(uri)` | `File.from_existing_remote(uri)` | Reference a file already stored remotely |
| `async with file.open(mode) as fh` | `with file.open_sync(mode) as fh` | Stream the file for reading/writing |
| `await file.download()` | `file.download_sync()` | Download to the local filesystem |
| `await file.exists()` | `file.exists_sync()` | Check whether the file exists |

#### Dir methods

| Async (in `async def`) | Sync (in `def`) | Purpose |
|---|---|---|
| `await Dir.from_local(path)` | `Dir.from_local_sync(path)` | Upload a local directory |
| `Dir.new_remote()` | `Dir.new_remote()` | Allocate a new remote directory |
| `Dir.from_existing_remote(uri)` | `Dir.from_existing_remote(uri)` | Reference a directory stored remotely |
| `async for f in dir.walk()` | `for f in dir.walk_sync()` | Iterate over the files (supports `file_pattern`, `recursive`, `max_depth`) |
| `await dir.list_files()` | `dir.list_files_sync()` | List files (non-recursive) |
| `await dir.get_file(name)` | `dir.get_file_sync(name)` | Get one file by name |
| `await dir.download()` | `dir.download_sync()` | Download the whole directory |
| `await dir.exists()` | `dir.exists_sync()` | Check whether the directory exists |

> [!NOTE] `walk()` yields `File` objects streaming from the directory; it does not require downloading the whole directory. If a `File`/`Dir` already points at the local filesystem, `download()`/`download_sync()` return its own path without copying (Flyte 2.11.2+); pass a different `local_path` to force a copy.

### Synchronous example

```python
import flyte
from flyte.io import File

env = flyte.TaskEnvironment(name="sync-file")

@env.task
def write_file(content: str) -> File:
    f = File.new_remote()          # no I/O, single form
    with f.open_sync("wb") as fh:  # stream into it, blocking call
        fh.write(content.encode("utf-8"))
    return f

@env.task
def read_file(f: File) -> str:
    with f.open_sync("rb") as fh:
        return fh.read().decode("utf-8")

@env.task
def main() -> str:
    return read_file(write_file("hello world"))
```

### flyte.io.File / Dir best practices

- **Always pass `flyte.io.File`/`flyte.io.Dir` between tasks** — never pass file paths as strings. Flyte serializes the reference to the remote blob and downloads it on access.
- Upload a local file with `await File.from_local(path)` (async) or `File.from_local_sync(path)` (sync); read/write by streaming with `open()`/`open_sync()`.
- **`file.path`** gives the local path inside the task container (after download/access); `file.name` is the basename.
- **Content-based caching**: because offloaded types are passed by reference, a cached downstream task does **not** hit on identical content at a new path. To cache on content, attach a hash — see [Content-based caching](#content-based-caching-for-dataframes-files-and-directories) below.
- Compress format is inferred from the extension (`.parquet`, `.csv`, `.json`, `.bin`, etc.).

## flyte.io.DataFrame — DataFrames (Pandas, Polars, Arrow, Dask)

Flyte auto-serializes these native DataFrame types between tasks (stored as Parquet in the blob store, passed **by reference**): `pandas.DataFrame`, `pyarrow.Table`, `dask.dataframe.DataFrame`, `polars.DataFrame`, and `flyte.io.DataFrame`. No annotation is required for a native type — returning one uploads it at task completion.

> [!NOTE] **Polars needs a plugin.** Native `pandas`/`pyarrow`/`dask` work out of the box. `polars.DataFrame` and `polars.LazyFrame` (and `flyte.io.DataFrame` of a Polars frame) require the **`flyteplugins-polars`** package in the image; it registers itself on install. Lance datasets require `flyteplugins-lance`. Add them with `flyte.Image.from_debian_base().with_pip_packages("flyteplugins-polars", ...)`.

```python
import pandas as pd
import flyte
import flyte.io

@env.task
async def produce() -> pd.DataFrame:
    return pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})

@env.task
async def consume(df: pd.DataFrame) -> int:
    # A native pandas.DataFrame input is downloaded and materialized for you.
    return int(df["value"].sum())
```

### flyte.io.DataFrame wrapper

`flyte.io.DataFrame` is a thin, uniform wrapper around any standard DataFrame type, useful when a task must accept or emit several engine types or you want to pin the storage format. Create it with `from_df` and pin the format with an `Annotated` type:

```python
from typing import Annotated
import pandas as pd
import flyte
import flyte.io

@env.task
async def create() -> Annotated[flyte.io.DataFrame, "parquet"]:
    return flyte.io.DataFrame.from_df(pd.DataFrame({"a": [1, 2, 3]}))

@env.task
async def read(df: flyte.io.DataFrame) -> float:
    # Materialize as a specific backend with open(...).all()
    pdf = await df.open(pd.DataFrame).all()
    return float(pdf["a"].mean())
```

Flyte converts a `flyte.io.DataFrame` into whatever concrete type a task declares as its input (for example `pd.DataFrame`) on access. To get a concrete backend from a `flyte.io.DataFrame` inside a task, `await df.open(pd.DataFrame).all()`.

### Eager vs Lazy workflows

- **Pandas / eager `pl.DataFrame`**: materialized on use.
- **Lazy (`pl.LazyFrame` / `dask`)**: the query plan is deferred until execution; Flyte serializes the result to Parquet when it is passed on. Call `collect()` in the producing task to trigger execution if needed.

## Polars DataFrames (plugin)

`polars.DataFrame` and `polars.LazyFrame` support comes from the **`flyteplugins-polars`** package, which must be installed in the task image. Both types are serialized as Parquet between tasks, just like the other DataFrame backends.

```python
import polars as pl
import flyte

env = flyte.TaskEnvironment(
    name="polars-dataframes",
    image=flyte.Image.from_debian_base().with_pip_packages("flyteplugins-polars", "polars"),
    resources=flyte.Resources(cpu="1", memory="2Gi"),
)

@env.task
async def create_dataframe() -> pl.DataFrame:
    """Polars DataFrames pass between tasks as Parquet — no manual upload."""
    return pl.DataFrame({"dept": ["eng", "fin"], "salary": [75_000, 68_000]})

@env.task
async def filter_high_earners(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(pl.col("salary") > 60_000).sort("salary", descending=True)

@env.task
async def create_lazyframe() -> pl.LazyFrame:
    """LazyFrames defer the plan; Flyte serializes the result to Parquet."""
    return pl.LazyFrame({"dept": ["eng", "fin"], "salary": [75_000, 68_000]})

@env.task
async def aggregate(lf: pl.LazyFrame) -> pl.DataFrame:
    # collect() executes the lazy plan
    return lf.group_by("dept").agg(pl.col("salary").mean()).collect()
```

> [!NOTE] Flyte's `flyte.io.DataFrame` converter does **not** auto-load in a task pinned to `pl.LazyFrame` unless the polars plugin is present; install `flyteplugins-polars` first.

## Dataclass and Pydantic Models

For structured data, use Python dataclasses or Pydantic models. Flyte serializes them to JSON.

```python
from dataclasses import dataclass
from pydantic import BaseModel
import flyte
import flyte.io

@dataclass
class TrainingConfig:
    learning_rate: float
    batch_size: int
    epochs: int

class PredictionOutput(BaseModel):
    predictions: list[float]
    confidence: list[float]
    model_version: str

@env.task
async def train(config: TrainingConfig) -> flyte.io.File:
    # config.learning_rate, config.batch_size, etc.
    ...

@env.task
async def predict(model: flyte.io.File, data: flyte.io.DataFrame) -> PredictionOutput:
    return PredictionOutput(
        predictions=[0.5, 0.8, 0.3],
        confidence=[0.9, 0.7, 0.95],
        model_version="v1.0",
    )
```

## Custom Type Transformers

Flyte's type system handles most Python types automatically. If it does not recognize a type it falls back to **pickle**, which is inefficient, Python-only, version-fragile, and opaque in the UI. For data that deserves a real format (Parquet, tensor formats, etc.), register a type transformer.

There are two kinds of extensions:

1. **Type transformers** — for scalar types (custom objects, files, directories).
2. **DataFrame extensions** — for tabular types with schema metadata (Parquet, parallel/partitioned writes).

A Flyte 2 type transformer subclasses `TypeTransformer[T]` and implements `get_literal_type`, `to_literal`, `to_python_value`, and `guess_python_type`. The method signatures use Flyte literal protobuf types and are `async`:

```python
from flyteidl2.core import literals_pb2, types_pb2
from flyte.types import TypeEngine, TypeTransformer, TypeTransformerFailedError

class PositiveInt:
    """Example custom type: an int that must be positive."""
    def __init__(self, value: int):
        if value <= 0:
            raise ValueError(f"expected positive, got {value}")
        self._value = value
    @property
    def value(self) -> int:
        return self._value

class PositiveIntTransformer(TypeTransformer[PositiveInt]):
    def __init__(self):
        super().__init__(name="PositiveInt", t=PositiveInt)

    def get_literal_type(self, t):
        return types_pb2.LiteralType(
            simple=types_pb2.SimpleType.INTEGER,
            structure=types_pb2.TypeStructure(tag="PositiveInt"),
        )

    async def to_literal(self, python_val, python_type, expected):
        if not isinstance(python_val, PositiveInt):
            raise TypeTransformerFailedError(...)
        return literals_pb2.Literal(
            scalar=literals_pb2.Scalar(primitive=literals_pb2.Primitive(integer=python_val.value))
        )

    async def to_python_value(self, lv, expected_python_type):
        return PositiveInt(lv.scalar.primitive.integer)

    def guess_python_type(self, literal_type):
        if literal_type.simple == types_pb2.SimpleType.INTEGER \
           and literal_type.structure.tag == "PositiveInt":
            return PositiveInt
        raise ValueError(f"cannot guess PositiveInt from {literal_type}")

# Register it (call before task execution)
TypeEngine.register(PositiveIntTransformer())
```

> [!WARNING] The Flyte 1 style `save()`/`load()`/`get_type()` `TypeTransformer` shown in older examples is **obsolete**. Flyte 2 uses the `get_literal_type` / `async to_literal` / `async to_python_value` / `guess_python_type` protocol above.

## Data I/O Patterns by Domain

### ETL / Data Engineering

```python
# CSV → Parquet conversion
@env.task(cache="auto")
async def csv_to_parquet(csv_file: flyte.io.File, output_path: str) -> flyte.io.File:
    import polars as pl
    df = pl.read_csv(csv_file.path)
    df.write_parquet(output_path)
    return await flyte.io.File.from_local(output_path)

# JsonlFile — streaming JSONL (needs the flyteplugins-jsonl plugin in your image)
@env.task
async def write_records() -> None:
    from flyteplugins.jsonl import JsonlFile
    out = JsonlFile.new_remote("results.jsonl")   # streaming writer to remote storage
    async with out.writer() as w:
        await w.write({"id": 1})                  # also write_many(), write_raw(), flush()

# JsonlDir — directory of sharded JSONL
@env.task
async def read_jsonl_dir(d: flyte.io.Dir) -> int:
    from flyteplugins.jsonl import JsonlDir
    jd = JsonlDir(d)
    total = 0
    async for rec in jd.iter_records():
        total += 1
    return total
```

### Image Processing

```python
from PIL import Image
import flyte
import flyte.io

@env.task
async def resize_image(input_file: flyte.io.File, size: tuple[int, int]) -> flyte.io.File:
    img = Image.open(input_file.path)
    resized = img.resize(size)
    output_path = f"/tmp/resized_{size[0]}x{size[1]}.png"
    resized.save(output_path)
    return await flyte.io.File.from_local(output_path)

@env.task
async def batch_resize(files: list[flyte.io.File], size: tuple[int, int]) -> list:
    import asyncio
    return await asyncio.gather(*(resize_image(f, size) for f in files))
```

### Audio Processing

```python
import librosa
import numpy as np
import flyte
import flyte.io

@env.task
async def extract_features(audio_file: flyte.io.File) -> flyte.io.File:
    """Extract MFCC features from audio file."""
    y, sr = librosa.load(audio_file.path, sr=None)
    mfccs = librosa.feature.mfcc(y=y, sr=sr)
    # Save as numpy array
    output_path = "/tmp/mfccs.npz"
    np.savez(output_path, mfccs=mfccs, sr=sr)
    return await flyte.io.File.from_local(output_path)
```

### HuggingFace Datasets

```python
from datasets import load_dataset, Dataset
import flyte
import flyte.io

@env.task
async def load_dataset_from_hub(dataset_name: str, split: str = "train") -> flyte.io.Dir:
    """Load a HF dataset and save locally, then upload as a Dir."""
    ds = load_dataset(dataset_name, split=split)
    path = f"/tmp/{dataset_name.replace('/', '_')}_{split}"
    ds.save_to_disk(path)
    return await flyte.io.Dir.from_local(path)

@env.task
async def process_dataset(d: flyte.io.Dir) -> flyte.io.DataFrame:
    """Convert HF dataset to a Flyte DataFrame."""
    ds = Dataset.load_from_disk(d.path)
    return flyte.io.DataFrame.from_df(ds.to_pandas())
```

## Distributing a type transformer as a plugin

To share a transformer as an installable package, register it through a `pyproject.toml` entry point so Flyte auto-loads it on `flyte.init()` / `flyte.init_from_config()`:

```toml
[project.entry-points."flyte.plugins.types"]
my_transformer = "my_transformer.transformer:register_positive_int_transformer"
```

The entry point group `flyte.plugins.types` tells the SDK to load the transformer when the package is installed. To keep init fast you can disable auto-loading with `flyte.init(load_plugin_type_transformers=False)` (default `True`).

## Content-based caching for DataFrames, files, and directories

Offloaded types are keyed by **remote path**, so a downstream cached task does *not* hit on identical content stored at a new path. To cache on content, attach a hash at production time with `flyte.io.HashFunction`:

```python
from typing import Annotated
import hashlib
import pandas as pd
import flyte
import flyte.io
from flyte.io import HashFunction

# Native DataFrame: annotate the return type with a HashFunction
HashedPandas = Annotated[pd.DataFrame, HashFunction.from_fn(lambda df: str(hash(tuple(df["value"]))))]

@env.task
async def produce() -> HashedPandas:
    return pd.DataFrame({"value": [1, 2, 3]})

@env.task(cache="auto")
async def consume(df: pd.DataFrame) -> int:   # cache key is the content hash
    return int(df["value"].sum())
```

- **`flyte.io.DataFrame`**: pass the `HashFunction` to `DataFrame.from_local(df, hash_method=...)` instead of annotating.
- **`flyte.io.File`**: `File.from_local(path, hash_method=HashFunction.from_fn(hash_bytes))` (also on `File.new_remote`).
- **`flyte.io.Dir`**: `Dir.from_local` does *not* take a `HashFunction`; compute a content key yourself and pass it as `dir_cache_key=`.

## Data Locality and Storage Best Practices

### How data flows between tasks

1. **By reference (default)** — large data (DataFrames, Files, Directories) is uploaded to the metadata bucket. Tasks receive a remote reference and download on demand.
2. **Inline (small data)** — primitives (int, float, str, bool) and small collections are passed inline as JSON.

### Choosing the right transport

| Data type | Transport | Max size |
|---|---|---|
| `int`, `float`, `bool`, `str` | Inline | None |
| `list`, `dict` (small) | Inline | ~10 MB |
| `flyte.io.File` | Reference (S3/GCS) | Unlimited |
| `flyte.io.Dir` | Reference (S3/GCS) | Unlimited |
| `flyte.io.DataFrame` (Pandas/Polars/Arrow/Dask) | Reference (Parquet) | Unlimited |
| `dataclass` / `BaseModel` | Inline (JSON) | ~10 MB |

### Storage best practices

1. **Use `flyte.io.File` for files** — don't pass strings. Flyte manages the upload/download.
2. **Use `flyte.io.DataFrame` for tabular data** — stored as Parquet, efficient for ETL pipelines.
3. **Use `flyte.io.Dir` for collections** — model checkpoints, output artifacts.
4. **Set `cache="auto"`** on idempotent tasks (ETL, transforms) to avoid re-processing.
5. **Use `raw_data_path`** for per-run customization: `flyte.with_runcontext(raw_data_path="s3://my-bucket/{run_id}/")`
6. **Large data should never be inline** — if your dataclass exceeds ~10 MB, switch to `flyte.io.File` or `flyte.io.Dir`.

## Inline I/O Threshold

Control when data is passed inline vs by reference. Offloaded types (`File`, `Dir`, `DataFrame`) always go by reference; the threshold governs when large materialized values (big `list`/`dict`/dataclass) switch to a blob instead of inline JSON:

```python
@env.task(inline_output_limit="10MB")  # data > 10MB goes by reference
async def process(data: dict) -> dict:
    ...
```

Default threshold is generous. For ML training outputs or large DataFrames, set it lower to avoid overhead.

## Common Type Mistakes

1. **Missing type hints** — Flyte 2 requires type annotations on all task inputs/outputs. No type hint = serialization error.
2. **Passing a path string where an offloaded type is expected** — use `flyte.io.File`/`flyte.io.Dir` objects (create with `File.from_local(...)` / `Dir.from_local(...)`). The path string alone won't serialize.
3. **Forgetting a DataFrame plugin** — `pandas`/`pyarrow`/`dask` work out of the box, but `polars` needs `flyteplugins-polars` and LANCE datasets need `flyteplugins-lance` in the image.
4. **Using the pre-2.0 type transformer API** — Flyte 2 transformers use `get_literal_type` / `async to_literal` / `async to_python_value` / `guess_python_type`, not the old `save()`/`load()`/`get_type()` protocol.
5. **Not registering (or distributing) custom transformers** — register via `TypeEngine.register(...)` before execution, or ship them as a `flyte.plugins.types` entry point so they auto-load.
6. **Forgetting `.path` on flyte.io.File/Dir** — inside a task, `file` is an offloaded-type object, not a string. Use `file.path` for the local path and `.name` for the basename.
