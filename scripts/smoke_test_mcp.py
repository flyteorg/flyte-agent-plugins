"""Smoke-test the bundled Flyte MCP server the way Claude Code launches it.

Reads ``plugins/flyte/.mcp.json``, spawns the exact command the local ``flyte-cluster``
server declares, completes the MCP handshake, lists the tools, and makes one real
read-only call against whatever tenant you are logged into.

The sibling ``flyte-docs`` server is hosted HTTP, not spawned, so it is not covered here --
curl its ``/health`` endpoint instead.

    python3 scripts/smoke_test_mcp.py [plugin_dir]

Works with or without a cluster. ``flyte-mcp`` registers its control-plane tools
unconditionally, so the tool list is the same either way; without a usable Flyte config
the read-only call fails at call time, which this script reports as "not connected"
rather than as a broken server.

The ``.mcp.json`` command deliberately leaves the three ``search`` tools out -- the hosted
``flyte-docs`` server already provides them, and enabling them here would shallow-clone a
~120 MB corpus into ``~/.flyte/mcp`` on first launch.
"""

import json
import os
import subprocess
import sys

_DEFAULT_PLUGIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", "flyte"
)
PLUGIN = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PLUGIN
MCP_JSON = os.path.join(PLUGIN, ".mcp.json")

spec = json.load(open(MCP_JSON))["mcpServers"]["flyte-cluster"]
argv = [spec["command"]] + list(spec["args"])
env = {**os.environ, **spec.get("env", {})}

print(f"$ {' '.join(argv)}\n")
proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, bufsize=1, env=env)

_id = 0


def rpc(method, params=None, notify=False):
    global _id
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if not notify:
        _id += 1
        msg["id"] = _id
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    line = proc.stdout.readline()
    if not line:
        raise SystemExit("server closed the stream; see stderr below")
    return json.loads(line)


try:
    r = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "smoke-test", "version": "0"}})
    info = r["result"]["serverInfo"]
    print(f"handshake  OK  -> {info['name']} (MCP SDK {info['version']})")

    rpc("notifications/initialized", notify=True)

    tools = rpc("tools/list")["result"]["tools"]
    print(f"tools/list OK  -> {len(tools)} tools: {', '.join(sorted(t['name'] for t in tools))}\n")

    names = {t["name"] for t in tools}

    def call(tool, args, describe):
        """Run one tool call. Returns True if it succeeded."""
        print(f"tools/call {tool}({args}) ...")
        resp = rpc("tools/call", {"name": tool, "arguments": args})
        if "error" in resp:
            print("  RPC ERROR:", resp["error"].get("message", resp["error"]))
            return False
        res = resp.get("result", {})
        if res.get("isError"):
            print("  ERROR from tool:", res["content"][0]["text"][:400])
            return False
        payload = res.get("structuredContent", {}).get("result")
        if payload is None:
            payload = res.get("content", [{}])[0].get("text", "")
        describe(payload)
        return True

    if "list_runs" not in names:
        raise SystemExit("list_runs is missing -- the declared --tool-groups did not take effect")

    ok = call("list_runs", {"limit": 3},
              lambda p: print(f"  OK -> {len(p if isinstance(p, list) else json.loads(p or '[]'))} run(s)"))
    if not ok:
        print("\nnot connected to a cluster -- the tools are registered but fail when called.")
        print("Log in with the `flyte` CLI (project + domain) and rerun to exercise list_runs.")
finally:
    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    err = proc.stderr.read().strip()
    if err:
        print("\n--- server stderr ---")
        print("\n".join(err.splitlines()[-12:]))
