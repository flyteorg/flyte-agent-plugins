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


def _status(r: dict) -> str:
    # Back-compat: old result dicts (pre-status) only had `passed`.
    return r.get("status") or ("scored" if r.get("passed") else "scored")


def _cell(r: dict) -> str:
    """Status glyph for a result row.
    ✅ scored & passed · 🟡 scored, checks ok but judge soft-fail ·
    ❌ regression (deterministic check failed) · ⏭ skipped · ⚠ harness error."""
    st = _status(r)
    if st == "skipped":
        return "⏭"
    if st == "error":
        return "⚠"
    if r.get("is_regression"):
        return "❌"
    return "✅" if r.get("passed") else "🟡"


def reason(result: dict) -> str:
    """One-line, human-readable reason for a scenario's outcome — skip cause,
    harness error, first failing deterministic check, or failed LLM judge."""
    st = _status(result)
    arms = result.get("arms", {})
    if st == "skipped":
        t = arms.get("treatment", {})
        return t.get("error") or "harness unavailable"
    for arm, ar in arms.items():
        for ch in ar.get("checks", []):
            if not ch["passed"]:
                return f"[{arm}] check {ch['kind']}: {ch['detail']}"
        if ar.get("error") and not ar.get("unavailable"):
            return f"[{arm}] error: {ar['error']}"
        judge = ar.get("judge")
        if judge and not judge.get("passed", True):
            rat = (judge.get("rationale") or "").strip().replace("\n", " ")
            return f"[{arm}] judge {_fmt(judge.get('score'))}: {rat[:240]}"
    return "no passing treatment arm"


def rating(results: list[dict]) -> dict:
    """Aggregate the run into a tracked rating rather than a pass/fail tally.

    rating = mean treatment score over *scored* scenarios (0..1); skipped and
    errored scenarios are excluded. `regressions` counts scored scenarios whose
    deterministic checks failed — the reliable, non-LLM signal CI gates on."""
    scored = [r for r in results if _status(r) == "scored"]
    skipped = [r for r in results if _status(r) == "skipped"]
    errored = [r for r in results if _status(r) == "error"]
    regressions = [r for r in scored if r.get("is_regression")]
    scores = [r["score"] for r in scored if r.get("score") is not None]
    lifts = [r["lift"] for r in scored if r.get("lift") is not None]
    by_skill: dict[str, list[float]] = {}
    for r in scored:
        if r.get("score") is not None:
            by_skill.setdefault(r["skill"], []).append(r["score"])
    return {
        "total": len(results),
        "scored": len(scored),
        "skipped": len(skipped),
        "errored": len(errored),
        "regressions": len(regressions),
        "rating": round(sum(scores) / len(scores), 4) if scores else None,
        "mean_lift": round(sum(lifts) / len(lifts), 4) if lifts else None,
        "per_skill_rating": {
            k: round(sum(v) / len(v), 4) for k, v in sorted(by_skill.items())
        },
    }


def rating_line(results: list[dict]) -> str:
    m = rating(results)
    rr = "n/a" if m["rating"] is None else f"{m['rating']:.3f}"
    lift = "n/a" if m["mean_lift"] is None else f"{m['mean_lift']:+.3f}"
    return (
        f"rating: {rr} (mean treatment score over {m['scored']} scored) | "
        f"lift: {lift} | {m['scored']} scored, {m['skipped']} skipped, "
        f"{m['errored']} errored, {m['regressions']} regressions"
    )


def _skip_breakdown(skipped: list[dict]) -> str:
    counts: dict[str, int] = {}
    for r in skipped:
        counts[r.get("harness") or "-"] = counts.get(r.get("harness") or "-", 0) + 1
    return ", ".join(f"{h}×{n}" for h, n in sorted(counts.items()))


