# /// script
# requires-python = ">=3.12"
# dependencies = ["flyte[mcp]>=2.5.11"]
# ///
"""Serve the Flyte MCP server over stdio, degrading gracefully when there is no cluster.

The server always starts, and offers only what can actually work:

* **Connected** -- a Flyte config resolved with a project *and* domain. Exposes the
  control-plane tools: run and inspect tasks, manage runs, apps, and triggers.
* **Not connected** -- no usable config. Exposes nothing rather than tools that would fail
  on every call.

That is deliberate. Someone installing this plugin to *deploy their first Flyte cluster*
has no config yet; failing at startup would make the plugin look broken at the exact
moment they are learning it. The control-plane tools appear on their own once they are
logged in (restart required -- the choice is made at startup).

Search is normally served by the sibling ``flyte-docs`` server declared in ``.mcp.json``,
which is hosted and needs no local corpus, so this file does not duplicate it. Set
``FLYTE_MCP_LOCAL_SEARCH`` to serve search here instead, from a local corpus -- useful
offline, or when search queries should not leave the machine.

Nothing here is tenant-specific: ``flyte.init_from_config()`` performs the SDK's normal
config discovery, so the tools act on the same control plane your ``flyte`` CLI talks to.

Why this file exists rather than ``.mcp.json`` just invoking the SDK's own ``flyte-mcp``
entry point -- two reasons, one temporary and one not:

1. *Temporary.* ``flyte[mcp]`` <= 2.5.11 has no working stdio transport.
   ``MCPAppEnvironment`` accepts ``transport="stdio"`` but ``__post_init__`` builds the
   Starlette app and points ``_server`` at uvicorn for every value, so "stdio" silently
   serves HTTP. flyteorg/flyte-sdk#1319 fixes that; it does not remove the need for this
   file.

2. *Ongoing.* ``flyte-mcp`` cannot express what this server does. It has no
   ``--project``/``--domain``, no allowlist flags, and no notion of degrading to the search
   tools when no cluster is reachable -- it initializes unconditionally and leaves the
   control-plane tools to fail at call time. The degrade-vs-fail default differs on
   purpose: this server is started automatically by an MCP client for someone who may not
   even have a cluster, whereas someone typing ``flyte-mcp`` almost certainly has one and
   is better served by a loud failure.

Retiring this file therefore needs the CLI to grow ``--project``, ``--domain``, the three
allowlist flags, and an explicit opt-in such as ``--fallback-tool-groups search``. At that
point ``.mcp.json`` can call ``flyte-mcp`` directly, which also drops the
``${CLAUDE_PLUGIN_ROOT}`` path that currently keeps the bundled server Claude Code-only
(Codex does not expand it -- openai/codex#22842).

Configuration is read from the environment, because this file is plugin-managed and gets
overwritten on update:

``FLYTE_MCP_TOOL_GROUPS``       comma-separated groups; overrides the automatic choice
``FLYTE_MCP_TOOLS``             comma-separated tool names (mutually exclusive with groups)
``FLYTE_MCP_CONFIG``            path to a Flyte config file (default: normal discovery)
``FLYTE_MCP_PROJECT``           override the project from the config
``FLYTE_MCP_DOMAIN``            override the domain from the config
``FLYTE_MCP_TASK_ALLOWLIST``    comma-separated task allowlist
``FLYTE_MCP_APP_ALLOWLIST``     comma-separated app allowlist
``FLYTE_MCP_TRIGGER_ALLOWLIST`` comma-separated trigger allowlist
``FLYTE_MCP_LOCAL_SEARCH``      set to serve the search tools from a local corpus
                                instead of the hosted flyte-docs server

The search corpus is a ~120 MB shallow clone of flyte-sdk and unionai-examples plus
llms.txt, cached under ``~/.flyte/mcp``. First run takes a few seconds; later runs reuse
the cache.
"""

from __future__ import annotations

import contextlib
import os
import sys

SEARCH_TOOLS = ("search_flyte_sdk_examples", "search_flyte_docs_examples", "search_full_docs")


def _csv(name: str) -> list[str] | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items or None


def _connect() -> tuple[bool, str]:
    """Try to initialize Flyte. Returns ``(connected, human-readable reason)``.

    "Connected" means a config resolved *and* carries a project and domain. Without those
    every control-plane tool fails at call time with a validation error about
    ``project_id.domain``, which reads as a broken tool rather than missing setup -- so we
    treat it as not connected and simply do not offer those tools.
    """
    import flyte

    try:
        flyte.init_from_config(
            os.environ.get("FLYTE_MCP_CONFIG"),
            project=os.environ.get("FLYTE_MCP_PROJECT"),
            domain=os.environ.get("FLYTE_MCP_DOMAIN"),
        )
    except Exception as e:
        return False, f"no usable Flyte config ({type(e).__name__}: {e})"

    try:
        from flyte._initialize import get_init_config

        cfg = get_init_config()
    except ImportError:  # private API moved; assume the init above was enough
        return True, "Flyte initialized"

    missing = [n for n in ("project", "domain") if getattr(cfg, n, None) is None]
    if missing:
        found = getattr(cfg, "source_config_path", None)
        where = f"config {found}" if found else "no config file found"
        return False, f"{' and '.join(missing)} not set ({where})"

    return True, f"project={cfg.project} domain={cfg.domain}"


