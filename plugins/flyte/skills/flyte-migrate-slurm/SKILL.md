---
name: flyte-migrate-slurm
description: Migrates Slurm (sbatch/srun) HPC workloads to Flyte 2 (the flyte Python SDK) — job scripts become typed tasks, `#SBATCH` pragmas become TaskEnvironment config, job arrays become flyte.map or asyncio.gather, and multi-node training becomes a clustered task environment. Use when porting an HPC or supercomputer cluster workload off Slurm, translating `#SBATCH` pragmas, or replacing sbatch chains, job arrays, and module load with Flyte. Trigger words are sbatch, srun, SLURM, `#SBATCH`, HPC, job array, partition, squeue, sinfo, module load, scancel, supercomputer, cluster migration.
---

# Slurm to Flyte 2 Migration Skill

Slurm schedules jobs. Somewhere along the way ML work stopped being jobs and became pipelines — a data prep step, a training step, an eval step, a sweep over configs, each with different hardware and failure characteristics. A Slurm job is a bash script with `#SBATCH` pragmas at the top; in Flyte 2 that script becomes a typed Python function decorated with `@env.task`, a pipeline is just a task that calls other tasks, and control flow is plain Python. This skill maps the Slurm surface area onto the Flyte 2 SDK and is honest about the places where Slurm still wins.

## Grounding References

| Resource          | URL                                                              |
| ----------------- | ---------------------------------------------------------------- |
| Migration guide   | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/ |
| Official docs     | https://www.union.ai/docs/v2/flyte                               |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt                      |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/      |
| Example code      | https://github.com/unionai/unionai-examples                      |
| Flyte MCP tools   | Available via `flyte-mcp` server                                 |

## Three mental shifts

Almost every point of friction for a Slurm migrant traces back to one of these three.

### 1. Modules become images

On Slurm you `module load cuda/12.1`, activate a venv on NFS, and hope the login node and the compute node agree. In Flyte 2 the environment is declared once, in Python, as a `flyte.Image`. There is no Dockerfile to write: images are built remotely and content-hashed, so an unchanged spec is a cache hit and a changed one rebuilds automatically.

```python
image = (
    flyte.Image.from_debian_base(python_version=(3, 12))
    .with_pip_packages("torch", "transformers", "datasets")
    .with_env_vars({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
```

### 2. The shared filesystem becomes explicit data

There is no shared `/home` or `/scratch` that every node sees. Instead you pass `flyte.io.File` and `flyte.io.Dir` — typed references to object storage that stream rather than copy. This is more typing than `/scratch/$USER/run17/ckpt.pt`, and in exchange you get lineage for free: every input and output of every task is recorded, so "which dataset produced this checkpoint" is a question the system answers instead of a question you grep for. If you genuinely need a parallel filesystem (Lustre, GPFS, FSx), mount it through a CSI driver and a `flyte.PodTemplate` — that path stays open.

### 3. Job scripts become functions

`sbatch` chains held together by `--dependency=afterok`, sentinel files on NFS, and a cron job that polls for them all collapse into ordinary Python: call a function, await it, branch on the result. Binaries you can't or won't rewrite in Python still run — as container tasks with typed inputs and outputs.

## Migration Cheat Sheet

