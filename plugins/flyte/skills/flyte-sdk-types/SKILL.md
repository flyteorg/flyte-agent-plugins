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

## flyte.io.File — Single Files

Use `flyte.io.File` for any single file that flows between tasks. Files are **automatically uploaded** to the metadata bucket at runtime.

```python
import flyte
import flyte.io

@env.task
async def download_url(url: str) -> flyte.io.File:
    """Download a file and return as flyte.io.File."""
    import urllib.request
    local_path = f"/tmp/{url.split('/')[-1]}"
    urllib.request.urlretrieve(url, local_path)
    return flyte.io.File(path=local_path)

@env.task
async def process(file: flyte.io.File) -> dict:
    """Read a file — flyte.io.File downloads it automatically."""
    # file.path gives the local path (already downloaded)
    with open(file.path) as f:
        content = f.read()
    return {"lines": len(content.splitlines())}

@env.task
async def main(url: str) -> dict:
    downloaded = await download_url(url)
    return await process(downloaded)  # type: flyte.io.File flows as remote reference
```

### flyte.io.File best practices

- **Always pass `flyte.io.File` between tasks** — never pass file paths as strings. Flyte serializes the reference to the remote blob.
- **`file.path`** gives the local download path inside the task container.
- **Don't hardcode paths** — let Flyte manage the download/upload lifecycle.
- **Compression**: Flyte infers format from extension (`.parquet`, `.csv`, `.json`, `.pt`, `.png`, etc.).

## flyte.io.Dir — Directories

Use `flyte.io.Dir` for a collection of files (e.g., model checkpoints, output artifacts).

```python
import flyte
import flyte.io

@env.task
async def train(checkpoint_dir: flyte.io.Dir) -> flyte.io.Dir:
    """Train and save checkpoints to a directory."""
    # Write checkpoints
    for i in range(10):
        path = f"{checkpoint_dir.path}/checkpoint_{i}.pt"
        save_model(path)
    return checkpoint_dir

@env.task
async def evaluate(checkpoints: flyte.io.Dir) -> dict:
    """Load checkpoints from a directory."""
    # List all files in the directory
    files = list(checkpoints.path.glob("*.pt"))
    ...
```

## flyte.io.DataFrame — Polars DataFrames

Flyte 2 has built-in support for Polars DataFrames. They are **passed by reference** (Parquet in the metadata bucket), not inline.

```python
import flyte
import flyte.io

@env.task
async def load_csv(url: str) -> flyte.io.DataFrame:
    """Load a CSV and return as Polars DataFrame."""
    import polars as pl
    df = pl.read_csv(url)
    return flyte.io.DataFrame(df)

@env.task
async def clean(df: flyte.io.DataFrame) -> flyte.io.DataFrame:
    """Clean the DataFrame."""
    inner = df.to_polars()  # Get the underlying Polars DataFrame
    cleaned = inner.drop_nulls()
    return flyte.io.DataFrame(cleaned)

@env.task
async def save_parquet(df: flyte.io.DataFrame, path: str) -> flyte.io.File:
    """Save DataFrame to Parquet."""
    inner = df.to_polars()
    inner.write_parquet(path)
    return flyte.io.File(path=path)

@env.task
async def main(url: str) -> flyte.io.DataFrame:
    raw = await load_csv(url)
    cleaned = await clean(raw)
    return cleaned  # Flows as Parquet reference
```

### Polars DataFrame patterns

```python
# Convert to Polars for manipulation
inner_df = df.to_polars()

# Convert from Polars
df = flyte.io.DataFrame(inner_df)

# Common operations
df = flyte.io.DataFrame(inner_df.filter(pl.col("age") > 18))
df = flyte.io.DataFrame(inner_df.group_by("category").agg(pl.col("value").mean()))

# Check shape
print(df.shape)  # (rows, cols)
print(df.schema)  # column names and types
```

### Eager vs Lazy DataFrames

```python
# Eager (loaded into memory)
df = flyte.io.DataFrame(inner_df)

# Lazy (streaming, for large datasets)
df = flyte.io.DataFrame(inner_df.lazy())

# Materialize lazy to eager
eager = df.to_polars()  # materializes
```

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

Extend Flyte's type system to support custom types (e.g., PIL Images, HuggingFace datasets).

### PIL Image transformer

