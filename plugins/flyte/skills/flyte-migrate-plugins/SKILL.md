---
name: flyte-migrate-plugins
description: Maps Flyte 1 plugins and agents (flytekitplugins-*) to their Flyte 2 equivalents (flyteplugins-*), lists the v1 integrations that have no v2 plugin and what to use instead, and shows the three ways a v2 plugin attaches to a task (plugin_config on a TaskEnvironment, a standalone plugin task wrapped with TaskEnvironment.from_task, or a decorator). Use when migrating Flyte 1 code that imports flytekitplugins, uses task_config=, or uses a connector/agent task such as BigQueryTask, SnowflakeTask, Spark, Ray, Dask, PyTorch, NotebookTask, or DbtTask. Trigger words are flytekitplugins, flyteplugins, plugin, agent, connector, task_config, plugin_config, Spark, Ray, Dask, BigQuery, Snowflake, Databricks, papermill, NotebookTask, dbt, wandb, mlflow, pandera, kfpytorch, Elastic.
---

# Flyte 1 to 2 Migration: Plugins and Connectors

Flyte 1 integrations ship as `flytekitplugins-<name>` packages. Some have a Flyte 2 package, `flyteplugins-<name>` (imported as `flyteplugins.<name>`), often with a changed API. Many have none, and the right move is a plain `@env.task` that calls the underlying library. Check the table below before porting a plugin, and keep its API notes in mind: several changes import fine but break at runtime.

The mapping and examples below come from migrating the plugin examples in flytesnacks to Flyte 2 (SDK and plugins 2.12.1). The "Verified" column says how far each one was tested.

## Grounding References

| Resource | URL |
|---|---|
| Migration guide | https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/ |
| Integrations docs | https://www.union.ai/docs/v2/flyte/integrations/ |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| Plugin source | https://github.com/flyteorg/flyte-sdk/tree/main/plugins |
| Flyte MCP tools | Available via `flyte-mcp` server (`search_flyte_sdk_examples` finds e.g. `bigquery_example.py`) |

## v1 plugins with a Flyte 2 plugin

Install the v2 package in the task image (`.with_pip_packages("flyteplugins-<name>")`) and in the local environment you run `flyte run` from.

| Flyte 1 | Flyte 2 package and API | How it attaches | Verified |
|---|---|---|---|
| `flytekitplugins-pandera` | `flyteplugins-pandera`; use `pandera.typing.DataFrame[Schema]` as before | Type transformer; install it in the image, no import needed | Ran on a cluster |
| `flytekitplugins-papermill` `NotebookTask` | `flyteplugins-papermill` `NotebookTask(task_environment=env, inputs={...}, outputs={...})` | Standalone task | Ran on a cluster |
| `flytekitplugins-mlflow` `@mlflow_autolog` | `flyteplugins-mlflow` `@mlflow_run(autolog=True, framework="keras")` | Decorator, outermost | Ran on a cluster |
| `flytekitplugins-wandb` `@wandb_init` | `flyteplugins-wandb` `@wandb_init(project=..., entity=...)`, `get_wandb_run()` | Decorator, outermost | Ran offline |
| `flytekitplugins-spark` | `flyteplugins-spark` `Spark(spark_conf=...)` | `plugin_config` | Imports and serializes |
| `flytekitplugins-dask` | `flyteplugins-dask` `Dask(scheduler=Scheduler(...), workers=WorkerGroup(...))` | `plugin_config` | Imports and serializes |
| `flytekitplugins-ray` | `flyteplugins-ray` `RayJobConfig(head_node_config=..., worker_node_config=[...])` | `plugin_config` | Imports and serializes |
| `flytekitplugins-kfpytorch` `Elastic` | `flyteplugins-pytorch` `Elastic(nnodes=..., nproc_per_node=...)` | `plugin_config` | Imports and serializes |
| `flytekitplugins-databricks` (`Databricks`, `DatabricksV2`) | `flyteplugins-databricks` `Databricks(spark_conf=..., databricks_conf=..., databricks_instance=...)` | `plugin_config` | Imports and serializes |
| `flytekitplugins-bigquery` | `flyteplugins-bigquery` `BigQueryTask(..., plugin_config=BigQueryConfig(ProjectID=...))` | Standalone task | Imports and serializes |
| `flytekitplugins-snowflake` | `flyteplugins-snowflake` `Snowflake(..., plugin_config=SnowflakeConfig(...))` | Standalone task | Imports and serializes |
| `flytekitplugins-dbt` | `flyteplugins-dbt` `DbtTask(task_environment=env, ...)` | Standalone task | Imports and serializes |
| `flytekitplugins-slurm` | `flyteplugins-slurm` `SlurmScriptTask`, `Slurm(...)` (see `flyte-migrate-slurm`) | Standalone task or `plugin_config` | Imports and serializes |
| `JSONLFile` (`flytekitplugins-openai`) | `flyteplugins-jsonl` `JsonlFile` | Type | Imports and serializes |