| Slurm                                             | Flyte 2                                                     |
| ------------------------------------------------- | ----------------------------------------------------------- |
| `sbatch train.sh`                                 | `flyte run train.py main`                                   |
| `srun --pty python train.py` (interactive)        | `flyte run --local train.py main`, or a devbox              |
| `#SBATCH --gres=gpu:a100:8`                       | `flyte.Resources(gpu="A100:8")`                             |
| `#SBATCH --cpus-per-task=16 --mem=64G`            | `flyte.Resources(cpu=16, memory="64Gi")`                    |
| `#SBATCH --tmp=100G`                              | `flyte.Resources(disk="100Gi")`                             |
| `#SBATCH --array=0-999`                           | `flyte.map(step, range(1000), concurrency=200)`             |
| `#SBATCH --nodes=4 --ntasks-per-node=8`           | `ClusteredTaskEnvironment(replicas=4, nproc_per_node=8)`    |
| `#SBATCH --partition=gpu --qos=high`              | `queue="gpu-high"` (queue must exist in cluster config)     |
| `#SBATCH --requeue`                               | `retries=3` plus `interruptible=True` for spot              |
| `#SBATCH --time=04:00:00`                         | `timeout=timedelta(hours=4)`                                |
| `#SBATCH --begin=...` / a crontab entry           | `flyte.Trigger(...)` with `flyte.Cron(...)`                 |
| `#SBATCH --dependency=afterok:$JOBID`             | Plain Python — call the next task after the first returns   |
| `module load cuda && source venv/bin/activate`    | `flyte.Image.from_debian_base().with_pip_packages(...)`     |
| `$SLURM_PROCID`, `$SLURM_NNODES`, `$SLURM_NTASKS` | `flyte.ctx().rank`, `.nnodes`, `.world_size`                |
| `$SLURM_ARRAY_TASK_ID`                            | The argument you mapped over                                |
| `/scratch/$USER/data.parquet`                     | `flyte.io.File` / `flyte.io.Dir` passed between tasks       |
| `squeue`, `sacct`                                 | `flyte get run`, `flyte get logs`, the UI                   |
| `scancel <jobid>`                                 | `flyte stop`, or abort from the UI                          |
| `srun --pty bash` / `ssh node042`                 | `flyte run --debug ...`, or `flyte debug <run-name>` (beta) |

## The job script becomes a task

This is the canonical translation. Everything above the `module load` line is configuration and moves onto the `TaskEnvironment` or the task decorator; everything below it is the function body.

### Slurm

```bash
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:8
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --requeue

module load cuda/12.1
source ~/venvs/train/bin/activate
srun python train.py --lr 3e-4
```

### Flyte 2

```python
from datetime import timedelta

import flyte
from flyte.io import File

env = flyte.TaskEnvironment(
    name="training",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages("torch"),
    resources=flyte.Resources(cpu=16, memory="64Gi", gpu="A100:8"),
)


@env.task(retries=3, timeout=timedelta(hours=4))
async def train(lr: float = 3e-4) -> File:
    import torch

    model = build_model().cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    ...  # the same training loop that was in train.py
    torch.save(model.state_dict(), "model.pt")
    return await File.from_local("model.pt")
```

```bash
flyte run train.py train --lr 3e-4     # remote (the sbatch equivalent)
flyte run --local train.py train       # same code, on your laptop
flyte deploy train.py env              # register the environment + triggers
```

The `#SBATCH --time` line has a richer counterpart than a single number. `timeout=` accepts a `timedelta`, an int number of seconds, or a `flyte.Timeout` object that separates the budgets Slurm collapses into one:

```python
@env.task(
    retries=2,
    timeout=flyte.Timeout(
        max_runtime=timedelta(hours=4),      # per-attempt wall clock
        max_queued_time=timedelta(minutes=30),  # fail fast if capacity never appears
        deadline=timedelta(hours=10),        # absolute budget across all attempts
    ),
)
async def train(...) -> File: ...
```

## Job arrays and sweeps

A Slurm array plus a results-collection script is two artifacts held together by a filename convention. In Flyte 2 the fan-out and the reduction live in the same function.

### Slurm

```bash
#!/bin/bash
#SBATCH --array=0-63
#SBATCH --gres=gpu:1
CONFIG=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" configs.txt)
python train.py --config "$CONFIG" --out "/scratch/$USER/sweep/$SLURM_ARRAY_TASK_ID.json"
# ...then a separate job, after the array drains, to read 64 JSON files and pick a winner.
```

### Flyte 2

```python
import asyncio

import flyte

env = flyte.TaskEnvironment(
    name="sweep",
    image=flyte.Image.from_debian_base().with_pip_packages("torch"),
    resources=flyte.Resources(cpu=8, memory="32Gi", gpu="L4:1"),
)


@env.task
async def train_one(lr: float, batch_size: int) -> float:
    ...  # returns a validation metric
    return val_loss


@env.task
async def sweep() -> dict:
    configs = [(lr, bs) for lr in (1e-4, 3e-4, 1e-3) for bs in (16, 32, 64)]
    # Small fan-out: gather is the most direct translation of an array job.
    losses = await asyncio.gather(*[train_one(lr, bs) for lr, bs in configs])
    # Picking the winner is plain Python — no second job, no sentinel files.
    best = min(range(len(losses)), key=lambda i: losses[i])
    return {"lr": configs[best][0], "batch_size": configs[best][1], "loss": losses[best]}
```

