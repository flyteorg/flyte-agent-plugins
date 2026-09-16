---
name: deploy-flyte-core-kind
description: 'Deploy Flyte v2 on a local kind cluster with the SPLIT flyte-core chart and a locally built image — runs, actions, events, cache, dataproxy, secret, and executor each as their own Deployment, backed by in-cluster PostgreSQL + MinIO by default (Supabase / S3 / R2 optional) and reached through one Traefik origin. Nothing is pulled from a public registry and no cloud account is needed. Use when testing the flyte-core chart or a local build of the Flyte binary before taking it to EKS. Trigger words: "flyte-core on kind", "test the core chart locally", "local flyte image", "kind load", "split deployment locally".'
---

# Deploy flyte-core to a kind cluster with a local image

Stand up the **split** Flyte v2 deployment on [kind](https://kind.sigs.k8s.io/):
eight Deployments from the `flyte-core` chart, a throwaway in-cluster PostgreSQL
and MinIO, and an image built from the user's own checkout. For **evaluation and
chart development only** — no TLS, no auth, static credentials, `emptyDir`
storage that dies with the pod.

Pick this skill over its siblings when:

| Situation | Skill |
| --- | --- |
| Test the `flyte-core` chart, or a local build of the binary, on your laptop | **this skill** |
| Single-binary Flyte on kind with hosted PostgreSQL + S3/R2 | `deploy-flyte-kind` |
| Split `flyte-core` on real infrastructure (EKS + S3 + RDS) | `flyte-deploy-aws-core` |

> [!IMPORTANT] Why the image must be local
> Every component runs the same binary with a different `--component` flag
> (`args: [--component, runs, ...]`). That flag lives in `manager/cmd/` on the
> commit that introduced the chart. The chart's default image
> (`cr.flyte.org/flyteorg/flyte-binary-v2:latest`) is built from `main`, so until
> that commit merges the published image rejects the flag and **all seven
> components CrashLoopBackOff**. Build the image from the **same checkout as the
> chart** — this is not an optimization, it is the only way the chart runs today.

## Step 0: Prerequisites and the checkout

Need on PATH: `docker`, `kind`, `kubectl`, `helm`. Confirm each before starting.

The chart and the image both come from one Flyte checkout. Confirm
`charts/flyte-core/` exists in it:

```bash
ls charts/flyte-core/Chart.yaml
```

If it does not, the checkout predates the chart — check out the branch that
carries it (as of writing, `flyte-core` on `github.com/Sovietaced/flyte`; on
`flyteorg/flyte` `master` once merged). **Ask the user which checkout to use;
never guess a path or clone over an existing one.**

Check for an existing cluster before creating one:

```bash
kind get clusters
```

If a `flyte` cluster already exists, ask whether to reuse or recreate it. Reuse
is fine — but a cluster made with a plain `kind create cluster` has no host-port
mappings, and those **cannot be added after creation** (Step 1).

## Step 1: Create the kind cluster (skip if reusing)

Map host ports 80 and 443 to the Traefik NodePorts now, whether or not auth is
ever added:

```bash
kind create cluster --name flyte --config - <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080   # Traefik web (HTTP) nodePort
        hostPort: 80
        protocol: TCP
      - containerPort: 30443   # Traefik websecure (HTTPS) nodePort
        hostPort: 443
        protocol: TCP
      - containerPort: 30000   # image registry nodePort (task images)
        hostPort: 30000
        protocol: TCP
EOF

kubectl cluster-info --context kind-flyte
kubectl create namespace flyte
```

**Map 30000 even if task images are not on the agenda yet.** Adding it later means
deleting and recreating the cluster — see "Task images: the local registry".

The split deployment is eight pods rather than one. Docker Desktop's default VM
(2 CPU / 4 GB) is tight — **4 CPU / 8 GB** avoids pods sitting `Pending`. Check
`kubectl -n flyte get pods` for `Pending` before raising any `replicaCount`.

## Step 2: Build the image and load it into kind

From the root of the checkout from Step 0:

```bash
docker build -t flyte-binary-v2:local .
kind load docker-image flyte-binary-v2:local --name flyte
```

The Go build takes several minutes on a cold cache. `FLYTE_VERSION` is an
optional build arg — omit it. The `go mod download` layer pulls the whole module
graph, so on a slow or contended link it can die with
`net/http: TLS handshake timeout` — just run the build again, everything before
it is cached.

**Do not pass `--platform`.** The kind node is a container on the host, so it is
the host's architecture; a `--platform linux/amd64` build on Apple Silicon gives
every pod `exec format error`. (Cross-building is for the EKS path, not this one.)

Confirm the image is the right one **before** installing — the wrong binary is
the failure this whole skill exists to avoid, and it is invisible until seven
pods crashloop:

```bash
docker run --rm --entrypoint /usr/local/bin/flyte flyte-binary-v2:local --help | grep component
# --component string   component to run: all, runs, actions, ...   <= right checkout
docker exec flyte-control-plane crictl images | grep flyte-binary-v2
# docker.io/library/flyte-binary-v2   local   <= the node has it
```

No output from the first command means the checkout predates the split (Step 0).

## Step 3: Choose and deploy the dependencies

**Ask the user two questions before writing anything** (use `AskUserQuestion`,
one per choice), and lead with the in-cluster default — this skill's whole point
is a cluster that needs no accounts:

1. **PostgreSQL** — *in-cluster throwaway* (default), *Supabase*, or *another
   external/self-hosted PostgreSQL*?
2. **Object store** — *in-cluster MinIO* (default), *AWS S3*, or *Cloudflare R2*?

The two are independent; a hosted database with in-cluster MinIO is fine. Take
the default pair unless the user wants otherwise — everything below is written
for it, and the hosted variants are a substitution at the end of this step.

### Default: in-cluster PostgreSQL and MinIO

Throwaway dependencies, pinned upstream images, no Helm repos. Both use
`emptyDir`, so they die with the pod — that is the deal for a cluster this
disposable:

```bash
kubectl apply -n flyte -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pg
  labels: { app: pg }
spec:
  replicas: 1
  selector: { matchLabels: { app: pg } }
  template:
    metadata:
      labels: { app: pg }
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          env:
            - { name: POSTGRES_PASSWORD, value: flyte }
            - { name: POSTGRES_DB, value: flyte }
            - { name: PGDATA, value: /var/lib/postgresql/data/pgdata }
          ports: [{ containerPort: 5432 }]
          readinessProbe:
            exec: { command: ["pg_isready", "-U", "postgres"] }
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - { name: data, mountPath: /var/lib/postgresql/data }
      volumes:
        - { name: data, emptyDir: {} }
---
apiVersion: v1
kind: Service
metadata:
  name: pg-postgresql
spec:
  selector: { app: pg }
  ports: [{ port: 5432, targetPort: 5432 }]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  labels: { app: minio }
spec:
  replicas: 1
  selector: { matchLabels: { app: minio } }
  template:
    metadata:
      labels: { app: minio }
    spec:
      containers:
        - name: minio
          image: minio/minio:RELEASE.2025-04-08T15-41-24Z
          args: ["server", "/data", "--console-address", ":9001"]
          env:
            - { name: MINIO_ROOT_USER, value: minio }
            - { name: MINIO_ROOT_PASSWORD, value: miniostorage }
          ports: [{ containerPort: 9000 }, { containerPort: 9001 }]
          readinessProbe:
            httpGet: { path: /minio/health/ready, port: 9000 }
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - { name: data, mountPath: /data }
      volumes:
        - { name: data, emptyDir: {} }
---
apiVersion: v1
kind: Service
metadata:
  name: minio
spec:
  selector: { app: minio }
  ports:
    - { name: api, port: 9000, targetPort: 9000 }
    - { name: console, port: 9001, targetPort: 9001 }
EOF

kubectl rollout status -n flyte deploy/pg deploy/minio --timeout=5m
```

**Create the bucket — the chart does not.** Without it the control plane comes up
but every metadata write fails:

```bash
kubectl run mc --rm -i --restart=Never -n flyte --image=minio/mc:latest --command -- \
  sh -c "mc alias set m http://minio.flyte.svc.cluster.local:9000 minio miniostorage && mc mb -p m/flyte"
```

### If the user chose a hosted backend

Nothing is deployed into the cluster for these. **Collect the connection details
and the gotchas from `deploy-flyte-kind` Step 2 rather than re-deriving them** —
it covers Supabase's session-pooler requirement (the direct host is IPv6-only and
kind is not), the S3 fields, and the R2 account endpoint. **Never invent a host,
bucket, key, or password**; if something is missing, stop and ask for that field.

