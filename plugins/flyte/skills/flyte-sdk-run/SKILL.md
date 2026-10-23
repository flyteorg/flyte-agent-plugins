---
name: flyte-sdk-run
description: 'Runs Flyte 2 workflows, interacts with runs and actions, retrieves logs and data, and manages run lifecycle. Use when the user wants to run a workflow, check run status, view logs, get run outputs, re-run a workflow, or manage runs programmatically. Trigger words: "run", "execute", "logs", "status", "output", "input", "watch", "rerun", "cancel", "abort", "run metadata", "action".'
---

# Flyte 2 SDK Run Skill

Run workflows, interact with runs, and manage the execution lifecycle.

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

## Tool Priority

1. **Flyte MCP** — if the harness has Flyte MCP tools, prefer them over shelling out to
   the CLI. They cover listing runs, fetching run details and inputs/outputs, polling to
   completion, executing a task, and aborting a run, and they return structured data
   instead of text you have to parse.
2. **`flyte` CLI** — for local run commands, and anything MCP does not expose
3. **Python SDK** — for programmatic run control

## Running Workflows

### Via Python SDK

```python
import flyte

if __name__ == "__main__":
    # Run with defaults from config
    result = flyte.run(main, inputs={"data": ["a", "b", "c"]})
    print(f"Run name: {result.name}")
    print(f"Status: {result.status}")
```

### Via CLI

```bash
# Run with local config
flyte run pipeline.py main --data '[1,2,3]'

# Run with specific project/domain
flyte run pipeline.py main --data '[1,2,3]' --project flytesnacks --domain development

# Run with custom run name
flyte run pipeline.py main --data '[1,2,3]' --name my-custom-run

# Run with specific image
flyte run pipeline.py main --data '[1,2,3]' --image ghcr.io/myorg/task:v1.0

# Run with local mode (in-process, no remote)
flyte run --local pipeline.py main --data '[1,2,3]'

# Run with TUI
flyte run --tui --local pipeline.py main --data '[1,2,3]'

# Pass arguments by type
flyte run pipeline.py main \
  --data '[1,2,3]' \
  --learning-rate 0.001 \
  --batch-size 32 \
  --train-data s3://bucket/train.parquet \
  --flag true
```

### Run command options

| Flag | Description |
|---|---|
| `--project` / `--domain` | Target project and domain |
| `--run-project` / `--run-domain` | Override run project/domain |
| `--local` | Run locally (in-process) |
| `--tui` | Terminal UI for local runs |
| `--name` | Custom run name |
| `--image` | Image mapping (named or default) |
| `--copy-style` | `loaded_modules` (default), `all`, `none` |
| `--root-dir` | Set root directory for code bundling |
| `--raw-data-path` | Override raw data path |
| `--service-account` | K8s service account |
| `--follow` | Follow run progress |
| `--no-sync-local-sys-paths` | Skip local sys path sync |

### Passing inputs by type

```bash
# List
flyte run pipeline.py main --data '[1,2,3]'

# Dict
flyte run pipeline.py main --config '{"lr": 0.001, "epochs": 10}'

# Boolean
flyte run pipeline.py main --flag true

# Datetime
flyte run pipeline.py main --date '2025-01-01T00:00:00'

# Duration
flyte run pipeline.py main --timeout '1h'

# File
flyte run pipeline.py main --input-file s3://bucket/data.parquet

# DataFrame (via file path)
flyte run pipeline.py main --data-file /path/to/data.parquet
```

## Interacting with Runs

### Using Flyte MCP

If Flyte MCP tools are available, prefer them for all of the above — listing runs,
fetching a run's details, polling until it completes, and reading its inputs and outputs.


### Using CLI

```bash
# List runs
flyte get run --project flytesnacks --domain development

# Get run info
flyte get run <run_name> --project flytesnacks --domain development

# Watch run progress
flyte get run <run_name> --project flytesnacks --domain development

# Get run outputs
flyte get io <run_name> --project flytesnacks --domain development

# Download run artifacts
flyte get io <run_name> --outputs-only --project flytesnacks --domain development
```

### Using Python SDK

```python
import flyte

# Run and get handle
result = flyte.run(main, inputs={"data": ["a", "b"]})

# Check status
print(result.status)  # RUNNING, SUCCEEDED, FAILED, CANCELED

# Wait for completion
result.wait()

# Get outputs
print(result.outputs)

# Get URL in console
print(result.url)
```

## Viewing Logs

### Using CLI

```bash
# Stream logs
flyte get logs <run_name> --project flytesnacks --domain development

# View logs for a specific attempt
flyte get logs <run_name> --attempt 0

# Filter system logs
flyte get logs <run_name> --filter-system

# Scope to project/domain
flyte get logs <run_name> --project flytesnacks --domain development
```

