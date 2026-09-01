#!/usr/bin/env node
// Install the bundled Flyte agent skills into whichever agent harness you use.
//
// Shared implementation for both npm distributions (`flyte-skills` and
// `flyte-agent-plugins`); packaging/build.py copies it into each generated
// package. The canonical source lives at packaging/templates/cli.mjs in the
// flyteorg/skills repo -- edit it there.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// For the npm distribution the package root IS the plugin root: Claude Code
// requires `.claude-plugin/plugin.json` at the top level of an `npm` source.
const PLUGIN_ROOT = PKG_ROOT;

// Skill discovery locations, as documented by each harness. `codex` uses the
// cross-harness `.agents/skills` convention, which Hermes also reads for
// project skills alongside its own `.hermes/skills`.
const TARGETS = {
  claude: { label: "Claude Code", user: ".claude/skills", project: ".claude/skills", marker: ".claude" },
  codex: { label: "Codex CLI", user: ".agents/skills", project: ".agents/skills", marker: ".codex" },
  hermes: { label: "Hermes", user: ".hermes/skills", project: ".hermes/skills", marker: ".hermes" },
  opencode: { label: "opencode", user: ".config/opencode/skills", project: ".opencode/skills", marker: ".config/opencode" },
  pi: { label: "pi", user: ".pi/agent/skills", project: null, marker: ".pi" },
};

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
    fs.existsSync(path.join(os.homedir(), t.marker)),
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
    if (!(t in TARGETS)) {
      console.error(`Unknown target: ${t} (choose from ${Object.keys(TARGETS).sort().join(", ")})`);
      process.exit(2);
    }
  }
  return opts;
}

function resolveDests(opts) {
  if (opts.dir) return [[null, path.resolve(opts.dir)]];

  let entries = opts.targets.length
    ? opts.targets.map((n) => [n, TARGETS[n]])
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

const USAGE = `Install the Flyte agent skills into your agent harness.

Usage: flyte-skills <command> [options]

Commands:
  install       Copy the skills into a harness skills directory
  uninstall     Remove previously installed skills
  list          List the bundled skills
  path          Print the bundled plugin directory
  emit-plugin   Print the plugin directory path (for a marketplace \`command\` source)
  version       Print the plugin version

Options:
  --target <${Object.keys(TARGETS).sort().join("|")}>   Harness to target (repeatable; default: auto-detect)
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
