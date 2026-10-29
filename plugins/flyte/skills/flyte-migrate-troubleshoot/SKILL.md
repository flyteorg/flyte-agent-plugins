---
name: flyte-migrate-troubleshoot
description: Diagnoses and fixes errors that show up when running Flyte 1 (flytekit) code freshly migrated to Flyte 2 (flyte), such as submit-time import failures, missing depends_on between environments, pandas DataFrames that are not wrapped, exceptions that are not caught, notebooks missing from the code bundle, File inputs from https URLs, NamedTuple outputs that lose their fields, shell tasks that fail with an empty error message, circular depends_on, sync/async call mismatches, flyte.map partials with several unbound inputs, oversized numpy inputs, and calling tasks missing a library to unpickle a sub-task output. Use when a migrated workflow fails on `flyte run` (locally or remotely) and the error matches one of the known migration failures. Trigger words are migration error, migrated code fails, attempted relative import with no known parent package, not found in image cache, depends_on, has no parent environment name, Did you forget to wrap your dataframe, RuntimeUserError, non-extendable image, Bytes object has no attribute decode, _LazyModule, FileNotFoundError ipynb, Timeout context manager, NamedTuple, has no attribute, ShellTask, shell.create, exit code 1, empty error message, maximum recursion depth exceeded, called in a blocking way, aio, coroutine object, Partial function must leave exactly one parameter, max_bytes limit, No module named, unexpected extra argument, troubleshoot, debug migration.
---

# Flyte 1 to 2 Migration: Troubleshooting

This skill covers errors observed when running migrated code, not how to write it. Each entry gives the exact symptom, the cause, and a verified fix. Start with the debug loop below, then find the error in the index.

Every entry here was reproduced by migrating the flytesnacks examples (153 entrypoints) to Flyte 2 (SDK 2.12.1) and running them on a cluster. About one entrypoint in five failed on its first run because of the migration; entries 1-11 are those causes. Entries 12-17 come from a second run with these skills (2026-10-29), where 7% still failed for new reasons.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Flyte MCP tools | Available via `flyte-mcp` server |

## Debug loop

Run the cheapest check that can catch the error first:

1. **Compile:** `python -m py_compile my_module.py` catches syntax errors left over from the rewrite.
2. **Run locally:** `flyte run --local my_module.py main --arg value` runs every task in-process. Import errors and Python-level errors (entries 3, 4, 5, and 8 below) reproduce here, with a full traceback, in seconds.
3. **Run remotely:** `flyte run my_module.py main --arg value`, then `flyte get logs <run_name>` for the task's output. For runs and logs in depth, see the `flyte-sdk-run` skill. Errors about images, environments, and files missing from the pod (entries 2, 6, and 7) only show up here.

Note at which stage the error appears. A failure before a run is created (no `Created Run:` line) is a load-time error in your module, not a cluster problem.

## Error index