def failure_report(results: list[dict]) -> str:
    """Plaintext breakdown for task logs / CI output: the rating line, then
    regressions (the gating signal) and errors in detail, and a one-line skip
    summary — skips are expected when an agent CLI isn't installed."""
    lines = [rating_line(results)]

    def _fmt_rows(rows, glyph):
        for r in sorted(rows, key=lambda r: (r["skill"], r["scenario_id"], r.get("harness") or "")):
            lines.append(
                f"  {glyph} {r['scenario_id']} [{r.get('harness') or '-'}] "
                f"({r['skill']}/{r['tier']}): {reason(r)}"
            )

    regressions = [r for r in results if r.get("is_regression")]
    if regressions:
        lines.append(f"\n{len(regressions)} regression(s) (static SKILL.md lint failed):")
        _fmt_rows(regressions, "✗")

    errored = [r for r in results if _status(r) == "error"]
    if errored:
        lines.append(f"\n{len(errored)} errored (harness ran but crashed):")
        _fmt_rows(errored, "⚠")

    skipped = [r for r in results if _status(r) == "skipped"]
    if skipped:
        lines.append(f"\n{len(skipped)} skipped (harness CLI unavailable): {_skip_breakdown(skipped)}")

    if not regressions and not errored:
        lines.append("\nno regressions — deterministic checks pass on all scored scenarios")
    return "\n".join(lines)


def to_markdown(results: list[dict]) -> str:
    m = rating(results)
    rr = "n/a" if m["rating"] is None else f"{m['rating']:.3f}"
    per_skill = " · ".join(f"{k} {v:.2f}" for k, v in m["per_skill_rating"].items())
    lines = [
        f"### flyte-agent-plugin evals — rating {rr}",
        "",
        f"{rating_line(results)}",
        "",
        *( [f"**Per-skill rating:** {per_skill}", ""] if per_skill else [] ),
        "| scenario | skill | harness | tier | status | treat | ctrl | lift |",
        "|---|---|---|---|:--:|--:|--:|--:|",
    ]
    for r in results:
        arms = r.get("arms", {})
        t = arms.get("treatment", {})
        c = arms.get("control", {})
        lift = "" if r.get("lift") is None else f"{r['lift']:+.2f}"
        lines.append(
            f"| {r['scenario_id']} | {r['skill']} | {r.get('harness') or '-'} | {r['tier']} | "
            f"{_cell(r)} | {_fmt(t.get('score'))} | {_fmt(c.get('score'))} | {lift} |"
        )
    detail = [r for r in results if _status(r) in ("scored",) and r.get("is_regression")]
    detail += [r for r in results if _status(r) == "error"]
    if detail:
        lines += ["", "<details><summary>Regression / error detail</summary>", ""]
        for r in detail:
            lines.append(f"- **{r['scenario_id']}** ({r.get('harness') or '-'}):")
            for arm, ar in r.get("arms", {}).items():
                for ch in ar.get("checks", []):
                    if not ch["passed"]:
                        lines.append(f"  - [{arm}] check `{ch['kind']}`: {ch['detail']}")
                if ar.get("error") and not ar.get("unavailable"):
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
            f"<td style='text-align:center'>{_cell(r)}</td>"
            f"<td style='text-align:right'>{_fmt(t.get('score'))}</td>"
            f"<td style='text-align:right'>{_fmt(c.get('score'))}</td>"
            f"<td style='text-align:right'>{lift}</td>"
            "</tr>"
        )
    m = rating(results)
    rr = "n/a" if m["rating"] is None else f"{m['rating']:.3f}"
    return f"""<!doctype html><meta charset=utf-8>
<title>flyte-agent-plugin evals</title>
<style>
 body{{font:14px/1.4 system-ui,sans-serif;margin:2rem}}
 table{{border-collapse:collapse;width:100%}}
 th,td{{border:1px solid #ddd;padding:6px 10px}}
 th{{background:#f4f4f5;text-align:left}}
</style>
<h1>flyte-agent-plugin evals — rating {rr}</h1>
<p>{html.escape(rating_line(results))}</p>
<table>
<thead><tr><th>scenario</th><th>skill</th><th>harness</th><th>tier</th>
<th>status</th><th>treatment</th><th>control</th><th>lift</th></tr></thead>
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
    # Non-zero only on regressions (scored scenarios with failing deterministic
    # checks) — skipped harnesses and soft judge scores don't fail the report.
    return 1 if rating(results)["regressions"] else 0


if __name__ == "__main__":
    sys.exit(main())
