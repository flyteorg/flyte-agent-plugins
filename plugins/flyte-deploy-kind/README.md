# flyte-deploy-kind

[Claude Code](https://docs.claude.com/en/docs/claude-code) skills for running **Flyte v2
(`flyte-binary`) on a [kind](https://kind.sigs.k8s.io/) cluster** — on your own machine
or a DigitalOcean VM (droplet), for evaluation only (no production hardening).

kind runs only the Flyte binary; the database and object store are hosted. The skill
collects your connection details and assembles the values file:

- **PostgreSQL** — Supabase (session pooler) or another external/self-hosted instance.
- **Object store** — AWS S3 or Cloudflare R2.

It optionally adds **OIDC auth** at the edge with Traefik + oauth2-proxy, gating the
console (and, if you want, the SDK/CLI over TLS). For an IdP with no cloud account, the
second skill stands up **Dex in-cluster** as a test OIDC provider.

## Skills

- **`deploy-flyte-kind`** — create/reuse the kind cluster, wire up the hosted DB and
  object store, install `flyte-binary`, and optionally add OIDC auth.
- **`start-dex-local`** — deploy Dex as a local in-cluster OIDC provider, invoked by the
  kind skill when you pick Dex for auth.

## Install (Claude Code plugin marketplace)

```
/plugin marketplace add flyteorg/skills
/plugin install flyte-deploy-kind@flyte-skills
```

Then ask Claude to "deploy Flyte on kind" (locally or on a DigitalOcean droplet), or
invoke it directly with `/flyte-deploy-kind:deploy-flyte-kind`.

To pin a specific version of the skills repo, add the marketplace with the full git URL
and append `#<ref>` — a tag or branch name (not a bare commit SHA; tag the commit to pin it):

```
/plugin marketplace add https://github.com/flyteorg/skills.git#<tag-or-branch>
/plugin install flyte-deploy-kind@flyte-skills
```

(To change the pinned version later, `/plugin marketplace remove flyte-skills` and re-add
with the new ref.)

## Install (other agent harnesses)

The skills are standard [Agent Skills](https://agentskills.io) (`SKILL.md`), so they also
work with:

**OpenAI Codex CLI** — add the repo as a plugin marketplace, then install via `/plugins`:

```
codex plugin marketplace add flyteorg/skills    # or --ref <tag-or-branch> to pin
```

**Hermes** — install the skills by repo path (default branch only):

```
hermes skills install flyteorg/skills/plugins/flyte-deploy-kind/skills/deploy-flyte-kind
hermes skills install flyteorg/skills/plugins/flyte-deploy-kind/skills/deploy-flyte-kind-vm
hermes skills install flyteorg/skills/plugins/flyte-deploy-kind/skills/start-dex-local
```

**opencode** — via the [`skills` CLI](https://github.com/vercel-labs/skills), or copy the
skill folders into `~/.config/opencode/skills/`:

```
npx skills add flyteorg/skills          # append @<ref> to pin
```

**pi** — installs via the repo's `pi.skills` manifest:

```
pi install git:github.com/flyteorg/skills@<tag>   # or the plain https URL for default branch
```
