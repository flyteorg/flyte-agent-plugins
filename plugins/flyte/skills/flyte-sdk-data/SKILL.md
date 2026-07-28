---
name: flyte-sdk-data
description: 'Handles data engineering patterns: ETL pipelines, data processing, data quality checks, fanout/map tasks, conditions, dynamic workflows, and batch data transformations. Use when the user wants to build ETL pipelines, process large datasets, run data quality checks, fan out data processing tasks, or handle batch data transformations. Trigger words: "ETL", "data pipeline", "data processing", "fanout", "map", "transform", "data quality", "parquet", "CSV", "batch", "extract", "load", "validate", "schema".'
---

# Flyte 2 SDK Data Engineering Skill

Build ETL pipelines, data processing workflows, and data quality checks with Flyte 2.

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

## ETL Pipeline Patterns

### Basic Extract-Transform-Load

```python
import flyte
import flyte.io

env = flyte.TaskEnvironment(
    name="etl-pipeline",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "pandas", "polars", "pyarrow", "boto3", "sqlalchemy",
    ),
)

@env.task(retries=3, cache="auto")
async def extract(source_uri: str) -> flyte.io.DataFrame:
    """Extract data from various sources."""
    import polars as pl
    if source_uri.endswith(".csv"):
        df = pl.read_csv(source_uri)
    elif source_uri.endswith(".parquet"):
        df = pl.read_parquet(source_uri)
    else:
        raise ValueError(f"Unsupported format: {source_uri}")
    return flyte.io.DataFrame(df)

@env.task(retries=2, cache="auto")
async def transform(df: flyte.io.DataFrame) -> flyte.io.DataFrame:
    """Clean and transform data."""
    inner = df.to_polars()
    cleaned = (
        inner
        .drop_nulls()
        .unique()
        .with_columns([
            pl.col("date").str.strptime(pl.Date, "%Y-%m-%d").alias("date_parsed"),
        ])
    )
    return flyte.io.DataFrame(cleaned)

@env.task(retries=1, cache="auto")
async def load(df: flyte.io.DataFrame, destination: str) -> str:
    """Load transformed data to destination."""
    inner = df.to_polars()
    if destination.endswith(".parquet"):
        inner.write_parquet(destination)
    elif destination.endswith(".csv"):
        inner.write_csv(destination)
    return destination

@env.task
async def etl_pipeline(source_uri: str, destination: str) -> dict:
    """Orchestrate the ETL pipeline."""
    raw = await extract(source_uri)
    cleaned = await transform(raw)
    loaded_path = await load(cleaned, destination)
    return {"source": source_uri, "destination": loaded_path}
```

### Multi-step ETL with intermediate storage

```python
@env.task(cache="auto")
async def extract_raw(source_uri: str) -> flyte.io.File:
    """Extract and save raw data to remote storage."""
    import polars as pl
    df = pl.read_csv(source_uri)
    path = "/tmp/raw.parquet"
    df.write_parquet(path)
    return flyte.io.File(path=path)

@env.task(cache="auto")
async def validate_raw(raw: flyte.io.File) -> dict:
    """Validate raw data quality."""
    df = pl.read_parquet(raw.path)
    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "null_counts": df.null_count().to_dict(),
    }

@env.task(cache="auto")
async def clean(raw: flyte.io.File) -> flyte.io.File:
    """Clean and normalize data."""
    df = pl.read_parquet(raw.path)
    cleaned = df.drop_nulls().unique()
    path = "/tmp/cleaned.parquet"
    cleaned.write_parquet(path)
    return flyte.io.File(path=path)

@env.task(cache="auto")
async def enrich(cleaned: flyte.io.File) -> flyte.io.File:
    """Enrich data with external features."""
    df = pl.read_parquet(cleaned.path)
    # Join with external feature store
    ...
    path = "/tmp/enriched.parquet"
    df.write_parquet(path)
    return flyte.io.File(path=path)

@env.task
async def load_enriched(enriched: flyte.io.File, destination: str) -> str:
    """Load enriched data to final destination."""
    ...
    return destination

@env.task
async def etl_with_validation(source_uri: str, destination: str) -> dict:
    """ETL pipeline with validation gates."""
    raw = await extract_raw(source_uri)
    quality = await validate_raw(raw)

    # Quality gate: fail if too many nulls
    if quality["null_counts"].get("critical_field", 0) / quality["row_count"] > 0.5:
        raise ValueError("Too many nulls in critical field")

    cleaned = await clean(raw)
    enriched = await enrich(cleaned)
    loaded = await load_enriched(enriched, destination)
    return {"quality": quality, "destination": loaded}
```

## Fan-out Data Processing

### Map over large datasets

