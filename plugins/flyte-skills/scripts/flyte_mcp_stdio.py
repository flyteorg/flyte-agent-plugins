# /// script
# requires-python = ">=3.12"
# dependencies = ["flyte[mcp]>=2.5.11"]
# ///
"""Serve the Flyte MCP server over stdio, against whatever tenant you are logged into.

Nothing here is tenant-specific: ``flyte.init_from_config()`` performs the SDK's
normal config discovery, so the tools act on the same control plane your ``flyte``
CLI talks to. Your config must set ``project`` and ``domain`` (or you must pass
``FLYTE_MCP_PROJECT`` / ``FLYTE_MCP_DOMAIN``) -- see :func:`_unconfigured`.

Why this file exists instead of calling the SDK's own entry point: the ``flyte-mcp``
console script serves streamable-HTTP under uvicorn, and ``transport="stdio"`` is not
actually wired up -- ``MCPAppEnvironment.__post_init__`` builds the Starlette app and
points ``_server`` at uvicorn for every transport value. So we build the environment
for its fully-registered ``FastMCP`` instance and run *that* over stdio.

Configuration comes from the environment, because this file is plugin-managed and is
overwritten on update. Set these in ``.mcp.json``'s ``env`` block or your shell:

``FLYTE_MCP_CONFIG``            path to a Flyte config file (default: normal discovery)
``FLYTE_MCP_PROJECT``           override the project from the config
``FLYTE_MCP_DOMAIN``            override the domain from the config
``FLYTE_MCP_TOOL_GROUPS``       comma-separated groups (default: task,run,app,trigger)
``FLYTE_MCP_TOOLS``             comma-separated tool names (mutually exclusive with groups)
``FLYTE_MCP_TASK_ALLOWLIST``    comma-separated task allowlist
``FLYTE_MCP_APP_ALLOWLIST``     comma-separated app allowlist
``FLYTE_MCP_TRIGGER_ALLOWLIST`` comma-separated trigger allowlist

The ``search`` group is off by default: its tools clone flyte-sdk and unionai-examples
into ``~/.flyte/mcp`` on first use, which is a slow surprise during MCP startup, and
this plugin's skills already cover docs grounding. Set ``FLYTE_MCP_TOOL_GROUPS=all``
to opt in.
"""

from __future__ import annotations

import contextlib
import os
import sys


def _csv(name: str) -> list[str] | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items or None


def _unconfigured() -> str | None:
    """Return an explanation if the initialized config can't actually serve tool calls.

    ``project``/``domain`` are what the control-plane tools need and what
    ``flyte._initialize.require_project_and_domain`` guards on. The import is of a private
    module, so treat its absence as "cannot check" rather than failing the server.
    """
    try:
        from flyte._initialize import get_init_config
    except ImportError:
        return None

    cfg = get_init_config()
    missing = [name for name in ("project", "domain") if getattr(cfg, name, None) is None]
    if not missing:
        return None

    found = getattr(cfg, "source_config_path", None)
    where = f"Config in use: {found}." if found else "No Flyte config file was found."
    return (
        f"Flyte initialized, but {' and '.join(missing)} "
        f"{'is' if len(missing) == 1 else 'are'} not set — every control-plane tool would "
        f"fail. {where}\n"
        "Fix by either:\n"
        "  * creating a config with `flyte create config ...` (sets project/domain under "
        "the `task:` section), or\n"
        "  * setting FLYTE_MCP_PROJECT and FLYTE_MCP_DOMAIN (and FLYTE_MCP_CONFIG if your "
        "config lives outside the default search path).\n"
        "The rest of the flyte-skills plugin works without this."
    )


def main() -> int:
    import flyte
    from flyte.ai.mcp import FlyteMCPAppEnvironment

    tool_groups = _csv("FLYTE_MCP_TOOL_GROUPS")
    tools = _csv("FLYTE_MCP_TOOLS")
    if tool_groups and tools:
        print("Set FLYTE_MCP_TOOL_GROUPS or FLYTE_MCP_TOOLS, not both.", file=sys.stderr)
        return 2
    if tool_groups is None and tools is None:
        tool_groups = ["task", "run", "app", "trigger"]

    # stdout is the JSON-RPC channel; anything the SDK prints during setup would
    # corrupt the stream, so bend it to stderr for the duration.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            flyte.init_from_config(
                os.environ.get("FLYTE_MCP_CONFIG"),
                project=os.environ.get("FLYTE_MCP_PROJECT"),
                domain=os.environ.get("FLYTE_MCP_DOMAIN"),
            )
        except Exception as e:
            print(
                f"Could not initialize Flyte ({type(e).__name__}: {e}).\n"
                "The Flyte MCP server needs an authenticated config. Create one with "
                "`flyte create config ...` and log in, or point FLYTE_MCP_CONFIG at a "
                "config file. The rest of the flyte-skills plugin works without this.",
                file=sys.stderr,
            )
            return 1

        # init_from_config() succeeds even when it finds no config file at all, leaving
        # project/domain unset. Every control-plane tool then fails mid-conversation with
        # "project_id.domain: must be at least 1 characters", which reads like a bug in the
        # tool rather than missing setup. Fail here instead, while we can still explain it.
        if (problem := _unconfigured()) is not None:
            print(problem, file=sys.stderr)
            return 1

        env = FlyteMCPAppEnvironment(
            name="flyte-mcp",
            instructions=(
                "Tools for the Flyte control plane you are currently authenticated "
                "against: run and inspect tasks, manage runs, apps, and triggers."
            ),
            tool_groups=tool_groups,
            tools=tools,
            task_allowlist=_csv("FLYTE_MCP_TASK_ALLOWLIST"),
            app_allowlist=_csv("FLYTE_MCP_APP_ALLOWLIST"),
            trigger_allowlist=_csv("FLYTE_MCP_TRIGGER_ALLOWLIST"),
        )

    env.mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