For a 10,000-element array, `flyte.map` gives you a bounded fan-out with a concurrency cap — the `%` throttle in `--array=0-9999%200`:

```python
@env.task
async def big_sweep(n: int = 10_000) -> float:
    # flyte.map returns a generator; wrap it in list() to materialize.
    losses = list(flyte.map(train_one_indexed, range(n), concurrency=200))
    return min(losses)
```

## Job dependencies become function calls

`--dependency=afterok:$JOBID` is the construct that most often turns into a shell script full of `sbatch --parsable` and `awk`. It has no counterpart in Flyte 2 because it doesn't need one: awaiting a task _is_ the dependency, and the value it returns _is_ the handoff.

### Slurm

```bash
PREP=$(sbatch --parsable prep.sh)
TRAIN=$(sbatch --parsable --dependency=afterok:$PREP train.sh)
sbatch --dependency=afterok:$TRAIN eval.sh
```

### Flyte 2

```python
from flyte.io import Dir, File


@env.task
async def pipeline(raw: Dir) -> float:
    prepared = await prep(raw)         # runs first
    model = await train(prepared)      # waits for prep, gets its output directly
    return await evaluate(model, prepared)
```

Branching that Slurm can't express at all — `afterok` on one job but `afternotok` on another, or "promote only if the eval didn't regress" — is just `try`/`except` and `if`:

```python
@env.task
async def pipeline_with_gate(raw: Dir) -> str:
    prepared = await prep(raw)
    try:
        model = await train(prepared)
    except Exception:
        model = await train_with_fallback_config(prepared)
    if await evaluate(model, prepared) < 0.85:
        return "held back"
    await promote(model)
    return "promoted"
```

## Data: from `/scratch` to typed references

The Slurm version writes to a path both jobs happen to agree on. The Flyte version passes a value.

### Slurm

```bash
# prep.sh
python prep.py --in /scratch/$USER/raw --out /scratch/$USER/prepared

# train.sh — coupled to prep.sh only by this string
python train.py --data /scratch/$USER/prepared --ckpt /scratch/$USER/ckpt.pt
```

### Flyte 2

```python
import flyte
from flyte.io import Dir, File


@env.task
async def prep(raw: Dir) -> Dir:
    local = await raw.download()
    ...  # write outputs into ./prepared
    return await Dir.from_local("prepared")


@env.task
async def train(prepared: Dir) -> File:
    local = await prepared.download()  # streams from object storage to this pod
    ...
    return await File.from_local("ckpt.pt")
```

Scratch space _inside_ a task is still just the local filesystem — request it with `flyte.Resources(disk="100Gi")` and use `os.getcwd()`. What changes is that anything another task needs must leave as a typed output. If a parallel filesystem is non-negotiable (a dataset too large or too latency-sensitive to stream), mount it with a CSI driver through `pod_template=flyte.PodTemplate.from_spec(pod_spec_with_lustre_pvc)` on the `TaskEnvironment`.

## Multi-node training

`--nodes=4 --ntasks-per-node=8` with `srun` as the launcher becomes a `ClusteredTaskEnvironment`. It launches its replicas as a single Kubernetes JobSet, runs `torchrun` rendezvous across them, and exposes the standard `RANK` / `WORLD_SIZE` / `MASTER_ADDR` environment variables — so training code written for `torchrun` needs no changes. The same values are on `flyte.ctx()`.

### Slurm

```bash
#!/bin/bash
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --gres=gpu:h100:8
export MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
srun python -m torch.distributed.run --nnodes=4 --nproc_per_node=8 pretrain.py
```

### Flyte 2