Then apply these substitutions in Step 5 and skip the matching pieces:

| Choice | Step 5 change | Also |
| --- | --- | --- |
| Hosted PostgreSQL | `configuration.database.postgres.*` → the collected values (`sslmode=require` for Supabase) | skip the `pg` manifest |
| S3 / R2 | `configuration.storage.providerConfig.s3.*` → real region, endpoint (R2 only), and keys | pre-create the bucket in that account |

With a hosted **object store**, also **delete the `signedUrl.stowConfigOverride`
block and the `FLYTE_AWS_ENDPOINT` env var** from the Step 5 values, and skip the
MinIO port-forward in Step 8. Those exist only because an in-cluster address means
nothing to the host; a real S3/R2 endpoint resolves from both sides, which is the
one thing the hosted path buys.

## Step 4: Build the chart dependency

`flyte-core` is **not in the Helm repo** — install it from the checkout:

```bash
cd charts/flyte-core
helm dependency build      # REQUIRED — Chart.yaml declares file://../flyteconnector
```

Skipping this fails every `helm template`/`install` with
`found in Chart.yaml, but missing in charts/ directory: flyteconnector`.

## Step 5: Write the values file

Write `values-kind-core.yaml` next to the chart. The chart has **no global image
key**, so a YAML anchor keeps the eight repetitions honest:

