# Flyte Skills

A [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin marketplace of
skills for working with [Flyte](https://flyte.org).

## Install

```
/plugin marketplace add flyteorg/skills
/plugin install <skill>@flyte-skills
```

## Skills

| Skill | Description |
|-------|-------------|
| [`flyte-deploy-aws`](plugins/flyte-deploy-aws) | Deploy a Flyte v2 (`flyte-binary`) cluster on AWS from scratch — EKS + S3 + RDS PostgreSQL + AWS Load Balancer Controller + `helm`, with optional TLS (ACM, incl. cross-account DNS) and Okta/OIDC SSO. |
| [`flyte-deploy-kind`](plugins/flyte-deploy-kind) | Deploy a Flyte v2 (`flyte-binary`) cluster on `kind` — on your local machine or a cloud VM (DigitalOcean, AWS EC2, or GCP), backed by a hosted PostgreSQL (Supabase/external) and object store (S3/R2), with optional OIDC auth via Traefik + oauth2-proxy and an in-cluster Dex IdP. |

Example:

```
/plugin install flyte-deploy-aws@flyte-skills
```

Then ask Claude to "deploy a Flyte v2 cluster on AWS", or invoke it directly with
`/flyte-deploy-aws:flyte-deploy-aws`.

## Layout

```
.claude-plugin/marketplace.json          # marketplace catalog
plugins/<skill>/.claude-plugin/plugin.json
plugins/<skill>/skills/<skill>/SKILL.md
```

## Contributing

Add a new skill as a plugin directory under `plugins/`, then list it in
`.claude-plugin/marketplace.json`. Keep everything generic — no account IDs,
hostnames, credentials, or other environment-specific values.
