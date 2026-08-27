---
name: deploy-flyte-kind
description: Deploy a complete Flyte stack (flyte-binary + a hosted PostgreSQL + an object store) onto a kind cluster, running on the user's own machine or a DigitalOcean VM (droplet). PostgreSQL is hosted (Supabase or external); the object store is AWS S3 or Cloudflare R2. Use when the user wants to run Flyte on kind — either reusing an existing kind cluster or creating a new one. For evaluation only (no TLS/auth on the base deployment; optional OIDC auth via Traefik + oauth2-proxy is covered).
---

# Deploy Flyte to a kind cluster

Stand up Flyte on a [kind](https://kind.sigs.k8s.io/) cluster: the flyte-binary
plus a hosted PostgreSQL and an S3-compatible object store. For **evaluation
only** — no TLS, no auth, static credentials.

kind runs anywhere Docker runs, so the cluster can live on the user's **own
machine** (default) or a **DigitalOcean VM** (droplet) — the host is a choice
made in Step 0.

The PostgreSQL and object store are independent choices the user makes in Step 2:

- **PostgreSQL** — **Supabase** or another external/self-hosted PostgreSQL.
- **Object store** — **AWS S3** or **Cloudflare R2**.

Both are hosted; kind runs only the flyte-binary. The user supplies connection
details for each.

## Step 0: Choose the host, check prerequisites, and check for an existing cluster

**First, ask the user where kind should run** (use `AskUserQuestion`):

- **the user's own machine** (default), or
- a **DigitalOcean VM** (droplet) — the only cloud-VM host this skill supports.

Do **not** offer or hand-roll AWS EC2 or GCP VM setups; for a real cloud
deployment, point the user at the AWS deployment skill instead.

If the user picks the droplet, **every `kind`, `kubectl`, and `helm` command
below runs on the droplet** (over SSH) — only the SDK/CLI and browser run on the
user's own machine. Provision it and install the tools there first (needs a few
GB of headroom for kind, so ≥ 4 vCPU / 8 GB):

```bash
# create the droplet (dashboard or doctl)
doctl compute droplet create flyte-kind \
  --image ubuntu-24-04-x64 --size s-4vcpu-8gb --region nyc1 \
  --ssh-keys <your-ssh-key-id>

# SSH in and install Docker, kind, kubectl, helm ON the droplet
ssh root@<droplet-ip>
curl -fsSL https://get.docker.com | sh
curl -Lo /usr/local/bin/kind \
  https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64 \
  && chmod +x /usr/local/bin/kind
curl -Lo /usr/local/bin/kubectl \
  "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
  && chmod +x /usr/local/bin/kubectl
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

> [!WARNING] A cloud VM is exposed to the internet
> On a droplet the stack is reachable from the public internet. Restrict ports
> `80`, `443`, and `22` to the user's own IP with a
> [cloud firewall](https://docs.digitalocean.com/products/networking/firewalls/)
> while they evaluate.

Then verify the required tools **on whichever host runs kind** (run the check on
the droplet over SSH if that's the host), and decide whether to create a cluster
or reuse one:

```bash
for t in docker kind kubectl helm; do command -v $t >/dev/null || echo "MISSING: $t"; done
kind get clusters
```

- If any tool is `MISSING`, stop and tell the user to install it
  ([docker](https://docs.docker.com/get-docker/),
  [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation),
  [kubectl](https://kubernetes.io/docs/tasks/tools/),
  [helm](https://helm.sh/docs/intro/install/)).
Read the `kind get clusters` output literally — it is the exact list of existing
cluster names, one per line. Do **not** assume a `flyte` cluster exists because
this guide uses that name; only treat it as present if `flyte` appears verbatim
in the output. A line like `kind` is a cluster named `kind`, not `flyte`.

- **`flyte` is in the list** → reuse it: skip Step 1, use `--context kind-flyte`
  below.
- **`flyte` is not in the list** → create it in Step 1. (Don't silently reuse a
  differently-named cluster; if the user wants to reuse one, confirm its name
  and substitute it into `--context kind-<name>` everywhere below.)
- **No clusters at all** → create one in Step 1.

## Step 1: Create the kind cluster (skip if reusing)

Create the cluster with **two** host-port mappings. kind fixes a cluster's port
mappings **at creation time** — they can't be added later — so map them both now
regardless of whether auth is added:

- **`30080 → 80`** lets the **browser** reach the Traefik ingress (plain HTTP) used
  by the optional auth section at `http://flyte.local`.
- **`30443 → 443`** lets the **SDK/CLI** reach the Traefik ingress over **TLS** at
  `https://flyte.local`. The SDK only authenticates over HTTPS (see the SDK-auth
  part of the auth section), so this is required if the user enables auth *and*
  wants to submit runs from the SDK. Harmless otherwise.

```bash
kind create cluster --name flyte --config - <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080   # Traefik web (HTTP) nodePort (auth section)
        hostPort: 80           # reach the ingress at http://flyte.local
        protocol: TCP
      - containerPort: 30443   # Traefik websecure (HTTPS) nodePort — SDK auth
        hostPort: 443          # reach the TLS ingress at https://flyte.local
        protocol: TCP
EOF
```

Map both even if the user isn't sure about auth — they're harmless if auth is never
added. **If a plain `kind create cluster --name flyte` was already made without
these, delete it (`kind delete cluster --name flyte`) and recreate with the config
above** — they can't be added in place.

On a **DigitalOcean droplet** these mappings bind to the droplet's **public IP** —
so in the auth section `flyte.local` points at that IP instead of `127.0.0.1`, and
the two ports are open to the internet unless restricted by the cloud firewall (see
the warning in Step 0).

```bash
kubectl cluster-info --context kind-flyte
```

## Step 2: Choose and deploy dependencies (PostgreSQL + object store)