### CLI log options

| Flag | Description |
|---|---|
| `--attempt` / `-a` | View specific attempt logs |
| `--filter-system` | Filter out system logs |
| `--pretty` | Auto-scrolling box (limited to `--lines`) |
| `--project` / `--domain` | Scope logs |

### Using Python SDK

```python
import flyte

result = flyte.run(main, inputs={"data": ["a"]})

# Logs are retrieved via the CLI: `flyte get logs <run_name>`
print(result.url)  # open the run in the UI to view logs
```

## Re-running Runs (rerun)

Every run is durable: its task, code, inputs, and configuration are recorded on the backend. `flyte rerun` / `flyte.rerun()` relaunches a new run from a previous one **without needing the original code checked out locally** — task and inputs are fetched from the platform.

### CLI

```bash
# Rerun with the prior run's exact code and inputs
flyte rerun <run-name>

# Give the new run a name and stream its parent-action logs
flyte rerun <run-name> --name retry-1 --follow

# Override an env var / set a label on the new run
flyte rerun <run-name> -e LOG_LEVEL=20 --label team=ml

# Rerun with a different input value (converted against the prior run's interface)
flyte rerun <run-name> --threshold 0.9
```

| Option | Description |
|---|---|
| `-p` / `-d` | Project / domain for the new run |
| `--name` | Name for the new run |
| `-e KEY=VALUE` | Override an environment variable (repeatable) |
| `--label KEY=VALUE` | Set a label (repeatable) |
| `-f` / `--follow` | Stream the parent action's logs after launch |

> [!NOTE] `flyte rerun` is **not** `flyte run`. `flyte run <file> <task>` uses your local code and CLI inputs; `flyte rerun <run>` fetches both from the backend. To keep the successful actions of a failed run and re-execute only what failed, add `--recover` — see **Recover a failed run** below.

### Python SDK

```python
import flyte
flyte.init_from_config()

# Rerun with the prior run's exact inputs (task + inputs fetched from the platform)
r = flyte.rerun("ul56wcvgqrb9vzhzz5l2")

# Change inputs — converted against the prior run's interface
r = flyte.rerun("ul56wcvgqrb9vzhzz5l2", x_list=[1, 2, 3])

# Control launch settings with flyte.with_runcontext(...)
flyte.with_runcontext(name="retry-1", env_vars={"LOG_LEVEL": "20"}).rerun("ul56wcvgqrb9vzhzz5l2")
```

`flyte.rerun()` returns a `flyte.remote.Run`, so you can wait on it and read outputs exactly like `flyte.run()`.

## Recover a failed run

**Recovery** launches a new run that **reuses the successful actions** of a previous run and re-executes only what failed or never ran. A reused action is not executed again: its recorded output is handed to whatever consumes it. Recovery is remote-only (not supported in `--local`).

Recovery differs from caching:

- **Caching** is content-addressed (keyed on inputs + task version), enabled per task in code, reusable across any run.
- **Recovery** is scoped to one named run, needs **no** task preparation in code, and is opted in per run at launch (`--recover`).

### Recover from the CLI

```bash
# Reuse the prior run's succeeded actions, re-running only what failed or never ran
flyte rerun <run-name> --recover --follow

# Force specific actions to re-execute even though they succeeded
flyte rerun <run-name> --recover --force-rerun-action a3 --force-rerun-action a7

# Re-run a single action on its own, rooted at its task with its recorded inputs
flyte rerun <run-name> --action-name a3

# Proceed even if the source run's outputs were cleaned up from storage
flyte rerun <run-name> --recover --allow-missing-outputs
```

| Option | Description |
|---|---|
| `--recover` | Reuse succeeded actions; re-run only what failed or never ran |
| `--action-name <action>` | Re-run only this action (cannot be combined with `--recover`) |
| `--force-rerun-action <action>` | With `--recover`, re-execute an action that already succeeded (repeatable) |
| `--allow-missing-outputs` | Proceed when the source run's outputs were cleaned up |
| `-e` / `--env KEY=VALUE` | Set an env var on the new run |

Action names are deterministic hashes, not positions — list them with `flyte get action <run-name>`. Reused actions land in the `RECOVERED` phase (terminal, success-equivalent), so `flyte get action <run-name>` shows exactly what recovery skipped.

> [!WARNING] Recovered actions keep their **original** outputs. Recovery does not recompute them against new inputs — name the actions that must re-execute in `--force-rerun-action`.

### Recover programmatically