def _search_paths(enabled: set[str]) -> dict[str, str | None]:
    """Materialize the local search corpus for whichever search tools are enabled."""
    paths: dict[str, str | None] = {
        "sdk_examples_path": None,
        "docs_examples_path": None,
        "full_docs_path": None,
    }
    if not os.environ.get("FLYTE_MCP_LOCAL_SEARCH"):
        # Off by default: the plugin ships a hosted `flyte-docs` server that already
        # provides these tools with no local corpus. Opt in for an offline/private one.
        return paths
    try:
        from flyte._bin.mcp import _MCP_CACHE_DIR, _prepare_search_corpus
    except ImportError:
        print("Could not import the search corpus helper; search tools may be empty.", file=sys.stderr)
        return paths

    try:
        sdk, docs, full = _prepare_search_corpus(
            _MCP_CACHE_DIR,
            fetch_sdk_examples="search_flyte_sdk_examples" in enabled,
            fetch_docs_examples="search_flyte_docs_examples" in enabled,
            fetch_full_docs="search_full_docs" in enabled,
        )
    except Exception as e:
        # A failed clone must not take the whole server down -- the control-plane tools
        # (if any) are still perfectly usable.
        print(f"Search corpus unavailable ({type(e).__name__}: {e}).", file=sys.stderr)
        return paths

    paths.update(sdk_examples_path=sdk, docs_examples_path=docs, full_docs_path=full)
    return paths


def main() -> int:
    from flyte.ai.mcp import FlyteMCPAppEnvironment
    from flyte.ai.mcp._flyte_mcp_app import _resolve_tools

    tool_groups = _csv("FLYTE_MCP_TOOL_GROUPS")
    tools = _csv("FLYTE_MCP_TOOLS")
    if tool_groups and tools:
        print("Set FLYTE_MCP_TOOL_GROUPS or FLYTE_MCP_TOOLS, not both.", file=sys.stderr)
        return 2

    # stdout is the JSON-RPC channel; anything printed during setup would corrupt it.
    with contextlib.redirect_stdout(sys.stderr):
        connected, reason = _connect()

        explicit = bool(tool_groups or tools)

        # Resolve the corpus before choosing tools, not after: registering a search tool
        # whose corpus is missing produces a tool that exists and always raises
        # "sdk_examples_path is not configured", which is worse than not offering it.
        wanted = _resolve_tools(tool_groups, tools) if explicit else set(SEARCH_TOOLS)
        paths = _search_paths(wanted & set(SEARCH_TOOLS))
        search_ok = any(paths.values())

        if not explicit:
            # Offer only what can actually work: cluster tools when connected, search
            # tools when their corpus is present. Either may be absent independently.
            groups = ["task", "run", "app", "trigger"] if connected else []
            if search_ok:
                groups.append("search")
            if not groups:
                print(
                    f"No tools available: not connected ({reason}) and no search corpus. "
                    "Serving an empty tool set.",
                    file=sys.stderr,
                )
                groups = ["core"]
            tool_groups = groups
        elif not connected:
            print(
                f"Flyte is not connected ({reason}), but tools were selected explicitly; "
                "any control-plane tool will fail when called.",
                file=sys.stderr,
            )

        enabled = _resolve_tools(tool_groups, tools)

        parts = []
        if connected:
            parts.append(
                f"Tools for the Flyte control plane you are authenticated against ({reason}): "
                "run and inspect tasks, manage runs, apps, and triggers."
            )
        else:
            parts.append(
                "This server is NOT connected to a Flyte cluster "
                f"({reason}), so it cannot run tasks or inspect runs. Once a Flyte config "
                "with a project and domain is available, restart this server to gain the "
                "control-plane tools."
            )
        if search_ok:
            parts.append(
                "The search tools grep a local copy of Flyte SDK examples, docs examples, "
                "and llms.txt -- use them to ground Flyte code you write."
            )
        instructions = " ".join(parts)

        print(
            f"flyte-mcp: {'connected' if connected else 'not connected'} ({reason}); "
            f"serving {len(enabled)} tool(s)",
            file=sys.stderr,
        )

        env = FlyteMCPAppEnvironment(
            name="flyte-mcp",
            instructions=instructions,
            tool_groups=tool_groups,
            tools=tools,
            task_allowlist=_csv("FLYTE_MCP_TASK_ALLOWLIST"),
            app_allowlist=_csv("FLYTE_MCP_APP_ALLOWLIST"),
            trigger_allowlist=_csv("FLYTE_MCP_TRIGGER_ALLOWLIST"),
            **paths,
        )

    env.mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