kind runs only the flyte-binary; the database and object store are hosted. **Before
writing the values file, ask the user two questions** (use the `AskUserQuestion`
tool — one question per choice, or one multi-part prompt):

1. **PostgreSQL** — *Supabase* or *another external/self-hosted PostgreSQL*?
2. **Object store** — *AWS S3* or *Cloudflare R2*?

Collect the connection details for each — the user can **type them or paste a
screenshot** of the relevant console page (Supabase Project Settings → Database; the
AWS S3 / Cloudflare R2 credentials page). Read the values out of the screenshot; if
anything required is missing or unreadable, ask for just that field. **Never invent
or guess a host, bucket name, key, or password** — if it isn't provided, stop and
ask. Required fields per choice are listed below.

Create the namespace:

```bash
kubectl create namespace flyte
```

### PostgreSQL

**Supabase** — nothing to install in the cluster. **Must use the session pooler, not
the direct connection** (see the warning below). Have the user open **Project Settings
→ Database → Connection string**, switch the tab to **Session pooler**, and type or
screenshot that string. Collect from it:

- host — `aws-<n>-<region>.pooler.supabase.com` (the pooler host, *not* `db.<ref>.supabase.co`)
- database name (Supabase default: `postgres`)
- username — `postgres.<project-ref>` (pooler username carries the project ref)
- password

Supabase requires TLS, so use `sslmode=require` in Step 3.

> [!WARNING] Why the session pooler, not the direct connection
> The direct host `db.<ref>.supabase.co` resolves to **IPv6 only**; kind is IPv4-only,
> so the Flyte pod can't reach it. `wait-for-db` still passes (it only probes the
> port via `pg_isready`), then Flyte crash-loops on `failed to connect`. The session
> pooler host has IPv4. Use port **`5432` (session)**, not `6543` (transaction) —
> Flyte's migrations need session semantics. **Read the host and username straight
> from the Session pooler tab; never reconstruct them** — a wrong region connects but
> is rejected with `tenant/user not found`, and the pooler username must be
> `postgres.<ref>`, not bare `postgres`.

**Reusing your own PostgreSQL** is also fine: take the same fields as Supabase. For
a DB on the host machine use `host.docker.internal` as the host. The database must
already exist.

### Object store

**AWS S3** — nothing to install. The user creates the bucket and an access key in
their AWS account; collect (type or screenshot):

- bucket name
- region (e.g. `us-east-1`)
- access key ID
- secret access key

**Cloudflare R2** — nothing to install. The user creates an R2 bucket and an R2 API
token in the Cloudflare dashboard; collect (type or screenshot):

- bucket name
- account endpoint (`https://<account-id>.r2.cloudflarestorage.com`)
- access key ID
- secret access key

Both endpoints are publicly resolvable, so no `signedURL` override is needed — the
SDK uploads code bundles straight to the bucket.

## Step 3: Write the values file

Assemble `values-local.yaml` from the `database` and `storage` blocks matching the
Step 2 choices. The skeleton:

```yaml
# values-local.yaml — local kind deployment
fullnameOverride: flyte

configuration:
  # << database block — Supabase/external below >>
  # << storage block — S3 or R2 below >>
  # << inline block — task-pod storage credentials + storagePrefix, REQUIRED (below) >>

serviceAccount:
  create: true
  annotations: {}

ingress:
  create: false
```

### Database block

**Supabase (or other external PostgreSQL)** — fill in the collected values. For
Supabase, host and username come from the **Session pooler** connection string:

```yaml
  database:
    postgres:
      host: aws-<n>-<region>.pooler.supabase.com   # session pooler host (has IPv4)
      port: 5432                        # session mode (not 6543 transaction mode)
      dbname: postgres                  # Supabase default
      username: postgres.<project-ref>  # pooler username carries the project ref
      password: <supabase-db-password>
      options: "sslmode=require"        # Supabase requires TLS
```

### Storage block

**AWS S3** — fill in the collected values:

```yaml
  storage:
    metadataContainer: <s3-bucket>
    userDataContainer: <s3-bucket>
    provider: s3
    providerConfig:
      s3:
        region: <bucket-region>
        authType: accesskey
        accessKey: <aws-access-key-id>
        secretKey: <aws-secret-access-key>
```

**Cloudflare R2** — fill in the collected values:

```yaml
  storage:
    metadataContainer: <r2-bucket>
    userDataContainer: <r2-bucket>
    provider: s3
    providerConfig:
      s3:
        endpoint: https://<account-id>.r2.cloudflarestorage.com
        region: auto                    # R2 ignores region; "auto" is conventional
        authType: accesskey
        accessKey: <r2-access-key-id>
        secretKey: <r2-secret-access-key>
        v2Signing: false
```

### Inline block — task-pod storage credentials + storagePrefix (required)

The `storage` block above configures only the **control plane**. Two more settings
are required for tasks to actually run — without them the API works but **every task
fails**:

- **Task pods get no object-store credentials.** The task-side SDK reads static
  credentials from the `FLYTE_AWS_ENDPOINT` / `FLYTE_AWS_ACCESS_KEY_ID` /
  `FLYTE_AWS_SECRET_ACCESS_KEY` env vars (`flyte/storage/_config.py`); with none set
  it falls back to the default AWS credential chain and probes the EC2 metadata
  endpoint, so tasks fail with
  `OSError: Generic S3 error: Error performing PUT http://169.254.169.254/latest/api/token`.
  The chart's `storage.*` values do **not** propagate to task pods — inject the vars
  via `plugins.k8s.default-env-vars`.
- **Task I/O goes to a nonexistent bucket.** `runs.storagePrefix` defaults to
  `s3://flyte-data`, so task input/output/`error.pb` writes fail with
  `403 Forbidden AccessDenied`. It is **distinct from**
  `metadataContainer`/`userDataContainer` (those only configure the control plane's
  dataproxy) — point it at the real bucket.

