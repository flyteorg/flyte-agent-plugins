"""Install the bundled Flyte agent skills into whichever agent harness you use.

This module is the shared implementation for both PyPI distributions
(``flyte-skills`` and ``flyte-agent-plugins``); ``packaging/build.py`` copies it
into each generated source tree. The canonical source lives at
``packaging/templates/cli.py`` in the flyteorg/skills repo -- edit it there.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

__all__ = ["main", "mcp_servers", "plugin_root", "resolve_target", "TARGETS"]


def plugin_root() -> Path:
    """Absolute path to the plugin directory bundled inside this package."""
    return Path(str(files(__package__).joinpath("plugin"))).resolve()


@dataclass(frozen=True)
class Target:
    name: str
    label: str
    user: str
    project: str | None
    # Directories whose existence means "this harness is set up on this machine".
    # More than one when several harnesses share a skills location.
    markers: tuple[str, ...]

    def dir_for(self, project: bool, root: Path) -> Path | None:
        if project:
            return (root / self.project).resolve() if self.project else None
        return (Path.home() / self.user).resolve()


# Skill discovery locations, as documented by each harness. `agents` is the
# cross-harness `.agents/skills` convention rather than any one harness: Codex
# reads it for user and project skills, and Hermes reads it for project skills
# alongside its own `.hermes/skills`. Anything else honouring the convention
# picks the skills up for free, which makes it the portable target.
TARGETS: dict[str, Target] = {
    t.name: t
    for t in (
        Target("agents", "Agent Skills standard", ".agents/skills", ".agents/skills", (".agents", ".codex")),
        Target("claude", "Claude Code", ".claude/skills", ".claude/skills", (".claude",)),
        Target("hermes", "Hermes", ".hermes/skills", ".hermes/skills", (".hermes",)),
        Target(
            "opencode",
            "opencode",
            ".config/opencode/skills",
            ".opencode/skills",
            (".config/opencode",),
        ),
        Target("pi", "pi", ".pi/agent/skills", None, (".pi",)),
    )
}

# `codex` predates the `agents` name and stays valid; it is the same location.
ALIASES = {"codex": "agents"}


def resolve_target(name: str) -> Target:
    return TARGETS[ALIASES.get(name, name)]


def target_choices() -> list[str]:
    return sorted(set(TARGETS) | set(ALIASES))


def skill_dirs() -> list[Path]:
    return sorted(
        p for p in (plugin_root() / "skills").iterdir() if (p / "SKILL.md").is_file()
    )


def detect() -> list[Target]:
    """Targets whose harness looks installed (a config dir for it exists)."""
    home = Path.home()
    return [
        t for t in TARGETS.values() if any((home / m).is_dir() for m in t.markers)
    ]


def _resolve(args) -> list[tuple[Target | None, Path]]:
    """Resolve CLI args into (target, destination directory) pairs."""
    root = Path.cwd()
    if args.dir:
        return [(None, Path(args.dir).expanduser().resolve())]

    if args.target:
        # `--target codex --target agents` names one location twice; install once.
        targets = list(dict.fromkeys(resolve_target(name) for name in args.target))
    else:
        targets = detect()
        if not targets:
            targets = [TARGETS["claude"]]
            print(
                "No harness config directory found; defaulting to Claude Code. "
                "Use --target or --dir to choose explicitly.",
                file=sys.stderr,
            )

    pairs: list[tuple[Target | None, Path]] = []
    for t in targets:
        dest = t.dir_for(args.project, root)
        if dest is None:
            print(
                f"{t.label} has no project-level skills directory; skipping.",
                file=sys.stderr,
            )
            continue
        pairs.append((t, dest))
    return pairs


def cmd_install(args) -> int:
    skills = skill_dirs()
    if not skills:
        print("No skills bundled in this package.", file=sys.stderr)
        return 1

    pairs = _resolve(args)
    if not pairs:
        return 1

    for target, dest in pairs:
        label = target.label if target else str(dest)
        print(f"{label}: {dest}")
        if not args.dry_run:
            dest.mkdir(parents=True, exist_ok=True)
        for src in skills:
            out = dest / src.name
            if out.exists() and not args.force:
                print(f"  skip {src.name} (exists; use --force to overwrite)")
                continue
            if args.dry_run:
                print(f"  install {src.name}")
                continue
            if out.exists() or out.is_symlink():
                if out.is_dir() and not out.is_symlink():
                    shutil.rmtree(out)
                else:
                    out.unlink()
            shutil.copytree(src, out)
            print(f"  install {src.name}")
    if args.dry_run:
        print("\nDry run: nothing was written.")
    return 0


def cmd_uninstall(args) -> int:
    names = {p.name for p in skill_dirs()}
    pairs = _resolve(args)
    if not pairs:
        return 1
    for target, dest in pairs:
        label = target.label if target else str(dest)
        print(f"{label}: {dest}")
        for name in sorted(names):
            out = dest / name
            if not (out.exists() or out.is_symlink()):
                continue
            if args.dry_run:
                print(f"  remove {name}")
                continue
            if out.is_dir() and not out.is_symlink():
                shutil.rmtree(out)
            else:
                out.unlink()
            print(f"  remove {name}")
    if args.dry_run:
        print("\nDry run: nothing was removed.")
    return 0


# --- MCP servers ------------------------------------------------------------
#
# Skills are inert markdown; MCP servers are live tools the agent can call, and
# they live in harness config rather than a skills directory. So this is an
# opt-in subcommand, never part of `install`, and it delegates to each harness's
# own CLI instead of editing config files: `~/.claude.json` in particular holds
# unrelated state that a bad merge would clobber.


@dataclass(frozen=True)
class McpTarget:
    name: str
    label: str
    binary: str
    # Claude Code stores servers per scope; Codex has a single config file.
    scoped: bool


MCP_TARGETS: dict[str, McpTarget] = {
    "claude": McpTarget("claude", "Claude Code", "claude", True),
    "codex": McpTarget("codex", "Codex CLI", "codex", False),
}


def mcp_servers() -> dict[str, dict]:
    """The servers bundled in the plugin's .mcp.json."""
    return json.loads((plugin_root() / ".mcp.json").read_text())["mcpServers"]


