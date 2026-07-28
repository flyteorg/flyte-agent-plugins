"""Static tier: skill-agnostic lint of a SKILL.md.

Runs with no LLM and no agent — it validates the skill file itself:
  - YAML frontmatter present, with `name` + `description`
  - `name` matches the containing directory
  - description length is within agent-skill norms (not empty, not enormous)
  - fenced code blocks parse (python -> ast, yaml -> safe_load) best-effort
  - no obviously-hardcoded secrets or environment-specific hostnames/IDs

Returns CheckResult list so it slots into the same reporting as other tiers.
"""

from __future__ import annotations

import ast
import pathlib
import re

import yaml

from .checks import CheckResult

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FENCE_RE = re.compile(r"^```([\w-]*)\n(.*?)^```", re.DOTALL | re.MULTILINE)

# Secret / environment-specific value patterns that must not be committed in a
# skill. Placeholders in <angle brackets> are fine and explicitly allowed.
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"aws_secret_access_key\s*=\s*[A-Za-z0-9/+]{40}"), "AWS secret key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"), "JWT"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "Slack token"),
    (re.compile(r"ghp_[0-9A-Za-z]{36}"), "GitHub PAT"),
]


def lint_skill(skill_dir: pathlib.Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return [CheckResult("skill_exists", False, f"no SKILL.md in {skill_dir}")]
    results.append(CheckResult("skill_exists", True, str(md)))

    text = md.read_text()
    m = FRONTMATTER_RE.match(text)
    if not m:
        results.append(CheckResult("frontmatter", False, "missing/invalid YAML frontmatter"))
        return results

    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        results.append(CheckResult("frontmatter", False, f"frontmatter not valid yaml: {e}"))
        return results
    results.append(CheckResult("frontmatter", True, "parsed"))

    name = fm.get("name")
    results.append(CheckResult(
        "frontmatter_name", bool(name) and name == skill_dir.name,
        f"name={name!r} dir={skill_dir.name!r}",
    ))
    desc = (fm.get("description") or "").strip()
    results.append(CheckResult(
        "frontmatter_description", 20 <= len(desc) <= 1500,
        f"description length {len(desc)} (want 20..1500)",
    ))

    # Code fences parse.
    py_bad, yaml_bad, n_py, n_yaml = [], [], 0, 0
    body = text[m.end():]
    for lang, code in FENCE_RE.findall(body):
        lang = lang.lower()
        if lang in ("python", "py"):
            n_py += 1
            try:
                ast.parse(code)
            except SyntaxError as e:
                py_bad.append(f"L{e.lineno}: {e.msg}")
        elif lang in ("yaml", "yml"):
            n_yaml += 1
            # skip fences that are obviously templated (helm/${}) — best-effort
            if "{{" in code or "${" in code:
                continue
            try:
                list(yaml.safe_load_all(code))
            except yaml.YAMLError as e:
                yaml_bad.append(str(e).splitlines()[0])
    results.append(CheckResult(
        "python_fences_parse", not py_bad, f"{n_py} python fence(s); errors: {py_bad or 'none'}",
    ))
    results.append(CheckResult(
        "yaml_fences_parse", not yaml_bad, f"{n_yaml} yaml fence(s); errors: {yaml_bad or 'none'}",
    ))

    # No committed secrets.
    found = [label for rx, label in SECRET_PATTERNS if rx.search(text)]
    results.append(CheckResult(
        "no_secrets", not found, f"secret-like values: {found or 'none'}",
    ))

    return results
