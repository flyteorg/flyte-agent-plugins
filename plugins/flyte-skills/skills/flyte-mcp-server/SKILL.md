---
name: flyte-mcp-server
description: 'Set up, run, scope, and connect the Flyte MCP server, which exposes Flyte control-plane operations (run tasks, monitor runs, manage apps/triggers, build images, run uv scripts, search docs/examples) as Model Context Protocol tools for AI assistants like Claude Code and OpenCode. Covers running locally with uvx (stdio), deploying remotely over HTTP with FlyteMCPAppEnvironment, tool-group/tool/allowlist scoping, and when to prefer the MCP server over the flyte CLI. Use when the user wants an assistant to act on their Flyte cluster, wire up flyte-mcp, or decide between MCP and CLI. Trigger words: "MCP", "flyte-mcp", "MCP server", "connect Claude to Flyte", "agentic Flyte", "mcp add", "act on my cluster".'
---

# Flyte MCP Server Skill

The **Flyte MCP server** exposes Flyte control-plane operations as
[Model Context Protocol](https://modelcontextprotocol.io) tools, so an AI assistant
(Claude Code, OpenCode, Cursor, …) can run tasks, monitor runs, manage apps and triggers,
build images, run `uv` scripts, and search Flyte docs/examples **on your behalf** — without
you copy-pasting CLI commands.

## Grounding References

| Resource | URL |
|---|---|
| Flyte MCP server docs | https://www.union.ai/docs/v2/flyte/user-guide/build-mcp/flyte_mcp_server/ |
| User-defined MCP server | https://www.union.ai/docs/v2/flyte/user-guide/build-mcp/mcp_server/ |
| `FlyteMCPAppEnvironment` API | https://www.union.ai/docs/v2/flyte/api-reference/flyte-sdk/packages/flyte.ai.mcp/flytemcpappenvironment/ |
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |

## When to use the MCP server vs. the `flyte` CLI

The MCP server and the CLI talk to the **same control plane** — the difference is *who
drives*. The MCP server is for letting an **AI assistant** act; the CLI is for a **human
or a script** acting deterministically.

**Prefer the MCP server when:**

- **Agentic development loops** — you want the assistant to run a task, wait for it, read
  its outputs, and iterate autonomously, without you shuttling commands back and forth.
- **Conversational operations** — "list my recent runs", "is run X still going?", "abort
  the stuck one" — expressed in natural language, executed as tool calls.
- **Docs- and example-aware coding** — enabling the `search` tools lets the assistant
  ground its generated Flyte code in real SDK examples and Union docs.
- **Scoped self-service automation** — you want to give a trusted internal agent a
  tightly-scoped surface (a few allowlisted tasks, no destructive tools) to do a narrow job.

**Prefer the `flyte` CLI when:**

- **CI/CD, shell scripts, cron** — deterministic, non-interactive automation with no LLM in
  the loop. Use the `flyte-sdk-run` / `flyte-sdk-ship` skills for those flows.
- **Full surface area** — the CLI exposes more than the MCP server (config creation,
  `devbox`, log streaming, secrets, project/domain admin). The MCP server intentionally
  exposes a curated, safer subset.
- **Precise, repeatable control** — when you want to run one exact command and know exactly
  what it does, without a model deciding which tool to call or with what arguments.
- **First-time setup and auth** — creating the Flyte config, logging in, and building images
  locally are CLI/SDK tasks (the MCP server *reuses* that config; it doesn't create it).

Rule of thumb: **CLI/SDK to build and configure; MCP to let an assistant operate.** They
are complementary — the MCP server uses your existing `flyte` config under the hood.

## Prerequisites

- **Python ≥ 3.12**
- **Install the MCP extra:** `pip install 'flyte[mcp]'` (or run ephemerally with `uvx`)
- **A working Flyte config** — the server calls `flyte.init_from_config()`, so you need an
  authenticated config (create one with `flyte create config …` and log in via the CLI/SDK
  first). See the `flyte-sdk-run` skill for config setup.

## Running the server

### Local (stdio) — for development

Runs against your local Flyte config; the client launches it as a subprocess.

```bash
uvx --from "flyte[mcp]" flyte-mcp
```

### Remote (HTTP) — for shared / production use

Deploy the server as a long-running Flyte app with authentication. Save as a `uv` script
(e.g. `flyte_mcp_app.py`) and run it:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#    "flyte>=2.0.0",
#    "mcp",
#    "starlette",
#    "uvicorn",
# ]
# ///

import flyte
from flyte.ai.mcp import FlyteMCPAppEnvironment

mcp_env = FlyteMCPAppEnvironment(
    name="flyte-mcp-server",
    resources=flyte.Resources(cpu=1, memory="512Mi"),
    transport="streamable-http",
    instructions=(
        "This MCP server provides tools to interact with the Flyte control plane. "
        "Use the available tools to run tasks, monitor runs, manage apps, build images, "
        "build and run UV scripts remotely, and search SDK/docs examples."
    ),
)

if __name__ == "__main__":
    flyte.init_from_config()
    app_handle = flyte.serve(mcp_env)
    app_handle.activate(wait=True)
    print(f"App is ready at {app_handle.endpoint}")
```

```bash
uv run flyte_mcp_app.py
```

The deployed endpoint is served at `https://<HOST>/flyte-mcp/mcp`. **Keep authentication
enabled** on any deployed server — its tools can mutate your cluster.

## Connecting clients

### Claude Code

```bash
# Local (stdio)
claude mcp add --transport stdio flyte-mcp -- uvx --from "flyte[mcp]" flyte-mcp

# Remote (HTTP, with a bearer token)
claude mcp add --transport http \
  --header "Authorization: Bearer $TOKEN" \
  flyte-mcp-remote https://<HOST>/flyte-mcp/mcp
```

### OpenCode

**Local** — in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "flyte-mcp": {
      "type": "local",
      "command": ["uvx", "--from", "flyte[mcp]", "flyte-mcp"],
      "enabled": true
    }
  }
}
```

**Remote** — in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "flyte-mcp-remote": {
      "type": "remote",
      "url": "https://<YOUR_HOST>/flyte-mcp/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer $TOKEN"
      }
    }
  }
}
```