```yaml
# values-kind-core.yaml — flyte-core on kind, local image, in-cluster deps.
# DO NOT set nameOverride or fullnameOverride (see Gotchas).

localImage: &localImage
  repository: flyte-binary-v2
  tag: local
  pullPolicy: IfNotPresent      # NOT Always — the image exists only inside kind

h2cService: &h2c
  annotations:
    traefik.ingress.kubernetes.io/service.serversscheme: h2c

components:
  runs:      { image: *localImage, service: *h2c }
  actions:   { image: *localImage, service: *h2c }
  events:    { image: *localImage, service: *h2c }
  cache:     { image: *localImage, service: *h2c }
  dataproxy: { image: *localImage, service: *h2c }
  secret:    { image: *localImage, service: *h2c }
  executor:  { image: *localImage }          # no ingress route — no h2c needed
  app:       { enabled: false }              # requires Knative Serving

configuration:
  database:
    postgres:
      host: pg-postgresql.flyte.svc.cluster.local
      port: 5432
      dbname: flyte
      username: postgres
      password: flyte
      options: "sslmode=disable"

  storage:                           # in-cluster MinIO — swap for S3/R2 per Step 3
    metadataContainer: flyte
    provider: s3
    providerConfig:
      s3:
        region: us-east-1
        disableSSL: true
        v2Signing: true
        endpoint: http://minio.flyte.svc.cluster.local:9000
        authType: accesskey
        accessKey: minio
        secretKey: miniostorage

  runs:
    storagePrefix: s3://flyte        # default is a nonexistent s3://flyte-data

  coPilot:
    image:                           # baked into every task pod spec
      repository: flyte-binary-v2
      tag: local

  inline:
    storage:
      signedUrl:                     # in-cluster MinIO ONLY — drop this for S3/R2.
        stowConfigOverride:            # signs client URLs for an address the host can reach
          endpoint: http://localhost:9000
    plugins:
      k8s:
        default-env-vars:            # REPLACES the chart default — keep all three _U_* vars
          - _U_EP_OVERRIDE: "actions.flyte:8080"
          - _U_INSECURE: "true"
          - _U_USE_ACTIONS: "1"
          - FLYTE_AWS_ENDPOINT: "http://minio.flyte.svc.cluster.local:9000"
          - FLYTE_AWS_ACCESS_KEY_ID: "minio"
          - FLYTE_AWS_SECRET_ACCESS_KEY: "miniostorage"

ingress:
  create: true
  host: ""                           # empty => the rule matches any host
  ingressClassName: traefik
```

