"""Install the bundled Flyte agent skills into whichever agent harness you use.

This module is the shared implementation for both PyPI distributions
(``flyte-skills`` and ``flyte-agent-plugins``); ``packaging/build.py`` copies it
into each generated source tree. The canonical source lives at
``packaging/templates/cli.py`` in the flyteorg/skills repo -- edit it there.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

__all__ = ["main", "plugin_root", "TARGETS"]


def plugin_root() -> Path:
    """Absolute path to the plugin directory bundled inside this package."""
    return Path(str(files(__package__).joinpath("plugin"))).resolve()


@dataclass(frozen=True)
class Target:
    name: str
    label: str
    user: str
    project: str | None
    # A directory whose existence means "this harness is set up on this machine".
    marker: str

    def dir_for(self, project: bool, root: Path) -> Path | None:
        if project:
            return (root / self.project).resolve() if self.project else None
        return (Path.home() / self.user).resolve()


# Skill discovery locations, as documented by each harness. `codex` uses the
# cross-harness `.agents/skills` convention, so anything else reading that
# standard location picks the skills up too.
TARGETS: dict[str, Target] = {
    t.name: t
    for t in (
        Target("claude", "Claude Code", ".claude/skills", ".claude/skills", ".claude"),
        Target("codex", "Codex CLI", ".agents/skills", ".agents/skills", ".codex"),
        Target(
            "opencode",
            "opencode",
            ".config/opencode/skills",
            ".opencode/skills",
            ".config/opencode",
        ),
        Target("pi", "pi", ".pi/agent/skills", None, ".pi"),
    )
}


def skill_dirs() -> list[Path]:
    return sorted(
        p for p in (plugin_root() / "skills").iterdir() if (p / "SKILL.md").is_file()
    )


def detect() -> list[Target]:
    """Targets whose harness looks installed (its config dir exists)."""
    return [t for t in TARGETS.values() if (Path.home() / t.marker).is_dir()]


def _resolve(args) -> list[tuple[Target | None, Path]]:
    """Resolve CLI args into (target, destination directory) pairs."""
    root = Path.cwd()
    if args.dir:
        return [(None, Path(args.dir).expanduser().resolve())]

    if args.target:
        targets = [TARGETS[name] for name in args.target]
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
        choices=sorted(TARGETS),
        help="Harness to target (repeatable). Default: auto-detect installed harnesses.",
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser(Path(sys.argv[0]).name or "flyte-skills").parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