| Error text (or symptom) | Stage | Entry |
|---|---|---|
| `ImportError: attempted relative import with no known parent package` | submit | 1 |
| `Environment '...' not found in image cache ... depends_on` | runtime | 2 |
| `RuntimeSystemError: Task ... has no parent environment name` | submit | 2 |
| `Type conversion failed ... Value received: [RuntimeUserError(...)]` after `flyte.map` | runtime | 2 |
| `Type conversion failed ... Did you forget to wrap your dataframe in a DataFrame instance?` | runtime | 3 |
| An `except SomeError:` around a task call never matches | runtime | 4 |
| `'builtins.Bytes' object has no attribute 'decode'` | runtime | 5 |
| `ValueError: Cannot add additional layers to a non-extendable image` | submit | 6 |
| `'_LazyModule' object has no attribute 'DataFrame'`, `Unable to find a usable engine` | runtime | 6 |
| `FileNotFoundError: /home/flyte/<package>/<file>.ipynb` (or another non-`.py` file) | runtime | 7 |
| `argument should be a str or an os.PathLike object ..., not 'File'` | submit | 8 |
| `HTTPFileSystem requires "requests" and "aiohttp" to be installed` | runtime | 8 |
| `Timeout context manager should be used inside a task` | runtime | 8 |
| `'latte' is not one of 'ESPRESSO', 'AMERICANO', 'LATTE', ...` | submit | 9 |
| `Got unexpected extra argument (true)` for a bool input | submit | 9 |
| `AttributeError: '<type>' object has no attribute '<field>'` on a `NamedTuple` output | runtime | 10 |
| Shell task fails with `exit code (1)` and an empty message | runtime | 11 |
| `Execution failed: maximum recursion depth exceeded` | submit | 12 |
| `Sync task '...' was called in a blocking way from async code` | runtime | 13 |
| `Expected value of type <class '...'> but got '<coroutine object ...>'` | runtime | 14 |
| `Partial function must leave exactly one parameter unspecified for mapping` | runtime | 15 |
| `Inputs exceed max_bytes limit of 10.0 MB` | runtime | 16 |
| `Error converting input ... No module named '<lib>'` in the calling task | runtime | 17 |

## 1. `ImportError: attempted relative import with no known parent package`

### Symptom

`flyte run` fails before any run is created:

```text
Error invoking command: Failed to load basics/launch_plan.py: ImportError: attempted
relative import with no known parent package
```

### Cause

Flyte 1 examples often import sibling modules relatively (`from .workflow import slope`). `flyte run <file>` loads the file as a standalone module, not as part of its package, so relative imports have no parent package to resolve against. Passing `--root-dir` does not change this.

### Fix

Use absolute imports rooted at the package, and run `flyte run` from the package's parent directory.

```python
# Flyte 1 (and a literal migration): fails under `flyte run`
from .workflow import env, intercept, slope
```

```python
# Flyte 2: absolute import from the package root
from basics.workflow import env, intercept, slope
```

```bash
# Run from the directory that contains the `basics/` package
cd examples/basics
flyte run basics/imperative_workflow.py imperative_wf --x '[-3,0,3]' --y '[7,4,-2]'
```

The remote container receives the same source tree, so the absolute import also resolves at runtime.

## 2. A task in another environment: `not found in image cache` / `has no parent environment name`

### Symptom

A task calls a task from a different `TaskEnvironment` and fails:

```text
Environment 'mindmeld' not found in image cache. ... declare that dependency using 'depends_on=[...]'
```

Or a plugin, connector, or shell task created as an object (not with `@env.task`) fails before the run starts:

```text
RuntimeSystemError: Task basic has no parent environment name
```

Inside `flyte.map`, the first error is hidden: the failures come back as list items, and the next task fails with `Type conversion failed ... Actual type: <class 'list'> Value received: [RuntimeUserError('Environment ... not found in image cache ...`.

### Cause

Flyte 1 let each `@task` set its own `container_image`. In Flyte 2, tasks with different images live in different environments, and the calling task's environment must declare the environments it calls in `depends_on`. Task objects such as `SlurmScriptTask`, `BigQueryTask`, `Snowflake`, or a `ContainerTask` have no environment at all until you give them one.

### Fix

```python
mindmeld = flyte.TaskEnvironment(name="mindmeld", image=sklearn_image)

borebuster = flyte.TaskEnvironment(
    name="borebuster",
    image=numpy_image,
    depends_on=[mindmeld],  # a task in borebuster calls get_data, which runs in mindmeld
)
```

For a task object, wrap it first:

```python
slurm_env = flyte.TaskEnvironment.from_task("slurm_scripts", slurm_job, other_job)
driver = flyte.TaskEnvironment(name="driver", depends_on=[slurm_env])
# Or, for an environment that already exists: driver.add_dependency(slurm_env)
```

See `flyte-migrate-tasks-workflows` and `flyte-migrate-plugins` for the full pattern.