Three things in there are load-bearing:

- **`coPilot.image`** is separate from the eight component images. It is written
  into the task-pod spec, so leaving it at the public default makes *tasks* pull
  an image the node does not have while the control plane looks healthy.
- **`default-env-vars` replaces the chart default outright.** The three `_U_*`
  vars must be repeated or task→control-plane callbacks break.
  `_U_EP_OVERRIDE` points at the **actions** service here — that is the
  `flyte-core` default, not the `flyte-http:8090` of the single-binary chart.
- **`storagePrefix`** is distinct from `metadataContainer`. Leave it at its
  default and the API works while every task's input/output write 403s.
- **`storage.signedUrl.stowConfigOverride`** splits the endpoint the control
  plane reads and writes through from the one it *signs client URLs for* — see
  Step 8. Without it the SDK is handed a URL it cannot resolve.

Check the render before installing:

```bash
helm template flyte . -n flyte --include-crds -f values-kind-core.yaml | less
```

## Step 6: Install

```bash
helm install flyte . -n flyte -f values-kind-core.yaml
kubectl -n flyte get pods
```

Expect **eight** Deployments: `runs`, `actions`, `events`, `cache`, `dataproxy`,
`secret`, `executor`, `console`. Services carry the same bare names (`runs`,
`actions`, …) plus `executor-cache`.

```bash
kubectl -n flyte rollout status deploy/runs deploy/actions deploy/executor --timeout=5m
```

Troubleshooting, in the order these actually happen:

- **Everything `CrashLoopBackOff`, logs say `unknown flag: --component`** — the
  pods are running the published image, not yours. Check
  `kubectl -n flyte get deploy runs -o jsonpath='{..image}'`, and that the image
  was `kind load`ed into *this* cluster.
- **`ErrImagePull` / `ImagePullBackOff` on `flyte-binary-v2:local`** —
  `pullPolicy` is `Always` somewhere, or the load went to a different cluster.
- **Only `runs` and `cache` stuck `Init:0/1`** — those two are the only
  components with the `wait-for-database` init container. PostgreSQL is
  unreachable: `kubectl -n flyte logs deploy/runs -c wait-for-database`.
- **`exec format error`** — the image was cross-built for the wrong arch (Step 2).

## Step 7: One origin for the API and console

`flyte-binary` served everything on one port; **`flyte-core` splits the API across
seven services**, so there is nothing single to port-forward. The chart's Ingress
already carries the path→service map (`/flyteidl2.workflow.RunService` → `runs`,
`/flyteidl2.actions.ActionsService` → `actions`, and so on, plus `/v2` → console)
— it just needs a controller:

```bash
helm repo add traefik https://traefik.github.io/charts
helm repo update

helm install traefik traefik/traefik -n traefik --create-namespace \
  --kube-context kind-flyte \
  --set "service.type=NodePort" \
  --set "ports.web.nodePort=30080" \
  --set "ports.websecure.nodePort=30443"
```

The `serversscheme: h2c` annotation from Step 5 is what makes the Connect/gRPC
routes work: without it Traefik forwards to the backends over HTTP/1.1 and the
SDK's HTTP/2 calls fail while plain `curl` still looks fine.

