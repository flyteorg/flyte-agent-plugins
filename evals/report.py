"""Render a scorecard (JSON already exists; this adds a human-readable HTML +
a markdown summary suitable for a PR comment) from evaluate results.

Input is the list-of-dicts produced by `ScenarioResult.to_dict()` (what
`evals.harness.run --json` writes and what the Flyte aggregate task collects).
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import sys


def _cell(passed: bool) -> str:
    return "✅" if passed else "❌"


def to_markdown(results: list[dict]) -> str:
    total = len(results)
    failed = [r for r in results if not r["passed"]]
    lines = [
        f"### flyte-skills evals — {total - len(failed)}/{total} passing",
        "",
        "| scenario | skill | harness | tier | pass | treat | ctrl | lift |",
        "|---|---|---|---|:--:|--:|--:|--:|",
    ]
    for r in results:
        arms = r.get("arms", {})
        t = arms.get("treatment", {})
        c = arms.get("control", {})
        lift = "" if r.get("lift") is None else f"{r['lift']:+.2f}"
        lines.append(
            f"| {r['scenario_id']} | {r['skill']} | {r.get('harness') or '-'} | {r['tier']} | "
            f"{_cell(r['passed'])} | {_fmt(t.get('score'))} | {_fmt(c.get('score'))} | {lift} |"
        )
    if failed:
        lines += ["", "<details><summary>Failure detail</summary>", ""]
        for r in failed:
            lines.append(f"- **{r['scenario_id']}** ({r.get('harness') or '-'}):")
            for arm, ar in r.get("arms", {}).items():
                for ch in ar.get("checks", []):
                    if not ch["passed"]:
                        lines.append(f"  - [{arm}] check `{ch['kind']}`: {ch['detail']}")
                if ar.get("error"):
                    lines.append(f"  - [{arm}] error: {ar['error']}")
        lines.append("</details>")
    return "\n".join(lines)


def to_html(results: list[dict]) -> str:
    rows = []
    for r in results:
        arms = r.get("arms", {})
        t = arms.get("treatment", {})
        c = arms.get("control", {})
        lift = "" if r.get("lift") is None else f"{r['lift']:+.2f}"
        rows.append(
            "<tr>"
            f"<td>{html.escape(r['scenario_id'])}</td>"
            f"<td>{html.escape(r['skill'])}</td>"
            f"<td>{html.escape(r.get('harness') or '-')}</td>"
            f"<td>{html.escape(r['tier'])}</td>"
            f"<td style='text-align:center'>{_cell(r['passed'])}</td>"
            f"<td style='text-align:right'>{_fmt(t.get('score'))}</td>"
            f"<td style='text-align:right'>{_fmt(c.get('score'))}</td>"
            f"<td style='text-align:right'>{lift}</td>"
            "</tr>"
        )
    passed = sum(1 for r in results if r["passed"])
    return f"""<!doctype html><meta charset=utf-8>
<title>flyte-skills evals</title>
<style>
 body{{font:14px/1.4 system-ui,sans-serif;margin:2rem}}
 table{{border-collapse:collapse;width:100%}}
 th,td{{border:1px solid #ddd;padding:6px 10px}}
 th{{background:#f4f4f5;text-align:left}}
</style>
<h1>flyte-skills evals — {passed}/{len(results)} passing</h1>
<table>
<thead><tr><th>scenario</th><th>skill</th><th>harness</th><th>tier</th>
<th>pass</th><th>treatment</th><th>control</th><th>lift</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
"""


def _fmt(v) -> str:
    return "" if v is None else f"{v:.2f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals.report")
    ap.add_argument("results_json", help="path to results JSON (list of ScenarioResult dicts)")
    ap.add_argument("--html", help="write HTML scorecard here")
    ap.add_argument("--markdown", help="write markdown summary here")
    args = ap.parse_args(argv)

    results = json.loads(pathlib.Path(args.results_json).read_text())
    if args.html:
        pathlib.Path(args.html).write_text(to_html(results))
    md = to_markdown(results)
    if args.markdown:
        pathlib.Path(args.markdown).write_text(md)
    else:
        print(md)
    failed = sum(1 for r in results if not r["passed"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
