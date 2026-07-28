"""Scenario and manifest schema + loaders.

A *scenario* is a declarative YAML spec describing one eval: which skill, which
tier, the user prompt handed to the agent, deterministic checks, an LLM-judge
rubric, and (for tier: real) how to actually execute the produced artifact.

Everything here is pure data + parsing — no LLM, no network, no subprocess — so
it is trivially unit-testable.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVALS_ROOT = REPO_ROOT / "evals"

VALID_TIERS = ("static", "trajectory", "real")
VALID_HARNESSES = ("opencode", "pi", "hermes")
VALID_ARMS = ("treatment", "control")


@dataclass(frozen=True)
class JudgeSpec:
    rubric: str
    weights: dict[str, float] = field(default_factory=dict)
    pass_threshold: float = 0.7

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> "JudgeSpec | None":
        if not d:
            return None
        return JudgeSpec(
            rubric=d["rubric"],
            weights=dict(d.get("weights") or {}),
            pass_threshold=float(d.get("pass_threshold", 0.7)),
        )


@dataclass(frozen=True)
class RealRunSpec:
    flyte_run: bool = False
    entrypoint: str | None = None          # e.g. "workflow.py main"; None -> autodetect
    inputs: dict[str, Any] = field(default_factory=dict)
    expect_status: str = "SUCCEEDED"

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> "RealRunSpec | None":
        if not d:
            return None
        return RealRunSpec(
            flyte_run=bool(d.get("flyte_run", False)),
            entrypoint=d.get("entrypoint"),
            inputs=dict(d.get("inputs") or {}),
            expect_status=str(d.get("expect_status", "SUCCEEDED")),
        )


@dataclass(frozen=True)
class Scenario:
    id: str
    skill: str
    tier: str
    prompt: str
    harnesses: tuple[str, ...]
    control: bool
    setup: dict[str, Any]
    checks: tuple[dict[str, Any], ...]
    judge: JudgeSpec | None
    real_run: RealRunSpec | None
    source_path: pathlib.Path | None = None

    @staticmethod
    def from_dict(d: dict[str, Any], source_path: pathlib.Path | None = None) -> "Scenario":
        _require(d, "id", source_path)
        _require(d, "skill", source_path)

        tier = d.get("tier", "trajectory")
        if tier not in VALID_TIERS:
            raise ValueError(f"{_loc(source_path)}: invalid tier {tier!r}, expected one of {VALID_TIERS}")

        # static tier lints the skill file directly — no agent prompt needed.
        if tier != "static":
            _require(d, "prompt", source_path)

        harnesses = tuple(d.get("harnesses") or VALID_HARNESSES)
        bad = [h for h in harnesses if h not in VALID_HARNESSES]
        if bad:
            raise ValueError(f"{_loc(source_path)}: unknown harness(es) {bad}")

        return Scenario(
            id=str(d["id"]),
            skill=str(d["skill"]),
            tier=tier,
            prompt=str(d.get("prompt", "")),
            harnesses=harnesses,
            control=bool(d.get("control", True)),
            setup=dict(d.get("setup") or {}),
            checks=tuple(d.get("checks") or ()),
            judge=JudgeSpec.from_dict(d.get("judge")),
            real_run=RealRunSpec.from_dict(d.get("real_run")),
            source_path=source_path,
        )

    def arms(self) -> tuple[str, ...]:
        """Arms to run: static tier is skill-agnostic (treatment only)."""
        if self.tier == "static" or not self.control:
            return ("treatment",)
        return ("treatment", "control")


@dataclass(frozen=True)
class Manifest:
    harnesses: tuple[str, ...]
    default_tiers: tuple[str, ...]
    scenarios_dir: str
    skill_dir_template: str
    shared_infra_globs: tuple[str, ...]
    kind_smoke_skills: tuple[str, ...]
    sdk_real_skills: tuple[str, ...]

    @staticmethod
    def load(path: pathlib.Path | None = None) -> "Manifest":
        path = path or (EVALS_ROOT / "manifest.yaml")
        d = yaml.safe_load(path.read_text())
        return Manifest(
            harnesses=tuple(d.get("harnesses") or VALID_HARNESSES),
            default_tiers=tuple(d.get("default_tiers") or ("static", "trajectory")),
            scenarios_dir=d.get("scenarios_dir", "evals/scenarios"),
            skill_dir_template=d.get("skill_dir_template", "plugins/flyte/skills/{skill}"),
            shared_infra_globs=tuple(d.get("shared_infra_globs") or ()),
            kind_smoke_skills=tuple(d.get("kind_smoke_skills") or ()),
            sdk_real_skills=tuple(d.get("sdk_real_skills") or ()),
        )

    def skill_dir(self, skill: str, repo_root: pathlib.Path = REPO_ROOT) -> pathlib.Path:
        return repo_root / self.skill_dir_template.format(skill=skill)


def load_scenarios(scenarios_dir: pathlib.Path | None = None) -> list[Scenario]:
    """Load every scenario spec under scenarios_dir (recursively)."""
    scenarios_dir = scenarios_dir or (EVALS_ROOT / "scenarios")
    out: list[Scenario] = []
    seen: dict[str, pathlib.Path] = {}
    for p in sorted(scenarios_dir.rglob("*.yaml")):
        doc = yaml.safe_load(p.read_text())
        if not isinstance(doc, dict):
            raise ValueError(f"{p}: scenario file must be a single YAML mapping")
        sc = Scenario.from_dict(doc, source_path=p)
        if sc.id in seen:
            raise ValueError(f"duplicate scenario id {sc.id!r} in {p} and {seen[sc.id]}")
        seen[sc.id] = p
        out.append(sc)
    return out


def scenarios_by_skill(scenarios: list[Scenario]) -> dict[str, list[Scenario]]:
    by: dict[str, list[Scenario]] = {}
    for sc in scenarios:
        by.setdefault(sc.skill, []).append(sc)
    return by


def _require(d: dict[str, Any], key: str, src: pathlib.Path | None) -> None:
    if key not in d:
        raise ValueError(f"{_loc(src)}: scenario missing required field {key!r}")


def _loc(src: pathlib.Path | None) -> str:
    return str(src) if src else "<scenario>"