Forward Traefik to 8080 so the run URLs the SDK prints resolve as-is:

```bash
kubectl -n traefik --context kind-flyte port-forward service/traefik 8080:80
```

- Console: `http://localhost:8080/v2`
- API: the same origin — `http://localhost:8080`

(The Step 1 host-port mapping also exposes both at `http://localhost/v2` with no
port-forward, but the printed run URLs say `:8080`.)

> [!NOTE] `helm upgrade` does not kill this port-forward
> Unlike the single-binary deploy, the forward targets Traefik, not a Flyte pod —
> rolling the components leaves it up.

## Step 8: Verify, and submit a run

```bash
curl -s -X POST \
  http://localhost:8080/flyteidl2.project.ProjectService/ListProjects \
  -H 'Content-Type: application/json' -d '{}'
```

JSON back (not a connection error, not a 404) means the ingress routing, `runs`,
and the database are all working. **A 404 means the request never matched an
ingress path** — check `kubectl -n flyte get ingress http -o yaml`.

To submit runs, the SDK needs the API **and** the object store. Ask the user
where their SDK config lives (the project-local `.flyte/config.yaml` wins over
`~/.flyte/config.yaml`) and whether to edit it or hand them the block:

```yaml
admin:
  endpoint: dns:///localhost:8080   # Traefik — API and console share this origin
  insecure: True
task:
  org: local
  domain: development
  project: flytesnacks
```

> [!IMPORTANT] The SDK uploads straight to MinIO, not through the API
> `CreateUploadLocation` hands the SDK a presigned URL and it PUTs at the object
> store itself. The URL carries whatever endpoint the control plane was
> configured with, and `host` sits inside `X-Amz-SignedHeaders` — so a URL naming
> the in-cluster address is both unresolvable from the host *and* unrewritable
> (changing it returns `SignatureDoesNotMatch`). An ingress cannot fix this: it
> changes where requests go, not what the control plane signed.
>
> The `signedUrl.stowConfigOverride` in the Step 5 values is what resolves it —
> the control plane keeps using `minio.flyte.svc.cluster.local:9000` for its own
> reads and writes, while client URLs get signed for `localhost:9000`. All that
> is left is to make that address real:
> ```bash
> kubectl -n flyte port-forward service/minio 9000:9000
> ```
> **None of this applies to a hosted S3/R2 backend** (Step 3): that endpoint
> resolves from inside and outside the cluster, so the signed URL works as
> handed over and there is no second port-forward.
> Verify before handing it back — the signed host is the thing that matters:
> ```bash
> curl -s -X POST http://localhost:8080/flyteidl2.dataproxy.DataProxyService/CreateUploadLocation \
>   -H 'Content-Type: application/json' \
>   -d '{"project":"flytesnacks","domain":"development","filename_root":"probe","filename":"p.txt","content_md5":"XUFAKrxLKna5cZ2REBfFkg=="}'
> # signedUrl must start http://localhost:9000/ — if it names the cluster DNS
> # address, the override did not reach the dataproxy config.
> ```
> This rewrites **every** signed URL, console download links included — correct
> for a laptop, wrong for anything in-cluster that consumes one. Without the
> override the fallback is to make the cluster name mean something locally
> (`kubectl port-forward` on the same port plus a
> `127.0.0.1 minio.flyte.svc.cluster.local` line in `/etc/hosts`), and backing
> the deployment with a real S3/R2 bucket (Step 3) avoids the whole question.

## Task images: the local registry

Skip this while tasks run on public images. The moment the SDK builds one, it
pushes to `localhost:30000` and the build dies with
`dial tcp [::1]:30000: i/o timeout`.

That address is not a guess by the user — `flyte/_image.py::_get_push_registry()`
resolves the push registry in this order: the `image.registry` from the init
config, then the ambient `image.registry` / `FLYTE_IMAGE_REGISTRY`, then **the
localhost registry (`localhost:30000`) if the configured endpoint contains
`localhost`**. Our endpoint is `dns:///localhost:8080`, so the SDK infers a devbox
and pushes at the devbox registry's NodePort — which this cluster does not have.