```python
@env.task(cache="auto")
async def process_file(file_uri: str) -> flyte.io.DataFrame:
    """Process a single data file."""
    import polars as pl
    df = pl.read_parquet(file_uri)
    cleaned = df.drop_nulls().unique()
    return flyte.io.DataFrame(cleaned)

@env.task
async def process_dataset(file_uris: list[str]) -> list:
    """Fan out processing across all files in parallel."""
    results = await flyte.map(process_file, file_uris)
    return results

@env.task
async def merge_results(results: list) -> flyte.io.DataFrame:
    """Merge processed results into a single DataFrame."""
    import polars as pl
    combined = pl.concat([r.to_polars() for r in results])
    return flyte.io.DataFrame(combined)

@env.task
async def main(file_uris: list[str]) -> flyte.io.DataFrame:
    processed = await process_dataset(file_uris)
    return await merge_results(processed)
```

### Fan-out with error handling

```python
@env.task
async def process_file_safe(file_uri: str) -> dict:
    """Process a file with error handling."""
    try:
        df = await process_file(file_uri)
        return {"status": "success", "file": file_uri, "rows": len(df.to_polars())}
    except Exception as e:
        return {"status": "error", "file": file_uri, "error": str(e)}

@env.task
async def process_with_errors(file_uris: list[str]) -> dict:
    """Process files, collecting both successes and errors."""
    results = await flyte.map(process_file_safe, file_uris)
    successes = [r for r in results if r["status"] == "success"]
    errors = [r for r in results if r["status"] == "error"]
    return {"successes": successes, "errors": errors, "total": len(results)}
```

### Limited concurrency fan-out

```python
@env.task
async def main(file_uris: list[str]) -> list:
    """Fan out with limited concurrency."""
    import asyncio
    sem = asyncio.Semaphore(20)  # max 20 concurrent

    async def bounded(uri):
        async with sem:
            return await process_file(uri)

    return await asyncio.gather(*(bounded(u) for u in file_uris))
```

## Data Quality Checks

### Comprehensive data quality

```python
@env.task(cache="auto")
async def validate_schema(df: flyte.io.DataFrame, expected_schema: dict) -> dict:
    """Validate DataFrame schema matches expected schema."""
    inner = df.to_polars()
    checks = {}

    # Column names
    expected_cols = set(expected_schema.keys())
    actual_cols = set(inner.columns)
    checks["columns_match"] = expected_cols == actual_cols
    checks["missing_columns"] = list(expected_cols - actual_cols)
    checks["extra_columns"] = list(actual_cols - expected_cols)

    # Column types
    for col, expected_type in expected_schema.items():
        if col in inner.columns:
            actual_type = str(inner[col].dtype)
            checks[f"type_{col}"] = {
                "expected": expected_type,
                "actual": actual_type,
                "match": expected_type in actual_type,
            }

    return checks

@env.task(cache="auto")
async def validate_nulls(df: flyte.io.DataFrame, max_null_pct: float = 0.1) -> dict:
    """Validate null percentages per column."""
    inner = df.to_polars()
    row_count = len(inner)
    checks = {}

    for col in inner.columns:
        null_count = inner[col].null_count()
        null_pct = null_count / row_count if row_count > 0 else 0
        checks[col] = {
            "null_count": null_count,
            "null_pct": null_pct,
            "passed": null_pct <= max_null_pct,
        }

    return checks

@env.task(cache="auto")
async def validate_values(df: flyte.io.DataFrame, constraints: dict) -> dict:
    """Validate value constraints (ranges, enums, patterns)."""
    inner = df.to_polars()
    checks = {}

    for col, constraint in constraints.items():
        if col not in inner.columns:
            continue

        if "min" in constraint:
            checks[f"{col}_min"] = inner[col].min() >= constraint["min"]
        if "max" in constraint:
            checks[f"{col}_max"] = inner[col].max() <= constraint["max"]
        if "allowed_values" in constraint:
            unique = set(inner[col].unique())
            checks[f"{col}_values"] = unique.issubset(set(constraint["allowed_values"]))

    return checks

@env.task
async def data_quality_gate(
    df: flyte.io.DataFrame,
    schema: dict,
    max_null_pct: float = 0.1,
    constraints: dict = None,
) -> dict:
    """Run all data quality checks and pass/fail."""
    schema_check = await validate_schema(df, schema)
    null_check = await validate_nulls(df, max_null_pct)
    value_checks = await validate_values(df, constraints or {})

    all_passed = (
        schema_check["columns_match"]
        and all(c["passed"] for c in null_check.values())
        and all(value_checks.values())
    )

    return {
        "passed": all_passed,
        "schema": schema_check,
        "nulls": null_check,
        "values": value_checks,
    }
```

### Data quality with custom checks

```python
@env.task(cache="auto")
async def check_distribution(df: flyte.io.DataFrame, column: str, expected_stats: dict) -> dict:
    """Check if data distribution matches expected statistics."""
    inner = df.to_polars()
    col_data = inner[column].drop_nulls()

    actual_mean = col_data.mean()
    actual_std = col_data.std()
    actual_min = col_data.min()
    actual_max = col_data.max()

    return {
        "column": column,
        "mean": {"actual": actual_mean, "expected": expected_stats.get("mean"),
                 "within_tolerance": abs(actual_mean - expected_stats.get("mean", 0)) < expected_stats.get("tolerance", 0.1)},
        "std": {"actual": actual_std, "expected": expected_stats.get("std"),
                "within_tolerance": abs(actual_std - expected_stats.get("std", 0)) < expected_stats.get("tolerance", 0.1)},
    }
```

