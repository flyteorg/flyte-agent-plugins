# flyte

A single plugin for [Flyte](https://flyte.org): cluster deployment and SDK / workflow
authoring skills, plus two bundled MCP servers.
[Claude Code](https://docs.claude.com/en/docs/claude-code) and
[OpenAI Codex](https://developers.openai.com/plugins) install it as a full plugin — skills
**and** MCP servers — and any harness that supports
[Agent Skills](https://agentskills.io) (Hermes, opencode, pi) can install the skills.

## Skills

### Deployment

- **`flyte-deploy-aws`** — deploy a Flyte 2 (`flyte-binary`) cluster on AWS from scratch:
  EKS + S3 + RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS
  (ACM, incl. cross-account DNS) and Okta/OIDC SSO.
- **`deploy-flyte-kind`** — deploy a complete Flyte stack on a [kind](https://kind.sigs.k8s.io/)
  cluster (local or a cloud VM), backed by a hosted PostgreSQL (Supabase/external) and an
  object store (AWS S3 or Cloudflare R2), with optional OIDC auth via Traefik + oauth2-proxy.
- **`deploy-flyte-kind-vm`** — provision a host (local or a fresh DigitalOcean / AWS EC2 /
  GCP VM), install the tooling, and run the kind Flyte deploy on it with access tunneled back.
- **`start-dex-local`** — deploy Dex as an in-cluster OIDC provider for testing kind auth
  with no cloud account or real users.

### SDK / Workflow Authoring

- **`flyte-sdk-author`** — scaffold Flyte 2 projects (tasks, workflows, launch plans, apps)
  and generate code from templates.
- **`flyte-sdk-types`** — correct types, I/O, and serialization for common data (Pandas,
  Arrow, Parquet, images, audio, HF datasets).
- **`flyte-sdk-ship`** — `flyte.Image` specs, Dockerfiles, dependency management, and
  reproducible builds.
- **`flyte-sdk-eval`** — minimal evaluation harnesses (unit tests + small-run workflows).
- **`flyte-sdk-optimize`** — performance improvements (task granularity, caching, resources,
  data formats) using observed run metadata.
- **`flyte-sdk-run`** — run workflows, manage runs and actions, retrieve logs and data.
- **`flyte-sdk-app`** — build and serve Flyte 2 apps (FastAPI, Streamlit, vLLM, SGLang,
  WebSocket, browser apps).
- **`flyte-sdk-agent`** — build durable agents (ReAct, Plan-and-Execute, LangGraph /
  PydanticAI / OpenAI Agents, memory, MCP tools).
- **`flyte-sdk-data`** — data engineering patterns (ETL, data quality, fanout/map,
  conditions, dynamic workflows, batch transforms).
- **`flyte-sdk-ml`** — ML workload patterns (training, HPO, experiment tracking, evaluation,
  batch/real-time inference, monitoring).

### Migration (Flyte 1 → 2)

Convert existing Flyte 1 (`flytekit`) code to Flyte 2, distilled from the official
[migration guide](https://www.union.ai/docs/v2/flyte/user-guide/migration/flyte-2/).

- **`flyte-migrate`** — start-here orchestrator: the `flytekit`→`flyte` shift, concept
  mapping, the two mechanical changes, incremental strategy, hybrid v1/v2 pipelines, gotchas.
- **`flyte-migrate-tasks-workflows`** — `@task`/`@workflow`/`@dynamic` → a single `@env.task`
  on a `TaskEnvironment`; ordering without `>>`; subworkflows as tasks.
- **`flyte-migrate-config`** — images (`ImageSpec`→`flyte.Image`), resources/GPUs, caching,
  secrets, scheduling (`LaunchPlan`/`CronSchedule`→`Trigger`/`Cron`), and `pyflyte`→`flyte`.
- **`flyte-migrate-control-flow`** — `conditional()`→`if`/`else`, `@dynamic`→plain loops,
  `on_failure`→`try`/`except`, `map_task`→`flyte.map`/`asyncio.gather`.
- **`flyte-migrate-data-io`** — `FlyteFile`/`FlyteDirectory`→`flyte.io.File`/`Dir`,
  `StructuredDataset`→`flyte.io.DataFrame`, dataclasses/Pydantic I/O.
- **`flyte-migrate-ml`** — training, HPO, GPU/deep learning, batch inference, and the
  new-in-v2 patterns (serving, apps, sandboxed execution).
- **`flyte-migrate-slurm`** — Slurm (`sbatch`/`srun`) → Flyte 2: `#SBATCH` pragmas →
  `TaskEnvironment` config, job arrays → `flyte.map`, `--dependency` chains → plain Python,
  multi-node `srun` → `ClusteredTaskEnvironment`, `--requeue` → retries/checkpoints/spot.

## Bundled MCP servers

The servers live in `.mcp.json`. Claude Code reads that file by convention; Codex picks it
up through the `mcpServers` entry in `.codex-plugin/plugin.json`. Hermes, opencode, and pi
install the skills and nothing else — they all support MCP, so you can add these by hand,
see [Adding the MCP servers elsewhere](../../README.md#adding-the-mcp-servers-elsewhere).

`.mcp.json` declares **two MCP servers**, split so nothing is duplicated:

- **`flyte-docs`** — hosted HTTP, 3 `search` tools over Flyte SDK examples, docs examples,
  and `llms.txt`. Read-only, unauthenticated, **operated by Union**. Needs nothing at all,
  so search works the moment you install. Your queries do leave your machine.
- **`flyte-cluster`** — local stdio, 29 control-plane tools: run and inspect tasks, runs,
  actions, and logs; manage apps, triggers, projects, secrets, and conditions; `whoami`.
  Needs [`uv`](https://docs.astral.sh/uv/) (for `uvx`) and a Flyte login.

`flyte-cluster` is the SDK's own published entry point — no wrapper script and no path to
expand, so the same line works in every harness:

```
uvx --from "flyte[mcp]==2.6.10" flyte-mcp --transport stdio \
  --tool-groups task,run,action,logs,app,trigger,project,secret,condition,identity \
  --no-init-from-config
```

Two things about that command are deliberate:

- **`2.6.10`** caps `mcp<2`. Earlier releases than `2.5.18` can resolve `mcp` 2.0.0,
  where `mcp.server.fastmcp` is gone and the server dies at import claiming "mcp is not installed".
  The exact pin keeps tool metadata and behavior reproducible for users and reviewers.
- **`--no-init-from-config`** prevents an unconfigured stdio server from starting an
  interactive login on its JSON-RPC stdout. Set `FLYTE_MCP_PROJECT` and
  `FLYTE_MCP_DOMAIN`, or pass `project` and `domain` to the relevant tool, before operating
  on a cluster.
- **The `search` groups are left out.** `flyte-docs` already serves those three tools from a
  hosted corpus; enabling them here would shallow-clone ~120 MB into `~/.flyte/mcp` on first
  launch for no gain.

**A cluster is optional.** The server starts even with no Flyte config at all, so the plugin
still works while you are deploying your first cluster — the tools are registered either way
and report a clean missing-target error when called. It is tenant-agnostic: choose a target
with `FLYTE_MCP_PROJECT` / `FLYTE_MCP_DOMAIN` or tool arguments, and nothing needs restarting
once you supply a usable Flyte login and target.

To test it, run `python3 scripts/smoke_test_mcp.py` from the repo root — it spawns the
server exactly as a client does, lists the tools, and makes one real read-only call.
(`flyte-docs` is hosted, so check it with
`curl https://flyte-mcp.apps.demo.hosted.unionai.cloud/health` instead.)

### Configuring `flyte-cluster`

Change what is served by editing `args` in `.mcp.json`: `--tool-groups` (valid groups are
`all`, `core`, `task`, `run`, `action`, `logs`, `app`, `trigger`, `project`, `secret`,
`condition`, `identity`, `search`), `--tools` for an explicit tool list instead, or
`--read-only` to narrow whatever those selected down to the tools annotated
`readOnlyHint=True`. `uvx --from "flyte[mcp]" flyte-mcp --help` lists the rest.

Two environment variables are read at startup. Set them in your shell or in an `env` block;
the plugin's own `.mcp.json` sets neither, so ambient values apply.

| Variable | Effect |
|---|---|
| `FLYTE_MCP_PROJECT` | set the default project for cluster tools |
| `FLYTE_MCP_DOMAIN` | set the default domain for cluster tools |

Note there is no per-server toggle for plugin MCP servers in Claude Code — it manages them
through plugin installation, not `/mcp`. Suppressing one needs a `deniedMcpServers` entry or
disabling the plugin.

To build an MCP server of your own — with allowlists, auth, and a shared endpoint for a
team — ask the `flyte-docs` search tools for `FlyteMCPAppEnvironment`; they return the
canonical `flyte_mcp_app.py` and `flyte_mcp_app_filtered.py` examples straight from the
flyte-sdk repo, which stay current as the SDK changes.

## Install (Claude Code plugin marketplace)

```
/plugin marketplace add flyteorg/flyte-agent-plugins
/plugin install flyte@flyte-agent-plugins
```

Then ask Claude to, e.g., "deploy a Flyte 2 cluster on AWS", "deploy Flyte on kind", or
"scaffold a Flyte workflow" — or invoke a skill directly, e.g.
`/flyte:flyte-deploy-aws`.

To pin a specific version of the skills repo, add the marketplace with the full git URL
and append `#<ref>` — a tag or branch name (not a bare commit SHA; tag the commit to pin it):

```
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<tag-or-branch>
/plugin install flyte@flyte-agent-plugins
```

(To change the pinned version later, `/plugin marketplace remove flyte-agent-plugins` and re-add
with the new ref.)

## Install (OpenAI Codex)

Add the repo as a plugin marketplace, then install via `/plugins` — the skills and both
MCP servers come with it:

```
codex plugin marketplace add flyteorg/flyte-agent-plugins    # or --ref <tag-or-branch> to pin
```

## Install (other agent harnesses)

The skills are standard [Agent Skills](https://agentskills.io) (`SKILL.md`), so they also
work with:

**Hermes** — install individual skills by repo path (default branch only):

```
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte/skills/<skill-name>
# e.g.
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte/skills/flyte-deploy-aws
```

**opencode** — via the [`skills` CLI](https://github.com/vercel-labs/skills), or copy a
skill folder into `~/.config/opencode/skills/`:

```
npx skills add flyteorg/flyte-agent-plugins          # append @<ref> to pin
```

**pi** — installs via the repo's `pi.skills` manifest:

```
pi install git:github.com/flyteorg/flyte-agent-plugins@<tag>   # or the plain https URL for default branch
```

## Install (manual)

Copy any skill folder under `skills/` into your `~/.claude/skills/` directory.

## Scope & safety

The deployment skills provision real, billable cloud resources and run `aws`/`eksctl`/
`gcloud`/`kubectl`/`helm` commands. Every value in `<angle brackets>` and the example
hostnames/IDs are placeholders — replace them with your own. Review each step before
running it.
