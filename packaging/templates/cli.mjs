#!/usr/bin/env node
// Install the bundled Flyte agent skills into whichever agent harness you use.
//
// Shared implementation for both npm distributions (`flyte-skills` and
// `flyte-agent-plugins`); packaging/build.py copies it into each generated
// package. The canonical source lives at packaging/templates/cli.mjs in the
// flyteorg/skills repo -- edit it there.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BIN_DIR = path.dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = path.resolve(BIN_DIR, "..");

// Written by packaging/build.py; absent only when running from a checkout.
const HAS_MCP = (() => {
  const f = path.join(BIN_DIR, "features.json");
  return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")).mcp === true : true;
})();
// For the npm distribution the package root IS the plugin root: Claude Code
// requires `.claude-plugin/plugin.json` at the top level of an `npm` source.
const PLUGIN_ROOT = PKG_ROOT;

// Skill discovery locations, as documented by each harness. `agents` is the
// cross-harness `.agents/skills` convention rather than any one harness: Codex
// reads it for user and project skills, and Hermes reads it for project skills
// alongside its own `.hermes/skills`. Anything else honouring the convention
// picks the skills up for free, which makes it the portable target.
const TARGETS = {
  agents: { label: "Agent Skills standard", user: ".agents/skills", project: ".agents/skills", markers: [".agents", ".codex"] },
  claude: { label: "Claude Code", user: ".claude/skills", project: ".claude/skills", markers: [".claude"] },
  hermes: { label: "Hermes", user: ".hermes/skills", project: ".hermes/skills", markers: [".hermes"] },
  opencode: { label: "opencode", user: ".config/opencode/skills", project: ".opencode/skills", markers: [".config/opencode"] },
  pi: { label: "pi", user: ".pi/agent/skills", project: null, markers: [".pi"] },
};

// `codex` predates the `agents` name and stays valid; it is the same location.
const ALIASES = { codex: "agents" };

const targetChoices = () => [...new Set([...Object.keys(TARGETS), ...Object.keys(ALIASES)])].sort();
const resolveTarget = (name) => TARGETS[ALIASES[name] ?? name];

function skillDirs() {
  const root = path.join(PLUGIN_ROOT, "skills");
  if (!fs.existsSync(root)) return [];
  return fs
    .readdirSync(root, { withFileTypes: true })
    .filter((e) => e.isDirectory() && fs.existsSync(path.join(root, e.name, "SKILL.md")))
    .map((e) => path.join(root, e.name))
    .sort();
}

function detect() {
  return Object.entries(TARGETS).filter(([, t]) =>
    t.markers.some((m) => fs.existsSync(path.join(os.homedir(), m))),
  );
}

function parseArgs(argv) {
  const opts = { command: argv[0], targets: [], dir: null, project: false, dryRun: false, force: false };
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target") opts.targets.push(argv[++i]);
    else if (a.startsWith("--target=")) opts.targets.push(a.slice(9));
    else if (a === "--dir") opts.dir = argv[++i];
    else if (a.startsWith("--dir=")) opts.dir = a.slice(6);
    else if (a === "--project") opts.project = true;
    else if (a === "--dry-run") opts.dryRun = true;
    else if (a === "--force") opts.force = true;
    else if (a === "-h" || a === "--help") opts.command = "help";
    else {
      console.error(`Unknown argument: ${a}`);
      process.exit(2);
    }
  }
  for (const t of opts.targets) {
    if (!resolveTarget(t)) {
      console.error(`Unknown target: ${t} (choose from ${targetChoices().join(", ")})`);
      process.exit(2);
    }
  }
  return opts;
}

function resolveDests(opts) {
  if (opts.dir) return [[null, path.resolve(opts.dir)]];

  // `--target codex --target agents` names one location twice; install once.
  let entries = opts.targets.length
    ? [...new Map(opts.targets.map((n) => [ALIASES[n] ?? n, resolveTarget(n)]))]
    : detect();
  if (!entries.length) {
    entries = [["claude", TARGETS.claude]];
    console.error(
      "No harness config directory found; defaulting to Claude Code. " +
        "Use --target or --dir to choose explicitly.",
    );
  }

  const pairs = [];
  for (const [, t] of entries) {
    if (opts.project && !t.project) {
      console.error(`${t.label} has no project-level skills directory; skipping.`);
      continue;
    }
    pairs.push([t, opts.project ? path.resolve(process.cwd(), t.project) : path.join(os.homedir(), t.user)]);
  }
  return pairs;
}

