from evals.report import to_html, to_markdown

RESULTS = [
    {"scenario_id": "a", "skill": "flyte-sdk-author", "tier": "trajectory",
     "harness": "opencode", "passed": True, "lift": 0.4,
     "arms": {"treatment": {"score": 0.9, "checks": []}, "control": {"score": 0.5, "checks": []}}},
    {"scenario_id": "b", "skill": "deploy-flyte-kind", "tier": "static",
     "harness": None, "passed": False, "lift": None,
     "arms": {"treatment": {"score": 0.0, "error": "boom",
                            "checks": [{"kind": "frontmatter", "passed": False, "detail": "bad"}]}}},
]


def test_markdown_has_summary_and_failure_detail():
    md = to_markdown(RESULTS)
    assert "1/2 passing" in md
    assert "flyte-sdk-author" in md and "+0.40" in md
    assert "frontmatter" in md and "boom" in md


def test_html_renders():
    html = to_html(RESULTS)
    assert "<table>" in html and "flyte-sdk-author" in html and "1/2 passing" in html
