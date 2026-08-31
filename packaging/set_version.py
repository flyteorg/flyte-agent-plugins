#!/usr/bin/env python3
"""Set the release version across every manifest that carries one.

    python packaging/set_version.py 0.4.0

The plugin manifest at plugins/flyte/.claude-plugin/plugin.json is the source of
truth that packaging/build.py reads; the Codex manifest and the repo-root
package.json must agree with it, so this writes all three at once.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFESTS = [
    REPO / "plugins" / "flyte" / ".claude-plugin" / "plugin.json",
    REPO / "plugins" / "flyte" / ".codex-plugin" / "plugin.json",
    REPO / "package.json",
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not SEMVER.match(argv[1]):
        print("usage: set_version.py <semver>  (e.g. 0.4.0)", file=sys.stderr)
        return 2
    version = argv[1]
    for path in MANIFESTS:
        data = json.loads(path.read_text())
        data["version"] = version
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"{path.relative_to(REPO)} -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