## Scoping the server

Control what the server can do with three layers, from coarse to fine. On any shared or
deployed server, **scope down** — expose only what the assistant needs.

### Tool groups (coarse)

Enable whole groups such as `task`, `run`, `script`, and `search`:

```python
mcp_env = FlyteMCPAppEnvironment(
    name="restricted-mcp",
    tool_groups=["task", "run", "script"],
)
```

### Individual tools (medium) — e.g. a read-only server

```python
mcp_env = FlyteMCPAppEnvironment(
    name="read-only-mcp",
    tools=["get_run", "list_runs", "get_run_io"],
)
```

### Allowlists (fine) — restrict which resources tools may target

```python
mcp_env = FlyteMCPAppEnvironment(
    name="restricted-mcp",
    tool_groups=["task", "run", "script", "search"],
    task_allowlist=["my-project/my-task", "another-task"],
    app_allowlist=["my-app"],
    trigger_allowlist=["nightly-retrain"],
    instructions=(
        "This MCP server provides tools to run and monitor specific Flyte tasks, "
        "build and run UV scripts remotely, and search Flyte SDK/docs examples. "
        "Only allowlisted tasks can be accessed."
    ),
)
```

## MCP tools reference

The canonical tool names the server exposes (MCP clients may namespace them, e.g.
`flyte-mcp` → `run_task`). Enable the `search` group to give the assistant docs/example
grounding.

| Group | Tools |
|---|---|
| **Task** | `run_task`, `get_task`, `list_tasks` |
| **Run** | `get_run`, `wait_for_run`, `get_run_io`, `abort_run`, `list_runs` |
| **App / Trigger** | `get_app`, `activate_app`, `deactivate_app`, `activate_trigger`, `deactivate_trigger` |
| **Build / Image** | `build_image`, `build_uv_script_image_remote`, `run_uv_script_remote` |
| **Script utilities** | `flyte_uv_script_format`, `flyte_uv_script_example` |
| **Search** | `search_flyte_sdk_examples`, `search_flyte_docs_examples`, `search_full_docs` |

Mutating tools (`run_task`, `abort_run`, `activate_*`/`deactivate_*`, `build_*`, `run_*`)
change cluster state — allowlist them and gate them behind auth on shared servers.

## Best practices

1. **Write specific `instructions`** — they guide the assistant toward the right tools; be
   explicit about what the server is for and what it may touch.
2. **Allowlist every mutating tool** on shared servers; prefer an explicit `tools=[…]` list
   over broad `tool_groups` for read-only deployments.
3. **Leave authentication enabled** on any deployed (remote) server.
4. **Reuse, don't recreate, config** — set up and log in with the CLI/SDK first; the server
   inherits that config via `flyte.init_from_config()`.

## Anti-Patterns

1. **Don't reach for the MCP server in CI or shell scripts** — use the `flyte` CLI/SDK for
   deterministic, non-interactive automation.
2. **Don't deploy a remote server with all tool groups and no allowlists** — that hands an
   assistant unrestricted, mutating access to your cluster.
3. **Don't disable auth on a deployed server** to "make it easier" — its tools can run and
   abort work.
4. **Don't expect the MCP server to create your Flyte config or log you in** — do that with
   the CLI/SDK first; the server only *uses* an existing authenticated config.
5. **Don't assume MCP covers the full CLI surface** — config management, `devbox`, log
   streaming, and admin operations remain CLI/SDK tasks.
