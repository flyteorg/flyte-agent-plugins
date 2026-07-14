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
and append `#<ref>` — a tag, branch, or commit SHA:

```
/plugin marketplace add https://github.com/flyteorg/skills.git#<tag-or-commit>
/plugin install flyte-deploy-kind@flyte-skills
```

(To change the pinned version later, `/plugin marketplace remove flyte-skills` and re-add
with the new ref.)