## 3. `Did you forget to wrap your dataframe in a DataFrame instance?`

### Symptom

```text
Type conversion failed for variable 'fdf'. Reason: Expected a DataFrame instance, but got
<class 'pandas.DataFrame'> instead. Did you forget to wrap your dataframe in a DataFrame instance?
```

### Cause

Flyte 1 converted a `pd.DataFrame` to a `StructuredDataset` implicitly. In a Flyte 2 driver task, a sub-task that returns `pd.DataFrame` hands back a real pandas object, and a sub-task typed `flyte.io.DataFrame` will not accept it.

### Fix

Wrap it at the call site:

```python
pandas_df = await get_df()
total = await total_payroll(flyte.io.DataFrame.from_df(pandas_df))
```

## 4. An `except` around a task call never matches

### Symptom

```python
try:
    return await raises_exc(x)
except TypeError:      # never matches
    return -1
```

The run fails with `flyte.errors.RuntimeUserError` (`code: "TypeError"`) raised from the `await` line.

### Cause

A failed sub-task does not re-raise its original exception type in the parent, either on a cluster or with `flyte run --local`. It arrives as `flyte.errors.RuntimeUserError`, and the original exception's class name is in `code`.

### Fix

```python
try:
    return await raises_exc(x)
except flyte.errors.RuntimeUserError as e:
    if e.code == "TypeError":
        return -1
    raise
```

Catch `Exception` when any failure should be handled, as in a replacement for `on_failure`. Typed subclasses such as `flyte.errors.OOMError` can still be caught directly.

## 5. `'builtins.Bytes' object has no attribute 'decode'`

### Cause

`File.open()` returns a handle whose `read()` gives an obstore `Bytes` buffer, not Python `bytes`.

### Fix

```python
async with f.open("rb") as fh:
    text = bytes(await fh.read()).decode("utf-8")
```

## 6. Image errors

### `ValueError: Cannot add additional layers to a non-extendable image`

The module fails to load. An image from `Image.from_base(uri)` (the Flyte 1 `ImageSpec(base_image=...)`) cannot be extended directly. Clone it first:

```python
image = (
    flyte.Image.from_base("ghcr.io/flyteorg/rawcontainers-python:v2")
    .clone(name="rawcontainers-python-pandas", extendable=True)
    .with_pip_packages("pandas")
)
```

### `'_LazyModule' object has no attribute 'DataFrame'`

This message hides an `ImportError` inside the image: Flyte imports pandas lazily, and when the real import fails, the lazy module raises this instead. The usual cause is a dependency pin conflict. For example, pinning `numpy<2` while `pyarrow` is unpinned installs a `pyarrow` that requires numpy 2, so pandas cannot import. Pin both sides (`"numpy<2", "pyarrow<18"`), or build the image and run `python -c "import pandas"` in it to see the real error.

### `ImportError: Unable to find a usable engine` while writing an output

A task returning `pd.DataFrame` or `flyte.io.DataFrame` writes Parquet and needs `pyarrow` in its image.

## 7. `FileNotFoundError` for a notebook or other non-Python file

### Symptom

```text
[Errno 2] No such file or directory: '/home/flyte/papermill_plugin/nb_simple.ipynb'
```

### Cause

`flyte run` bundles only the Python modules it loads. Notebooks, SQL files, and data files next to your code are not shipped. Note also that the task's working directory is `/home/flyte`, not `/root` as in many Flyte 1 images, so CWD-relative paths from v1 code may point elsewhere.

### Fix

Bake the file into the image. `dst` is the destination **file** path (not a folder, despite the docstring; a folder path turns the directory into a file and breaks code-bundle extraction with `tar: ... Not a directory`):

```python
image = (
    flyte.Image.from_debian_base()
    .with_pip_packages("flyteplugins-papermill")
    .with_source_file(NB_DIR / "nb_simple.ipynb", dst="/home/flyte/papermill_plugin/nb_simple.ipynb")
)
```