```python
import flyte
from flyte.clustered import ClusteredTaskEnvironment, ClusterFailurePolicy, TorchRun

env = ClusteredTaskEnvironment(
    name="pretrain",
    image=image,
    resources=flyte.Resources(cpu=16, memory="64Gi", gpu="H100:8", shm="auto"),
    replicas=4,          # pods == nodes
    nproc_per_node=8,    # processes per pod  =>  world size 32
    runtime=TorchRun(rdzv_backend="c10d"),  # "static" relies on JobSet restarts instead
    failure_policy=ClusterFailurePolicy(max_restarts=2, restart_on_host_maintenance=True),
)


@env.task
async def pretrain(steps: int = 10_000) -> File:
    import torch
    import torch.distributed as dist

    ctx = flyte.ctx()
    torch.cuda.set_device(ctx.local_rank or 0)
    dist.init_process_group(backend="nccl")  # torchrun already set RANK/WORLD_SIZE/MASTER_ADDR
    print(f"rank {ctx.rank}/{ctx.world_size} on node {ctx.node_rank}/{ctx.nnodes}", flush=True)

    ...  # the same DDP/FSDP loop you ran under srun

    dist.barrier()
    dist.destroy_process_group()
    # Only rank 0 has anything to return.
    return await File.from_local("ckpt.pt")
```

`restart_on_host_maintenance=True` is the piece with no Slurm analogue: a node reclaimed by the cloud provider (spot reclaim, host maintenance, drain) restarts the whole set _for free_, leaving the `max_restarts` budget untouched, so an unreliable cluster can't burn the budget you reserved for real bugs.

A clustered task is a worker, not a driver — it cannot launch subtasks. To compose distributed steps, orchestrate from a plain `TaskEnvironment` that declares `depends_on=[clustered_env]`:

```python
driver_env = flyte.TaskEnvironment(
    name="driver",
    image=image,
    resources=flyte.Resources(cpu=1, memory="1Gi"),
    depends_on=[env],  # without this, awaiting pretrain() fails on image-cache lookup
)


@driver_env.task
async def main(steps: int = 10_000) -> float:
    ckpt = await pretrain(steps)   # JobSet #1
    return await evaluate(ckpt)    # JobSet #2
```

Ephemeral, per-task Ray / Spark / Dask clusters (via the `flyteplugins-ray`, `flyteplugins-spark`, and `flyteplugins-dask` integrations) replace the long-lived clusters an HPC site usually stands up by hand — they exist for the duration of the task and are torn down with it.

## Fault tolerance: `--requeue`, decomposed

`#SBATCH --requeue` restarts the job from the top and hopes you wrote your own checkpoint logic. Flyte 2 splits that into four independent mechanisms you compose.

**Retries, declaratively.** `retries=3` on the decorator, or a `RetryStrategy` when you want backoff:

```python
@env.task(
    retries=flyte.RetryStrategy(
        count=4,
        backoff=flyte.Backoff(base=timedelta(seconds=10), factor=2.0, cap=timedelta(minutes=5)),
    ),
)
async def flaky_download(url: str) -> File: ...
```

**Spot capacity, safely.** `interruptible=True` says the task may run on preemptible instances. Preemptions are tracked as _system_ failures and do not consume your retry budget, and the final attempt falls back to on-demand — so `interruptible=True, retries=2` means two spot attempts and one guaranteed on-demand attempt. Set it on the environment, override it per task:

```python
env = flyte.TaskEnvironment(name="sweep", image=image, interruptible=True)


@env.task(interruptible=False)  # the one step you don't want preempted
async def publish(model: File) -> str: ...
```

**Checkpoints that survive node changes.** Checkpoints go to object storage, not `/scratch`, so a retry resumes on whatever node it lands on. No shared filesystem required:

```python
@env.task(retries=3)
async def train(n_epochs: int = 100) -> int:
    checkpoint = flyte.ctx().checkpoint
    path = await checkpoint.load()            # None on the first attempt
    start = int(path.read_bytes()) if path else 0

    for epoch in range(start, n_epochs):
        ...
        await checkpoint.save(f"{epoch + 1}".encode())
    return n_epochs
```

**Durable function calls.** `@flyte.trace` records the result of an individual function call inside a task. On a retry, recorded calls are skipped instead of re-executed — the granularity Slurm has no way to express:

```python
@flyte.trace
async def call_expensive_api(prompt: str) -> str:
    ...  # on retry, an already-recorded call replays instead of re-running
```

**Caching.** Task-level caching is keyed on the code and the inputs, so rerunning a twelve-hour pipeline after fixing step nine starts at step nine:

