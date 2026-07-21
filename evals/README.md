# flyte-skills eval harness

Automated testing & evaluation for the `flyte-skills` agent skills. It runs a real
agent harness (**opencode / pi / hermes**) against the union-hosted **GLM** endpoint,
hands it a skill + a task, and scores what it produces — orchestrated as **Flyte
workflows on `demo.hosted.unionai.cloud`**, with path-based selection so only the
scenarios for changed skills run per PR.

## Concepts

- **Scenario** (`scenarios/<skill>/*.yaml`) — one declarative eval: a prompt, the
  deterministic `checks`, an LLM-judge `rubric`, and (tier `real`) a `real_run`.
- **Tiers** — `static` (lint the SKILL.md; no LLM), `trajectory` (run the agent with
  side-effecting commands stubbed, judge the artifacts it produces), `real` (actually
  `flyte run` SDK output on demo.hosted; kind stood up for real on a CI runner).
- **Control arm** — every trajectory/real scenario runs twice: **treatment** (skill
  installed) and **control** (skill absent). The headline metric is
  **lift = treatment − control**, isolating the skill's contribution. A negative lift
  is a regression signal.

## Run locally

```bash
pip install pyyaml requests            # + the harness CLI(s) you want to exercise
export PYTHONPATH=$(git rev-parse --show-toplevel)

# Static lint of every skill — no LLM, no agent:
python -m evals.harness.run --tier static

# One trajectory scenario end-to-end (needs GLM_API_KEY + the harness CLI):
export GLM_API_KEY=...     # token for the demo.hosted GLM app
python -m evals.harness.run --scenario sdk-author-map-task --harness opencode

# Everything for one skill, JSON out + scorecard:
python -m evals.harness.run --skill flyte-sdk-author --json out.json
python -m evals.report out.json --html scorecard.html
```

`GLM_BASE_URL` / `GLM_MODEL` / `GLM_API_KEY` configure the endpoint (see
`harness/glm.py`). The `real` tier only submits remote runs when
`FLYTE_EVALS_ENABLE_REAL=1` is set.

## Run on demo.hosted (Flyte)

```bash
flyte --config evals/config/flyte.yaml run evals/workflows/eval_wf.py main \
    --skills '["flyte-sdk-author"]' --tiers '["static","trajectory"]'
```

Fans out one action per (scenario × harness); the `aggregate` task attaches an HTML
scorecard to the run's report tab. GLM creds come from the `glm-api-key` Flyte secret.

## Selective execution

```bash
python -m evals.select --base origin/main        # changed files -> scenario subset
```

Emits `{run_all, skills, scenario_ids, run_kind, run_real}`. A change under a skill
dir selects that skill's scenarios; a change to the engine (`harness/**`,
`workflows/**`, `manifest.yaml`, …) forces the whole suite. CI wiring is in
`.github/workflows/skill-evals.yml`.

## Layout

```
manifest.yaml            cross-cutting config + shared-infra globs + skill classes
scenarios/<skill>/*.yaml declarative eval specs
harness/                 spec, checks, static_lint, sandbox, runners/, judge, evaluate, run
workflows/               eval_wf.py (Flyte fan-out+aggregate), images.py
config/flyte.yaml        demo.hosted admin/image/task config
select.py  report.py     changed-files selector; JSON+HTML+markdown scorecard
kind_smoke/run.sh        real kind-in-Docker smoke (privileged CI runner)
tests/                   unit tests (no network/LLM)
```

## Status / open spikes

- **GLM endpoint contract** — endpoint is live but auth-gated; confirm the exact
  OpenAI-compatible route + auth header + model name, wire the key as a Flyte/GH
  secret. Single point of change: `harness/glm.py`.
- **Harness invocation** — the opencode adapter is complete; `pi` and `hermes`
  adapters carry a best-effort headless invocation to confirm in the adapter spike
  (`is_available()` gates uninstalled harnesses cleanly). See `harness/runners/`.