```python
from PIL import Image
import flyte
import flyte.io
from flyte.types import TypeTransformer

class PILImageTransformer(TypeTransformer[Image.Image]):
    _type = Image.Image

    def get_type(self, input: Image.Image) -> type:
        return Image.Image

    def save(self, img: Image.Image, path: str) -> None:
        img.save(path)

    def load(self, path: str) -> Image.Image:
        return Image.open(path)

# Register the transformer
flyte.types.TypeEngine.register(PILImageTransformer())

# Now use it in tasks
@env.task
async def process_image(img: Image.Image) -> flyte.io.File:
    # img is a PIL Image, already downloaded
    ...
```

### HuggingFace Dataset transformer

```python
from datasets import Dataset
import flyte

class HFDatasetTransformer(TypeTransformer[Dataset]):
    _type = Dataset

    def get_type(self, input: Dataset) -> type:
        return Dataset

    def save(self, ds: Dataset, path: str) -> None:
        ds.save_to_disk(path)

    def load(self, path: str) -> Dataset:
        return Dataset.load_from_disk(path)

flyte.types.TypeEngine.register(HFDatasetTransformer())
```

## Data I/O Patterns by Domain

### ETL / Data Engineering

```python
# CSV → Parquet conversion
@env.task(cache="auto")
async def csv_to_parquet(csv_file: flyte.io.File, output_path: str) -> flyte.io.File:
    import polars as pl
    df = pl.read_csv(csv_file.path)
    df.write_parquet(output_path)
    return flyte.io.File(path=output_path)

# JsonlFile — batched JSONL reading
@env.task
async def process_jsonl(path: str) -> int:
    from flyte.extend import JsonlFile
    jf = JsonlFile(path)
    count = 0
    async for record in jf.stream():
        process(record)
        count += 1
    return count

# JsonlDir — batched JSONL directory
@env.task
async def process_jsonl_dir(dir_path: str) -> dict:
    from flyte.extend import JsonlDir
    jd = JsonlDir(dir_path)
    total = 0
    async for batch in jd.stream_batches():
        total += len(batch)
    return {"records": total}
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
    return flyte.io.File(path=output_path)

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
    return flyte.io.File(path=output_path)
```

### HuggingFace Datasets

```python
from datasets import load_dataset, Dataset
import flyte
import flyte.io

@env_task
async def load_dataset_from_hub(dataset_name: str, split: str = "train") -> flyte.io.File:
    """Load a HF dataset and save locally."""
    ds = load_dataset(dataset_name, split=split)
    path = f"/tmp/{dataset_name.replace('/', '_')}_{split}"
    ds.save_to_disk(path)
    return flyte.io.File(path=path)

@env.task
async def process_dataset(file: flyte.io.File) -> flyte.io.DataFrame:
    """Convert HF dataset to Flyte DataFrame."""
    ds = Dataset.load_from_disk(file.path)
    df = ds.to_pandas()
    return flyte.io.DataFrame(df)
```

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
| `flyte.io.DataFrame` (Polars) | Reference (Parquet) | Unlimited |
| `dataclass` / `BaseModel` | Inline (JSON) | ~10 MB |

### Storage best practices

1. **Use `flyte.io.File` for files** — don't pass strings. Flyte manages the upload/download.
2. **Use `flyte.io.DataFrame` for tabular data** — stored as Parquet, efficient for ETL pipelines.
3. **Use `flyte.io.Dir` for collections** — model checkpoints, output artifacts.
4. **Set `cache="auto"`** on idempotent tasks (ETL, transforms) to avoid re-processing.
5. **Use `raw_data_path`** for per-run customization: `flyte.with_runcontext(raw_data_path="s3://my-bucket/{run_id}/")`
6. **Large data should never be inline** — if your dataclass exceeds ~10 MB, switch to `flyte.io.File` or `flyte.io.Dir`.

## Inline I/O Threshold

Control when data is passed inline vs by reference:

```python
@env.task(inline_output_limit="10MB")  # data > 10MB goes by reference
async def process(data: dict) -> dict:
    ...
```

Default threshold is generous. For ML training outputs or large DataFrames, set it lower to avoid overhead.

## Common Type Mistakes

1. **Missing type hints** — Flyte 2 requires type annotations on all task inputs/outputs. No type hint = serialization error.
2. **Passing `flyte.io.File` as a string** — always use `flyte.io.File(path=...)` objects. The path string alone won't serialize.
3. **Using Pandas instead of Polars** — Flyte 2's native DataFrame is Polars. Use `df.to_polars()` to get the underlying DataFrame.
4. **Not registering custom transformers** — if you register a custom type transformer, it must be registered before task execution.
5. **Forgetting `.path` on flyte.io.File** — inside a task, `file` is a FlyteFile object, not a string. Use `file.path` for the local path.