"Imports and serializes" means the module imports and every task serializes the way `flyte deploy` would, but nothing was run against the service. Test against your own account before relying on it.

## v1 integrations with no Flyte 2 plugin

Do not look for a package; write a regular `@env.task` that uses the library directly, with credentials from `secrets=` on the environment.

| Flyte 1 | Flyte 2 replacement |
|---|---|
| `flytekitplugins-kfpytorch` `PyTorch` (PyTorchJob with `Worker(replicas=N)`) | `flyteplugins-pytorch` `Elastic`, or `flyte.clustered.ClusteredTaskEnvironment` (see "Multi-node training" in `flyte-migrate-slurm`) |
| `flytekitplugins-kftensorflow` (TFJob), `flytekitplugins-kfmpi` (MPIJob, Horovod) | No equivalent; run single-node, or restructure around `Elastic` / a clustered environment |
| `flytekitplugins-openai` `ChatGPTTask`, `create_batch` | The `openai` client in a regular task. Note: `flyteplugins-openai` exists, but it only provides `function_tool` for the OpenAI Agents SDK; it is not a replacement |
| Athena, Hive, `SQLAlchemyTask`, `SQLite3Task`, `DuckDBQuery` | `pyathena`, `pyhive`, `sqlalchemy`, `sqlite3`, `duckdb` in a regular task |
| Great Expectations, whylogs, modin, memray, ONNX, Dolt | The library in a regular task; values without a type transformer fall back to pickle, or pass a `File`. Don't pass a modin `DataFrame` between tasks: the pickle fallback calls `sys.getsizeof` on it, which raises (on a cluster this surfaces only as a Ray crash). Convert with `._to_pandas()` and pass a pandas `DataFrame` |
| Comet ML, Neptune | `comet_ml.login()` / `neptune.init_run()` in the task |
| AWS Batch | Drop the config; tasks run as Kubernetes pods |
| SageMaker inference, mmcloud, Perian | `boto3` (or the vendor SDK) in a regular task, or plain tasks with `flyte.Resources` |
| `flytekitplugins-inference` (NIM, Ollama sidecars) | A `flyte.app.AppEnvironment` serving the model, with `TaskEnvironment(depends_on=[app])` and `app.endpoint` (see `flyte-sdk-app`) |
| Airflow agent (Airflow operators inside Flyte) | Re-implement the operator as a task (for example, a `FileSensor` becomes a polling task with `flyte.storage.exists`) |
| Airflow provider (Flyte operators inside Airflow) | An Airflow `PythonOperator` that calls `flyte.remote` |
| `flytekitplugins-flyteinteractive` `@vscode` | `flyte run --debug` (run-level only; no per-task decorator) |
| `flytekitplugins-flyteinteractive` `@jupyter` | No equivalent |
| `flytekitplugins-deck-standard` renderers | Hand-built HTML with `flyte.report` |

## How a v2 plugin attaches to a task

`task_config=` becomes `plugin_config=`, and `kwtypes(a=int)` becomes a plain dict `{"a": int}`. Beyond that, plugins attach in one of three ways.

### 1. `plugin_config` on a `TaskEnvironment` (Spark, Dask, Ray, Elastic, Databricks, Slurm functions)

The plugin config moves from each task to the environment. Tasks in a plugin environment are workers, so call them from a separate driver environment that lists the plugin environment in `depends_on`:

```python
import flyte
from flyteplugins.spark import Spark

image = (
    flyte.Image.from_base("apache/spark-py:v3.4.0")
    .clone(name="spark", python_version=(3, 10), extendable=True)
    .with_pip_packages("flyteplugins-spark")
)

spark_env = flyte.TaskEnvironment(
    name="spark_pi",
    image=image,
    resources=flyte.Resources(cpu="1", memory="2000M"),
    plugin_config=Spark(spark_conf={"spark.executor.instances": "2"}),
)

driver = flyte.TaskEnvironment(name="spark_driver", image=image, depends_on=[spark_env])

@spark_env.task
async def hello_spark(partitions: int) -> float:
    # Flyte 1: flytekit.current_context().spark_session
    sess = flyte.ctx().data["spark_session"]
    ...

@driver.task
async def main(partitions: int = 10) -> float:
    return await hello_spark(partitions)
```

### 2. A standalone plugin task wrapped with `TaskEnvironment.from_task` (BigQuery, Snowflake, Slurm scripts)

Query and connector tasks are objects, not `@env.task` functions, so they have no environment. Running one directly fails with `RuntimeSystemError: Task <name> has no parent environment name`. Group them with `TaskEnvironment.from_task` and depend on that group:

