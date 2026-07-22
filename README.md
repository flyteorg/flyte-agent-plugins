# Flyte Agent Plugins

A [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin marketplace of
skills for working with [Flyte](https://flyte.org).

All skills ship in a single `flyte-skills` plugin, which also bundles a **Flyte MCP
server** so Claude can act on your own cluster — see
[Bundled MCP server](#bundled-mcp-server).

## Install

```
/plugin marketplace add flyteorg/flyte-agent-plugins
/plugin install flyte-skills@flyte-skills
```

### Install a specific version

The `flyteorg/flyte-agent-plugins` shorthand tracks the default branch. To pin the marketplace to a
specific version, add it with the full git URL and append `#<ref>` — a **tag or branch
name** (bare commit SHAs are not supported; to pin an exact commit, tag it first):

```
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<tag-or-branch>
/plugin install flyte-skills@flyte-skills
```

To switch to a different version later, remove and re-add the marketplace:

```
/plugin marketplace remove flyte-skills
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<other-ref>
```

## Install with other agent harnesses

The skills are plain [Agent Skills](https://agentskills.io) (`SKILL.md` + YAML
frontmatter), so they work in any harness that supports the standard.

### OpenAI Codex CLI

Codex reads this repo's marketplace catalog and the per-plugin
`.codex-plugin/plugin.json` manifests:

```
codex plugin marketplace add flyteorg/flyte-agent-plugins            # or --ref <tag-or-branch> to pin
```

Then browse and install the plugins via `/plugins` inside Codex.

### Hermes

Install individual skills by their repo path (Hermes installs from the default
branch; ref pinning is not supported):

```
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte-skills/skills/<skill-name>
# e.g.
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte-skills/skills/flyte-deploy-aws
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
`cp -r plugins/flyte-skills/skills/flyte-deploy-aws ~/.config/opencode/skills/`.

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
| [`flyte-deploy-aws`](plugins/flyte-skills/skills/flyte-deploy-aws) | Deploy a Flyte v2 (`flyte-binary`) cluster on AWS from scratch — EKS + S3 + RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS (ACM, incl. cross-account DNS) and Okta/OIDC SSO. |
| [`deploy-flyte-kind`](plugins/flyte-skills/skills/deploy-flyte-kind) | Deploy a Flyte v2 (`flyte-binary`) cluster on `kind` — on your local machine or a cloud VM (DigitalOcean, AWS EC2, or GCP), backed by a hosted PostgreSQL (Supabase/external) and object store (S3/R2), with optional OIDC auth via Traefik + oauth2-proxy. |
| [`deploy-flyte-kind-vm`](plugins/flyte-skills/skills/deploy-flyte-kind-vm) | Provision a host (local or a fresh DigitalOcean / AWS EC2 / GCP VM), install the tooling, and run the kind Flyte deploy on it with access tunneled back to your machine. |
| [`start-dex-local`](plugins/flyte-skills/skills/start-dex-local) | Deploy Dex as an in-cluster OIDC provider for testing kind-based Flyte auth with no cloud account or real users. |

### SDK / Workflow Authoring

| Skill | Description |
|-------|-------------|
| [`flyte-sdk-author`](plugins/flyte-skills/skills/flyte-sdk-author) | Creates Flyte 2 project scaffolds (tasks, workflows, launch plans, apps), selects patterns (map tasks, traces, dynamic workflows, conditions), and generates code from templates. For: "write a Flyte workflow", "create a task", "scaffold a Flyte project". |
| [`flyte-sdk-types`](plugins/flyte-skills/skills/flyte-sdk-types) | Guides correct types, I/O, and serialization for common data (Pandas, Arrow, Parquet, images, audio, HF datasets), including data locality and storage best practices. For: type annotations, custom type transformers, DataFrame handling. |
| [`flyte-sdk-ship`](plugins/flyte-skills/skills/flyte-sdk-ship) | Generates flyte.Image specs, Dockerfiles, dependency management, image tagging strategy, and reproducible build instructions. For: custom images, BYOI, uv monorepo, dependency pinning. |
| [`flyte-sdk-eval`](plugins/flyte-skills/skills/flyte-sdk-eval) | Builds minimal evaluation harnesses (unit tests + small-run workflows) and suggests ways to validate correctness and performance early. For: testing, data quality checks, experiment tracking, benchmarking. |
| [`flyte-sdk-optimize`](plugins/flyte-skills/skills/flyte-sdk-optimize) | Suggests performance improvements (task granularity, caching, resource requests, data format changes) using observed run metadata. For: slow tasks, throughput, latency, cost optimization. |
| [`flyte-sdk-run`](plugins/flyte-skills/skills/flyte-sdk-run) | Runs workflows, interacts with runs and actions, retrieves logs and data, and manages run lifecycle. For: running, watching, logging, re-running, aborting, run metadata. |
| [`flyte-sdk-app`](plugins/flyte-skills/skills/flyte-sdk-app) | Builds and serves Flyte 2 apps — FastAPI, Streamlit, vLLM, SGLang, WebSocket, and browser apps. For: model serving, REST APIs, dashboards, LLM backends, webhooks. |
| [`flyte-sdk-agent`](plugins/flyte-skills/skills/flyte-sdk-agent) | Builds durable agents with Flyte 2 — ReAct patterns, Plan-and-Execute, LangGraph/PydanticAI/OpenAI Agents integration, agent memory, MCP tool integration. For: agent building, tool calling, memory, chat UI. |
| [`flyte-sdk-data`](plugins/flyte-skills/skills/flyte-sdk-data) | Handles data engineering patterns: ETL pipelines, data processing, data quality checks, fanout/map tasks, conditions, dynamic workflows, and batch data transformations. For: ETL, Parquet, CSV, JsonlFile/Dir, schema validation. |
| [`flyte-sdk-ml`](plugins/flyte-skills/skills/flyte-sdk-ml) | Handles ML workload patterns: model training, hyperparameter optimization, experiment tracking, model evaluation and selection, batch inference, real-time serving, and model monitoring. For: PyTorch, scikit-learn, HuggingFace, GPU, drift detection. |

### Tooling / Integration

| Skill | Description |
|-------|-------------|
| [`flyte-mcp-server`](plugins/flyte-skills/skills/flyte-mcp-server) | Set up, run, scope, and connect the Flyte MCP server so an AI assistant (Claude Code, OpenCode) can act on your cluster — run tasks, monitor runs, manage apps/triggers, search docs/examples. Covers the server bundled with this plugin, running it standalone over local HTTP, remote deployment, tool/allowlist scoping, and when to use MCP vs. the `flyte` CLI. |

Example:

```
/plugin install flyte-skills@flyte-skills
```

Then ask Claude to "deploy a Flyte v2 cluster on AWS", or invoke a skill directly with
`/flyte-skills:flyte-deploy-aws`.

## Bundled MCP server

Installing the plugin also registers a **Flyte MCP server**, so Claude can operate your
cluster directly — run and inspect tasks, manage runs, apps, and triggers.

Nothing is tenant-specific: the server calls `flyte.init_from_config()`, so it acts on the
same control plane your `flyte` CLI is authenticated against. It needs
[`uv`](https://docs.astral.sh/uv/) on `PATH` and a Flyte config that sets **`project` and
`domain`** (the control-plane tools fail without them). If either is missing the server
refuses to start and tells you how to fix it; the skills keep working regardless.

Test it end-to-end — this spawns the server exactly as Claude Code does, handshakes, and
makes one read-only `list_runs` call against your tenant:

```
python3 scripts/smoke_test_mcp.py
```

Default tools are `task,run,app,trigger`. Scope it (or opt into `search`) with
`FLYTE_MCP_TOOL_GROUPS`, `FLYTE_MCP_TOOLS`, `FLYTE_MCP_CONFIG`, `FLYTE_MCP_PROJECT`,
`FLYTE_MCP_DOMAIN`, or the `FLYTE_MCP_{TASK,APP,TRIGGER}_ALLOWLIST` variables — see the
[`flyte-mcp-server`](plugins/flyte-skills/skills/flyte-mcp-server) skill.

## Layout

All skills live in the single `flyte-skills` plugin:

```
.claude-plugin/marketplace.json               # marketplace catalog (Claude Code + Codex)
package.json                                   # pi package manifest (pi.skills)
plugins/flyte-skills/.claude-plugin/plugin.json   # Claude Code plugin manifest
plugins/flyte-skills/.codex-plugin/plugin.json    # Codex plugin manifest
plugins/flyte-skills/.mcp.json                    # bundled Flyte MCP server (Claude Code)
plugins/flyte-skills/scripts/flyte_mcp_stdio.py   # stdio adapter the .mcp.json launches
plugins/flyte-skills/skills/<skill>/SKILL.md
```

The `.mcp.json` server is Claude Code-specific; the skills themselves stay portable across
harnesses.

## Contributing

Add a new skill as a directory under `plugins/flyte-skills/skills/<skill>/SKILL.md`.
It is picked up automatically by the `flyte-skills` plugin, the Codex manifest, and the
`pi.skills` entry — no marketplace edit needed. Add a row to the skills table above. Keep
everything generic — no account IDs, hostnames, credentials, or other environment-specific
values.
