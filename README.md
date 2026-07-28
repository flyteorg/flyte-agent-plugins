# Flyte Agent Plugins

A [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin marketplace for
working with [Flyte](https://flyte.org).

Everything ships in a single `flyte` plugin: 14 skills, plus two **MCP servers** that let
Claude search Flyte docs and act on your own cluster — see
[Bundled MCP servers](#bundled-mcp-servers).

## Install

```
/plugin marketplace add flyteorg/flyte-agent-plugins
/plugin install flyte@flyte-agent-plugins
```

### Install a specific version

The `flyteorg/flyte-agent-plugins` shorthand tracks the default branch. To pin the marketplace to a
specific version, add it with the full git URL and append `#<ref>` — a **tag or branch
name** (bare commit SHAs are not supported; to pin an exact commit, tag it first):

```
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<tag-or-branch>
/plugin install flyte@flyte-agent-plugins
```

To switch to a different version later, remove and re-add the marketplace:

```
/plugin marketplace remove flyte-agent-plugins
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<other-ref>
```

## Install with other agent harnesses

The skills are plain [Agent Skills](https://agentskills.io) (`SKILL.md` + YAML
frontmatter), so they work in any harness that supports the standard.

> **Only Claude Code gets the MCP servers automatically.** They are declared in
> `plugins/flyte/.mcp.json`, which Claude Code reads by convention. Every other harness
> installs the **skills only** — you can still wire the servers up by hand in a few lines,
> see [Adding the MCP servers elsewhere](#adding-the-mcp-servers-elsewhere).

| Harness | Skills | MCP servers |
|---|---|---|
| Claude Code | all 14 | both, automatically |
| Codex CLI | all 14 | none — add manually |
| Hermes | per-skill | none — add manually |
| opencode | all 14 | none — add manually |
| pi | all 14 | none — add manually |

### OpenAI Codex CLI

Codex reads this repo's marketplace catalog and the per-plugin
`.codex-plugin/plugin.json` manifests:

```
codex plugin marketplace add flyteorg/flyte-agent-plugins            # or --ref <tag-or-branch> to pin
```

Then browse and install the plugins via `/plugins` inside Codex.

Codex plugins *can* bundle MCP servers (via an `mcpServers` field pointing at an
`.mcp.json`), but this one deliberately does not: our `.mcp.json` uses
`${CLAUDE_PLUGIN_ROOT}` to locate the local launcher script, and Codex does not expand it
([openai/codex#22842](https://github.com/openai/codex/issues/22842)), so the local server
would fail to start. Add the servers manually instead — the hosted one needs no path and
works fine.

### Hermes

Install individual skills by their repo path (Hermes installs from the default
branch; ref pinning is not supported):

```
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte/skills/<skill-name>
# e.g.
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte/skills/flyte-deploy-aws
```

`hermes skills check` / `hermes skills update` refresh installed skills.

### opencode

opencode discovers `SKILL.md` folders in `.opencode/skills/` (project) and
`~/.config/opencode/skills/` (global). The easiest install is the
[`skills` CLI](https://github.com/vercel-labs/skills), which reads this repo's
marketplace manifest:

```
npx skills add flyteorg/flyte-agent-plugins          # interactive skill + agent selection
npx skills add flyteorg/flyte-agent-plugins@<ref>    # pin a tag/branch/commit
```

Or copy a skill folder directly, e.g.
`cp -r plugins/flyte/skills/flyte-deploy-aws ~/.config/opencode/skills/`.

### pi

pi reads the `pi.skills` manifest in this repo's `package.json`:

```
pi install https://github.com/flyteorg/flyte-agent-plugins           # default branch
pi install git:github.com/flyteorg/flyte-agent-plugins@<tag>         # pinned to a tag/commit
```

(Alternatively, clone the repo into `~/.pi/agent/skills/` — pi discovers nested
`SKILL.md` folders recursively.)

## Skills

### Deployment

| Skill | Description |
|-------|-------------|
| [`flyte-deploy-aws`](plugins/flyte/skills/flyte-deploy-aws) | Deploy a Flyte v2 (`flyte-binary`) cluster on AWS from scratch — EKS + S3 + RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS (ACM, incl. cross-account DNS) and Okta/OIDC SSO. |
| [`deploy-flyte-kind`](plugins/flyte/skills/deploy-flyte-kind) | Deploy a Flyte v2 (`flyte-binary`) cluster on `kind` — on your local machine or a cloud VM (DigitalOcean, AWS EC2, or GCP), backed by a hosted PostgreSQL (Supabase/external) and object store (S3/R2), with optional OIDC auth via Traefik + oauth2-proxy. |
| [`deploy-flyte-kind-vm`](plugins/flyte/skills/deploy-flyte-kind-vm) | Provision a host (local or a fresh DigitalOcean / AWS EC2 / GCP VM), install the tooling, and run the kind Flyte deploy on it with access tunneled back to your machine. |
| [`start-dex-local`](plugins/flyte/skills/start-dex-local) | Deploy Dex as an in-cluster OIDC provider for testing kind-based Flyte auth with no cloud account or real users. |

### SDK / Workflow Authoring

| Skill | Description |
|-------|-------------|
| [`flyte-sdk-author`](plugins/flyte/skills/flyte-sdk-author) | Creates Flyte 2 project scaffolds (tasks, workflows, launch plans, apps), selects patterns (map tasks, traces, dynamic workflows, conditions), and generates code from templates. For: "write a Flyte workflow", "create a task", "scaffold a Flyte project". |
| [`flyte-sdk-types`](plugins/flyte/skills/flyte-sdk-types) | Guides correct types, I/O, and serialization for common data (Pandas, Arrow, Parquet, images, audio, HF datasets), including data locality and storage best practices. For: type annotations, custom type transformers, DataFrame handling. |
| [`flyte-sdk-ship`](plugins/flyte/skills/flyte-sdk-ship) | Generates flyte.Image specs, Dockerfiles, dependency management, image tagging strategy, and reproducible build instructions. For: custom images, BYOI, uv monorepo, dependency pinning. |
| [`flyte-sdk-eval`](plugins/flyte/skills/flyte-sdk-eval) | Builds minimal evaluation harnesses (unit tests + small-run workflows) and suggests ways to validate correctness and performance early. For: testing, data quality checks, experiment tracking, benchmarking. |
| [`flyte-sdk-optimize`](plugins/flyte/skills/flyte-sdk-optimize) | Suggests performance improvements (task granularity, caching, resource requests, data format changes) using observed run metadata. For: slow tasks, throughput, latency, cost optimization. |
| [`flyte-sdk-run`](plugins/flyte/skills/flyte-sdk-run) | Runs workflows, interacts with runs and actions, retrieves logs and data, and manages run lifecycle. For: running, watching, logging, re-running, aborting, run metadata. |
| [`flyte-sdk-app`](plugins/flyte/skills/flyte-sdk-app) | Builds and serves Flyte 2 apps — FastAPI, Streamlit, vLLM, SGLang, WebSocket, and browser apps. For: model serving, REST APIs, dashboards, LLM backends, webhooks. |
| [`flyte-sdk-agent`](plugins/flyte/skills/flyte-sdk-agent) | Builds durable agents with Flyte 2 — ReAct patterns, Plan-and-Execute, LangGraph/PydanticAI/OpenAI Agents integration, agent memory, MCP tool integration. For: agent building, tool calling, memory, chat UI. |
| [`flyte-sdk-data`](plugins/flyte/skills/flyte-sdk-data) | Handles data engineering patterns: ETL pipelines, data processing, data quality checks, fanout/map tasks, conditions, dynamic workflows, and batch data transformations. For: ETL, Parquet, CSV, JsonlFile/Dir, schema validation. |
| [`flyte-sdk-ml`](plugins/flyte/skills/flyte-sdk-ml) | Handles ML workload patterns: model training, hyperparameter optimization, experiment tracking, model evaluation and selection, batch inference, real-time serving, and model monitoring. For: PyTorch, scikit-learn, HuggingFace, GPU, drift detection. |

### Migration (Flyte 1 → 2)

Convert existing Flyte 1 (`flytekit`) code to Flyte 2. Distilled from the official
[Flyte 1 → 2 migration guide](https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/).

| Skill | Description |
|-------|-------------|
| [`flyte-migrate`](plugins/flyte/skills/flyte-migrate) | Start-here migration orchestrator: the `flytekit`→`flyte` shift, the terminology/concept mapping, the two mechanical changes, an incremental migration strategy, hybrid v1/v2 pipelines during transition, and the gotchas — routes to the specific skills below. |
| [`flyte-migrate-tasks-workflows`](plugins/flyte/skills/flyte-migrate-tasks-workflows) | Migrate `@task`/`@workflow`/`@dynamic` into a single `@env.task` on a `TaskEnvironment`; sequential ordering without `>>`, nested "subworkflows" as tasks, and the parameter-mapping table. |
| [`flyte-migrate-config`](plugins/flyte/skills/flyte-migrate-config) | Migrate task configuration (images `ImageSpec`→`flyte.Image`, resources/GPUs, `cache_version`→`cache`, secrets, `LaunchPlan`/`CronSchedule`→`Trigger`/`Cron`) and the `pyflyte`→`flyte` CLI / config files. |
| [`flyte-migrate-control-flow`](plugins/flyte/skills/flyte-migrate-control-flow) | Replace `conditional()` with native `if`/`else`, `@dynamic` with plain Python loops, `on_failure` with `try`/`except`, and `map_task` with `flyte.map` / `asyncio.gather`. |
| [`flyte-migrate-data-io`](plugins/flyte/skills/flyte-migrate-data-io) | Migrate data types & I/O: `FlyteFile`/`FlyteDirectory`→`flyte.io.File`/`Dir`, `StructuredDataset`→`flyte.io.DataFrame`, dataclasses/Pydantic as task I/O. |
| [`flyte-migrate-ml`](plugins/flyte/skills/flyte-migrate-ml) | Migrate ML workloads (training, HPO, GPU/deep learning, batch inference, end-to-end pipelines) and the new-in-v2 patterns (real-time serving, apps, sandboxed execution) they unlock. |

Example:

```
/plugin install flyte@flyte-agent-plugins
```

Then ask Claude to "deploy a Flyte v2 cluster on AWS", or invoke a skill directly with
`/flyte:flyte-deploy-aws`.

## Bundled MCP servers

Installing the plugin registers **two MCP servers**, split so nothing is duplicated:

| Server | Tools | Needs |
|---|---|---|
| **`flyte-docs`** (hosted HTTP) | 3 `search` — Flyte SDK examples, docs examples, `llms.txt` | nothing at all |
| **`flyte-cluster`** (local stdio) | 13 control-plane — run/inspect tasks, manage runs, apps, triggers | `uv`, plus a Flyte login |

`flyte-docs` is a read-only, unauthenticated server **operated by Union**, so search works
the moment you install — no setup, no corpus, no `uv`. Your search queries do leave your
machine; set `FLYTE_MCP_LOCAL_SEARCH=1` to serve search from a local corpus instead
(~120 MB cached under `~/.flyte/mcp`).

`flyte-cluster` is tenant-agnostic: it calls `flyte.init_from_config()`, so it acts on the same
control plane your `flyte` CLI is authenticated against. **A cluster is optional** — it
starts either way and offers nothing until one is reachable, so the plugin still works
while you are deploying your first cluster. The tools appear once you are logged in
(run `/reload-plugins`, or restart Claude Code — the choice is made at startup).

Test it end-to-end — this spawns the server exactly as Claude Code does, handshakes, and
reports which mode it landed in:

```
python3 scripts/smoke_test_mcp.py
```

Override the automatic tool choice with `FLYTE_MCP_TOOL_GROUPS` / `FLYTE_MCP_TOOLS`, and
scope with `FLYTE_MCP_CONFIG`, `FLYTE_MCP_PROJECT`, `FLYTE_MCP_DOMAIN`,
`FLYTE_MCP_{TASK,APP,TRIGGER}_ALLOWLIST`, or `FLYTE_MCP_LOCAL_SEARCH` — see the plugin
[README](plugins/flyte/README.md).

### Adding the MCP servers elsewhere

Codex, Hermes, opencode, and pi all support MCP — this plugin just doesn't configure it
for them. Wiring it up yourself is a few lines.

**`flyte-docs`** is plain remote HTTP with no auth and no local dependency, so it drops
into any harness:

```toml
# Codex — ~/.codex/config.toml
[mcp_servers.flyte-docs]
url = "https://flyte-mcp.apps.demo.hosted.unionai.cloud/flyte-mcp/mcp"
```

```json
// opencode — opencode.json
{ "mcp": { "flyte-docs": { "type": "remote",
  "url": "https://flyte-mcp.apps.demo.hosted.unionai.cloud/flyte-mcp/mcp",
  "enabled": true } } }
```

```yaml
# Hermes — ~/.hermes/config.yaml
mcp_servers:
  flyte-docs:
    url: "https://flyte-mcp.apps.demo.hosted.unionai.cloud/flyte-mcp/mcp"
```

pi uses the same `mcpServers` shape in `~/.pi/agent/mcp.json`.

**`flyte-cluster`** is a local stdio process, so point your harness at the launcher script
with an absolute path — there is no `${CLAUDE_PLUGIN_ROOT}` outside Claude Code:

```
uv run --quiet --no-project /abs/path/to/plugins/flyte/scripts/flyte_mcp_stdio.py
```

Once [flyte-sdk#1319](https://github.com/flyteorg/flyte-sdk/pull/1319) ships, that becomes
`uvx --from "flyte[mcp]" flyte-mcp --transport stdio` — no path, no script, portable
everywhere.

## Layout

All skills live in the single `flyte` plugin:

```
.claude-plugin/marketplace.json             # marketplace catalog
package.json                                # pi package manifest (pi.skills)
plugins/flyte/.claude-plugin/plugin.json    # Claude Code plugin manifest
plugins/flyte/.codex-plugin/plugin.json     # Codex plugin manifest
plugins/flyte/.mcp.json                     # the two bundled MCP servers (Claude Code)
plugins/flyte/scripts/flyte_mcp_stdio.py    # stdio adapter that .mcp.json launches
plugins/flyte/skills/<skill>/SKILL.md
scripts/smoke_test_mcp.py                   # end-to-end check of the local MCP server
```

Each harness consumes a different part of this. Claude Code and Codex read the plugin
manifests, so the **plugin name** matters to them. Hermes, opencode, and pi install skills
by **directory path**, so `plugins/flyte/skills/…` is their interface.

The `.mcp.json` server is Claude Code-specific; the skills themselves stay portable across
harnesses.

## Contributing

Add a new skill as a directory under `plugins/flyte/skills/<skill>/SKILL.md`.
It is picked up automatically by the `flyte` plugin, the Codex manifest, and the
`pi.skills` entry — no marketplace edit needed. Add a row to the skills table above. Keep
everything generic — no account IDs, hostnames, credentials, or other environment-specific
values.