For a whole folder of assets, use `.with_source_folder(...)`.

## 8. `File` inputs that point at an `https://` URL

Three separate errors, each from Flyte 1 code that passed a public URL as a `FlyteFile`:

| Error | Cause |
|---|---|
| `argument should be a str or an os.PathLike object ..., not 'File'` (no run created) | An entrypoint input with a `File` default value breaks `flyte run`'s argument parsing. |
| `HTTPFileSystem requires "requests" and "aiohttp" to be installed` | The default image lacks the packages fsspec needs for `https://`. |
| `Timeout context manager should be used inside a task` | `await f.download()` of an `https://` path fails in an async task (SDK 2.12.1). |

### Fix

Take the URL as a `str` and read it inside the task, either directly with the library (`pd.read_csv(url)`) or with a `File` and the sync API in a sync task, with `aiohttp` and `requests` in the image:

```python
env = flyte.TaskEnvironment(
    name="data",
    image=flyte.Image.from_debian_base().with_pip_packages("pandas", "aiohttp", "requests"),
)

@env.task
def normalize(csv_url: str) -> File:
    local = File.from_existing_remote(csv_url).download_sync()
    ...
    return File.from_local_sync(out_path)
```

## 9. Enum and bool inputs on the CLI

### Symptom

```text
Error invoking command: 'latte' is not one of 'ESPRESSO', 'AMERICANO', 'LATTE', 'CAPPUCCINO'.
```

```text
Error invoking command: Got unexpected extra argument (true)
```

### Cause and fix

The code needs no change in either case:

- `pyflyte run` took an enum's value; `flyte run` takes the member **name**. Pass `--coffee_enum LATTE`.
- A `bool` input is a bare flag. Pass `--boolean_input` to set it to true, not `--boolean_input true`.

## 10. `AttributeError: '<type>' object has no attribute '<field>'` on a NamedTuple output

### Symptom

A task that reads a `NamedTuple` output from another task by attribute fails at runtime. It also reproduces with `flyte run --local`:

```text
File "basics/named_outputs.py", line 38, in simple_wf_with_named_outputs
    intercept_value = intercept(x, y, slope_value.slope)
AttributeError: 'float' object has no attribute 'slope'
```

### Cause

In Flyte 1, a workflow could read a named output by attribute (`slope_value.slope`). In Flyte 2, calling a task whose return type is a `NamedTuple` gives back:

- for a **single-field** `NamedTuple`, the bare value (here a `float`);
- for a **multi-field** `NamedTuple`, a plain `tuple`, so `result.train_features` fails with `'tuple' object has no attribute 'train_features'`.

The error is raised at the **call site**, not in the task that returns the `NamedTuple`. Changing the callee to return `slope_value(slope=...)` explicitly does not fix it.

### Fix

Use the returned value directly, or unpack a multi-field result by position.

```python
# Flyte 1 style: fails in Flyte 2
slope_value = slope(x, y)
intercept_value = intercept(x, y, slope_value.slope)
return slope_and_intercept_values(slope=slope_value.slope, intercept=intercept_value.intercept)
```

```python
# Flyte 2: a single-field NamedTuple output arrives as the bare value
slope_value = slope(x, y)
intercept_value = intercept(x, y, slope_value)
return slope_and_intercept_values(slope=slope_value, intercept=intercept_value)

# A multi-field NamedTuple output arrives as a plain tuple
train_features, train_labels, test_features, test_labels = split_data(df)
```

Returning a multi-field `NamedTuple` from the top-level task still works. Be aware that the run's outputs are reported positionally as `o0`, `o1`, ... rather than by field name.

## 11. Shell task fails with `exit code (1)` and an empty message

### Symptom

A task built with `flyte.extras.shell.create()` (the Flyte 2 replacement for `ShellTask`) fails, and the error carries no message from the script:

