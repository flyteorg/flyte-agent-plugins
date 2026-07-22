# flyte

A single [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin for
[Flyte](https://flyte.org): cluster deployment and SDK / workflow authoring skills, plus
two bundled MCP servers.

## Skills

### Deployment

- **`flyte-deploy-aws`** — deploy a Flyte v2 (`flyte-binary`) cluster on AWS from scratch:
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

### Tooling / Integration

- **`flyte-mcp-server`** — set up, run, scope, and connect the Flyte MCP server (including
  the one bundled with this plugin), and decide between MCP and the `flyte` CLI.

## Bundled MCP servers

The plugin's `.mcp.json` declares **two MCP servers**, split so nothing is duplicated:

- **`flyte-docs`** — hosted HTTP, 3 `search` tools over Flyte SDK examples, docs examples,
  and `llms.txt`. Read-only, unauthenticated, **operated by Union**. Needs nothing at all,
  so search works the moment you install. Your queries do leave your machine.
- **`flyte`** — local stdio (`scripts/flyte_mcp_stdio.py`), 13 control-plane tools: run and
  inspect tasks, manage runs, apps, and triggers. Needs [`uv`](https://docs.astral.sh/uv/)
  and a Flyte config with `project` and `domain`.

**A cluster is optional.** `flyte` starts either way and offers nothing until one is
reachable, so the plugin still works while you are deploying your first cluster. It is
tenant-agnostic — `flyte.init_from_config()` targets whatever control plane your `flyte`
CLI is authenticated against. Restart the server after logging in; the choice is made at
startup.

Set `FLYTE_MCP_LOCAL_SEARCH=1` to serve search from a local corpus (~120 MB under
`~/.flyte/mcp`) instead of the hosted server — offline and private. Note there is no
per-server toggle for plugin MCP servers, so `flyte-docs` stays declared either way; see
the `flyte-mcp-server` skill.

To test it, run `python3 scripts/smoke_test_mcp.py` from the repo root — it reports what it
landed in.

Scope further with `FLYTE_MCP_TOOL_GROUPS` / `FLYTE_MCP_TOOLS`, `FLYTE_MCP_CONFIG`,
`FLYTE_MCP_PROJECT`, `FLYTE_MCP_DOMAIN`, or `FLYTE_MCP_{TASK,APP,TRIGGER}_ALLOWLIST`.

## Install (Claude Code plugin marketplace)

```
/plugin marketplace add flyteorg/flyte-agent-plugins
/plugin install flyte@flyte
```

Then ask Claude to, e.g., "deploy a Flyte v2 cluster on AWS", "deploy Flyte on kind", or
"scaffold a Flyte workflow" — or invoke a skill directly, e.g.
`/flyte:flyte-deploy-aws`.

To pin a specific version of the skills repo, add the marketplace with the full git URL
and append `#<ref>` — a tag or branch name (not a bare commit SHA; tag the commit to pin it):

```
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<tag-or-branch>
/plugin install flyte@flyte
```

(To change the pinned version later, `/plugin marketplace remove flyte` and re-add
with the new ref.)

## Install (other agent harnesses)

The skills are standard [Agent Skills](https://agentskills.io) (`SKILL.md`), so they also
work with:

**OpenAI Codex CLI** — add the repo as a plugin marketplace, then install via `/plugins`:

```
codex plugin marketplace add flyteorg/flyte-agent-plugins    # or --ref <tag-or-branch> to pin
```

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
