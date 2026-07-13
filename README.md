# Flyte Skills

A [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin marketplace of
skills for working with [Flyte](https://flyte.org).

## Install

```
/plugin marketplace add flyteorg/skills
/plugin install <skill>@flyte-skills
```

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
.claude-plugin/marketplace.json          # marketplace catalog
plugins/<skill>/.claude-plugin/plugin.json
plugins/<skill>/skills/<skill>/SKILL.md
```

## Contributing

Add a new skill as a plugin directory under `plugins/`, then list it in
`.claude-plugin/marketplace.json`. Keep everything generic — no account IDs,
hostnames, credentials, or other environment-specific values.
