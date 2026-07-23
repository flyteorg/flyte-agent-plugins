"""Smoke-test the bundled Flyte MCP server the way Claude Code launches it.

Reads ``plugins/flyte/.mcp.json``, spawns the exact command the local ``flyte-cluster``
server declares (expanding ``${CLAUDE_PLUGIN_ROOT}``), completes the MCP handshake, lists
the tools, and makes one real read-only call against whatever tenant you are logged into.

The sibling ``flyte-docs`` server is hosted HTTP, not spawned, so it is not covered here --
curl its ``/health`` endpoint instead.

    python3 scripts/smoke_test_mcp.py [plugin_dir]

Works with or without a cluster: given a Flyte config with ``project`` and ``domain`` it
exercises a real read-only control-plane call (``list_runs``); without one it reports that
the control-plane tools are simply not offered. The local server serves the search tools
only when ``FLYTE_MCP_LOCAL_SEARCH`` is set -- otherwise search comes from the hosted
``flyte-docs`` server, which this test does not spawn.
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
argv = [spec["command"]] + [a.replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN) for a in spec["args"]]
env = {**os.environ, **{k: v.replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN) for k, v in spec.get("env", {}).items()}}

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
    connected = "list_runs" in names

    def call(tool, args, describe):
        print(f"tools/call {tool}({args}) ...")
        resp = rpc("tools/call", {"name": tool, "arguments": args})
        if "error" in resp:
            print("  RPC ERROR:", resp["error"].get("message", resp["error"]))
            return
        res = resp.get("result", {})
        if res.get("isError"):
            print("  ERROR from tool:", res["content"][0]["text"][:400])
            return
        payload = res.get("structuredContent", {}).get("result")
        if payload is None:
            payload = res.get("content", [{}])[0].get("text", "")
        describe(payload)

    # The local server serves search only under FLYTE_MCP_LOCAL_SEARCH; by default search
    # comes from the hosted flyte-docs server, which this test does not spawn.
    if "search_flyte_sdk_examples" in names:
        call("search_flyte_sdk_examples", {"pattern": "TaskEnvironment"},
             lambda p: print(f"  OK -> {len(str(p))} chars, "
                             f"{'found matches' if 'TaskEnvironment' in str(p) else 'NO MATCHES'}"))
    else:
        print("search not served locally (set FLYTE_MCP_LOCAL_SEARCH=1 to exercise it here).")

    if connected:
        call("list_runs", {"limit": 3},
             lambda p: print(f"  OK -> {len(p if isinstance(p, list) else json.loads(p or '[]'))} run(s)"))
    else:
        print("\nnot connected to a cluster -- control-plane tools are not offered.")
        print("Set a Flyte config (project + domain) and rerun to exercise list_runs.")
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