**Ask the user which they want** — the resolution order above is exactly the two
options, and a team that already has a registry usually wants to keep using it:

1. **A registry they already have** (ECR, GHCR, Docker Hub, an internal one) —
   default to this whenever they name one.
2. **An in-cluster throwaway registry** (below) — nothing to configure, nothing
   to clean up beyond the cluster, and no images left in a real account.

### Their own registry

Point the SDK at it and skip the rest of this section:

```bash
export FLYTE_IMAGE_REGISTRY=<account>.dkr.ecr.<region>.amazonaws.com/<repo>
```

(or `image.registry` in the Flyte config — the init-config value wins over the
env var). The user must be logged in for the push, and the **node pulls over the
internet**, so a private registry needs a pull secret. Task pods run as the
`default` ServiceAccount in the Flyte namespace with no `imagePullSecrets`, so
attach one there:

```bash
kubectl -n flyte create secret docker-registry regcred \
  --docker-server=<registry> --docker-username=<user> --docker-password=<token>
kubectl -n flyte patch serviceaccount default \
  -p '{"imagePullSecrets":[{"name":"regcred"}]}'
```

A public registry needs neither. Either way the images are real and outlive the
cluster — the point of choosing this over the throwaway.

### In-cluster throwaway registry

Give the SDK the registry it is already asking for:

```bash
kubectl apply -n flyte -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: registry
  labels: { app: registry }
spec:
  replicas: 1
  selector: { matchLabels: { app: registry } }
  template:
    metadata:
      labels: { app: registry }
    spec:
      containers:
        - name: registry
          image: registry:2
          ports: [{ containerPort: 5000 }]
          readinessProbe:
            httpGet: { path: /v2/, port: 5000 }
            initialDelaySeconds: 3
            periodSeconds: 5
          volumeMounts:
            - { name: data, mountPath: /var/lib/registry }
      volumes:
        - { name: data, emptyDir: {} }
---
apiVersion: v1
kind: Service
metadata:
  name: registry
spec:
  type: NodePort
  selector: { app: registry }
  ports:
    - { port: 5000, targetPort: 5000, nodePort: 30000 }
EOF
```

A NodePort is what makes both halves work off one address. Inside the node,
`localhost:30000` **is** the NodePort, so containerd pulls `localhost:30000/...`
with no registry configuration at all (it treats `localhost` as plain HTTP). The
Step 1 host-port mapping publishes that same NodePort out of the node container,
which is what lets the builder push to it.

> [!WARNING] `kubectl port-forward` does NOT work for this
> The builder runs inside the Docker VM, and `port-forward` listens on the user's
> machine — the VM's `localhost` is not the Mac's. A forward makes `curl` from a
> terminal succeed while `docker push` and the SDK both time out on `[::1]:30000`,
> which reads like a registry fault and is not one. The port has to be published
> from a container, which is exactly what the Step 1 mapping does.
>
> **On a cluster already created without the 30000 mapping**, publish the node's
> NodePort from a container instead of recreating everything:
> ```bash
> docker run -d --name kind-registry-proxy --network kind -p 30000:30000 \
>   --restart=unless-stopped alpine/socat \
>   tcp-listen:30000,fork,reuseaddr tcp-connect:flyte-control-plane:30000
> ```

Verify both directions before handing it back — pushing and pulling fail for
completely different reasons:

```bash
curl -s http://localhost:30000/v2/_catalog                      # registry reachable
docker pull alpine:3.20 && docker tag alpine:3.20 localhost:30000/probe:1
docker push localhost:30000/probe:1                             # host/VM -> registry
kubectl -n flyte run pulltest --image=localhost:30000/probe:1 --restart=Never \
  --command -- sh -c 'echo PULL_OK'                             # node -> registry
kubectl -n flyte logs pulltest && kubectl -n flyte delete pod pulltest
```

