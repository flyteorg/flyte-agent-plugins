# Releasing

How to publish a new version of `flyte-skills` and `flyte-agent-plugins` to PyPI.

Both names are published from the same tag as identical mirrors, so there is one
release, not two. The version comes from
`plugins/flyte/.claude-plugin/plugin.json` and the tag must match it — CI refuses
to publish otherwise.

For how the packages are built, see [`packaging/README.md`](packaging/README.md).
npm publishing is currently disabled; that document explains how to turn it on.

## First-time setup

Needed once per repository, not once per release. Skip if
<https://pypi.org/project/flyte-skills/> already exists.

- [ ] Create a GitHub environment named `pypi` (**Settings → Environments**). Add
      required reviewers if you want a human gate before each publish.
- [ ] Add a PyPI trusted publisher for `flyte-skills` at
      <https://pypi.org/manage/account/publishing/>, using the settings below.
      Before the first release the project does not exist yet, so add it under
      **pending publishers**.
- [ ] Add a second publisher, identical except for the project name, for
      `flyte-agent-plugins`. One publisher is needed per package name.

| Field | Value |
|---|---|
| PyPI project name | `flyte-skills`, then `flyte-agent-plugins` |
| Owner | `flyteorg` |
| Repository name | `flyte-agent-plugins` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

No API tokens are stored anywhere. The workflow authenticates over OIDC through
its `id-token: write` permission.

## Release checklist

### 1. Pick the version

- [ ] Decide the new version. These are `SKILL.md` files, so judge the bump by
      what changes for someone whose agent already loads them:
      **patch** for wording and fixes, **minor** for new skills or a changed
      workflow, **major** for renaming or removing a skill (that breaks
      `/flyte:<skill>` invocations and any harness pinned to a path).
- [ ] Confirm the version is not already on PyPI. A version can never be
      re-uploaded, even after a yank:

      ```bash
      curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/flyte-skills/0.4.0/json
      # 404 = free to use, 200 = already published, pick the next one
      ```

### 2. Prepare the commit

- [ ] Start from an up-to-date `main` with a clean tree:

      ```bash
      git checkout main && git pull origin main && git status
      ```

- [ ] Set the version everywhere (plugin manifest, Codex manifest, root
      `package.json`):

      ```bash
      python packaging/set_version.py 0.4.0
      ```

- [ ] Verify locally — this builds every distribution and installs it, which is
      the same check CI runs:

      ```bash
      python packaging/verify.py
      ```

- [ ] Commit and open a PR. `main` requires one approving review, so the bump
      lands through review like anything else. Sign off the commit — the repo
      enforces DCO:

      ```bash
      git checkout -b release-0.4.0
      git commit -s -am "release 0.4.0"
      git push -u origin release-0.4.0 && gh pr create --fill
      ```

- [ ] Merge once `verify` and `DCO` are green.

### 3. Tag

- [ ] Tag the **merge commit on `main`**, not the branch:

      ```bash
      git checkout main && git pull origin main
      git tag v0.4.0
      git push origin v0.4.0
      ```

      The `v` prefix is required — `publish.yml` triggers on `v*` — and the rest
      must match the manifest exactly. A mismatch fails the build job with a
      message naming both versions.

### 4. Watch the publish

- [ ] Follow the run at
      <https://github.com/flyteorg/flyte-agent-plugins/actions/workflows/publish.yml>,
      or from the terminal once the tag push has registered:

      ```bash
      gh run watch "$(gh run list --workflow=publish.yml --limit=1 --json databaseId --jq '.[0].databaseId')"
      ```

      It builds and verifies, then publishes `flyte-skills` and
      `flyte-agent-plugins` as separate matrix jobs, then attaches the artifacts
      to a GitHub release. The two names publish independently, so one failing
      does not block the other.

### 5. Confirm it landed

- [ ] Both projects show the new version:

      ```bash
      for p in flyte-skills flyte-agent-plugins; do
        echo "$p $(curl -s https://pypi.org/pypi/$p/json | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["version"])')"
      done
      ```

- [ ] A real install works end to end, from a clean cache:

      ```bash
      uvx --refresh --from flyte-skills==0.4.0 flyte-skills list   # expect 21 skills
      uvx --refresh --from flyte-skills==0.4.0 flyte-skills install --dry-run
      ```

- [ ] The GitHub release exists and carries the sdists, wheels, and npm
      tarballs: `gh release view v0.4.0`.

## When something goes wrong

**The tag does not match the manifest.** The build job stops before publishing
anything. Delete the tag (`git push origin :v0.4.0`), fix the version with
`set_version.py`, and tag again.

**One name published and the other failed.** Re-run the failed matrix job. The
publish step uses `skip-existing`, so the name that already succeeded is a no-op
rather than an error.

**A bad version reached PyPI.** You cannot overwrite or re-upload it, even after
deleting it. Publish a new patch version with the fix. Yank the bad one from the
PyPI project page — yanking hides it from new resolutions while leaving anyone
who pinned it working.

**Rehearse without publishing.** Run `publish.yml` manually from the Actions tab
with `dry_run: true` (the default). It builds, verifies, and validates the
packages, then stops before any upload.

## After the release

- [ ] Consider whether the marketplace entry should pin the new version. The git
      source in `.claude-plugin/marketplace.json` tracks the default branch and
      needs no change; only an explicit `version` pin would.
- [ ] Adoption numbers show up within about a day at
      <https://pypistats.org/packages/flyte-skills>. Note PyPI counts downloads,
      not people — CI re-installs and mirrors are in there too.
