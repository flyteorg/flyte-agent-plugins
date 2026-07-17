# Flyte Skills

A [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin marketplace of
skills for working with [Flyte](https://flyte.org).

## Install

```
/plugin marketplace add flyteorg/skills
/plugin install <skill>@flyte-skills
```

### Install a specific version

The `flyteorg/skills` shorthand tracks the default branch. To pin the marketplace to a
specific version, add it with the full git URL and append `#<ref>` — a **tag or branch
name** (bare commit SHAs are not supported; to pin an exact commit, tag it first):

```
/plugin marketplace add https://github.com/flyteorg/skills.git#<tag-or-branch>
/plugin install <skill>@flyte-skills
```

To switch to a different version later, remove and re-add the marketplace:

```
/plugin marketplace remove flyte-skills
/plugin marketplace add https://github.com/flyteorg/skills.git#<other-ref>
```

## Install with other agent harnesses

The skills are plain [Agent Skills](https://agentskills.io) (`SKILL.md` + YAML
frontmatter), so they work in any harness that supports the standard.

### OpenAI Codex CLI

Codex reads this repo's marketplace catalog and the per-plugin
`.codex-plugin/plugin.json` manifests:

```
codex plugin marketplace add flyteorg/skills            # or --ref <tag-or-branch> to pin
```

Then browse and install the plugins via `/plugins` inside Codex.

### Hermes

Install individual skills by their repo path (Hermes installs from the default
branch; ref pinning is not supported):

```
hermes skills install flyteorg/skills/plugins/<plugin>/skills/<skill-name>
# e.g.
hermes skills install flyteorg/skills/plugins/flyte-deploy-aws/skills/flyte-deploy-aws
```

`hermes skills check` / `hermes skills update` refresh installed skills.

### opencode

opencode discovers `SKILL.md` folders in `.opencode/skills/` (project) and
`~/.config/opencode/skills/` (global). The easiest install is the
[`skills` CLI](https://github.com/vercel-labs/skills), which reads this repo's
marketplace manifest:

```
npx skills add flyteorg/skills          # interactive skill + agent selection
npx skills add flyteorg/skills@<ref>    # pin a tag/branch/commit
```

Or copy a skill folder directly, e.g.
`cp -r plugins/flyte-deploy-aws/skills/flyte-deploy-aws ~/.config/opencode/skills/`.

### pi

pi reads the `pi.skills` manifest in this repo's `package.json`:

```
pi install https://github.com/flyteorg/skills           # default branch
pi install git:github.com/flyteorg/skills@<tag>         # pinned to a tag/commit
```

(Alternatively, clone the repo into `~/.pi/agent/skills/` — pi discovers nested
`SKILL.md` folders recursively.)

## Skills

### Deployment

| Skill | Description |
|-------|-------------|
| [`flyte-deploy-aws`](plugins/flyte-deploy-aws) | Deploy a Flyte v2 (`flyte-binary`) cluster on AWS from scratch — EKS + S3 + RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS (ACM, incl. cross-account DNS) and Okta/OIDC SSO. |
| [`flyte-deploy-kind`](plugins/flyte-deploy-kind) | Deploy a Flyte v2 (`flyte-binary`) cluster on `kind` — on your local machine or a cloud VM (DigitalOcean, AWS EC2, or GCP), backed by a hosted PostgreSQL (Supabase/external) and object store (S3/R2), with optional OIDC auth via Traefik + oauth2-proxy and an in-cluster Dex IdP. |

### SDK / Workflow Authoring

| Skill | Description |
|-------|-------------|
| [`flyte-sdk-author`](plugins/flyte-sdk-skills/skills/flyte-sdk-author) | Creates Flyte 2 project scaffolds (tasks, workflows, launch plans, apps), selects patterns (map tasks, traces, dynamic workflows, conditions), and generates code from templates. For: "write a Flyte workflow", "create a task", "scaffold a Flyte project". |
| [`flyte-sdk-types`](plugins/flyte-sdk-skills/skills/flyte-sdk-types) | Guides correct types, I/O, and serialization for common data (Pandas, Arrow, Parquet, images, audio, HF datasets), including data locality and storage best practices. For: type annotations, custom type transformers, DataFrame handling. |
| [`flyte-sdk-ship`](plugins/flyte-sdk-skills/skills/flyte-sdk-ship) | Generates flyte.Image specs, Dockerfiles, dependency management, image tagging strategy, and reproducible build instructions. For: custom images, BYOI, uv monorepo, dependency pinning. |
| [`flyte-sdk-eval`](plugins/flyte-sdk-skills/skills/flyte-sdk-eval) | Builds minimal evaluation harnesses (unit tests + small-run workflows) and suggests ways to validate correctness and performance early. For: testing, data quality checks, experiment tracking, benchmarking. |
| [`flyte-sdk-optimize`](plugins/flyte-sdk-skills/skills/flyte-sdk-optimize) | Suggests performance improvements (task granularity, caching, resource requests, data format changes) using observed run metadata. For: slow tasks, throughput, latency, cost optimization. |
| [`flyte-sdk-run`](plugins/flyte-sdk-skills/skills/flyte-sdk-run) | Runs workflows, interacts with runs and actions, retrieves logs and data, and manages run lifecycle. For: running, watching, logging, re-running, aborting, run metadata. |
| [`flyte-sdk-app`](plugins/flyte-sdk-skills/skills/flyte-sdk-app) | Builds and serves Flyte 2 apps — FastAPI, Streamlit, vLLM, SGLang, WebSocket, and browser apps. For: model serving, REST APIs, dashboards, LLM backends, webhooks. |
| [`flyte-sdk-agent`](plugins/flyte-sdk-skills/skills/flyte-sdk-agent) | Builds durable agents with Flyte 2 — ReAct patterns, Plan-and-Execute, LangGraph/PydanticAI/OpenAI Agents integration, agent memory, MCP tool integration. For: agent building, tool calling, memory, chat UI. |
| [`flyte-sdk-data`](plugins/flyte-sdk-skills/skills/flyte-sdk-data) | Handles data engineering patterns: ETL pipelines, data processing, data quality checks, fanout/map tasks, conditions, dynamic workflows, and batch data transformations. For: ETL, Parquet, CSV, JsonlFile/Dir, schema validation. |
| [`flyte-sdk-ml`](plugins/flyte-sdk-skills/skills/flyte-sdk-ml) | Handles ML workload patterns: model training, hyperparameter optimization, experiment tracking, model evaluation and selection, batch inference, real-time serving, and model monitoring. For: PyTorch, scikit-learn, HuggingFace, GPU, drift detection. |

Example:

```
/plugin install flyte-deploy-aws@flyte-skills
```

Then ask Claude to "deploy a Flyte v2 cluster on AWS", or invoke it directly with
`/flyte-deploy-aws:flyte-deploy-aws`.

## Layout

```
.claude-plugin/marketplace.json          # marketplace catalog (Claude Code + Codex)
package.json                             # pi package manifest (pi.skills)
plugins/<plugin>/.claude-plugin/plugin.json   # Claude Code plugin manifest
plugins/<plugin>/.codex-plugin/plugin.json    # Codex plugin manifest
plugins/<plugin>/skills/<skill>/SKILL.md
```

## Contributing

Add a new skill as a plugin directory under `plugins/`, then list it in
`.claude-plugin/marketplace.json` and the `pi.skills` array in `package.json`,
and give it a `.codex-plugin/plugin.json`. Keep everything generic — no account
IDs, hostnames, credentials, or other environment-specific values.
