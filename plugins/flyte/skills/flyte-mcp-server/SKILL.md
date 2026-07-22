---
name: flyte-mcp-server
description: 'Set up, run, scope, and connect the Flyte MCP server, which exposes Flyte control-plane operations (run tasks, monitor runs, manage apps/triggers, search docs/examples) as Model Context Protocol tools for AI assistants like Claude Code and OpenCode. Covers the server bundled with this plugin, running it standalone over local HTTP, deploying it remotely with FlyteMCPAppEnvironment, tool-group/tool/allowlist scoping, and when to prefer the MCP server over the flyte CLI. Use when the user wants an assistant to act on their Flyte cluster, wire up flyte-mcp, or decide between MCP and CLI. Trigger words: "MCP", "flyte-mcp", "MCP server", "connect Claude to Flyte", "agentic Flyte", "mcp add", "act on my cluster".'
---

# Flyte MCP Server Skill

The **Flyte MCP server** exposes Flyte control-plane operations as
[Model Context Protocol](https://modelcontextprotocol.io) tools, so an AI assistant
(Claude Code, OpenCode, Cursor, …) can run tasks, monitor runs, manage apps and triggers,
and search Flyte docs/examples **on your behalf** — without you copy-pasting CLI commands.

It is **tenant-agnostic**: the server calls `flyte.init_from_config()`, so it always acts on
the control plane you are already authenticated against. Nothing is hardcoded to a
particular cluster.

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

### Bundled with this plugin (recommended)

The plugin's `.mcp.json` declares **two** servers, split so nothing is duplicated:

| Server | Transport | Tools | Needs |
|---|---|---|---|
| **`flyte-docs`** | hosted HTTP | 3 `search` — Flyte SDK examples, docs examples, `llms.txt` | nothing at all |
| **`flyte`** | local stdio | 13 control-plane — run/inspect tasks, manage runs, apps, triggers | `uv`, plus a config with `project` **and** `domain` |

`flyte-docs` is a read-only, unauthenticated server **operated by Union** at
`flyte-mcp.apps.demo.hosted.unionai.cloud`. It makes search work with zero setup — no
install, no corpus, no `uv`. The tradeoff is that your search queries leave your machine;
see [Keeping search local](#keeping-search-local) if that matters.

`flyte` is tenant-agnostic: it calls `flyte.init_from_config()`, so it acts on whatever
control plane your `flyte` CLI is already authenticated against. **A cluster is optional** —
it starts either way and simply offers nothing until one is reachable, so the plugin never
looks broken to someone who is still deploying their first cluster. The tools appear once
you are logged in; **restart the server**, since the choice is made at startup.

> Both halves of "connected" matter. `flyte.init_from_config()` **succeeds even when it
> finds no config file at all**, leaving `project`/`domain` unset — after which every
> control-plane tool fails with `project_id.domain: must be at least 1 characters`, which
> reads as a tool bug rather than missing setup. The server checks for that and withholds
> those tools instead.

### Keeping search local

Set `FLYTE_MCP_LOCAL_SEARCH=1` and the `flyte` server serves the search tools itself, from
a corpus cached under `~/.flyte/mcp` (~120 MB, a few seconds on first run). Nothing leaves
your machine and it works offline.

Note that this does **not** stop `flyte-docs` from being declared — Claude Code manages
plugin MCP servers through plugin installation, not `/mcp`, so there is no per-server
toggle. To suppress it entirely you need a `deniedMcpServers` entry (see
[Managed MCP configuration](https://code.claude.com/docs/en/managed-mcp)) or to disable the
plugin. Otherwise you would see both sets of search tools.

### Environment variables

| Variable | Default |
|---|---|
| `FLYTE_MCP_TOOL_GROUPS` | automatic — cluster tools when connected |
| `FLYTE_MCP_TOOLS` | — (mutually exclusive with groups) |
| `FLYTE_MCP_CONFIG` | — (normal config discovery) |
| `FLYTE_MCP_PROJECT` / `FLYTE_MCP_DOMAIN` | — (from config) |
| `FLYTE_MCP_TASK_ALLOWLIST` / `_APP_` / `_TRIGGER_` | — (unrestricted) |
| `FLYTE_MCP_LOCAL_SEARCH` | — (set to serve search locally) |

Setting `FLYTE_MCP_TOOL_GROUPS`/`FLYTE_MCP_TOOLS` overrides the automatic choice, including
offering control-plane tools while disconnected — they will fail when called.

The search corpus is a ~120 MB shallow clone of flyte-sdk and unionai-examples plus
`llms.txt`, cached under `~/.flyte/mcp`. First run takes a few seconds; later runs reuse it.

### Local, standalone — for development

By default `flyte-mcp` serves **streamable-HTTP under uvicorn**. It binds `--port`
(default 8080) and blocks:

```bash
uvx --from "flyte[mcp]" flyte-mcp            # http://localhost:8080/flyte-mcp/mcp
```

Always use `uvx --from "flyte[mcp]"`, never `uvx --with "flyte[mcp]"`. `uvx <cmd>` resolves
the package from the *command name*, and `flyte-mcp` is an unrelated third-party project on
PyPI — `--with` installs and runs **that** instead.

#### stdio: check your `flyte` version first

MCP clients usually prefer to launch a local server as a subprocess over stdio.

- **`flyte[mcp]` ≤ 2.5.11** has no working stdio transport. `MCPAppEnvironment` accepts
  `transport="stdio"` and validates it, but `__post_init__` builds the Starlette app and
  points `_server` at uvicorn for *every* value — so `"stdio"` silently serves HTTP. Use
  this plugin's bundled server, which runs the environment's `FastMCP` object directly
  (`env.mcp.run(transport="stdio")`) to work around it.
- **Newer versions** support it natively
  ([flyte-sdk#1319](https://github.com/flyteorg/flyte-sdk/pull/1319)):

  ```bash
  uvx --from "flyte[mcp]" flyte-mcp --transport stdio
  ```

  Note that stdio cannot be deployed or served via `flyte.serve()` — that path runs the
  server on a background thread behind an HTTP health check. It is local-only.

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
        "Use the available tools to run tasks, monitor runs, manage apps and triggers, "
        "and search SDK/docs examples."
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

Installing the `flyte` plugin is enough — its `.mcp.json` registers the server. To
wire one up by hand instead:

```bash
# Local, stdio — requires a flyte[mcp] with native stdio (see the version note above).
claude mcp add --transport stdio flyte-mcp -- \
  uvx --from "flyte[mcp]" flyte-mcp --transport stdio

# Local, HTTP — works on any version. Start `uvx --from "flyte[mcp]" flyte-mcp`
# first, leave it running, then attach.
claude mcp add --transport http flyte-mcp-http http://localhost:8080/flyte-mcp/mcp

# Remote (HTTP, with a bearer token)
claude mcp add --transport http \
  --header "Authorization: Bearer $TOKEN" \
  flyte-mcp-remote https://<HOST>/flyte-mcp/mcp
```

On a version without native stdio, `--transport stdio` pointed at the bare `flyte-mcp`
command will appear to connect and then fail: the process serves HTTP while the client
waits for JSON-RPC on stdout.

### OpenCode

**Local, stdio** — on a `flyte[mcp]` with native stdio, `"type": "local"` works directly:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "flyte-mcp": {
      "type": "local",
      "command": ["uvx", "--from", "flyte[mcp]", "flyte-mcp", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

**Local, HTTP** — on older versions, `"type": "local"` would spawn a process expecting
stdio that only speaks HTTP. Start the server (`uvx --from "flyte[mcp]" flyte-mcp`) and
attach to it as a *remote* instead:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "flyte-mcp": {
      "type": "remote",
      "url": "http://localhost:8080/flyte-mcp/mcp",
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

Enable whole groups — the valid ones are `all`, `core`, `task`, `run`, `app`, `trigger`,
and `search`:

```python
mcp_env = FlyteMCPAppEnvironment(
    name="restricted-mcp",
    tool_groups=["task", "run", "search"],
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
    tool_groups=["task", "run", "trigger", "search"],
    task_allowlist=["my-project/my-task", "another-task"],
    app_allowlist=["my-app"],
    trigger_allowlist=["nightly-retrain"],
    instructions=(
        "This MCP server provides tools to run and monitor specific Flyte tasks, "
        "manage triggers, and search Flyte SDK/docs examples. "
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
| `task` | `run_task`, `get_task`, `list_tasks` |
| `run` | `get_run`, `wait_for_run`, `get_run_io`, `abort_run`, `list_runs` |
| `app` | `get_app`, `activate_app`, `deactivate_app` |
| `trigger` | `activate_trigger`, `deactivate_trigger` |
| `search` | `search_flyte_sdk_examples`, `search_flyte_docs_examples`, `search_full_docs` |

That is the complete surface — 16 tools. `all` selects every one of them; `core` selects
none (it serves only the HTTP routes, `/health` and the MCP mount).

> Earlier releases also exposed `build_image`, `build_uv_script_image_remote`,
> `run_uv_script_remote`, `flyte_uv_script_format`, and `flyte_uv_script_example` under
> `build` and `script` groups. Those were **removed in flyte-sdk v2.3.6**
> ([`c8a6ec5e`](https://github.com/flyteorg/flyte-sdk/commit/c8a6ec5e), "simplify flyte
> mcp"). Passing `--tool-groups build,script` now raises `Unknown tool group(s)`.

Mutating tools (`run_task`, `abort_run`, `activate_*`/`deactivate_*`) change cluster
state — allowlist them and gate them behind auth on shared servers.

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