function rmAny(p) {
  fs.rmSync(p, { recursive: true, force: true });
}

function cmdInstall(opts) {
  const skills = skillDirs();
  if (!skills.length) {
    console.error("No skills bundled in this package.");
    return 1;
  }
  const pairs = resolveDests(opts);
  if (!pairs.length) return 1;

  for (const [target, dest] of pairs) {
    console.log(`${target ? target.label : dest}: ${dest}`);
    if (!opts.dryRun) fs.mkdirSync(dest, { recursive: true });
    for (const src of skills) {
      const name = path.basename(src);
      const out = path.join(dest, name);
      if (fs.existsSync(out) && !opts.force) {
        console.log(`  skip ${name} (exists; use --force to overwrite)`);
        continue;
      }
      if (opts.dryRun) {
        console.log(`  install ${name}`);
        continue;
      }
      rmAny(out);
      fs.cpSync(src, out, { recursive: true });
      console.log(`  install ${name}`);
    }
  }
  if (opts.dryRun) console.log("\nDry run: nothing was written.");
  return 0;
}

function cmdUninstall(opts) {
  const names = skillDirs().map((s) => path.basename(s));
  const pairs = resolveDests(opts);
  if (!pairs.length) return 1;
  for (const [target, dest] of pairs) {
    console.log(`${target ? target.label : dest}: ${dest}`);
    for (const name of names) {
      const out = path.join(dest, name);
      if (!fs.existsSync(out)) continue;
      if (opts.dryRun) {
        console.log(`  remove ${name}`);
        continue;
      }
      rmAny(out);
      console.log(`  remove ${name}`);
    }
  }
  if (opts.dryRun) console.log("\nDry run: nothing was removed.");
  return 0;
}

// --- MCP servers ------------------------------------------------------------
//
// Skills are inert markdown; MCP servers are live tools the agent can call, and
// they live in harness config rather than a skills directory. So this is an
// opt-in subcommand, never part of `install`, and it delegates to each harness's
// own CLI instead of editing config files: `~/.claude.json` in particular holds
// unrelated state that a bad merge would clobber.

const MCP_TARGETS = {
  claude: { label: "Claude Code", binary: "claude", scoped: true },
  codex: { label: "Codex CLI", binary: "codex", scoped: false },
};

const mcpServers = () =>
  JSON.parse(fs.readFileSync(path.join(PLUGIN_ROOT, ".mcp.json"), "utf8")).mcpServers;

// Quote only for display; commands are spawned as argv, never through a shell.
const quote = (a) => (/^[\w@%+=:,./-]+$/.test(a) ? a : `'${a.replace(/'/g, "'\\''")}'`);
const joinCmd = (argv) => argv.map(quote).join(" ");

function describeServer(cfg) {
  if (cfg.url) return `hosted HTTP endpoint, ${cfg.url}`;
  return `local process, ${joinCmd([cfg.command, ...(cfg.args ?? [])])}`;
}

function onPath(binary) {
  const probe = process.platform === "win32" ? "where" : "command";
  const args = process.platform === "win32" ? [binary] : ["-v", binary];
  return spawnSync(probe, args, { shell: process.platform !== "win32" }).status === 0;
}

function mcpAddCommand(target, name, cfg, scope) {
  if (target.binary === "claude") {
    return [target.binary, "mcp", "add-json", name, JSON.stringify(cfg), "--scope", scope];
  }
  if (cfg.url) return [target.binary, "mcp", "add", name, "--url", cfg.url];
  return [target.binary, "mcp", "add", name, "--", cfg.command, ...(cfg.args ?? [])];
}

const mcpRemoveCommand = (target, name, scope) =>
  target.binary === "claude"
    ? [target.binary, "mcp", "remove", name, "--scope", scope]
    : [target.binary, "mcp", "remove", name];

