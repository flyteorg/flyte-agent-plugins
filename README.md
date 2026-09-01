# Flyte Agent Plugins

A plugin marketplace for working with [Flyte](https://flyte.org) — in
[Claude Code](https://docs.claude.com/en/docs/claude-code),
[OpenAI Codex](https://developers.openai.com/plugins), or any agent harness that
supports [Agent Skills](https://agentskills.io).

21 skills, plus two **MCP servers** that let Claude search Flyte docs and act on your own
cluster. `uvx flyte-skills install` gets you the skills in any harness; installing the
`flyte` plugin gets you the skills *and* the servers — see
[Bundled MCP servers](#bundled-mcp-servers).

## Install

```bash
uvx flyte-skills install
```

That copies all 21 skills into whichever harness directories it finds on your machine —
no arguments needed. (`pip install flyte-skills` then `flyte-skills install` works the
same way.)

| Harness | User-level directory | Project-level (`--project`) |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex CLI | `~/.agents/skills/` | `.agents/skills/` |
| Hermes | `~/.hermes/skills/` | `.hermes/skills/` |
| opencode | `~/.config/opencode/skills/` | `.opencode/skills/` |
| pi | `~/.pi/agent/skills/` | — |

```bash
flyte-skills install --target claude --target codex   # pick harnesses explicitly
flyte-skills install --dir ~/somewhere/skills         # any directory you choose
flyte-skills install --project                        # this repo only
flyte-skills install --dry-run                        # preview, change nothing
flyte-skills install --force                          # overwrite existing copies
flyte-skills uninstall                                # remove them again
flyte-skills list                                     # list the bundled skills
```

> **This installs the skills, not the MCP servers.** The two servers that let Claude search
> Flyte docs and act on your cluster ship with the **plugin**, not the CLI — see
> [Install as a plugin](#install-as-a-plugin-claude-code-and-codex) if you want them, or
> [Adding the MCP servers elsewhere](#adding-the-mcp-servers-elsewhere) to wire them up by
> hand.

The package is published under two interchangeable names, `flyte-skills` and
`flyte-agent-plugins` — identical mirrors of the same release, so pick either. To pin a
version, `uvx --from flyte-skills==<version> flyte-skills install`.

## Install as a plugin (Claude Code and Codex)

Installing the plugin instead of the skills gets you the same 21 skills **plus** both MCP
servers, which are declared in `plugins/flyte/.mcp.json`.

### Claude Code

```
/plugin marketplace add flyteorg/flyte-agent-plugins
/plugin install flyte@flyte-agent-plugins
```

The `flyteorg/flyte-agent-plugins` shorthand tracks the default branch. To pin the
marketplace to a specific version, add it with the full git URL and append `#<ref>` — a
**tag or branch name** (bare commit SHAs are not supported; to pin an exact commit, tag it
first):

```
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<tag-or-branch>
/plugin install flyte@flyte-agent-plugins
```

To switch to a different version later, remove and re-add the marketplace:

```
/plugin marketplace remove flyte-agent-plugins
/plugin marketplace add https://github.com/flyteorg/flyte-agent-plugins.git#<other-ref>
```

### OpenAI Codex CLI

Codex reads this repo's marketplace catalog and the per-plugin
`.codex-plugin/plugin.json` manifests:

```
codex plugin marketplace add flyteorg/flyte-agent-plugins            # or --ref <tag-or-branch> to pin
```

Then browse and install the plugins via `/plugins` inside Codex.

Both MCP servers come with it: `.codex-plugin/plugin.json` carries an `mcpServers` field
pointing at the same `.mcp.json` Claude Code reads. (The key is spelled `mcpServers`, not
the `mcp_servers` the Codex docs show — the manifest struct is `camelCase`,
[openai/codex#22105](https://github.com/openai/codex/issues/22105).) Neither server needs a
path expanded, so `${CLAUDE_PLUGIN_ROOT}` — which Codex does not expand,
[openai/codex#22842](https://github.com/openai/codex/issues/22842) — never comes up.

## Harness-native installs

The skills are plain [Agent Skills](https://agentskills.io) (`SKILL.md` + YAML
frontmatter), so they work in any harness that supports the standard. `flyte-skills
install` above covers all five; each harness also has its own installer, which is what you
want when you would rather track the repo than a release, or to install a single skill
rather than all 21.

| Harness | Skills | MCP servers | `flyte-skills install` |
|---|---|---|---|
| Claude Code | all 21 | both, automatically | `--target claude` |
| Codex CLI | all 21 | both, automatically | `--target codex` |
| Hermes | per-skill | none — add manually | `--target hermes` |
| opencode | all 21 | none — add manually | `--target opencode` |
| pi | all 21 | none — add manually | `--target pi` |

### Hermes

`flyte-skills install --target hermes` writes all 21 into `~/.hermes/skills/`, which Hermes
auto-discovers with no registration step. Add `--project` for `<repo>/.hermes/skills/` —
project skills need `hermes skills trust` before first use.

To install skills individually instead, use their repo path (Hermes installs from the
default branch; ref pinning is not supported):

```
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte/skills/<skill-name>
# e.g.
hermes skills install flyteorg/flyte-agent-plugins/plugins/flyte/skills/flyte-deploy-aws
```

`hermes skills check` / `hermes skills update` refresh installed skills.

### opencode

opencode discovers `SKILL.md` folders in `.opencode/skills/` (project) and
`~/.config/opencode/skills/` (global). Besides `flyte-skills install --target opencode`,
the [`skills` CLI](https://github.com/vercel-labs/skills) reads this repo's marketplace
manifest:

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

(Alternatively, `flyte-skills install --target pi`, or clone the repo into
`~/.pi/agent/skills/` — pi discovers nested `SKILL.md` folders recursively.)


## Skills

### Deployment

| Skill | Description |
|-------|-------------|
| [`flyte-deploy-aws`](plugins/flyte/skills/flyte-deploy-aws) | Deploy a Flyte 2 (`flyte-binary`) cluster on AWS from scratch — EKS + S3 + RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS (ACM, incl. cross-account DNS) and Okta/OIDC SSO. |
| [`deploy-flyte-kind`](plugins/flyte/skills/deploy-flyte-kind) | Deploy a Flyte 2 (`flyte-binary`) cluster on `kind` — on your local machine or a DigitalOcean droplet (for AWS EC2 or GCP VMs, see `deploy-flyte-kind-vm`), backed by a hosted PostgreSQL (Supabase/external) and object store (S3/R2), with optional OIDC auth via Traefik + oauth2-proxy. |
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
| [`flyte-migrate-slurm`](plugins/flyte/skills/flyte-migrate-slurm) | Migrate Slurm (`sbatch`/`srun`) workloads: `#SBATCH` pragmas → `TaskEnvironment` config, job arrays → `flyte.map`, `--dependency` chains → plain Python, multi-node `srun` → `ClusteredTaskEnvironment`, `--requeue` → retries/checkpoints/spot. |

Example:

```
/plugin install flyte@flyte-agent-plugins
```

Then ask Claude to "deploy a Flyte 2 cluster on AWS", or invoke a skill directly with
`/flyte:flyte-deploy-aws`.

## Bundled MCP servers

Installing the plugin registers **two MCP servers**, split so nothing is duplicated:

| Server | Tools | Needs |
|---|---|---|
| **`flyte-docs`** (hosted HTTP) | 3 `search` — Flyte SDK examples, docs examples, `llms.txt` | nothing at all |
| **`flyte-cluster`** (local stdio) | 29 control-plane — tasks, runs, actions, logs, apps, triggers, projects, secrets, conditions, `whoami` | `uv`, plus a Flyte login |

`flyte-docs` is a read-only, unauthenticated server **operated by Union**, so search works
the moment you install — no setup, no corpus, no `uv`. Your search queries do leave your
machine.

`flyte-cluster` is the SDK's own `flyte-mcp` entry point, run straight from PyPI with
`uvx` — nothing is vendored here:

```
uvx --from "flyte[mcp]==2.6.10" flyte-mcp --transport stdio \
  --tool-groups task,run,action,logs,app,trigger,project,secret,condition,identity \
  --no-init-from-config
```

`2.6.10` caps `mcp<2`; earlier releases than `2.5.18` can resolve `mcp` 2.0.0 and die at import.
Pinning the version keeps tool metadata and behavior reproducible for users and reviewers. The
`search` groups are left out on purpose — `flyte-docs` already serves them hosted, and
enabling them here shallow-clones ~120 MB into `~/.flyte/mcp` on first launch.

It is tenant-agnostic. The bundled command uses `--no-init-from-config`, so an
unconfigured client gets a clean MCP error instead of the server starting an interactive
login on its JSON-RPC stdout. Set `FLYTE_MCP_PROJECT` and `FLYTE_MCP_DOMAIN` in the MCP
environment, or have calls supply `project` and `domain`, before using cluster tools.
**A cluster is optional** — the tools are still registered while you are deploying your
first cluster, and calls then report the missing target rather than breaking the protocol.

Test it end-to-end — this spawns the server exactly as a client does, handshakes, lists the
tools, and makes one real read-only call:

```
python3 scripts/smoke_test_mcp.py
```

Change what is served by editing `args` in `plugins/flyte/.mcp.json` (`--tool-groups`,
`--tools`, `--read-only`), and scope it with `FLYTE_MCP_PROJECT` / `FLYTE_MCP_DOMAIN` — see
the plugin [README](plugins/flyte/README.md).

### Adding the MCP servers elsewhere

Hermes, opencode, and pi all support MCP — this plugin just doesn't configure it for them.
(Claude Code and Codex get both servers from the plugin; use these snippets only if you
want them configured globally rather than per-plugin.) Wiring it up yourself is a few
lines.

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

**`flyte-cluster`** is a local stdio process, but it is just the SDK's published
`flyte-mcp` entry point run with `uvx` — no checkout, no path, so it is as portable as the
hosted one. It needs [`uv`](https://docs.astral.sh/uv/) on `PATH`, a usable Flyte login,
and a project/domain supplied by `FLYTE_MCP_PROJECT` / `FLYTE_MCP_DOMAIN` or the tool call:

```toml
# Codex — ~/.codex/config.toml
[mcp_servers.flyte-cluster]
command = "uvx"
args = ["--from", "flyte[mcp]==2.6.10", "flyte-mcp", "--transport", "stdio",
        "--tool-groups", "task,run,action,logs,app,trigger,project,secret,condition,identity",
        "--no-init-from-config"]
```

```json
// opencode — opencode.json
{ "mcp": { "flyte-cluster": { "type": "local", "enabled": true,
  "command": ["uvx", "--from", "flyte[mcp]==2.6.10", "flyte-mcp", "--transport", "stdio",
              "--tool-groups",
              "task,run,action,logs,app,trigger,project,secret,condition,identity",
              "--no-init-from-config"] } } }
```

```yaml
# Hermes — ~/.hermes/config.yaml
mcp_servers:
  flyte-cluster:
    command: "uvx"
    args: ["--from", "flyte[mcp]==2.6.10", "flyte-mcp", "--transport", "stdio",
           "--tool-groups", "task,run,action,logs,app,trigger,project,secret,condition,identity",
           "--no-init-from-config"]
```

Drop `--tool-groups` to get everything, including the three `search` tools — but then the
server shallow-clones a ~120 MB corpus into `~/.flyte/mcp` on first launch, which is exactly
what `flyte-docs` exists to avoid.

## Layout

All skills live in the single `flyte` plugin:

```
.claude-plugin/marketplace.json             # marketplace catalog
package.json                                # pi package manifest (pi.skills)
plugins/flyte/.claude-plugin/plugin.json    # Claude Code plugin manifest
plugins/flyte/.codex-plugin/plugin.json     # Codex plugin manifest (points at .mcp.json)
plugins/flyte/.mcp.json                     # the two bundled MCP servers
plugins/flyte/skills/<skill>/SKILL.md
packaging/build.py                          # fans plugins/flyte out into the npm + PyPI packages
packaging/verify.py                         # builds every distribution and proves it installs
scripts/smoke_test_mcp.py                   # end-to-end check of the local MCP server
```

Each harness consumes a different part of this. Claude Code and Codex read the plugin
manifests, so the **plugin name** matters to them. Hermes, opencode, and pi install skills
by **directory path**, so `plugins/flyte/skills/…` is their interface.

`.mcp.json` is shared by Claude Code (which finds it by convention) and Codex (which is
pointed at it by `.codex-plugin/plugin.json`); the skills themselves stay portable across
every harness.

The PyPI packages are a fourth consumer: `packaging/build.py` vendors the whole
`plugins/flyte/` tree into each one, which is how `flyte-skills install` can write the
skills into any of these directories from a single release.

## Contributing

Add a new skill as a directory under `plugins/flyte/skills/<skill>/SKILL.md`.
It is picked up automatically by the `flyte` plugin, the Codex manifest, and the
`pi.skills` entry — no marketplace edit needed. Add a row to the skills table above. Keep
everything generic — no account IDs, hostnames, credentials, or other environment-specific
values.

The published PyPI packages are generated from `plugins/flyte/`, so a new skill ships
with the next release automatically. Run `python packaging/verify.py` to check it packages
and installs cleanly. To cut a release, follow [`RELEASING.md`](RELEASING.md); for how the
packages are built, see [`packaging/README.md`](packaging/README.md).