def describe_server(cfg: dict) -> str:
    if "url" in cfg:
        return f"hosted HTTP endpoint, {cfg['url']}"
    argv = [cfg.get("command", "")] + list(cfg.get("args", []))
    return f"local process, {shlex.join(a for a in argv if a)}"


def mcp_add_command(target: McpTarget, name: str, cfg: dict, scope: str) -> list[str]:
    if target.name == "claude":
        return [
            target.binary, "mcp", "add-json", name,
            json.dumps(cfg, separators=(",", ":")), "--scope", scope,
        ]
    if "url" in cfg:
        return [target.binary, "mcp", "add", name, "--url", cfg["url"]]
    return [target.binary, "mcp", "add", name, "--", cfg["command"], *cfg.get("args", [])]


def mcp_remove_command(target: McpTarget, name: str, scope: str) -> list[str]:
    if target.name == "claude":
        return [target.binary, "mcp", "remove", name, "--scope", scope]
    return [target.binary, "mcp", "remove", name]


def resolve_mcp_targets(args) -> list[McpTarget]:
    if args.target:
        wanted = [MCP_TARGETS[n] for n in dict.fromkeys(args.target)]
    else:
        wanted = [t for t in MCP_TARGETS.values() if shutil.which(t.binary)]
        if not wanted:
            print(
                "No harness CLI found on PATH. `mcp install` drives `claude` or "
                "`codex` directly; install one, or add the servers by hand from "
                f"{plugin_root() / '.mcp.json'}.",
                file=sys.stderr,
            )
    missing = [t for t in wanted if not shutil.which(t.binary)]
    for t in missing:
        print(f"{t.label}: `{t.binary}` is not on PATH; skipping.", file=sys.stderr)
    return [t for t in wanted if t not in missing]


def selected_servers(args) -> dict[str, dict]:
    servers = mcp_servers()
    if not args.server:
        return servers
    unknown = [n for n in args.server if n not in servers]
    if unknown:
        raise SystemExit(
            f"Unknown server(s): {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(servers))}"
        )
    return {n: servers[n] for n in args.server}


def run_mcp(commands: list[list[str]], dry_run: bool) -> int:
    failures = 0
    for cmd in commands:
        if dry_run:
            print(f"  {shlex.join(cmd)}")
            continue
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode == 0:
            print(f"  ok   {cmd[3] if len(cmd) > 3 else ''}")
        else:
            failures += 1
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            print(f"  FAIL {shlex.join(cmd)}")
            if detail:
                print(f"       {detail[-1]}")
    return failures


def cmd_mcp_list(args) -> int:
    for name, cfg in mcp_servers().items():
        print(f"{name}\t{describe_server(cfg)}")
    return 0