```python
import flyte
from flyte.io import DataFrame
from flyteplugins.bigquery import BigQueryConfig, BigQueryTask

bq_query = BigQueryTask(
    name="sql.bigquery.w_io",
    inputs={"version": int},              # Flyte 1: kwtypes(version=int)
    output_dataframe_type=DataFrame,
    plugin_config=BigQueryConfig(ProjectID="my-project"),  # Flyte 1: task_config=
    query_template="SELECT * FROM `bigquery-public-data.crypto_dogecoin.transactions` WHERE version = @version LIMIT 10;",
)

bigquery_env = flyte.TaskEnvironment.from_task("bigquery_env", bq_query)

env = flyte.TaskEnvironment(
    name="bigquery_example",
    image=flyte.Image.from_debian_base().with_pip_packages("flyteplugins-bigquery", "pandas", "pyarrow"),
    depends_on=[bigquery_env],
)

@env.task
async def main(version: int) -> DataFrame:
    return await bq_query(version=version)
```

`NotebookTask` and `DbtTask` are also standalone, but they take `task_environment=env` directly, so they need no `from_task`.

### 3. A decorator (wandb, mlflow)

The plugin decorator must be the **outermost** decorator, above `@env.task`. This is the reverse of the usual Flyte 1 order:

```python
from flyteplugins.wandb import get_wandb_run, wandb_init

@wandb_init(project="my-project", entity="my-team")
@env.task
async def train() -> float:
    run = get_wandb_run()
    ...
```

## API changes that break a literal port

These import and serialize fine, so only a run catches them.

- **Snowflake:** `SnowflakeTask` becomes `Snowflake`. Query parameters use printf style, `%(nation_key)s`, instead of Go templates, `{{ .inputs.nation_key }}`. `SnowflakeConfig(user=...)` is now required.
- **wandb:** no `secret=` argument; the API key is read from the `WANDB_API_KEY` environment variable, so declare the secret with `flyte.Secret(key="wandb-api-key", as_env_var="WANDB_API_KEY")`.
- **mlflow:** `@mlflow_autolog(framework=mlflow.keras)` becomes `@mlflow_run(autolog=True, framework="keras")`.
- **dbt:** the three task classes (`DBTRun`, `DBTTest`, `DBTFreshness`) and their input/output dataclasses collapse into one `DbtTask`, which you call with a dbt command and which returns `list[DbtNodeResult]`.
- **Databricks:** both v1 `Databricks` (backend plugin) and `DatabricksV2` (agent) map to the same v2 `Databricks` class. The Spark session comes from `flyte.ctx().data["spark_session"]`.
- **Spark:** `current_context().spark_session` becomes `flyte.ctx().data["spark_session"]`.

### papermill `NotebookTask`

- **It is a sync task.** Calling it with `await nb(...)` from an `async` task fails with `SyncTaskCallInAsyncContextError`. Use `.aio()`:

  ```python
  @env.task
  async def main(v: float) -> float:
      return await nb.aio(v=v)  # not `await nb(v=v)`
  ```

- **The notebook is not shipped with your code.** `flyte run` bundles only the Python modules it loads, so the pod fails with `FileNotFoundError: /home/flyte/<package>/<notebook>.ipynb`. Bake the notebook into the image at that path. `dst` is the full destination file path:

  ```python
  image = (
      flyte.Image.from_debian_base()
      .with_pip_packages("flyteplugins-papermill")
      .with_source_file(NB_DIR / "nb_simple.ipynb", dst="/home/flyte/papermill_plugin/nb_simple.ipynb")
  )
  ```

- **It does not inherit the environment's `resources`.** Set `resources=` on the `NotebookTask` itself, or a memory-hungry notebook is OOMKilled.
- **DataFrame outputs fail** with `No transformers could reverse Flyte literal type structured_dataset_type` in 2.12.1. Write the frame to Parquet and output a `flyte.io.File` instead.
- **String outputs containing quotes break `record_outputs`.** Emit them with `display({"text/plain": record_outputs(...)}, raw=True)`.

## Anti-Patterns

1. **Don't install `flytekitplugins-*` in a Flyte 2 image.** They depend on `flytekit`; use the `flyteplugins-*` package or the underlying library.
2. **Don't assume a same-named package is a replacement.** `flyteplugins-openai` is an Agents SDK helper, not a port of `ChatGPTTask`.
3. **Don't call a plugin task without `depends_on`.** Wrap standalone tasks with `TaskEnvironment.from_task`, and list every plugin environment in the caller's `depends_on`.
4. **Don't keep `task_config=` or `kwtypes(...)`.** Use `plugin_config=` and a plain dict.
5. **Don't put a plugin decorator inside `@env.task`.** `@wandb_init` and `@mlflow_run` go on top.
6. **Don't trust a load check for connectors.** Query templating, credentials, and secrets only fail at runtime; run one small query before migrating the rest.
