# /// script
# requires-python = ">=3.12"
# dependencies = ["flyte[mcp]>=2.5.11"]
# ///
"""Serve the Flyte MCP server over stdio, degrading gracefully when there is no cluster.

The server always starts. What it exposes depends on whether a Flyte connection could be
resolved:

* **Connected** -- a Flyte config resolved with a project and domain. Exposes everything:
  run and inspect tasks, manage runs, apps, and triggers, plus the search tools.
* **Not connected** -- no usable config. Exposes the ``search`` tools only, which grep a
  local corpus and need no cluster at all, so the server is still useful for looking up
  Flyte APIs, examples, and docs while writing code.

That split is deliberate. Someone installing this plugin to *deploy their first Flyte
cluster* has no config yet; failing at startup would make the plugin look broken at the
exact moment they are learning it. They get docs and example search instead, and the
control-plane tools appear on their own once they are logged in.

Nothing here is tenant-specific: ``flyte.init_from_config()`` performs the SDK's normal
config discovery, so the tools act on the same control plane your ``flyte`` CLI talks to.

Why this file exists rather than calling the SDK's entry point: ``flyte[mcp]`` <= 2.5.11
has no working stdio transport -- ``MCPAppEnvironment`` accepts ``transport="stdio"`` but
``__post_init__`` builds the Starlette app and points ``_server`` at uvicorn for every
value, so "stdio" silently serves HTTP. flyteorg/flyte-sdk#1319 fixes that upstream; once
released, ``.mcp.json`` can call ``flyte-mcp --transport stdio`` and this file goes away.

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
``FLYTE_MCP_NO_SEARCH``         set to skip the search corpus entirely

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
    if os.environ.get("FLYTE_MCP_NO_SEARCH"):
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
        if not explicit:
            # Offer the cluster tools only when they can actually work.
            tool_groups = ["all"] if connected else ["search"]
        elif not connected:
            print(
                f"Flyte is not connected ({reason}), but tools were selected explicitly; "
                "any control-plane tool will fail when called.",
                file=sys.stderr,
            )

        enabled = _resolve_tools(tool_groups, tools)
        paths = _search_paths(enabled & set(SEARCH_TOOLS))

        if connected:
            instructions = (
                f"Tools for the Flyte control plane you are authenticated against ({reason}): "
                "run and inspect tasks, manage runs, apps, and triggers. The search tools "
                "grep Flyte SDK examples, docs examples, and llms.txt."
            )
        else:
            instructions = (
                "Flyte search tools only: grep Flyte SDK examples, docs examples, and "
                "llms.txt to ground Flyte code you write. This server is NOT connected to a "
                f"Flyte cluster ({reason}), so it cannot run tasks or inspect runs. Once a "
                "Flyte config with a project and domain is available, restart this server "
                "to gain the control-plane tools."
            )

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