```text
Pod failed. No message received from kubernetes.
[flyte-copilot-uploader] terminated with ExitCode 0.
[flyte-copilot-downloader] terminated with ExitCode 0.
[<pod>] terminated with exit code (1). Reason [Error]. Message:
.
```

The task's container log is empty; only the copilot sidecars log anything.

### Why the message is empty

The shell wrapper redirects the script's stdout and stderr to files (`/var/outputs/_stdout`, `/var/outputs/_stderr`), so nothing reaches the container log. To see what actually ran, read the container's arguments, which contain the script with every `{inputs.*}` and `{outputs.*}` placeholder already substituted:

```bash
kubectl -n <namespace> get pod <pod> -o jsonpath='{.spec.containers[0].args}'
```

Then check each path the script touches against the input paths the downloader logged (`Successfully copied ... to local [/var/inputs/...]`).

### A common cause: output files are named after the output variable

In Flyte 1, `OutputLocation(var="i", var_type=FlyteFile, location="{inputs.x}")` wrote the output to the input's path, so the file kept its original name (for example `test.txt`). In Flyte 2, a `File` output declared in `outputs={"i": File}` is always written to `{outputs.i}`, so downstream tasks receive a file named `i`.

Any later script that derives a path from that file's name, such as `$(basename {inputs.x})`, now looks for the wrong file and exits with 1 under `set -e`.

```python
# Flyte 1
t1 = ShellTask(
    name="task_1",
    script="""echo "Showcasing Flyte's Shell Task." >> {inputs.x}""",
    inputs=kwtypes(x=FlyteFile),
    output_locs=[OutputLocation(var="i", var_type=FlyteFile, location="{inputs.x}")],
)
```

```python
# Flyte 2: write the output explicitly; downstream it is named "i"
from flyte.extras import shell
from flyte.io import File

t1 = shell.create(
    name="task_1",
    image="debian:12-slim",
    script="""
    echo "Showcasing Flyte's Shell Task." >> {inputs.x}
    cp {inputs.x} {outputs.i}
    """,
    inputs={"x": File},
    outputs={"i": File},
)
```

### Fix

Make every name-dependent step use the file that actually flows through the pipeline. In the flytesnacks example, `task_2` copies `t1`'s output into a directory and `task_3` looks it up by basename, so pass `t1`'s output, not the original file, to `task_3`:

```python
@env.task
async def shell_task_wf() -> File:
    x, y = await create_entities()
    t1_out = await t1(x=x)
    t2_out = await t2(x=t1_out, y=y)
    # Not `x=x`: the copied file is named after t1's output variable.
    t3_out = await t3(x=t1_out, y=y, z=t2_out)
    return t3_out
```

### Required wiring for shell tasks

The `TaskEnvironment` whose tasks call shell tasks declares them in `depends_on`, as the SDK's shell examples do:

```python
env = flyte.TaskEnvironment(
    name="shell_task",
    depends_on=[t1.env, t2.env, t3.env],
)
```

Shell tasks are async; `await` them from an `async` task.

## 12. `maximum recursion depth exceeded` at submit

### Cause

The `depends_on` graph has a cycle. A typical case: the driver environment depends on a worker environment, and a worker task calls a helper that lives in the driver environment, so the worker was given `depends_on` (or `add_dependency`) back to the driver.

### Fix

Move the shared helper tasks into a third environment that both depend on:

```python
helpers = flyte.TaskEnvironment(name="helpers")
worker = flyte.TaskEnvironment(name="worker", depends_on=[helpers])
driver = flyte.TaskEnvironment(name="driver", depends_on=[worker, helpers])
```

Every entrypoint in an environment on the cycle fails the same way, so fix the environments before re-running each entrypoint.

## 13. `Sync task '...' was called in a blocking way from async code`

### Symptom

```text
Sync task 'simple-nb' was called in a blocking way from async code. This blocks the event loop and
can hang the run. Use `await simple-nb.aio(...)` instead.
```

### Cause