```python
import flyte
flyte.init_from_config()

# Re-run everything with the prior run's inputs
flyte.rerun("<run-name>")

# Reuse the succeeded actions, re-running only what failed or never ran
flyte.rerun("<run-name>", recover=True)

# Force specific actions to re-execute even though they succeeded
flyte.rerun("<run-name>", recover=True, force_rerun_actions=["a3", "a7"])

# Change inputs, keeping the ones you leave out, and still reuse succeeded actions
flyte.rerun("<run-name>", recover=True, threshold=0.9)

# Re-run a single action rooted at its task
flyte.rerun("<run-name>", action_name="a3")

flyte.with_runcontext(name="retry-1", env_vars={"LOG_LEVEL": "20"}).rerun("<run-name>", recover=True)
```

> [!NOTE] Task inputs share the keyword namespace with these arguments, so a task input named `run_name`, `action_name`, `recover`, `force_rerun_actions`, or `allow_missing_source_outputs` cannot be passed via `flyte.rerun`.

## Running Tasks (vs Workflows)

### Run a single task

```bash
# Ephemeral run (deploy + run in one command)
flyte run pipeline.py preprocess --data '[1,2,3]'

# Run a deployed task
flyte run --task-name preprocess --project flytesnacks --domain development \
  --inputs '{"data": "[1,2,3]"}'
```

### Using Flyte MCP

Executing a registered task is available as an MCP tool, taking project, domain, task name,
version, and inputs.


## Run Context Configuration

### Programmatic run context

```python
import flyte

# Configure a run programmatically
result = flyte.run(
    main,
    inputs={"data": ["a", "b"]},
    run_context=flyte.with_runcontext(
        project="flytesnacks",
        domain="development",
        raw_data_path="s3://my-bucket/{run_id}/",
        service_account="my-sa",
    ),
)
```

### Reading run context inside a task

```python
@env.task
async def my_task(data: str) -> str:
    # Access run metadata inside the task
    ctx = flyte.ctx()
    print(f"Run: {ctx.run_id}")
    print(f"Project: {ctx.project}")
    print(f"Domain: {ctx.domain}")
    print(f"Version: {ctx.version}")
    return data
```

## Abort and Cancel Runs

### CLI

```bash
# Abort a run
flyte abort run <run_name> --project flytesnacks --domain development
```

### Python SDK

```python
import flyte

result = flyte.run(main, inputs={"data": ["a"]})
result.abort()
```

### Using Flyte MCP

Aborting a run is available as an MCP tool, taking the run name.


## Programmatic Abort from Within a Task

```python
@env.task
async def long_task(data: str) -> str:
    import asyncio
    import signal

    async def check_abort():
        while True:
            if asyncio.current_task().cancelled():
                raise asyncio.CancelledError("Run was aborted")
            await asyncio.sleep(1)

    # Start abort watcher
    watcher = asyncio.create_task(check_abort())

    try:
        # Long-running work
        await asyncio.sleep(3600)
    finally:
        watcher.cancel()
        await watcher

    return data
```

## Run Data Access

### Accessing large data from cloud storage

```python
import flyte
import flyte.io

@env.task
async def get_run_data(run_name: str) -> flyte.io.File:
    """Download artifacts from a past run."""
    # Flyte stores outputs in the metadata bucket
    # Access via the SDK's data retrieval methods
    ...

@env.task
async def upload_local_data(file_path: str) -> flyte.io.File:
    """Upload local file to remote storage for a run."""
    return await flyte.io.File.from_local(file_path)
```

### S3 / GCS / Azure access

```python
# S3
import boto3
s3 = boto3.client("s3")
obj = s3.get_object(Bucket="my-bucket", Key="run-artifacts/output.parquet")

# GCS
from google.cloud import storage
client = storage.Client()
bucket = client.bucket("my-bucket")
blob = bucket.blob("run-artifacts/output.parquet")

# Azure
from azure.storage.blob import BlobServiceClient
client = BlobServiceClient(account_url="https://myacct.blob.core.windows.net/")
blob = client.get_blob_client(container="my-container", blob="output.parquet")
```

## Run Modes

### Local execution

```bash
# In-process (no remote backend needed)
flyte run --local pipeline.py main --data '[1,2,3]'

# With TUI
flyte run --tui --local pipeline.py main --data '[1,2,3]'
```

### Devbox

```bash
# Start local dev environment
flyte start devbox

# Create config for devbox
flyte create config \
    --endpoint localhost:30080 \
    --project flytesnacks \
    --domain development \
    --builder local \
    --insecure

# Run on devbox
flyte run pipeline.py main --data '[1,2,3]'
```

### Remote execution

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
```

## Anti-Patterns

1. **Don't confuse `flyte run` (workflow) with `flyte run --task-name` (single task)** — use the right command for your intent.
2. **Don't skip `--follow`** when running long workflows — you won't see progress.
3. **Don't hardcode run names** — let Flyte generate them, or use meaningful prefixes.
4. **Don't access run data directly from S3/GCS** — use Flyte's data retrieval methods when possible.
5. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