Task images land in this registry, not in the node's image store, so they do not
need `kind load` — only the server image from Step 2 does.

> [!WARNING] Recreating the cluster strands the SDK's image cache
> The SDK records every image it has verified in a local SQLite cache — the run
> directory's `.flyte/local-cache/cache.db`, else `~/.flyte/local-cache/cache.db`
> — keyed by endpoint + project + domain + repository + tag + arch. A throwaway
> registry dies with its cluster; that cache does not. The next run therefore
> sees a hit, **skips the build and push**, and the task pod fails to start with
> a message that points at the registry rather than the cache:
> ```
> failed to resolve reference "localhost:30000/flyte:<tag>": not found
> ```
> The endpoint is unchanged across a rebuild, so the cache key still matches.
> After recreating a cluster, drop the rows for the throwaway registry:
> ```bash
> sqlite3 .flyte/local-cache/cache.db \
>   "DELETE FROM image_cache WHERE image_uri LIKE 'localhost:30000/%'"
> ```
> The registry is the ground truth — `curl -s http://localhost:30000/v2/_catalog`
> shows what is really there. This does not apply to a registry of the user's own:
> those images outlive the cluster, which is exactly what the cache assumes.

## Iterating on the image

The point of this setup. After changing Go code:

```bash
docker build -t flyte-binary-v2:local .
kind load docker-image flyte-binary-v2:local --name flyte
kubectl -n flyte rollout restart deploy/runs deploy/actions deploy/events \
  deploy/cache deploy/dataproxy deploy/secret deploy/executor
```

The tag does not change, so nothing restarts on its own — the `rollout restart`
is what picks up the reloaded image.

**Keep every component on the same image.** `runs` and `cache` each run their own
migrations against the same database; restarting only one after a schema change
leaves the other reading a schema it does not know.

For chart-only changes, `helm upgrade` is enough — but **re-apply the CRD**, which
Helm installs on `install` and never touches on `upgrade`:

```bash
kubectl apply -f crds/flyte.org_taskactions.yaml
helm upgrade flyte . -n flyte -f values-kind-core.yaml
```

## Gotchas

1. **Never set `nameOverride` or `fullnameOverride`.** With no override the
   resources are named bare — `runs`, `actions`, `service-account` — and the
   chart's own defaults hardcode those names (`actionsService.url:
   http://actions:8080`). An override renames the Services but not the URLs, and
   the components silently fail to find each other.
2. **`pullPolicy: Always` defeats the whole setup.** It sends the kubelet to
   `cr.flyte.org` for a tag that only exists in the node's local store.
3. **The published image and this chart are not interchangeable right now.** Until
   the `--component` commit merges, the chart only runs an image built from the
   same tree (see Step 0).
4. **Digest pinning does not work with this chart.** The template is
   `printf "%s:%s" repository tag`, so a `repo@sha256:…` repository renders as
   `repo@sha256:…:tag`. Use an immutable tag.
5. **`emptyDir` everywhere.** Deleting the `pg` or `minio` pod loses the database
   and every artifact. That is deliberate for a throwaway cluster — do not point
   anything real at it.
6. **`components.app` needs Knative Serving**, which this skill does not install.
   Leave it disabled; the chart drops its ingress routes to match.

## Tear down

```bash
kind delete cluster --name flyte
docker rm -f kind-registry-proxy      # only if the socat retrofit was used
```

Deleting the cluster leaves nothing else behind — the registry, database, and
object store all lived inside it. **If a throwaway registry was used, clear the
SDK's image cache too** (see the warning in "Task images"), or the next cluster's
first run will skip the push and fail to pull. The socat container does survive, though: it
carries `--restart=unless-stopped`, so it comes back after a reboot and holds
port 30000 against the next cluster.

Then, if the MinIO hosts entry was added (the fallback path, not needed with the
`signedUrl` override), remove the `minio.flyte.svc.cluster.local` line from
`/etc/hosts`.