```python
env = flyte.TaskEnvironment(name="etl", image=image, cache="auto")
```

## Warm pools

Slurm feels fast at submit time because the allocation is already running — `srun` inside an existing allocation starts in milliseconds. `flyte.ReusePolicy` is the equivalent: containers stay warm between tasks, keeping in-memory state, so a model loaded once serves thousands of task invocations.

```python
env = flyte.TaskEnvironment(
    name="scorer",
    image=image,
    resources=flyte.Resources(cpu=4, memory="16Gi", gpu="L4:1"),
    reusable=flyte.ReusePolicy(
        replicas=(2, 10),   # autoscaling range; a bare int pins the count
        concurrency=4,      # concurrent tasks per replica (async tasks only)
        idle_ttl=300,       # shut the environment down after 5 idle minutes
    ),
)
```

The caveat is the same one that bites long-lived Slurm allocations: the process outlives the task. Treat module-level globals and caches deliberately, and don't let one task's state leak into the next.

## Existing binaries

A Fortran solver, a C++ simulator, a genomics tool — anything you're not rewriting runs as a `ContainerTask` with typed inputs and outputs. Inputs are staged into `input_data_dir`, and whatever the command writes into `output_data_dir` is read back as the declared types.

```python
from flyte.extras import ContainerTask
from flyte.io import File

align = ContainerTask(
    name="align_reads",
    image="quay.io/biocontainers/bwa:0.7.17",
    resources=flyte.Resources(cpu=16, memory="64Gi"),
    inputs={"reference": File, "reads": File},
    outputs={"alignment": File},
    input_data_dir="/var/inputs",
    output_data_dir="/var/outputs",
    file_input_layout="NAMED_DIR",  # preserves original filenames + extensions
    command=[
        "/bin/sh", "-c",
        "bwa mem /var/inputs/reference/* /var/inputs/reads/* > /var/outputs/alignment",
    ],
)


@env.task
async def main(reference: File, reads: File) -> File:
    return await align(reference=reference, reads=reads)
```

## Scheduling, monitoring, and interactive work

`#SBATCH --begin=` and the crontab that wraps most recurring HPC work become a `flyte.Trigger` attached to the task and deployed with it:

```python
from datetime import datetime

nightly = flyte.Trigger(
    name="nightly_retrain",
    automation=flyte.Cron("0 2 * * *", timezone="America/Los_Angeles"),
    inputs={"start_time": flyte.TriggerTime, "lr": 3e-4},
    auto_activate=True,
)


@env.task(triggers=nightly)
async def retrain(start_time: datetime, lr: float) -> File: ...
```

For monitoring, `squeue` and `sacct` become `flyte get run` and `flyte get logs` (or the UI, which shows the pipeline structure rather than a flat job list):

```bash
flyte get run                                  # like squeue
flyte get run <run_name>                       # detail for one run
flyte get logs <run_name> --attempt 0          # like sacct + tailing a slurm-*.out
flyte stop <run_name>                          # like scancel
```

`srun --pty bash` and `ssh node042` have two counterparts. `flyte run --debug` opens a browser-based VS Code session in the task pod:

```bash
flyte run --debug train.py train --lr 3e-4
```

```python
run = flyte.with_runcontext(debug=True).run(train, lr=3e-4)
print(run.get_debug_url())
```

SSH into the running task is available in beta (requires `flyteplugins-union`) and is closer to the muscle memory of `ssh` onto a compute node:

```bash
flyte debug <run-name> --write-config
ssh flyte-debug
```

## Migration order that works

Do not start with the thing Slurm does best.

1. **Pipeline-shaped work first** — data processing, evals, sweeps, batch inference, RL rollouts. These are multi-step, embarrassingly parallel, and failure-prone in boring ways, so composition, caching, and retries pay off on day one. They also exercise images and data plumbing on workloads where a bad hour costs little.
2. **Single-node training next** — one `TaskEnvironment`, one GPU resource string, checkpoints to object storage. At this point you've validated that your image builds, your data streams, and your logs are where you expect.
3. **Multi-node training last** — once images, data, and observability are proven. `ClusteredTaskEnvironment` is the piece with the most moving parts and the least tolerance for a half-migrated environment.

