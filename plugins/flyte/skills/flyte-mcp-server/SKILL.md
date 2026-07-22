---
name: flyte-mcp-server
description: 'Decide when to drive Flyte through MCP tools versus the flyte CLI, and build your own Flyte MCP server with FlyteMCPAppEnvironment — choosing transports, scoping it with tool groups, explicit tool lists, and task/app/trigger allowlists, deploying it to a cluster, and connecting clients to it. Use when the user wants to stand up an MCP server for their team, restrict what an assistant may touch on a cluster, or decide whether a job belongs in MCP or the CLI. Trigger words: "MCP", "flyte-mcp", "MCP server", "FlyteMCPAppEnvironment", "agentic Flyte", "scope the MCP server", "allowlist", "act on my cluster".'
---

# Flyte MCP Server Skill

The **Flyte MCP server** exposes Flyte control-plane operations as
[Model Context Protocol](https://modelcontextprotocol.io) tools, so an AI assistant can run
tasks, monitor runs, manage apps and triggers, and search Flyte docs on the user's behalf.

It is **tenant-agnostic**: the server calls `flyte.init_from_config()`, so it acts on the
control plane the caller is already authenticated against. Nothing is hardcoded to a cluster.

> **This plugin already bundles two MCP servers** (`flyte-docs` for search, `flyte-cluster`
> for the control plane), configured automatically on install. Users do not need to build
> anything to use them — point them at the plugin README rather than this skill. This skill
> is for *deciding when to use MCP at all*, and for *building a server of your own*.

## Grounding References

| Resource | URL |
|---|---|
| Flyte MCP server docs | https://www.union.ai/docs/v2/flyte/user-guide/build-mcp/flyte_mcp_server/ |
| `FlyteMCPAppEnvironment` API | https://www.union.ai/docs/v2/flyte/api-reference/flyte-sdk/packages/flyte.ai.mcp/flytemcpappenvironment/ |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |

## When to use the MCP server vs. the `flyte` CLI

Both talk to the **same control plane** — the difference is *who drives*. MCP is for
letting an **AI assistant** act; the CLI is for a **human or a script** acting
deterministically.

**Prefer the MCP server when:**

- **Agentic development loops** — the assistant runs a task, waits, reads the outputs, and
  iterates without a human shuttling commands back and forth.
- **Conversational operations** — "list my recent runs", "is run X still going?", "abort
  the stuck one".
- **Docs-aware coding** — the `search` tools ground generated Flyte code in real examples.
- **Scoped self-service** — give a trusted agent a narrow surface (a few allowlisted tasks,
  no destructive tools) to do one job.

**Prefer the `flyte` CLI when:**

- **CI/CD, shell scripts, cron** — deterministic, non-interactive automation with no LLM in
  the loop. See the `flyte-sdk-run` / `flyte-sdk-ship` skills.
- **Full surface area** — the CLI does more than MCP: config creation, `devbox`, log
  streaming, secrets, project/domain admin. MCP exposes a curated, safer subset.
- **Precise, repeatable control** — one exact command, no model choosing arguments.
- **First-time setup and auth** — creating the config and logging in are CLI/SDK tasks. The
  server *reuses* that config; it never creates one.

Rule of thumb: **CLI/SDK to build and configure; MCP to let an assistant operate.**

## Building your own server

Requires Python ≥ 3.12, `pip install 'flyte[mcp]'`, and an authenticated Flyte config.

Deploy it as a long-running Flyte app so a team can share one endpoint:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["flyte>=2.0.0", "mcp", "starlette", "uvicorn"]
# ///

import flyte
from flyte.ai.mcp import FlyteMCPAppEnvironment

mcp_env = FlyteMCPAppEnvironment(
    name="flyte-mcp-server",
    resources=flyte.Resources(cpu=1, memory="512Mi"),
    transport="streamable-http",
    instructions=(
        "Tools to interact with the Flyte control plane: run tasks, monitor runs, "
        "manage apps and triggers, and search SDK/docs examples."
    ),
)

if __name__ == "__main__":
    flyte.init_from_config()
    app_handle = flyte.serve(mcp_env)
    app_handle.activate(wait=True)
    print(f"App is ready at {app_handle.endpoint}")
```

The endpoint is `https://<HOST>{mcp_mount_path}/mcp`. **Keep authentication enabled** on
anything deployed — these tools mutate cluster state.

**Transports.** `streamable-http` (default) and `sse` are servable and deployable. `stdio`
is local-only: it speaks JSON-RPC on the process's stdin/stdout for a client that launches
it as a subprocess, and cannot be deployed — `flyte.serve()` runs the server on a background
thread behind an HTTP health check that a stdio server never satisfies. Run
`flyte-mcp --transport stdio` for that case instead.

> On `flyte[mcp]` ≤ 2.5.11 `transport="stdio"` is accepted but silently serves HTTP —
> `__post_init__` builds the Starlette app for every transport value. Fixed in
> [flyte-sdk#1319](https://github.com/flyteorg/flyte-sdk/pull/1319).

## Scoping the server

Three layers, coarse to fine. On anything shared, **scope down** — expose only what the
assistant needs.

```python
# Coarse: whole groups. Valid: all, core, task, run, app, trigger, search.
FlyteMCPAppEnvironment(name="restricted-mcp", tool_groups=["task", "run", "search"])

# Medium: an explicit list, e.g. a read-only server.
FlyteMCPAppEnvironment(name="read-only-mcp", tools=["get_run", "list_runs", "get_run_io"])

# Fine: allowlists restrict which resources the tools may target.
FlyteMCPAppEnvironment(
    name="restricted-mcp",
    tool_groups=["task", "run", "trigger", "search"],
    task_allowlist=["my-project/my-task", "another-task"],
    app_allowlist=["my-app"],
    trigger_allowlist=["nightly-retrain"],
    instructions="Runs and monitors specific Flyte tasks. Only allowlisted tasks are reachable.",
)
```

`tool_groups` and `tools` are mutually exclusive. Do not hardcode a tool list in
documentation — read it from the running server, which describes its own tools.

The mutating tools are `run_task`, `abort_run`, and `activate_*`/`deactivate_*`. Everything
else only reads.

## Connecting to a server you deployed

```bash
claude mcp add --transport http \
  --header "Authorization: Bearer $TOKEN" \
  flyte-mcp-remote https://<HOST>/flyte-mcp/mcp
```

```json
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "flyte-mcp-remote": {
      "type": "remote",
      "url": "https://<HOST>/flyte-mcp/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer $TOKEN" }
    }
  }
}
```

## Anti-Patterns

1. **Don't reach for MCP in CI or shell scripts** — use the CLI/SDK for deterministic,
   non-interactive automation.
2. **Don't deploy with all tool groups and no allowlists** — that hands an assistant
   unrestricted, mutating access to a cluster.
3. **Don't disable auth on a deployed server** to "make it easier". Its tools run and abort
   real work.
4. **Don't expect the server to create a config or log anyone in** — it only *uses* an
   existing authenticated config.
5. **Don't assume MCP covers the full CLI surface** — config management, `devbox`, log
   streaming, and admin operations stay CLI/SDK tasks.
6. **Don't write vague `instructions`** — they steer the assistant's tool choice. Say what
   the server is for and what it may touch.