## Dynamic Workflows for Data

### Dynamic file processing

```python
@env.task
async def discover_files(prefix: str) -> list[str]:
    """Discover data files in a storage prefix."""
    import boto3
    s3 = boto3.client("s3")
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket="my-data-bucket", Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith((".parquet", ".csv")):
                files.append(f"s3://{obj['Bucket']}/{obj['Key']}")
    return files

@env.task
async def process_file(file_uri: str) -> flyte.io.File:
    """Process a single file."""
    import polars as pl
    df = pl.read_parquet(file_uri)
    cleaned = df.drop_nulls()
    path = f"/tmp/cleaned_{file_uri.split('/')[-1]}"
    cleaned.write_parquet(path)
    return flyte.io.File(path=path)

@env.task
async def merge_files(files: list[flyte.io.File]) -> flyte.io.File:
    """Merge processed files."""
    import polars as pl
    dfs = [pl.read_parquet(f.path) for f in files]
    combined = pl.concat(dfs)
    path = "/tmp/merged.parquet"
    combined.write_parquet(path)
    return flyte.io.File(path=path)

@env.task
async def dynamic_etl(prefix: str, destination: str) -> dict:
    """Dynamic ETL: discover files, process, merge."""
    files = await discover_files(prefix)
    processed = await flyte.map(process_file, files)
    merged = await merge_files(processed)
    # Copy to destination
    return {"source_prefix": prefix, "destination": destination, "file_count": len(files)}
```

### Conditional data routing

```python
@env.task
async def route_data(df: flyte.io.DataFrame, threshold: float) -> dict:
    """Route data based on quality score."""
    score = compute_quality_score(df)
    if score >= threshold:
        return {"route": "production", "score": score}
    else:
        return {"route": "review", "score": score}

@env.task
async def process_production(df: flyte.io.DataFrame) -> flyte.io.File:
    """Process data for production."""
    ...

@env.task
async def process_review(df: flyte.io.DataFrame) -> flyte.io.File:
    """Flag data for manual review."""
    ...

@env.task
async def conditional_pipeline(df: flyte.io.DataFrame, threshold: float) -> dict:
    """Route data based on quality."""
    routed = await route_data(df, threshold)
    if routed["route"] == "production":
        result = await process_production(df)
    else:
        result = await process_review(df)
    return {**routed, "result": result}
```

## JsonlFile and JsonlDir for Large Datasets

### JsonlFile — streaming JSONL

```python
@env.task
async def process_jsonl(path: str) -> int:
    """Process a JSONL file with streaming."""
    from flyte.extend import JsonlFile
    jf = JsonlFile(path)
    count = 0
    async for record in jf.stream():
        process(record)
        count += 1
    return count
```

### JsonlDir — batched JSONL directories

```python
@env.task
async def process_jsonl_dir(dir_path: str) -> dict:
    """Process JSONL directory with batched streaming."""
    from flyte.extend import JsonlDir
    jd = JsonlDir(dir_path)
    total = 0
    async for batch in jd.stream_batches():
        total += len(batch)
    return {"records": total}
```

## Data Format Reference

| Format | Flyte Type | Best For |
|---|---|---|
| Parquet | `flyte.io.DataFrame` | Tabular data, ETL |
| CSV | `flyte.io.File` | Small datasets, interchange |
| JSONL | `JsonlFile` / `JsonlDir` | Streaming records |
| JSON | inline (dict) | Small structured data |
| Pickle | `flyte.io.File` | Python objects |
| NumPy (.npy/.npz) | `flyte.io.File` | Arrays, embeddings |
| PNG/JPEG | `flyte.io.File` | Images |
| Model (.pt/.safetensors) | `flyte.io.File` | Model checkpoints |

## Performance Tips for Data Pipelines

1. **Use Parquet over CSV** — columnar format, compressed, faster I/O
2. **Cache idempotent transforms** — `cache="auto"` on ETL steps
3. **Fan out with `flyte.map`** — parallel processing for independent files
4. **Use `flyte.trace` for lightweight ops** — no container spin-up cost
5. **Set `raw_data_path`** — control where intermediate data is stored
6. **Use `inline_output_limit`** — control when data goes by reference vs inline
7. **Use `interruptible=True`** — spot instances for fault-tolerant data processing

## Anti-Patterns

1. **Don't load entire datasets into memory** — use streaming (`JsonlFile`, Polars lazy) for large data.
2. **Don't pass DataFrames inline** — they go by reference automatically, but small dicts do go inline.
3. **Don't skip data quality gates** — always validate before and after transforms.
4. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