An `async` task called a sync task directly. This is common with plugin tasks that are sync even though you `await` everything else, such as the papermill `NotebookTask`.

### Fix

```python
out = await nb.aio(v=f)   # not `await nb(v=f)` or `nb(v=f)`
```

## 14. A task returns `<coroutine object ...>`

### Symptom

```text
Expected value of type <class 'str'> but got '<coroutine object RemoteController.submit at 0x...>'
```

### Cause

A **sync** task called an **async** task. The call returns an un-awaited coroutine instead of running the task, and the error appears only when that coroutine is used as a value.

### Fix

Make the calling task `async` and `await` the call, or make the callee a plain `def` task. Keep a migrated pipeline all sync or all async (see `flyte-migrate-tasks-workflows`).

## 15. `Partial function must leave exactly one parameter unspecified for mapping`

### Cause

Flyte 1 `map_task(partial(...))` could map over several list inputs at once. `flyte.map` maps over exactly one unbound parameter per `partial`.

### Fix

Drop the `partial` and pass one iterable per parameter, positionally:

```python
results = list(flyte.map(multi_input_task, list_q, list_p, [shipping] * len(list_q)))
```

## 16. `Inputs exceed max_bytes limit of 10.0 MB`

### Cause

A large value without a type transformer, usually an `np.ndarray`, was passed between tasks. It falls back to pickle, which stores values inline when `sys.getsizeof` reports under 10 KB. Sliced arrays (views, as from a train/test split) report about 160 bytes regardless of their size, so the whole array is stored inline and breaks the 10 MB inline I/O limit.

### Fix

Save the arrays with `np.savez` and pass a `flyte.io.File` (see `flyte-migrate-data-io`).

## 17. `No module named '<lib>'` while converting a task's input

### Symptom

The **calling** task fails while receiving a sub-task's output, even though the sub-task succeeded:

```text
Error converting input o0 ... Expected Python type: typing.Any Exception: No module named 'sklearn'
```

### Cause

The sub-task runs in another environment and returned a pickled object, such as a scikit-learn model. The calling task deserializes every sub-task output, so its own image needs the library too. A correct `depends_on` doesn't help here.

### Fix

Add the library to the calling environment's image, or return a `File` (for example the saved model) instead of the object.

## Anti-Patterns

1. **Don't debug a submit-time error on the cluster.** If no run was created, the module failed to load locally. Fix imports first.
2. **Don't skip `flyte run --local`.** Python-level errors such as the `NamedTuple`, DataFrame, and exception-type errors reproduce locally with a full traceback.
3. **Don't keep relative imports between workflow modules.** Use absolute imports from the package root.
4. **Don't call across environments without `depends_on`.** Wrap task objects with `TaskEnvironment.from_task` first.
5. **Don't pass a raw `pd.DataFrame` to a `flyte.io.DataFrame` input.** Wrap it with `flyte.io.DataFrame.from_df`.
6. **Don't catch the original exception type around a task call.** Catch `flyte.errors.RuntimeUserError` and check `.code`.
7. **Don't assume non-Python files reach the pod.** Bake notebooks and data files into the image.
8. **Don't use a `File` default or an async download for an `https://` URL.** Take a `str` and read it in the task.
9. **Don't read a `NamedTuple` output by attribute.** Use the value directly or unpack it by position.
10. **Don't assume a shell task's output keeps its input's file name.** It is named after the output variable.
11. **Don't rely on pod logs to explain a shell task failure.** The script's stderr is redirected to a file; inspect the substituted script in the container args.
12. **Don't make `depends_on` circular.** Put tasks that two environments both call into a third environment.
13. **Don't mix sync and async calls blindly.** From async code call sync tasks with `.aio()`; never call an async task from a sync one.
14. **Don't pass large `np.ndarray`s between tasks.** Pass an `.npz` `File`.
15. **Don't assume only the callee's image matters.** The caller needs every library required to unpickle what it receives.
