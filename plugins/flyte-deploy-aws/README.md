# flyte-deploy-aws

A [Claude Code](https://docs.claude.com/en/docs/claude-code) skill that walks an agent
through deploying a **Flyte v2 (`flyte-binary`) cluster on AWS from scratch**: EKS + S3 +
RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS (ACM, incl.
cross-account DNS) and Okta/OIDC SSO (console edge SSO + CLI Bearer-bypass).

It encodes the full runbook plus the non-obvious gotchas that break a first deploy
(eksctl version vs EKS, the RDS source security group, ALB controller IAM drift, the
`runs` vs `runs.server` config nesting, and the task-pod control-plane callback env vars).

## Install (Claude Code plugin marketplace)

```
/plugin marketplace add flyteorg/skills
/plugin install flyte-deploy-aws@flyte-skills
```

Then ask Claude to "deploy a Flyte v2 cluster on AWS", or invoke it directly with
`/flyte-deploy-aws:flyte-deploy-aws`.

To pin a specific version of the skills repo, add the marketplace with the full git URL
and append `#<ref>` — a tag or branch name (not a bare commit SHA; tag the commit to pin it):

```
/plugin marketplace add https://github.com/flyteorg/skills.git#<tag-or-branch>
/plugin install flyte-deploy-aws@flyte-skills
```

(To change the pinned version later, `/plugin marketplace remove flyte-skills` and re-add
with the new ref.)

## Install (other agent harnesses)

The skill is a standard [Agent Skill](https://agentskills.io) (`SKILL.md`), so it also
works with:

**OpenAI Codex CLI** — add the repo as a plugin marketplace, then install via `/plugins`:

```
codex plugin marketplace add flyteorg/skills    # or --ref <tag-or-branch> to pin
```

**Hermes** — install the skill by repo path (default branch only):

```
hermes skills install flyteorg/skills/plugins/flyte-deploy-aws/skills/flyte-deploy-aws
```

**opencode** — via the [`skills` CLI](https://github.com/vercel-labs/skills), or copy the
skill folder into `~/.config/opencode/skills/`:

```
npx skills add flyteorg/skills          # append @<ref> to pin
```

**pi** — installs via the repo's `pi.skills` manifest:

```
pi install git:github.com/flyteorg/skills@<tag>   # or the plain https URL for default branch
```

## Install (manual)

Copy `skills/flyte-deploy-aws/` into your `~/.claude/skills/` directory.

## Scope & safety

The skill provisions real, billable AWS resources and runs `aws`/`eksctl`/`helm`
commands. Every value in `<angle brackets>` and the example hostnames/IDs are
placeholders — replace them with your own. Review each step before running it.
