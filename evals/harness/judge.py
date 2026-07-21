"""LLM-as-judge over an agent trajectory, via the GLM endpoint.

The judge is a *secondary* signal: deterministic `checks.py` gate pass/fail; the
judge produces a graded rubric score (0..1 per dimension) used for the lift
metric and for surfacing quality regressions. Judge output is forced to JSON and
parsed defensively so a malformed response degrades to score 0, never a crash.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .glm import GLMConfig, chat_completion
from .spec import JudgeSpec

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM = (
    "You are a strict evaluator of an AI coding agent's work. You are given a "
    "rubric and the agent's trajectory (what it said and the files it produced). "
    "Score each named dimension from 0.0 to 1.0. Respond ONLY with a JSON object "
    'of the form {"scores": {"<dimension>": <float>, ...}, "rationale": "<short>"}. '
    "Do not include any prose outside the JSON."
)


@dataclass(frozen=True)
class JudgeResult:
    score: float                      # weighted aggregate in [0, 1]
    passed: bool                      # score >= pass_threshold
    dimensions: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    raw: str = ""

    @staticmethod
    def error(msg: str) -> "JudgeResult":
        return JudgeResult(score=0.0, passed=False, rationale=f"judge error: {msg}", raw=msg)


def build_prompt(rubric: str, dimensions: list[str], trajectory_text: str) -> list[dict]:
    dims = ", ".join(dimensions) if dimensions else "correctness, skill_adherence, idiomatic"
    user = (
        f"# Rubric\n{rubric}\n\n"
        f"# Dimensions to score\n{dims}\n\n"
        f"# Agent trajectory\n{trajectory_text}\n"
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse_response(text: str, weights: dict[str, float], threshold: float) -> JudgeResult:
    m = _JSON_RE.search(text or "")
    if not m:
        return JudgeResult.error(f"no JSON in judge response: {text[:200]!r}")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return JudgeResult.error(f"bad JSON: {e}")
    scores = {k: _clamp(v) for k, v in (obj.get("scores") or {}).items()}
    agg = _weighted(scores, weights)
    return JudgeResult(
        score=agg,
        passed=agg >= threshold,
        dimensions=scores,
        rationale=str(obj.get("rationale", "")),
        raw=text,
    )


def judge(spec: JudgeSpec, trajectory_text: str, cfg: GLMConfig) -> JudgeResult:
    dims = list(spec.weights) or ["correctness", "skill_adherence", "idiomatic"]
    messages = build_prompt(spec.rubric, dims, trajectory_text)
    try:
        text = chat_completion(cfg, messages, temperature=0.0, max_tokens=1024)
    except Exception as exc:
        return JudgeResult.error(repr(exc))
    return parse_response(text, spec.weights, spec.pass_threshold)


def _clamp(v: object) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _weighted(scores: dict[str, float], weights: dict[str, float]) -> float:
    if not scores:
        return 0.0
    if weights:
        total_w = sum(weights.values()) or 1.0
        return sum(scores.get(k, 0.0) * w for k, w in weights.items()) / total_w
    return sum(scores.values()) / len(scores)
