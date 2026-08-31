# Packaging and release

The skills in `plugins/flyte/` are published from this one source of truth:

| Registry | Package | Install | Status |
|---|---|---|---|
| PyPI | [`flyte-skills`](https://pypi.org/project/flyte-skills/) | `uvx flyte-skills install` | published |
| PyPI | [`flyte-agent-plugins`](https://pypi.org/project/flyte-agent-plugins/) | `uvx flyte-agent-plugins install` | published |
| npm | `flyte-skills` | `npx flyte-skills install` | **built, not published** |
| npm | `flyte-agent-plugins` | `npx flyte-agent-plugins install` | **built, not published** |

**npm publishing is currently disabled** while distribution focuses on pip/uvx.
The npm packages are still generated, packed, and validated on every CI run, so
turning them on later is a one-line change to `publish.yml` — see
[Enabling npm](#enabling-npm).

The two names are **identical mirrors**, not an alias plus a shim. Each carries
the full payload, so each registry's download counter reports real installs of
that name rather than a redirect — and both names stay reserved against
squatting on Flyte-adjacent packages.

## Why registries at all

A git-distributed plugin has no download counter. GitHub clone traffic is the
only proxy, it conflates CI and update re-fetches with installs, and GitHub
retains just a rolling 14-day window. PyPI publishes free, historical download
data:

```
https://pypistats.org/api/packages/flyte-skills/recent
https://pypistats.org/api/packages/flyte-skills/overall
```

(npm has the equivalent at
`https://api.npmjs.org/downloads/range/last-year/<package>`, once those packages
are published.)

For full history and mirror-free numbers, query
`bigquery-public-data.pypi.file_downloads` and filter
`details.installer.name IN ('pip','uv')`. Neither registry gives a unique-user
signal — they answer "is adoption trending up", not "how many teams use this".
The `flyte-docs` MCP server is the place to measure actives.

## Layout

```
packaging/
├── build.py            # generates all four source trees into ./build
├── set_version.py      # writes one version into every manifest
├── verify.py           # builds + installs every distribution, asserts contents
└── templates/
    ├── cli.py          # the Python installer CLI (shared by both PyPI dists)
    ├── cli.mjs         # the Node installer CLI (shared by both npm dists)
    └── README.md.tmpl  # the per-package README shown on npm/PyPI
```

`build.py` fans the payload out per name:

* **npm** — the package root *is* the plugin root (`.claude-plugin/plugin.json`
  at the top level), which is what Claude Code's `npm` plugin source requires.
  `package.json` carries an explicit `files` allowlist because npm's default
  file selection is not reliable about dot-directories, plus the `pi.skills`
  manifest so pi reads the same tree.
* **PyPI** — an `src/<module>/` package with the whole plugin vendored at
  `<module>/plugin/` as package data, and a console script named after the
  distribution. The two dists use different module and script names
  (`flyte_skills` / `flyte_agent_plugins`), so installing both into one
  environment does not collide.

## Local development

```bash
python packaging/build.py          # write ./build/{npm,pypi}/<name>/
python packaging/verify.py         # what CI runs: build, install, assert
```

`verify.py` needs `node`/`npm` and either `uv` or `python -m build`.

## Cutting a release

```bash
python packaging/set_version.py 0.4.0   # updates all three manifests
git commit -am "release 0.4.0"
git tag v0.4.0 && git push origin main --tags
```

`.github/workflows/publish.yml` then:

1. refuses to continue unless the tag matches the plugin manifest version;
2. runs `verify.py` — a package that does not install is never published;
3. builds the npm tarballs and the sdists/wheels, and runs
   `npm publish --dry-run` and `twine check`;
4. publishes both names to PyPI (trusted publishing, no token), each as a
   separate matrix job so one failure does not block the other;
5. attaches every artifact to the GitHub release.

To rehearse without publishing, run the workflow manually with `dry_run: true`
(the default) — it does everything through step 3 and stops.

`.github/workflows/packaging.yml` runs step 2 on every PR that touches
`plugins/**` or `packaging/**`.

## One-time setup

**GitHub environments.** Create an environment named `pypi` (Settings →
Environments). Add required reviewers there if you want a human gate on
publishes.

**PyPI trusted publishing.** Configure one publisher per package name at
<https://pypi.org/manage/account/publishing/>. Because the projects do not exist
until the first release, add them as *pending publishers*:

| Field | Value |
|---|---|
| PyPI project name | `flyte-skills` (then again for `flyte-agent-plugins`) |
| Owner | `flyteorg` |
| Repository name | this repo |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

No API token is stored anywhere; the workflow's `id-token: write` permission is
what authenticates. **This is all the setup a release needs today.**

## Enabling npm

The `npm` job in `publish.yml` is gated behind `if: false`. To turn it on:
restore the condition to `github.event_name == 'push' || inputs.dry_run == false`,
add `npm` back to the `release` job's `needs`, create an `npm` environment, and
add the token described below.

**npm needs a token, unlike PyPI.** npm has no equivalent of PyPI's
pending publishers: a trusted publisher can only be configured on a package that
already exists, and OIDC cannot perform a package's first publish
([npm/cli#8544](https://github.com/npm/cli/issues/8544)). So the first release of
each name must authenticate with a token.

Create the token on npmjs.com and store it as the secret `NPM_TOKEN` in the
`npm` environment. Use a classic **automation** token, or a granular token with
"All packages" — a granular token scoped to specific packages cannot cover names
that do not exist yet, and these are unscoped names, so scoping by org does not
help either. Tighten it after the first release.

`--provenance` needs no extra secret — it uses the workflow's OIDC token — but it
**does** require `package.json`'s `repository.url` to match the repo the workflow
runs in. `build.py` derives that from `GITHUB_SERVER_URL` / `GITHUB_REPOSITORY`
at build time so it always matches; the hardcoded fallback is only used for local
builds.

*After* both names exist on npm you can switch to OIDC trusted publishing and
delete `NPM_TOKEN`. Configure the publisher per package on npmjs.com (pointing at
this workflow file and the `npm` environment), then in the `npm` job: drop
`NODE_AUTH_TOKEN`, drop `--provenance` (OIDC generates provenance
automatically), and bump `node-version` to `22` or later — trusted publishing
needs npm >= 11.5.1 / Node >= 22.14.0, and the pinned Node 20 ships npm 10.x.

## Using the npm package as a plugin source

Once the npm job is enabled and the packages are published, `marketplace.json`
can point at npm instead of (or alongside) the git source, which routes installs
through a counter:

```json
{
  "name": "flyte",
  "source": { "source": "npm", "package": "flyte-skills", "version": "^0.3.0" }
}
```

There is no `pip` plugin source type. The PyPI package instead ships an
installer CLI, and `flyte-skills emit-plugin` satisfies the `command` source
contract (print one absolute path to the plugin directory, exit 0):

```json
{
  "name": "flyte",
  "source": {
    "source": "command",
    "command": "uvx --from flyte-skills flyte-skills emit-plugin",
    "timeout": 120,
    "mode": "copy"
  }
}
```

Do not make that the only path — a `command` source runs a local program at
install time, so enterprise-managed settings block it, and it needs `uv` on the
machine.