Add this under `configuration:`. **The `default-env-vars` list replaces the chart
default outright**, so the three `_U_*` control-plane vars must be repeated — dropping
them breaks task→control-plane callbacks:

```yaml
  inline:
    runs:
      storagePrefix: s3://<bucket>      # the SAME bucket as the storage block
    plugins:
      k8s:
        default-env-vars:               # replaces the chart default — keep all three _U_* vars
          - _U_EP_OVERRIDE: "flyte-http.flyte:8090"
          - _U_INSECURE: "true"
          - _U_USE_ACTIONS: "1"
          - FLYTE_AWS_ACCESS_KEY_ID: "<access-key-id>"
          - FLYTE_AWS_SECRET_ACCESS_KEY: "<secret-access-key>"
          # Cloudflare R2 only — task pods must also be told the endpoint:
          - FLYTE_AWS_ENDPOINT: "https://<account-id>.r2.cloudflarestorage.com"
```

For **AWS S3**, omit `FLYTE_AWS_ENDPOINT` and add the standard
`- AWS_REGION: "<bucket-region>"` instead (the SDK's object store reads the standard
AWS env vars for anything the `FLYTE_AWS_*` overrides don't cover).

## Step 4: Install Flyte

```bash
helm repo add flyteorg https://flyteorg.github.io/flyte
helm repo update
helm install flyte flyteorg/flyte-binary -n flyte -f values-local.yaml

kubectl -n flyte rollout status deploy/flyte
kubectl -n flyte get pods
```

If a pod is stuck in `Init`, the `wait-for-db` init container is blocking on
PostgreSQL — the DB isn't up yet, or the host/credentials are wrong. Check
`kubectl -n flyte logs <pod> -c wait-for-db`.

## Step 5: Verify access

Make the API reachable at `localhost:8090` on the machine where the SDK/CLI runs:

```bash
kubectl -n flyte port-forward service/flyte-http 8090:8090
```

**On a DigitalOcean droplet** the port-forward runs on the droplet, so tunnel it
back to the user's own machine over SSH — this one command starts the port-forward
on the droplet *and* exposes it at `localhost:8090` locally:

```bash
ssh -L 8090:localhost:8090 root@<droplet-ip> \
  kubectl -n flyte port-forward service/flyte-http 8090:8090
```

> [!NOTE] `helm upgrade` kills this port-forward
> Every `helm upgrade` rolls the flyte pod, which drops the `flyte-http`
> port-forward — the SDK then reports "Flyte system is currently unavailable."
> Restart the port-forward (and the SSH tunnel, on a droplet) after each upgrade.

In another terminal:

```bash
curl -s -X POST \
  http://localhost:8090/flyteidl2.project.ProjectService/ListProjects \
  -H 'Content-Type: application/json' -d '{}'
```

A JSON response (not a connection error) confirms Flyte is up and talking to
its database. The base deployment is done.

**To submit runs from the SDK**, point it at the API forward. **Ask the user where
their SDK config lives** — the SDK reads the project-local `.flyte/config.yaml` (the
run directory) before `~/.flyte/config.yaml` — **and whether to edit it for them or
just give them the block to apply themselves.** Use this config:

```yaml
admin:
  endpoint: dns:///localhost:8090   # the port-forwarded API — 8090, NOT 8080
  insecure: True                    # plain HTTP, no TLS
task:
  org: local
  domain: development
  project: flytesnacks
```

The code-bundle upload needs no second port-forward — the S3/R2 endpoint is
publicly resolvable, so the SDK uploads straight to the bucket.

**Two different ports are in play — don't conflate them.** The SDK talks to the
API on **`:8090`** (this port-forward), while the browser console lives on
**`:8080`** (Step 6). The run URL that `flyte run` prints
(`http://localhost:8080/v2/...`) is a **console** link — it only works once Step 6
is done; it is not the API endpoint, and pointing `admin.endpoint` at `:8080`
does not work.

## Step 6: Access the web console (no auth)

The base deployment leaves the console unreachable: port-forwarding
`flyte-console` directly serves only the SPA, whose frontend calls the API at the
**same origin** it was served from (`NEXT_PUBLIC_ADMIN_API_URL` is unset, so the
API base URL defaults to `/`) — those calls 404 and run pages load blank. The fix
is to put console + API behind **one origin** with Traefik.

Install Traefik (identical to step 1 of the auth section — if it's already
installed, skip this command):

```bash
helm repo add traefik https://traefik.github.io/charts
helm repo update

helm install traefik traefik/traefik -n traefik --create-namespace \
  --kube-context kind-flyte \
  --set "service.type=NodePort" \
  --set "ports.web.nodePort=30080" \
  --set "ports.websecure.nodePort=30443"
```

Route the two path groups to one origin — `flyteidl2.*` (the Connect API, over
h2c) to `flyte-http`, everything else to the console:

```bash
kubectl --context kind-flyte apply -f - <<'EOF'
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: flyte-api-noauth
  namespace: flyte
spec:
  entryPoints: [web]
  routes:
    - kind: Rule
      priority: 100
      match: PathPrefix(`/flyteidl2.`)
      services:
        - name: flyte-http
          port: 8090
          scheme: h2c        # gRPC/Connect over cleartext HTTP/2
---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: flyte-console-noauth
  namespace: flyte
spec:
  entryPoints: [web]
  routes:
    - kind: Rule
      priority: 10
      match: PathPrefix(`/`)
      services:
        - name: flyte-console
          port: 80
EOF
```

Then open the console:

- **Local machine** — forward Traefik to **8080** (this makes the
  `http://localhost:8080/v2/...` run URLs the SDK prints work as-is):
  ```bash
  kubectl -n traefik --context kind-flyte port-forward service/traefik 8080:80
  ```
  Open `http://localhost:8080/v2`. (Alternatively, the Step 1 host-port mapping
  already exposes Traefik at `http://localhost/v2` with no port-forward — but the
  SDK's printed run URLs still say `:8080`.)
- **DigitalOcean droplet** — the Step 1 mapping binds host port 80 on the
  droplet's public IP, so the console is directly at **`http://<droplet-ip>/v2`**
  (the Step 0 firewall scopes it to the user's IP). Or tunnel it:
  `ssh -N -L 8080:localhost:80 root@<droplet-ip>` → `http://localhost:8080/v2`.
  Note the SDK still prints run URLs as `http://localhost:8080/...` — swap
  `localhost:8080` for `<droplet-ip>` unless the tunnel is up.

These routes carry **no auth** — they're the evaluation-mode front door. If the
user later enables the auth section, **delete them first**
(`kubectl -n flyte delete ingressroute flyte-api-noauth flyte-console-noauth`);
they match any host at low priority and would otherwise bypass the OIDC gate.

Now **ask the user whether they want to add OIDC authentication.** The base
deployment has no auth — anyone with network access can reach the API. If they
say yes, do the "Add OIDC authentication via an ingress controller" section
below. If no, stop here.

## Optional extras

Only do these if the user asks.

- **Load a local image into kind** (custom task/Flyte image, no registry):
  ```bash
  kind load docker-image <your-image>:<tag> --name flyte
  ```
  Reference that exact `<image>:<tag>` in task config; `IfNotPresent` pull
  policy then uses the loaded image. On a **DigitalOcean droplet** the image must
  be in the droplet's Docker daemon first — build it there, or ship it from the
  user's machine with `docker save <image> | ssh root@<droplet-ip> docker load`.

## Add OIDC authentication via an ingress controller

Do this when the user opts in at the Step 6 prompt (or asks later). This adds
OIDC single sign-on at the edge, the kind equivalent of gating the cloud
console behind an ALB.

The pattern: run [Traefik](https://doc.traefik.io/traefik/) as the ingress
controller and delegate auth to
[oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/). Traefik
intercepts each request through a `ForwardAuth` middleware, asks oauth2-proxy
whether the caller is logged in, and redirects to the IdP if not. oauth2-proxy
is the auth proxy at the edge.

### First: choose the OIDC provider

oauth2-proxy needs an OIDC provider to validate against. **Ask the user which
they want** before installing anything:

- **External IdP** (Okta, Google, Auth0, …) — for a setup close to production.
  Requires a registered app with redirect URI `http://flyte.local/oauth2/callback`,
  and its **client ID** and **client secret**. If the user picks this but
  doesn't have those ready, stop — the rest won't work.
- **Dex (local, in-cluster)** — an IdP stand-in for testing, no cloud account
  or real users. If the user picks this, you'll deploy Dex via the
  **`start-dex-local` skill** after Traefik is up (step 2 below).

Steps 1 and 3–4 are the same either way; only step 2 (the provider) differs.

### 1. Install Traefik

**First confirm the cluster has the `hostPort: 80 → 30080` mapping from Step 1**
(`docker ps --filter name=flyte-control-plane --format '{{.Ports}}'` should show
`0.0.0.0:80->30080/tcp`). If it doesn't — e.g. the user reused a plain cluster —
`http://flyte.local` can't reach Traefik, and the mapping can't be added in
place. Stop and have the user recreate the cluster with the auth-ready config in
Step 1 (`kind delete cluster --name flyte`, then recreate). Warn that this wipes
all data. If the user also wants SDK auth, the cluster needs `hostPort: 443 →
30443` too (also from Step 1) — same recreate-if-missing rule.

Expose both entrypoints: `web` (HTTP, for the browser) and `websecure` (HTTPS,
for the SDK — the SDK only authenticates over TLS):

```bash
helm repo add traefik https://traefik.github.io/charts
helm repo update

helm install traefik traefik/traefik -n traefik --create-namespace \
  --kube-context kind-flyte \
  --set "service.type=NodePort" \
  --set "ports.web.nodePort=30080" \
  --set "ports.websecure.nodePort=30443"
```

Installs the `Middleware` CRD, registers a `traefik` IngressClass, and serves a
default self-signed cert on `websecure` — fine for the browser.

**If Traefik is already installed from Step 6**, skip the install but **delete
the no-auth routes** — they match any host at low priority and would bypass the
OIDC gate added below:

```bash
kubectl -n flyte --context kind-flyte delete ingressroute flyte-api-noauth flyte-console-noauth
```

#### Replace the default cert with one for `flyte.local` (only if SDK auth)

Skip this if the user only needs the browser console. The SDK rejects Traefik's
default cert for two reasons, hit in sequence if you only set `insecureSkipVerify`:

- Its SAN is `*.traefik.default`, so the hostname check fails with
  `certificate not valid for name "flyte.local"`. The SDK validates the SAN **even
  with `insecureSkipVerify`** (that flag relaxes CA trust, not the hostname).
- The SDK implements `insecureSkipVerify` by fetching the server's chain and
  **pinning it as the CA**. A bare self-signed leaf then fails with
  `CaUsedAsEndEntity` — rustls won't use a leaf as a CA.

The fix is a **two-tier chain**: a self-signed root CA signs a leaf carrying
`SAN=flyte.local`. Traefik serves `leaf + CA`; the SDK pins the root as CA.

```bash
# 1. Root CA
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout ca.key -out ca.crt -subj "/CN=flyte-local-ca" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
# 2. Leaf key + CSR
openssl req -nodes -newkey rsa:2048 -keyout leaf.key -out leaf.csr -subj "/CN=flyte.local"
# 3. CA signs the leaf (CA:FALSE, SAN=flyte.local, server auth)
openssl x509 -req -in leaf.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 3650 -out leaf.crt \
  -extfile <(printf "subjectAltName=DNS:flyte.local\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth")
# 4. Secret holds the full chain so Traefik serves both
cat leaf.crt ca.crt > fullchain.crt
kubectl --context kind-flyte -n traefik create secret tls flyte-local-tls \
  --cert=fullchain.crt --key=leaf.key
```

Point Traefik's cluster-wide default cert at it with a `TLSStore` named `default`
(the only name Traefik honours), then restart Traefik:

```bash
kubectl --context kind-flyte apply -f - <<'EOF'
apiVersion: traefik.io/v1alpha1
kind: TLSStore
metadata:
  name: default
  namespace: traefik
spec:
  defaultCertificate:
    secretName: flyte-local-tls
EOF
kubectl --context kind-flyte -n traefik rollout restart deploy/traefik
```

The cert still chains to a self-signed root the SDK doesn't trust, so the SDK
config in step 5 **still** sets `insecureSkipVerify`. To drop that entirely you'd
install `ca.crt` into each client's trust store, or use a publicly-resolvable
domain + a publicly-trusted cert (Traefik ACME / Let's Encrypt) — impossible for a
purely-local `flyte.local`.

### 2. Set up the provider + oauth2-proxy

**If the user chose Dex:** invoke the **`start-dex-local` skill** now (Traefik
is up, which it requires). That skill deploys Dex, routes its issuer through
Traefik, and installs oauth2-proxy already pointed at Dex
(`oidc-issuer-url=http://flyte.local/dex`). When it finishes, skip to step 3 —
the middlewares. (If the user also wants SDK auth, the three SDK Bearer flags
below must be added to that oauth2-proxy install too — `helm upgrade` it with
`--reuse-values` and the three `--set extraArgs.*` lines.)

**If the user chose an external IdP:** install oauth2-proxy yourself.
`set-xauthrequest` emits the `X-Auth-Request-*` headers Traefik forwards
downstream (these feed Flyte's `executed_by` run attribution); `reverse-proxy`
trusts the forwarded host/proto from Traefik. The last three flags let the
**SDK/CLI** authenticate too (not just the browser) — include them now if the
user wants SDK auth, so you don't have to upgrade later. Substitute the user's
IdP values for the `<...>` placeholders.

```bash
# Cookie secret MUST decode to 16/24/32 bytes — head -c 32 trims the base64
# string; a raw 44-char value fails with "cookie_secret must be 16, 24, or 32 bytes".
COOKIE_SECRET=$(openssl rand -base64 32 | head -c 32)

helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests
helm repo update

helm install oauth2-proxy oauth2-proxy/oauth2-proxy -n flyte \
  --kube-context kind-flyte \
  --set config.clientID='<oidc-client-id>' \
  --set config.clientSecret='<oidc-client-secret>' \
  --set config.cookieSecret="$COOKIE_SECRET" \
  --set extraArgs.provider=oidc \
  --set extraArgs.oidc-issuer-url='https://<your-idp>/oauth2/default' \
  --set extraArgs.upstream='static://202' \
  --set extraArgs.reverse-proxy='true' \
  --set extraArgs.set-xauthrequest='true' \
  --set extraArgs.email-domain='*' \
  --set extraArgs.cookie-secure='false' \    # local HTTP, not HTTPS
  --set extraArgs.skip-jwt-bearer-tokens='true' \      # accept SDK Bearer JWTs
  --set extraArgs.oidc-extra-audience='<public-client-id>' \  # SDK client's audience
  --set extraArgs.bearer-token-login-fallback='false'  # invalid token → 403, not HTML
```

The browser uses the session cookie; the SDK sends an `Authorization: Bearer`
JWT. `skip-jwt-bearer-tokens` verifies that JWT against the IdP's JWKS and passes
it through; `oidc-extra-audience` must be the **public client ID** the SDK uses
(the `flyteClient.clientId` advertised in `authMetadata`) — its tokens carry that
audience. The flag is **singular** (`oidc-extra-audience`); the plural form is not
a valid flag and crash-loops oauth2-proxy with `unknown flag`. Without these flags
the SDK is rejected and `flyte.run` fails the upload with `Unauthorized`.

### 3. Create the ForwardAuth middlewares

Two Traefik `Middleware` objects: one sends each request to oauth2-proxy for a
verdict and forwards the identity headers; the other catches the `401` an
unauthenticated request gets and redirects to the sign-in page. Apply with
`kubectl --context kind-flyte apply -f -`:

```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: oauth2-auth
  namespace: flyte
spec:
  forwardAuth:
    address: http://oauth2-proxy.flyte.svc.cluster.local/oauth2/auth
    trustForwardHeader: true
    authResponseHeaders:        # forwarded to Flyte; feed executed_by attribution
      - X-Auth-Request-User
      - X-Auth-Request-Email
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: oauth2-signin
  namespace: flyte
spec:
  errors:
    status:
      - "401"
    service:
      name: oauth2-proxy
      port: 80
    query: "/oauth2/sign_in?rd={url}"
```

### 4. Enable the Flyte ingress with the middlewares

Replace the `ingress.create: false` block in `values-local.yaml` with this. The
`router.middlewares` annotation chains both middlewares onto every route
(reference format `<namespace>-<name>@kubernetescrd`):

```yaml
ingress:
  create: true
  host: flyte.local                 # add "127.0.0.1 flyte.local" to /etc/hosts
  ingressClassName: traefik
  httpAnnotations:
    traefik.ingress.kubernetes.io/router.middlewares: flyte-oauth2-signin@kubernetescrd,flyte-oauth2-auth@kubernetescrd
```

Also apply a route that sends `/oauth2` to oauth2-proxy itself so the sign-in
redirect resolves:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: oauth2-proxy
  namespace: flyte
spec:
  ingressClassName: traefik
  rules:
  - host: flyte.local
    http:
      paths:
      - path: /oauth2
        pathType: Prefix
        backend:
          service:
            name: oauth2-proxy
            port:
              number: 80
```

For `executed_by` run attribution, add `identityHeaders` to `values-local.yaml` so
Flyte reads the headers oauth2-proxy forwards (`X-Auth-Request-*`), not ALB's
`X-Amzn-Oidc-*` defaults — otherwise `executed_by` is left unset:

```yaml
flyte-core-components:
  runs:
    identityHeaders:
      claimsJwtHeader: ""
      subjectHeader: X-Auth-Request-User
      emailHeader: X-Auth-Request-Email
```

Re-render Flyte:

```bash
helm upgrade flyte flyteorg/flyte-binary -n flyte --kube-context kind-flyte \
  -f values-local.yaml
```

Then add a hosts entry so the browser can resolve `flyte.local` to the local
Traefik node port. Editing `/etc/hosts` needs sudo, so **have the user run it**
rather than running it yourself. First check if it's already there:

```bash
grep -q "flyte.local" /etc/hosts && echo "present" || echo "absent"
```

- **`present`** → continue.
- **`absent`** → tell the user to run it (suggest `! echo "127.0.0.1
  flyte.local" | sudo tee -a /etc/hosts` so it runs in this session), then **ask
  whether they've added it or want to skip.** If added, re-run the `grep` to
  confirm, then continue. If skip, stop here — the deployment is complete, but
  browser login won't work until the entry exists. (Opening the console by raw
  IP is not a substitute: Traefik has no route for that host, and the OIDC issuer
  is `flyte.local`, so login fails on an issuer mismatch.)

**On a DigitalOcean droplet**, Traefik's node ports are bound to the droplet's
**public IP**, so point `flyte.local` there in the user's **own machine's**
`/etc/hosts` (not the droplet's) — `echo "<droplet-ip> flyte.local" | sudo tee -a
/etc/hosts`. Every other `flyte.local` reference (Dex issuer, redirect URIs, cert
SAN, ingress host) stays the same; only this mapping differs. Alternatively, point
a real DNS A record at the droplet and substitute that hostname everywhere.

Once present, open `http://flyte.local/v2` — Traefik bounces you through the IdP
and back into the console.

This gates the **browser** only.

#### Split the API and discovery paths off the browser middleware (required for SDK auth)

The same `oauth2-signin` redirect on **every** path breaks the SDK, so do this before
SDK auth. Two path groups need different handling (the cloud equivalent is the
three-ingress `ingress`/`apiJwtIngress`/`wellknownIngress` split):

- **Auth-discovery** (`AuthMetadataService`, `IdentityService`) — the SDK reads these
  *before* it has a token, so they must **bypass auth**. Gated, they return a
  `text/plain` 401 that ConnectRPC reports as `UNAVAILABLE` (`flyte.run` fails with
  "Service is unavailable"), and the SDK never starts login.
- **The `flyteidl2.*` API** — needs `oauth2-auth` (Bearer validation) but **not**
  `oauth2-signin`, so an unauthenticated call gets a clean gRPC 401 the SDK retries
  after login, not sign-in HTML.

Two higher-priority `IngressRoute`s (Traefik matches highest `priority` first):

```bash
kubectl --context kind-flyte apply -f - <<'EOF'
# Discovery — highest priority, NO middleware (= wellknownIngress).
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: flyte-auth-discovery
  namespace: flyte
spec:
  entryPoints: [web, websecure]
  routes:
    - kind: Rule
      priority: 300
      match: Host(`flyte.local`) && (PathPrefix(`/flyteidl2.auth.AuthMetadataService`) || PathPrefix(`/flyteidl2.auth.IdentityService`))
      services:
        - name: flyte-http
          port: 8090
          scheme: h2c        # gRPC over cleartext HTTP/2
---
# API — oauth2-auth only, no oauth2-signin (= apiJwtIngress).
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: flyte-api-bearer
  namespace: flyte
spec:
  entryPoints: [web, websecure]
  routes:
    - kind: Rule
      priority: 100
      match: Host(`flyte.local`) && PathPrefix(`/flyteidl2.`)
      middlewares:
        - name: oauth2-auth
      services:
        - name: flyte-http
          port: 8090
          scheme: h2c
EOF
```

Verify discovery returns JSON, not oauth2-proxy's 401:
```bash
curl -s -X POST --resolve flyte.local:443:127.0.0.1 -k \
  https://flyte.local/flyteidl2.auth.AuthMetadataService/GetPublicClientConfig \
  -H 'Content-Type: application/json' -d '{}' | head -c 120
# → {"clientId":"flytectl", ...}   (JSON, not "Unauthorized")
```

The `--resolve flyte.local:<port>:127.0.0.1` flags here (and in every other `curl`
below) assume the command runs on the host running kind. **On a DigitalOcean
droplet** that means running them in the SSH session, where `127.0.0.1` works
as-is; to run them from the user's own machine instead, substitute the droplet's
public IP for `127.0.0.1`.

### 5. Let the SDK/CLI authenticate (only if the user wants to submit runs)

The browser flow works over plain HTTP, but **the SDK does not**: it attaches its
auth interceptors only over **TLS**. With `insecure: True` it assumes "plaintext ⇒
no auth" and sends no token, so `flyte.run` fails the upload with `Unauthorized`
and no browser opens. Getting the SDK through auth needs the TLS pieces from above
(websecure on `30443`, the `443` mapping, and the three oauth2-proxy Bearer flags)
plus the SDK config below.

**Point the SDK at HTTPS.** The SDK reads the **project-local** `.flyte/config.yaml`
(the directory the run command is invoked from) *before* `~/.flyte/config.yaml`, so the
right file isn't always the home one. **Ask the user which config file applies, and
whether to edit it for them or just hand them the block to apply themselves** — don't
assume `~/.flyte/config.yaml`. Use this config:

```yaml
admin:
  endpoint: dns:///flyte.local        # must match SelectCluster's clusterEndpoint (no :443)
  insecure: False                     # TLS — the SDK only authenticates over TLS
  insecureSkipVerify: True            # accept the self-signed CA (camelCase! see below)
  authType: Pkce
task:
  org: local
  domain: development
  project: flytesnacks
```

**The key is camelCase `insecureSkipVerify`** — the SDK reads `admin.insecureSkipVerify`;
snake_case `insecure_skip_verify` is silently ignored, so the SDK keeps full verification
and fails on the self-signed cert.

The `endpoint` must match what `SelectCluster` returns, or the SDK builds a
separate per-cluster session for the upload that may skip auth. Check it:
```bash
curl -s -X POST --resolve flyte.local:443:127.0.0.1 -k \
  https://flyte.local/flyteidl2.cluster.ClusterService/SelectCluster \
  -H 'Content-Type: application/json' \
  -d '{"operation":"OPERATION_CREATE_UPLOAD_LOCATION","project":"flytesnacks","domain":"development","org":"local"}'
# → {"clusterEndpoint":"https://flyte.local"}  ⇒  endpoint: dns:///flyte.local  (no :443)
```

**If the IdP runs in-cluster (Dex):** an external IdP needs nothing more, but Dex
needs two fixes so Flyte's `GetOAuth2Metadata` (which fetches the IdP's discovery
doc to tell the SDK where to log in) succeeds:

- **DNS** — Flyte fetches `http://flyte.local/dex/...`, unresolvable in-cluster.
  Add `flyte.local → Traefik ClusterIP` to the Flyte pod:
  ```bash
  TRAEFIK_IP=$(kubectl -n traefik --context kind-flyte get svc traefik -o jsonpath='{.spec.clusterIP}')
  helm upgrade flyte flyteorg/flyte-binary -n flyte --kube-context kind-flyte -f values-local.yaml \
    --set "deployment.extraPodSpec.hostAliases[0].ip=$TRAEFIK_IP" \
    --set "deployment.extraPodSpec.hostAliases[0].hostnames[0]=flyte.local"
  ```
- **Discovery path** — Flyte fetches `/.well-known/oauth-authorization-server`
  (RFC 8414), but Dex only serves `/.well-known/openid-configuration` (→ 404).
  Same endpoints; rewrite at Traefik:
  ```bash
  kubectl --context kind-flyte apply -f - <<'EOF'
  apiVersion: traefik.io/v1alpha1
  kind: Middleware
  metadata:
    name: dex-wellknown-rewrite
    namespace: flyte
  spec:
    replacePathRegex:
      regex: ^/dex/\.well-known/oauth-authorization-server$
      replacement: /dex/.well-known/openid-configuration
  ---
  apiVersion: traefik.io/v1alpha1
  kind: IngressRoute
  metadata:
    name: dex-oauth-metadata
    namespace: flyte
  spec:
    entryPoints: [web, websecure]
    routes:
      - kind: Rule
        priority: 200
        match: Host(`flyte.local`) && Path(`/dex/.well-known/oauth-authorization-server`)
        middlewares:
          - name: dex-wellknown-rewrite
        services:
          - name: dex
            port: 5556
  EOF
  ```

Verify metadata resolves (should return JSON, not 404/timeout), then run an
example — `flyte.run` opens a browser to log in, then submits with the token:
```bash
curl -s -X POST --resolve flyte.local:443:127.0.0.1 -k \
  https://flyte.local/flyteidl2.auth.AuthMetadataService/GetOAuth2Metadata \
  -H 'Content-Type: application/json' -d '{}' | head -c 200
```

**First clear any stale SDK token from a previous cluster.** The SDK caches OAuth
tokens in the keyring (macOS Keychain), keyed by endpoint host — `kind delete
cluster` doesn't wipe them. Dex's `storage: memory` mints new signing keys on every
restart, so an old token fails signature check with `403 Forbidden` on
`SelectCluster` and **no browser opens**. Clear it after any cluster/Dex recreate:

```bash
# macOS; "not found" is fine. Linux: keyring del flyte.local access_token / refresh_token
for k in access_token refresh_token; do security delete-generic-password -s flyte.local -a "$k" 2>/dev/null; done
```

**SDK-auth troubleshooting:**
- Upload `Unauthorized`, **no browser** → SDK on plain HTTP. Use `insecure: False` + `https://flyte.local`.
- `Connection refused` to `https://flyte.local` → no TLS listener (websecure not exposed, or no `30443 → 443` mapping).
- 401 *after* a successful browser login → oauth2-proxy rejects the Bearer token; confirm `skip-jwt-bearer-tokens` + `oidc-extra-audience=<client-id>`; check its logs for `audience ... does not match`.
- `403 Forbidden` on `SelectCluster`, **no browser** (oauth2-proxy logs `failed to verify id token signature`) → stale cached token; Dex's in-memory keys changed on restart. Clear the keyring tokens (block above) and rerun.
- `GetOAuth2Metadata` 404 `oauth-authorization-server` → in-cluster IdP: well-known rewrite missing.
- `GetOAuth2Metadata` times out → in-cluster IdP: `hostAliases` missing on the Flyte pod.

## Enable app serving (optional — Knative + Kourier)

Flyte can host long-running **apps** (web services, dashboards, model servers —
deployed via the SDK), each published at `{name}-{project}-{domain}.<base-domain>`.
It's **off by default**: the binary always exposes `AppService`, but with no
controller behind it the console's Apps tab and any `flyteidl2.app.AppService/List`
call return `{"code":"unimplemented","message":"404 Not Found"}` until enabled.
Apps run as **Knative Services**, so Knative Serving + a Knative networking layer
(Kourier) must be installed first. Skip this section unless the user wants apps.
Official doc: https://www.union.ai/docs/v2/flyte/oss-deployment/app-serving/.

On kind there's no cloud load balancer and no real DNS, so this recipe uses
**[sslip.io](https://sslip.io) wildcard DNS** (any `X.127.0.0.1.sslip.io` resolves
to `127.0.0.1`; any `X.<droplet-ip>.sslip.io` to the droplet — `/etc/hosts` can't
do wildcards, and every app gets its own hostname) and routes app traffic through
**Traefik** on the existing host-port-80 mapping. It requires Traefik from Step 6
(or the auth section).

**1. Install Knative Serving + Kourier.** Pick a Knative release that supports the
cluster's k8s version (Knative supports only the most recent k8s minors — the
pinned version below may need bumping), and use the **same version** for serving
and net-kourier:

```bash
KV=knative-v1.22.1   # must support your k8s version; serving + net-kourier must match
kubectl --context kind-flyte apply -f https://github.com/knative/serving/releases/download/$KV/serving-crds.yaml
kubectl --context kind-flyte apply -f https://github.com/knative/serving/releases/download/$KV/serving-core.yaml
kubectl --context kind-flyte apply -f https://github.com/knative-extensions/net-kourier/releases/download/$KV/kourier.yaml
kubectl --context kind-flyte patch configmap/config-network -n knative-serving --type merge \
  -p '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'
kubectl --context kind-flyte wait --for=condition=Available deploy --all -n knative-serving --timeout=180s
kubectl --context kind-flyte wait --for=condition=Available deploy --all -n kourier-system --timeout=180s
```

If `kubectl apply` rejects the manifests, the Knative release is newer than the
cluster's k8s version supports — install an older one (serving + net-kourier
matched).

**2. Configure the apps domain.** Base domain = `127.0.0.1.sslip.io` locally, or
`<droplet-ip>.sslip.io` on a droplet. Drop the namespace from Knative's hostname
template so each app is a **single label** under the base domain (the default
`{{.Name}}.{{.Namespace}}.{{.Domain}}` is two labels):

```bash
BASE=127.0.0.1.sslip.io   # droplet: <droplet-ip>.sslip.io
kubectl --context kind-flyte patch configmap/config-domain -n knative-serving --type merge \
  -p "{\"data\":{\"$BASE\":\"\"}}"
kubectl --context kind-flyte patch configmap/config-network -n knative-serving --type merge \
  -p '{"data":{"domain-template":"{{.Name}}.{{.Domain}}"}}'
```

**3. Route app hostnames through Traefik.** Kourier's `kourier` Service is
`LoadBalancer` type, which stays `<pending>` forever on kind — switch it to
`ClusterIP` and front it with an IngressRoute that matches any sslip.io app host.
The higher priority (150) wins over the Step 6 no-auth routes for app hosts;
`localhost`/`flyte.local` traffic is untouched:

```bash
kubectl --context kind-flyte patch svc kourier -n kourier-system --type merge -p '{"spec":{"type":"ClusterIP"}}'
kubectl --context kind-flyte apply -f - <<EOF
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: kourier-apps
  namespace: kourier-system
spec:
  entryPoints: [web]
  routes:
    - kind: Rule
      priority: 150
      match: HostRegexp(\`^.+\.${BASE//./\\.}$\`)
      services:
        - name: kourier
          port: 80
EOF
```

**4. Enable the app controller in Flyte.** Add to `values-local.yaml` under the
existing `configuration.inline` block — `baseDomain` MUST equal the
`config-domain` from step 2:

```yaml
    internalApps:
      enabled: true
      baseDomain: 127.0.0.1.sslip.io   # droplet: <droplet-ip>.sslip.io
      scheme: http                     # plain HTTP through Traefik (evaluation)
      ingressAppsPort: 0               # apps ride host port 80; omit the port
```

```bash
helm upgrade flyte flyteorg/flyte-binary -n flyte --kube-context kind-flyte -f values-local.yaml
kubectl -n flyte --context kind-flyte rollout status deploy/flyte
```

The chart auto-grants the `serving.knative.dev` RBAC when `internalApps.enabled`.
The upgrade rolls the flyte pod, so **restart the `flyte-http` port-forward**
(Step 5) afterward.

**5. Verify.**

```bash
kubectl --context kind-flyte auth can-i create services.serving.knative.dev \
  --as=system:serviceaccount:flyte:flyte -n flyte          # => yes
# AppService now answers 200 + {} (NOT 404/unimplemented) — needs the Step 5 port-forward:
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  http://localhost:8090/flyteidl2.app.AppService/List \
  -H 'Content-Type: application/json' -d '{}'              # => 200
```

The console's Apps tab now loads. Deploy an app with the SDK and open
`http://<name>-<project>-<domain>.<base-domain>/` (sslip.io needs internet DNS;
on a droplet the Step 0 firewall scopes port 80 to the user's IP).

**Gotchas:** (a) Knative version too new for the k8s version → manifests rejected
on apply. (b) two-label app hostnames → confirm the single-label
`domain-template`. (c) `baseDomain` ≠ `config-domain` → the URLs Flyte advertises
don't match what Knative serves. (d) `List` still 404s after enabling → the
binary didn't roll; `kubectl -n flyte rollout restart deploy/flyte`. (e) apps are
**unauthenticated** — anyone who can reach port 80 can open them (locally that's
just the machine; on a droplet, whatever the firewall admits).

## Tear down

```bash
kind delete cluster --name flyte
```

Deletes the cluster and Flyte. **On a DigitalOcean droplet**, also destroy the
droplet so it stops billing:

```bash
doctl compute droplet delete flyte-kind
```

The hosted PostgreSQL and S3/R2 bucket are untouched — clean those up in their own
consoles.