function resolveMcpTargets(opts) {
  let wanted = opts.targets.length
    ? [...new Set(opts.targets)].map((n) => MCP_TARGETS[n])
    : Object.values(MCP_TARGETS).filter((t) => onPath(t.binary));
  if (!opts.targets.length && !wanted.length) {
    console.error(
      "No harness CLI found on PATH. `mcp install` drives `claude` or `codex` " +
        `directly; install one, or add the servers by hand from ${path.join(PLUGIN_ROOT, ".mcp.json")}.`,
    );
  }
  return wanted.filter((t) => {
    if (onPath(t.binary)) return true;
    console.error(`${t.label}: \`${t.binary}\` is not on PATH; skipping.`);
    return false;
  });
}

function selectedServers(opts) {
  const servers = mcpServers();
  if (!opts.servers.length) return servers;
  const unknown = opts.servers.filter((n) => !(n in servers));
  if (unknown.length) {
    console.error(
      `Unknown server(s): ${unknown.join(", ")}. Available: ${Object.keys(servers).sort().join(", ")}`,
    );
    process.exit(1);
  }
  return Object.fromEntries(opts.servers.map((n) => [n, servers[n]]));
}

function runMcp(commands, dryRun) {
  let failures = 0;
  for (const cmd of commands) {
    if (dryRun) {
      console.log(`  ${joinCmd(cmd)}`);
      continue;
    }
    const r = spawnSync(cmd[0], cmd.slice(1), { encoding: "utf8" });
    if (r.status === 0) {
      console.log(`  ok   ${cmd[3] ?? ""}`);
    } else {
      failures++;
      console.log(`  FAIL ${joinCmd(cmd)}`);
      const detail = (r.stderr || r.stdout || "").trim().split("\n").pop();
      if (detail) console.log(`       ${detail}`);
    }
  }
  return failures;
}

function cmdMcpInstall(opts) {
  const servers = selectedServers(opts);
  const targets = resolveMcpTargets(opts);
  if (!targets.length) return 1;

  console.log("Adding these MCP servers — they are tools the agent can call:");
  for (const [name, cfg] of Object.entries(servers)) console.log(`  ${name}: ${describeServer(cfg)}`);
  console.log();

  let failures = 0;
  for (const target of targets) {
    console.log(`${target.label} [${target.scoped ? opts.scope : "(single config)"}]`);
    if (!target.scoped && opts.scope !== "user") {
      console.error(`  note: ${target.label} has one config file; --scope is ignored.`);
    }
    const commands = [];
    for (const [name, cfg] of Object.entries(servers)) {
      if (opts.force) commands.push(mcpRemoveCommand(target, name, opts.scope));
      commands.push(mcpAddCommand(target, name, cfg, opts.scope));
    }
    failures += runMcp(commands, opts.dryRun);
  }

  if (opts.dryRun) console.log("\nDry run: nothing was changed.");
  else if (failures) {
    console.error(
      "\nSome servers were not added. A server of the same name already " +
        "configured is the usual cause — re-run with --force to replace it.",
    );
    return 1;
  } else console.log("\nNote: flyte-cluster needs `uv` and a Flyte login before it will connect.");
  return 0;
}

function cmdMcpUninstall(opts) {
  const servers = selectedServers(opts);
  const targets = resolveMcpTargets(opts);
  if (!targets.length) return 1;
  for (const target of targets) {
    console.log(target.label);
    runMcp(
      Object.keys(servers).map((n) => mcpRemoveCommand(target, n, opts.scope)),
      opts.dryRun,
    );
  }
  if (opts.dryRun) console.log("\nDry run: nothing was changed.");
  return 0;
}

const MCP_USAGE = `Manage the MCP servers bundled with the Flyte skills.

Usage: flyte-skills mcp <list|install|uninstall> [options]

Options:
  --target <claude|codex>   Harness to configure (repeatable; default: whichever CLI is on PATH)
  --server <name>           Only this server (repeatable; default: all)
  --scope <local|project|user>
                            Claude Code config scope (default: user). Ignored by Codex.
  --force                   Remove an existing server of the same name first (install only)
  --dry-run                 Print the commands only
`;

