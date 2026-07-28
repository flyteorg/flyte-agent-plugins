"""Deterministic, LLM-free checks referenced by scenario specs.

Each check kind is a function `(workspace: Path, params: dict) -> CheckResult`.
Checks run against the workspace an agent produced (trajectory tier) or against a
skill directory (static tier). They are pure w.r.t. the filesystem + subprocess
only — no network, no LLM — so they are deterministic and unit-testable.

Add a new kind by decorating a function with @check("my_kind").
"""

from __future__ import annotations

import ast
import glob as _glob
import pathlib
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

import yaml


@dataclass(frozen=True)
class CheckResult:
    kind: str
    passed: bool
    detail: str

    def __bool__(self) -> bool:  # allow `all(results)`
        return self.passed


CheckFn = Callable[[pathlib.Path, dict], CheckResult]
_REGISTRY: dict[str, CheckFn] = {}


def check(kind: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        _REGISTRY[kind] = fn
        return fn
    return deco


def run_checks(workspace: pathlib.Path, specs: list[dict[str, Any]]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for spec in specs:
        kind = spec.get("kind")
        fn = _REGISTRY.get(kind)
        if fn is None:
            results.append(CheckResult(str(kind), False, f"unknown check kind {kind!r}"))
            continue
        try:
            results.append(fn(workspace, spec))
        except Exception as exc:  # a check crash is a failure, never a harness crash
            results.append(CheckResult(str(kind), False, f"check raised: {exc!r}"))
    return results


def _files(workspace: pathlib.Path, pattern: str) -> list[pathlib.Path]:
    return [pathlib.Path(p) for p in _glob.glob(str(workspace / pattern), recursive=True)]


# ---------------------------------------------------------------------------- #
# Check kinds
# ---------------------------------------------------------------------------- #

@check("file_glob")
def _file_glob(ws: pathlib.Path, p: dict) -> CheckResult:
    """At least `min_count` (default 1) files match `glob`."""
    pattern = p["glob"]
    minc = int(p.get("min_count", 1))
    matches = [f for f in _files(ws, pattern) if f.is_file()]
    ok = len(matches) >= minc
    return CheckResult("file_glob", ok, f"{len(matches)} match(es) for {pattern!r} (need >= {minc})")


@check("contains_regex")
def _contains_regex(ws: pathlib.Path, p: dict) -> CheckResult:
    """Some file matching `file_glob` contains `pattern`."""
    pattern = re.compile(p["pattern"], re.MULTILINE)
    files = [f for f in _files(ws, p.get("file_glob", "**/*")) if f.is_file()]
    for f in files:
        try:
            if pattern.search(f.read_text(errors="ignore")):
                return CheckResult("contains_regex", True, f"{p['pattern']!r} found in {f.name}")
        except OSError:
            continue
    return CheckResult("contains_regex", False, f"{p['pattern']!r} not found in {len(files)} file(s)")


@check("not_contains_regex")
def _not_contains_regex(ws: pathlib.Path, p: dict) -> CheckResult:
    """No file matching `file_glob` contains `pattern` (anti-pattern guard)."""
    pattern = re.compile(p["pattern"], re.MULTILINE)
    for f in _files(ws, p.get("file_glob", "**/*")):
        if not f.is_file():
            continue
        try:
            m = pattern.search(f.read_text(errors="ignore"))
        except OSError:
            continue
        if m:
            return CheckResult("not_contains_regex", False, f"forbidden {p['pattern']!r} in {f.name}")
    return CheckResult("not_contains_regex", True, f"{p['pattern']!r} absent (good)")


@check("python_imports")
def _python_imports(ws: pathlib.Path, p: dict) -> CheckResult:
    """Some produced .py file imports `module` (top-level name)."""
    module = p["module"]
    want = module.split(".")[0]
    for f in _files(ws, p.get("file_glob", "**/*.py")):
        if not f.is_file():
            continue
        try:
            tree = ast.parse(f.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == want for a in node.names):
                return CheckResult("python_imports", True, f"import {module} in {f.name}")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == want:
                return CheckResult("python_imports", True, f"from {module} in {f.name}")
    return CheckResult("python_imports", False, f"no import of {module!r} found")


@check("python_parses")
def _python_parses(ws: pathlib.Path, p: dict) -> CheckResult:
    """Every .py file matching `file_glob` parses (valid syntax)."""
    files = [f for f in _files(ws, p.get("file_glob", "**/*.py")) if f.is_file()]
    if not files:
        return CheckResult("python_parses", False, "no python files produced")
    for f in files:
        try:
            ast.parse(f.read_text(errors="ignore"))
        except SyntaxError as e:
            return CheckResult("python_parses", False, f"syntax error in {f.name}: {e}")
    return CheckResult("python_parses", True, f"{len(files)} python file(s) parse")


@check("yaml_valid")
def _yaml_valid(ws: pathlib.Path, p: dict) -> CheckResult:
    """Every file matching `file_glob` is valid YAML."""
    files = [f for f in _files(ws, p.get("file_glob", "**/*.y*ml")) if f.is_file()]
    if not files and p.get("required", True):
        return CheckResult("yaml_valid", False, "no yaml files produced")
    for f in files:
        try:
            list(yaml.safe_load_all(f.read_text(errors="ignore")))
        except yaml.YAMLError as e:
            return CheckResult("yaml_valid", False, f"invalid yaml {f.name}: {e}")
    return CheckResult("yaml_valid", True, f"{len(files)} yaml file(s) valid")


@check("cmd_succeeds")
def _cmd_succeeds(ws: pathlib.Path, p: dict) -> CheckResult:
    """Run `cmd` in the workspace; pass iff exit code == expected (default 0)."""
    cmd = p["cmd"]
    expected = int(p.get("expect_code", 0))
    timeout = int(p.get("timeout", 120))
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(ws), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return CheckResult("cmd_succeeds", False, f"timeout after {timeout}s: {cmd}")
    ok = proc.returncode == expected
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
    return CheckResult("cmd_succeeds", ok, f"exit {proc.returncode} (want {expected}) :: {' / '.join(tail)}")


@check("stub_called")
def _stub_called(ws: pathlib.Path, p: dict) -> CheckResult:
    """A stubbed binary (e.g. kubectl) was invoked with an argument matching `pattern`.

    The stub-PATH bins append their argv to `.stublog` in the workspace (see
    evals/harness/stubs/). This lets trajectory-tier deploy scenarios assert on
    what the agent *would* have run, with zero real infra.
    """
    log = ws / ".stublog"
    if not log.exists():
        return CheckResult("stub_called", False, "no .stublog (no stubbed commands ran)")
    text = log.read_text(errors="ignore")
    pattern = re.compile(p["pattern"])
    ok = bool(pattern.search(text))
    return CheckResult("stub_called", ok, f"{p['pattern']!r} in stublog" if ok else f"{p['pattern']!r} not invoked")


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)
