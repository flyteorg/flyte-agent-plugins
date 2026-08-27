from evals.report import rating, to_html, to_markdown

RESULTS = [
    {"scenario_id": "a", "skill": "flyte-sdk-author", "tier": "trajectory",
     "harness": "opencode", "status": "scored", "passed": True, "score": 0.9,
     "lift": 0.4, "is_regression": False,
     "arms": {"treatment": {"score": 0.9, "checks": []},
              "control": {"score": 0.5, "checks": []}}},
    {"scenario_id": "b", "skill": "deploy-flyte-kind", "tier": "static",
     "harness": None, "status": "scored", "passed": False, "score": 0.0,
     "lift": None, "is_regression": True,
     "arms": {"treatment": {"score": 0.0, "error": "boom",
                            "checks": [{"kind": "frontmatter", "passed": False, "detail": "bad"}]}}},
    {"scenario_id": "c", "skill": "flyte-sdk-run", "tier": "trajectory",
     "harness": "pi", "status": "skipped", "passed": False, "score": None,
     "lift": None, "is_regression": False,
     "arms": {"treatment": {"unavailable": True, "error": "pi CLI not available",
                            "checks": []}}},
    {"scenario_id": "d", "skill": "flyte-sdk-run", "tier": "trajectory",
     "harness": "opencode", "status": "error", "passed": False, "score": None,
     "lift": None, "is_regression": False,
     "arms": {"treatment": {"error": "harness crashed", "checks": []}}},
]


def test_rating_aggregates():
    m = rating(RESULTS)
    assert m["total"] == 4 and m["scored"] == 2
    assert m["skipped"] == 1 and m["errored"] == 1
    assert m["regressions"] == 1
    assert m["rating"] == 0.45  # mean treatment score over the 2 scored rows
    assert m["mean_lift"] == 0.4


def test_markdown_has_rating_glyphs_and_failure_detail():
    md = to_markdown(RESULTS)
    assert "2 scored, 1 skipped, 1 errored, 1 regressions" in md
    assert "flyte-sdk-author" in md and "+0.40" in md
    assert "✅" in md and "❌" in md and "⏭" in md and "⚠" in md
    assert "frontmatter" in md and "bad" in md and "harness crashed" in md


def test_html_renders():
    html = to_html(RESULTS)
    assert "<table>" in html and "flyte-sdk-author" in html
    assert "rating 0.450" in html