Nothing forces a big bang: Slurm and Flyte can run side by side indefinitely, and a Flyte task can `subprocess` out to `sbatch` during the overlap if you need a bridge.

## Gotchas

- **`flyte.map` returns a generator.** Wrap it in `list()` to materialize results.
- **`memory`, not `mem`.** And GPUs use a combined `"A100:8"` string — type and count together, not `--gres` plus a separate accelerator argument.
- **`shm="auto"` matters for PyTorch DataLoader.** The container default `/dev/shm` is tiny; multi-worker data loading will fail cryptically without it.
- **A clustered task cannot launch subtasks.** Orchestrate from a plain `TaskEnvironment` with `depends_on=[clustered_env]`, or you'll hit an image-cache lookup failure at runtime.
- **`nproc_per_node` must not exceed the GPU count.** `ClusteredTaskEnvironment` validates this locally and raises `ValueError` before anything is submitted.
- **Only rank 0 should return outputs.** Every replica runs the task body; have non-zero ranks return early or return a trivial value.
- **Retries have no platform cap.** Total attempts equal `retries + 1`, so audit any large values ported from a `--requeue` habit.
- **`interruptible=True` with zero retries runs on-demand.** The final attempt always falls back off spot, and a single attempt _is_ the final attempt.
- **Clustered tasks are torchrun-focused.** Classic MPI HPC codes (`mpirun`, tightly-coupled CFD, molecular dynamics) are not the target. Keep those on Slurm.
- **Gang scheduling and topology-aware placement are still maturing on Kubernetes.** Slurm's scheduler has decades of work behind co-scheduling N nodes on the same rack or fabric; the Kubernetes ecosystem is closing the gap but is not there.
- **Queues order work; they don't preempt it.** `queue="gpu-high"` is the nearest analogue to `--partition` plus `--qos`, but a lower-priority task already running is not interrupted. Queue names must exist in your cluster configuration, and the feature is platform-dependent — check what your deployment supports before designing around it.
- **Frontier scale is still Slurm's.** Hundreds of GPUs per job with explicit InfiniBand topology control is where Slurm keeps winning. Migrate the pipeline layer; be deliberate about the rest.

## Anti-Patterns

1. **Don't recreate `/scratch` as a hardcoded bucket path.** Pass `flyte.io.File` / `flyte.io.Dir` between tasks. Two tasks agreeing on a string is exactly the coupling you're migrating away from — and it forfeits the lineage you get for free.
2. **Don't port `#SBATCH` pragmas onto every task decorator.** Image, resources, cache, and interruptibility belong on a shared `flyte.TaskEnvironment`; override per task only where a task genuinely differs.
3. **Don't translate `--dependency=afterok` into a sentinel-file poll.** Await the task and use its return value.
4. **Don't keep the array-plus-collector split.** After `asyncio.gather` or `flyte.map`, reduce in plain Python inside the same task.
5. **Don't `srun` inside a task.** The task body _is_ the rank's process. For multi-node, use `ClusteredTaskEnvironment` and let torchrun do the launching.
6. **Don't checkpoint to a local path and expect a retry to find it.** Use `flyte.ctx().checkpoint` or write a `File` to object storage — a retry may land on a different node.
7. **Don't do heavy compute in an orchestrating task.** A task that calls other tasks is a driver pod; CPU-bound work between awaits stalls everything downstream.
8. **Don't lean on global state in a reusable environment.** `ReusePolicy` keeps the process alive across tasks — cache the model deliberately, and don't let mutable state leak between invocations.
9. **Don't migrate tightly-coupled MPI simulation first (or at all).** Start with pipeline-shaped work; leave the workloads Slurm is genuinely better at on Slurm.

## Related skills

- **`flyte-sdk-ml`** — greenfield ML authoring in Flyte 2 (training, HPO, inference) once the migration shape is clear.
- **`flyte-migrate`** — the entry point if you _also_ have Flyte 1 (`flytekit`) code to port.
- **`flyte-sdk-ship`** — image specs, dependency management, and reproducible builds, i.e. everything that replaces `module load`.
- **`flyte-sdk-app`** — serving and endpoints, for the step after training that Slurm never covered.