def cmd_mcp_install(args) -> int:
    servers = selected_servers(args)
    targets = resolve_mcp_targets(args)
    if not targets:
        return 1

    print("Adding these MCP servers — they are tools the agent can call:")
    for name, cfg in servers.items():
        print(f"  {name}: {describe_server(cfg)}")
    print()

    failures = 0
    for target in targets:
        scope = args.scope if target.scoped else "(single config)"
        print(f"{target.label} [{scope}]")
        if not target.scoped and args.scope != "user":
            print(
                f"  note: {target.label} has one config file; --scope is ignored.",
                file=sys.stderr,
            )
        commands = []
        for name, cfg in servers.items():
            if args.force:
                commands.append(mcp_remove_command(target, name, args.scope))
            commands.append(mcp_add_command(target, name, cfg, args.scope))
        failures += run_mcp(commands, args.dry_run)

    if args.dry_run:
        print("\nDry run: nothing was changed.")
    elif failures:
        print(
            "\nSome servers were not added. A server of the same name already "
            "configured is the usual cause — re-run with --force to replace it.",
            file=sys.stderr,
        )
        return 1
    else:
        print(
            "\nNote: flyte-cluster needs `uv` and a Flyte login before it will "
            "connect."
        )
    return 0


def cmd_mcp_uninstall(args) -> int:
    servers = selected_servers(args)
    targets = resolve_mcp_targets(args)
    if not targets:
        return 1
    for target in targets:
        print(target.label)
        run_mcp(
            [mcp_remove_command(target, name, args.scope) for name in servers],
            args.dry_run,
        )
    if args.dry_run:
        print("\nDry run: nothing was changed.")
    return 0


def cmd_list(args) -> int:
    for src in skill_dirs():
        print(src.name)
    return 0


def cmd_path(args) -> int:
    print(plugin_root())
    return 0


def cmd_emit_plugin(args) -> int:
    # Contract for a Claude Code marketplace `command` source: print exactly one
    # line -- the absolute path of the plugin directory -- and exit 0.
    sys.stdout.write(f"{plugin_root()}\n")
    return 0


def cmd_version(args) -> int:
    manifest = plugin_root() / ".claude-plugin" / "plugin.json"
    print(json.loads(manifest.read_text())["version"])
    return 0


def _add_target_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--target",
        action="append",
        choices=target_choices(),
        help=(
            "Harness to target (repeatable). `agents` is the harness-agnostic "
            "`.agents/skills` convention. Default: auto-detect installed harnesses."
        ),
    )
    p.add_argument(
        "--dir",
        help="Install into this directory instead of a harness default.",
    )
    p.add_argument(
        "--project",
        action="store_true",
        help="Use the project-level skills directory under the current directory.",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would change.")


def build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Install the Flyte agent skills into your agent harness.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("install", help="Copy the skills into a harness skills directory.")
    _add_target_flags(p)
    p.add_argument("--force", action="store_true", help="Overwrite existing skills.")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="Remove previously installed skills.")
    _add_target_flags(p)
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("list", help="List the bundled skills.")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("path", help="Print the bundled plugin directory.")
    p.set_defaults(func=cmd_path)

    p = sub.add_parser(
        "emit-plugin",
        help="Print the plugin directory path (for a marketplace `command` source).",
    )
    p.set_defaults(func=cmd_emit_plugin)

    p = sub.add_parser("version", help="Print the plugin version.")
    p.set_defaults(func=cmd_version)

    mcp = sub.add_parser("mcp", help="Manage the bundled MCP servers.")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)

    p = mcp_sub.add_parser("list", help="List the bundled MCP servers.")
    p.set_defaults(func=cmd_mcp_list)

    for action, handler, blurb in (
        ("install", cmd_mcp_install, "Add the bundled MCP servers to a harness."),
        ("uninstall", cmd_mcp_uninstall, "Remove them again."),
    ):
        p = mcp_sub.add_parser(action, help=blurb)
        p.add_argument(
            "--target",
            action="append",
            choices=sorted(MCP_TARGETS),
            help=(
                "Harness to configure (repeatable). Default: whichever of these "
                "CLIs is on PATH."
            ),
        )
        p.add_argument(
            "--server",
            action="append",
            help="Only this server (repeatable). Default: all of them.",
        )
        p.add_argument(
            "--scope",
            default="user",
            choices=["local", "project", "user"],
            help="Claude Code config scope (default: user). Ignored by Codex.",
        )
        p.add_argument("--dry-run", action="store_true", help="Print the commands only.")
        if action == "install":
            p.add_argument(
                "--force",
                action="store_true",
                help="Remove an existing server of the same name first.",
            )
        p.set_defaults(func=handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser(Path(sys.argv[0]).name or "flyte-skills").parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