function mcpMain(argv) {
  const sub = argv[0];
  const opts = { targets: [], servers: [], scope: "user", dryRun: false, force: false };
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target") opts.targets.push(argv[++i]);
    else if (a.startsWith("--target=")) opts.targets.push(a.slice(9));
    else if (a === "--server") opts.servers.push(argv[++i]);
    else if (a.startsWith("--server=")) opts.servers.push(a.slice(9));
    else if (a === "--scope") opts.scope = argv[++i];
    else if (a.startsWith("--scope=")) opts.scope = a.slice(8);
    else if (a === "--dry-run") opts.dryRun = true;
    else if (a === "--force") opts.force = true;
    else if (a === "-h" || a === "--help") {
      process.stdout.write(MCP_USAGE);
      return 0;
    } else {
      console.error(`Unknown argument: ${a}`);
      return 2;
    }
  }
  for (const t of opts.targets) {
    if (!(t in MCP_TARGETS)) {
      console.error(`Unknown target: ${t} (choose from ${Object.keys(MCP_TARGETS).sort().join(", ")})`);
      return 2;
    }
  }
  if (!["local", "project", "user"].includes(opts.scope)) {
    console.error(`Unknown scope: ${opts.scope} (choose from local, project, user)`);
    return 2;
  }
  switch (sub) {
    case "list":
      for (const [name, cfg] of Object.entries(mcpServers())) console.log(`${name}\t${describeServer(cfg)}`);
      return 0;
    case "install":
      return cmdMcpInstall(opts);
    case "uninstall":
      return cmdMcpUninstall(opts);
    default:
      if (sub) console.error(`Unknown mcp command: ${sub}\n`);
      process.stdout.write(MCP_USAGE);
      return sub ? 2 : 0;
  }
}

const USAGE = `Install the Flyte agent skills into your agent harness.

Usage: flyte-skills <command> [options]

Commands:
  install       Copy the skills into a harness skills directory
  uninstall     Remove previously installed skills
  list          List the bundled skills
  path          Print the bundled plugin directory
  emit-plugin   Print the plugin directory path (for a marketplace \`command\` source)
  version       Print the plugin version${
  HAS_MCP ? "\n  mcp           Manage the bundled MCP servers (`mcp --help`)" : ""
}

Options:
  --target <${targetChoices().join("|")}>
                   Harness to target (repeatable; default: auto-detect).
                   \`agents\` is the harness-agnostic .agents/skills convention.
  --dir <path>     Install into this directory instead of a harness default
  --project        Use the project-level skills directory under the current directory
  --force          Overwrite existing skills
  --dry-run        Show what would change
`;

function main(argv) {
  if (!argv.length) {
    process.stdout.write(USAGE);
    return 2;
  }
  if (argv[0] === "mcp") {
    if (!HAS_MCP) {
      // A bare "unknown command" would not tell you the subcommand exists under
      // the other distribution, which is the only thing worth knowing here.
      console.error(
        "This package installs skills only; the `mcp` subcommand ships with the " +
          "flyte-agent-plugins distribution.\n\n" +
          "    npx flyte-agent-plugins mcp install\n",
      );
      return 2;
    }
    return mcpMain(argv.slice(1));
  }
  const opts = parseArgs(argv);
  switch (opts.command) {
    case "install":
      return cmdInstall(opts);
    case "uninstall":
      return cmdUninstall(opts);
    case "list":
      skillDirs().forEach((s) => console.log(path.basename(s)));
      return 0;
    case "path":
      console.log(PLUGIN_ROOT);
      return 0;
    case "emit-plugin":
      // Contract for a Claude Code marketplace `command` source: print exactly
      // one line -- the absolute plugin directory path -- and exit 0.
      process.stdout.write(`${PLUGIN_ROOT}\n`);
      return 0;
    case "version": {
      const manifest = path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json");
      console.log(JSON.parse(fs.readFileSync(manifest, "utf8")).version);
      return 0;
    }
    case "help":
      process.stdout.write(USAGE);
      return 0;
    default:
      console.error(`Unknown command: ${opts.command}\n`);
      process.stdout.write(USAGE);
      return 2;
  }
}

process.exit(main(process.argv.slice(2)));
