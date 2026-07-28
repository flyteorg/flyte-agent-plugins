"""Per-harness runner adapters (opencode, pi, hermes) behind one interface."""

from __future__ import annotations

from .base import Runner, Trajectory
from .opencode import OpenCodeRunner
from .pi import PiRunner
from .hermes import HermesRunner

_RUNNERS: dict[str, type[Runner]] = {
    "opencode": OpenCodeRunner,
    "pi": PiRunner,
    "hermes": HermesRunner,
}


def get_runner(name: str) -> Runner:
    try:
        return _RUNNERS[name]()
    except KeyError:
        raise ValueError(f"unknown harness {name!r}; known: {sorted(_RUNNERS)}")


def available_harnesses() -> list[str]:
    return sorted(_RUNNERS)
