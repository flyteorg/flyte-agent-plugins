---
name: flyte-deploy-aws-core
description: 'Use when deploying Flyte v2 on AWS with the SPLIT flyte-core chart — each service (runs, actions, events, cache, dataproxy, secret, executor, app) as its own independently scalable Deployment behind an ALB, on EKS + S3 + RDS. Choose this over flyte-deploy-aws when you need to scale services independently, isolate the executor, or run more than one replica of anything. Trigger words: "flyte-core", "split deployment", "distributed flyte", "scale flyte components", "flyte core chart on EKS".'
---

# Deploying Flyte v2 on AWS with the split `flyte-core` chart

`flyte-core` runs Flyte v2 as **eight independent Deployments** plus the console, instead of
the single unified pod that `flyte-binary` ships. Same image (`flyte-binary-v2`), same
`flyteidl2.*` Connect API — the binary just takes a `--component <name>` flag and starts only
that service.

```
flyte-binary                       flyte-core
┌───────────────────┐              ┌──────┐┌───────┐┌──────┐┌─────┐
│ runs actions      │              │ runs ││actions││events││cache│
│ events cache      │   ────►      └──────┘└───────┘└──────┘└─────┘
│ dataproxy secret  │              ┌─────────┐┌──────┐┌────────┐┌───┐
│ executor app      │              │dataproxy││secret││executor││app│
└───────────────────┘              └─────────┘└──────┘└────────┘└───┘
   scale vertically                   scale each one independently
```

## Which chart should you use?

| | `flyte-binary` (skill: `flyte-deploy-aws`) | `flyte-core` (this skill) |
|---|---|---|
| Pods | 1 + console | 8 + console |
| Scaling | vertical only | per-component `replicaCount` |
| Blast radius | one crash takes everything | executor crash doesn't drop the API |
| Chart source | published Helm repo (`flyte-binary`) | published Helm repo (`flyte-core`, `v2.x` — see Step 5) |
| Config keys | `flyte-core-components.*` | `configuration.*` |
| Operational cost | lowest | more pods, more nodes, more moving parts |

**Default to `flyte-binary` unless the user has a concrete reason to split.** Good reasons:
they need >1 replica of a specific service, they want the executor isolated from the API, or
they are testing the split topology itself. "It looks more production-grade" is not one —
`flyte-binary` is the supported path today and `flyte-core` is at chart version 0.1.0.

> ⚠️ **`flyte-core` is new and unreleased.** It is not on `flyteorg.github.io/flyte`, its
> chart version is `0.1.0`, and it carries the open issues in **Known chart issues** below.
> Tell the user this before starting. If they want the supported path, switch to
> `flyte-deploy-aws`.

## Step 0–4 — AWS infrastructure

Identical to the flyte-binary deploy. Follow **`references/aws-infra.md`** in this skill
directory: cluster reuse check, parameter confirmation, EKS, S3 + IRSA, RDS PostgreSQL, and
the AWS Load Balancer Controller. Come back here for Step 5.

Two things to carry forward from that file for this chart specifically:

- **ServiceAccount name.** `flyte-core`'s default SA name is literally `service-account`
  (`flyte-core.resourceName` with no prefix). The IRSA trust policy in Step 2 is written for
  `system:serviceaccount:flyte:flyte`, so set `serviceAccount.name: flyte` in your values —
  otherwise every S3 call fails with `AccessDenied` and nothing explains why.
- **Node sizing.** 8 Deployments + console at 1 replica each still fits two `m5.large`, but
  check for `Pending` pods before raising any `replicaCount`.

## Step 5 — Get the chart

```bash
helm repo add flyteorg https://flyteorg.github.io/flyte && helm repo update flyteorg
helm search repo flyteorg/flyte-core --versions | head
```

> [!WARNING] Two different charts share the name `flyte-core`
> The same index carries the **Flyte 1** chart under this name at `v1.16.x` — unrelated to
> this one, with a different values schema and a different topology. Semver puts `v2.x` on
> top, so an unpinned install currently lands on the split chart, but the two lines release
> independently and the description is the only thing that distinguishes them. **Pin the
> version** and check what you resolved:
> ```bash
> helm search repo flyteorg/flyte-core --versions | head -3
> # v2.0.45  Distributed Flyte 2 core services   <= this chart
> # v1.16.8  A Helm chart for Flyte core         <= Flyte 1, unrelated
> ```

**Installing from a git clone instead** (chart development, or a change not yet released)
needs one extra step, because only the packaged chart bundles its subchart:

```bash
git clone --branch main https://github.com/flyteorg/flyte && cd flyte/charts/flyte-core
helm dependency build      # REQUIRED from a clone — Chart.yaml declares file://../flyteconnector
```

Skipping it fails with `found in Chart.yaml, but missing in charts/ directory: flyteconnector`.

**Image tags.** Every component's image defaults to `cr.flyte.org/flyteorg/flyte-binary-v2:latest`
with `pullPolicy: IfNotPresent` — a floating tag and a pull policy that will happily keep a
stale node-cached layer.

> [!WARNING] `latest` is NOT the tag that tracks `main`
> The image workflow tags `nightly` on every push to `main` and `latest` only on a manual
> `workflow_dispatch`, so `latest` can lag `main` by an arbitrary amount — including missing
> the `--component` flag every component in this chart starts with. A component running an
> image without it exits on `unknown flag: --component`, and nothing in the pod events points
> at the tag. Verify whatever tag you choose before installing:
> ```bash
> docker run --rm --platform linux/amd64 --entrypoint /usr/local/bin/flyte \
>   cr.flyte.org/flyteorg/flyte-binary-v2:<tag> --help | grep component
> # --component string   component to run: all, runs, actions, ...
> ```
> `nightly` carries it. For a fixed deploy prefer the `sha-<full-sha>` tag the same workflow
> pushes — it is immutable, unlike both of the floating ones. There is **no global image key**;
set it per component (the values below do this). **Digest pinning does not work with this
chart** — the template is `printf "%s:%s" repository tag`, so a `repo@sha256:…` repository
renders as `repo@sha256:…:tag` and the pull fails. Pin an immutable tag instead (the
`core-<sha>` above), and note that `configuration.coPilot.image` is a ninth place to change.

> **Keep every component on the SAME image.** `runs` and `cache` each run their own DB
> migrations (`runs/migrations`, `cache_service/migrations`) against the same database. Mixed
> image versions across components means one migrates a schema another can't scan — see
> gotcha 5.

## Step 6 — `helm install flyte-core`

`values-eks-core.yaml` (ALB HTTP-only variant). Substitute `BUCKET`, `RDS_HOST`, `DBPW`,
`IRSA_ARN`, and the region before installing:

```bash
sed -i "s/BUCKET/$BUCKET/g; s/RDS_HOST/$RDS_HOST/; s/DBPW/$DBPW/; s#IRSA_ARN#$IRSA_ARN#; s/us-west-2/$REGION/g" values-eks-core.yaml
```

```yaml
# --- DO NOT set nameOverride or fullnameOverride: see Known chart issues #1 ---

serviceAccount:
  create: true
  name: flyte                                  # must match the IRSA trust policy from Step 2
  annotations: { eks.amazonaws.com/role-arn: IRSA_ARN }

components:
  runs:      { replicaCount: 1, image: { pullPolicy: Always } }
  actions:   { replicaCount: 1, image: { pullPolicy: Always } }
  events:    { replicaCount: 1, image: { pullPolicy: Always } }
  cache:     { replicaCount: 1, image: { pullPolicy: Always } }
  dataproxy: { replicaCount: 1, image: { pullPolicy: Always } }
  secret:    { replicaCount: 1, image: { pullPolicy: Always } }
  executor:  { replicaCount: 1, image: { pullPolicy: Always } }
  app:       { enabled: false }                # requires Knative Serving — see App serving

configuration:
  database:
    postgres:
      host: RDS_HOST
      port: 5432
      dbname: flyte
      username: flyte
      password: "DBPW"                         # written only into the generated Secret
      options: "sslmode=require"
  storage:
    metadataContainer: BUCKET
    provider: s3
    providerConfig:
      s3: { region: us-west-2, authType: iam }
  runs:
    storagePrefix: "s3://BUCKET"               # default is a nonexistent s3://flyte-data
  executor:
    defaultK8sServiceAccount: flyte            # task pods inherit S3 via IRSA

ingress:
  create: true
  host: ""                                     # empty => rule matches any host => reach by ALB DNS
  ingressClassName: alb
  httpAnnotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
    alb.ingress.kubernetes.io/healthcheck-path: /healthz
    alb.ingress.kubernetes.io/success-codes: "200-404"   # see "Mixed backends" below
```

```bash
helm install flyte . -n flyte --create-namespace -f values-eks-core.yaml --dry-run   # check
helm install flyte . -n flyte --create-namespace -f values-eks-core.yaml
kubectl -n flyte get pods
# runs/cache stuck Init:0/1 => wait-for-db can't reach RDS (aws-infra gotcha 2)
```

### Mixed backends behind one ALB — health checks

This is the biggest operational difference from `flyte-binary`. The http ingress fans out to
**seven or more different Services**, so the ALB creates a target group per Service, and
`healthcheck-path` on the Ingress applies to **all of them**.

- Every Flyte component serves `/healthz` and `/readyz` on its own port
  (`flytestdlib/app/app.go` registers them whenever `Port > 0`).
- The **console is a different image** and does not serve `/healthz`.

So a plain `healthcheck-path: /healthz` marks the console target group unhealthy. The
pragmatic fix is `success-codes: "200-404"` above — components answer 200, the console answers
404, both count as healthy. Verify after install rather than assuming:

```bash
ALB_ARN=$(aws elbv2 describe-load-balancers --region $REGION \
  --query "LoadBalancers[?contains(DNSName,'$(kubectl -n flyte get ing http -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' | cut -d. -f1)')].LoadBalancerArn" --output text)
for tg in $(aws elbv2 describe-target-groups --region $REGION --load-balancer-arn $ALB_ARN --query 'TargetGroups[].TargetGroupArn' --output text); do
  aws elbv2 describe-target-health --region $REGION --target-group-arn $tg \
    --query 'TargetHealthDescriptions[].TargetHealth.State' --output text
done   # expect healthy for every target group
```

If you would rather keep a strict `200`-only health check, give the console its own ingress
(`ingress.httpExtraPaths` plus a separate Ingress resource in the same ALB group) and drop
`/v2` from the shared one.

### CRD

`flyte-core` ships `taskactions.flyte.org` under **`templates/crds/`**, not the root `crds/`
directory Helm special-cases — so it is an ordinary template that `helm upgrade` reconciles
and `helm uninstall` deletes, exactly like `flyte-binary`. No manual re-apply step.

```bash
kubectl get crd taskactions.flyte.org -o jsonpath='{.status.conditions[?(@.type=="Established")].status}'   # => True
```

The flip side of not being in `crds/`: **`helm uninstall` takes the CRD with it**, and every
TaskAction along with it. Deleting the release on a cluster whose run history matters is
destructive in a way the `crds/` layout would have prevented.

## Step 7 — Verify

```bash
kubectl -n flyte get deploy    # 8 Deployments with the values above, all AVAILABLE:
                               #   runs actions events cache dataproxy secret executor console
                               #   (+ app when components.app.enabled=true)
kubectl -n flyte get pods      # all 1/1 Running — check EVERY pod, not just one
```

A green `helm install` proves nothing here: with eight Deployments, one can crashloop while
the ALB still serves. Check them all, then exercise the API:

```bash
ALB=$(kubectl -n flyte get ingress http -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl -s -X POST "http://$ALB/flyteidl2.project.ProjectService/ListProjects" \
  -H 'Content-Type: application/json' -d '{}'      # => JSON listing flytesnacks
curl -s -X POST "http://$ALB/flyteidl2.workflow.RunService/ListActions" \
  -H 'Content-Type: application/json' -d '{"project_id":{"domain":"development","name":"flytesnacks"}}'
curl -s -o /dev/null -w "%{http_code}\n" "http://$ALB/v2"    # => 200 (console)
```

ALB takes ~2-3 min after the address appears to pass health checks. Then run an actual
workflow — inter-service wiring is what this topology adds, and only a real run exercises it
(`runs → actions → executor → events/cache`, and the task pod calling back to `actions`).

The chart injects the task-pod callback env vars automatically
(`configuration.inline.plugins.k8s.default-env-vars` resolves `_U_EP_OVERRIDE` to the actions
Service via a chart helper), so the `host.docker.internal` failure mode from the flyte-binary
skill should not occur. Confirm on a live task pod:

```bash
kubectl -n flyte get pod <run>-a0-0 -o jsonpath='{..env[*].name}'    # expect _U_EP_OVERRIDE
```

## Scaling — the reason to use this chart

```yaml
components:
  runs:     { replicaCount: 3 }     # API-facing, stateless — scale for request volume
  actions:  { replicaCount: 2 }     # watches TaskActions
  dataproxy:{ replicaCount: 3 }     # data upload/download + log streaming
  executor: { replicaCount: 1 }     # see below
```

**`runs`, `events`, `cache`, `dataproxy`, `secret`, `app` are safe to scale horizontally** —
they are request handlers behind a Service.

**`executor` is different.** It runs a controller-runtime Manager. Scaling it past 1 replica
requires leader election, which the chart exposes but defaults off:

```yaml
configuration:
  executor:
    leaderElect: true       # REQUIRED before executor replicaCount > 1
```

Without it, multiple executors reconcile the same TaskActions and fight over pods. With it,
extra replicas are warm standbys, not extra throughput — raise
`configuration.executor.maxConcurrentReconciles` (default 512) for throughput instead.

**`actions` scaling is untested at the time of writing.** Each replica opens its own
TaskAction watch with its own buffer (`configuration.actions.watchBufferSize`,
`watchWorkers`). Verify against your workload before raising it in production.

## TLS on its own (do this before any SSO)

ALB `authenticate-oidc` only runs on an HTTPS listener and IdPs reject non-`https` redirect
URIs, so TLS is a hard prerequisite for SSO — but it is also worth doing alone, and it is a
`helm upgrade`, not a redeploy. **The ALB is reused**, so its DNS name does not change and
the record you create in step 4 survives later upgrades.

The certificate must live in the **Flyte account and the ALB's region**; the DNS zone may
live in **another account** — you then run steps 2 and 4 with that account's credentials and
everything else with the Flyte account's. Ask the user for the hostname; never invent one,
and in a shared company zone say which zone you are about to write to.

```bash
HOST=<chosen hostname>; ZONE=<hosted zone id>          # zone may be in another account
# 1. Flyte account — request the cert, then read the validation record it wants
CERT=$(aws acm request-certificate --region $REGION --domain-name $HOST \
  --validation-method DNS --query CertificateArn --output text)
aws acm describe-certificate --region $REGION --certificate-arn $CERT \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord'
# 2. DNS account — UPSERT that CNAME, then wait for ISSUED (usually 2-10 min)
aws route53 change-resource-record-sets --hosted-zone-id $ZONE --change-batch file://validate.json
aws acm describe-certificate --region $REGION --certificate-arn $CERT --query Certificate.Status
```

3. Add to the values and `helm upgrade` — `tls` is a **list of host groups**, and
   `ssl-redirect` needs `HTTP` to stay in `listen-ports` or port 80 has nothing to redirect
   *from*:

```yaml
ingress:
  host: <hostname>                  # no longer empty: the rule now matches this host only
  tls:
    - hosts: [<hostname>]
  httpAnnotations:
    alb.ingress.kubernetes.io/certificate-arn: <ACM_ARN>
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/ssl-redirect: "443"
```

4. **DNS account** — point the hostname at the ALB (a subdomain CNAME is fine cross-account;
   no alias-target dance):
   `CNAME <hostname> -> $(kubectl -n flyte get ingress http -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')`

5. Verify all three, not just the first:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://$HOST/v2                      # 200
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://$HOST/v2       # 301 -> https
curl -s -X POST https://$HOST/flyteidl2.project.ProjectService/ListProjects \
  -H 'Content-Type: application/json' -d '{}'                                  # JSON, over TLS
echo | openssl s_client -connect $HOST:443 -servername $HOST 2>/dev/null \
  | openssl x509 -noout -subject                                               # CN = $HOST
```

**Then fix the SDK config**, which is easy to forget because the API keeps answering `curl`:
`endpoint: dns:///<hostname>` (no `:80`) and `insecure: False`. Leaving `insecure: True`
against a TLS endpoint — or `False` against an HTTP-only one — fails at the *upload* step with
`InitializationError: Service is unavailable`, pointing at the DataProxy rather than at the
config.

## TLS, SSO, and the three ingresses

`flyte-core` ships the three-ingress auth split natively — the same pattern the flyte-binary
skill builds by hand:

| Ingress resource | values key | routes |
|---|---|---|
| `wellknown` | `ingress.wellknownIngress` | `/.well-known/oauth-authorization-server`, `AuthMetadataService` → runs |
| `api-jwt` | `ingress.apiJwtIngress` | all `flyteidl2.*` service paths → their own components |
| `http` | `ingress` (main) | console `/v2` + everything not claimed above |

Enable them, put all three in one ALB group ordered by precedence, on top of the TLS setup
above. (The `flyte-deploy-aws` TLS section covers the same ground for the binary chart,
including cross-account DNS.)

```yaml
ingress:
  create: true
  host: flyte.example.com
  ingressClassName: alb
  tls: [{ hosts: [flyte.example.com] }]
  httpAnnotations:
    alb.ingress.kubernetes.io/group.name: flyte
    alb.ingress.kubernetes.io/group.order: "-100"
    alb.ingress.kubernetes.io/certificate-arn: <ACM_ARN>
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP":80},{"HTTPS":443}]'
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/auth-type: oidc         # console SSO
    # ... auth-idp-oidc-config referencing the OIDC Secret
  apiJwtIngress:
    enabled: true
    annotations:
      alb.ingress.kubernetes.io/group.name: flyte
      alb.ingress.kubernetes.io/group.order: "-140"
      # ... certificate-arn, listen-ports, ssl-redirect
  wellknownIngress:
    enabled: true
    annotations:
      alb.ingress.kubernetes.io/group.name: flyte
      alb.ingress.kubernetes.io/group.order: "-150"
      # no auth — discovery must precede the token
configuration:
  runs:
    authMetadata:
      externalAuthServerBaseUrl: "https://<idp>/oauth2/default"
      flyteClient:
        clientId: <native-PKCE-app>
        redirectUri: http://localhost:53593/callback
        scopes: [openid, profile, offline_access]
```

> **The Bearer-match condition is per-Service, and this chart has many.** In `flyte-binary`
> the ALB `alb.ingress.kubernetes.io/conditions.<service>` annotation names one backend
> (`flyte-http`). Here `api-jwt` fans out to `runs`, `actions`, `events`, `cache`, `dataproxy`,
> `secret` (and `app` when enabled), so you need **one `conditions.<service>` key per backend
> Service** — six or seven of them, each matching `Authorization: Bearer*`. Miss one and that
> service's paths fall through to the cookie-auth ingress and 302 your CLI. Enumerate the
> backends from the rendered ingress before writing the annotations:
>
> ```bash
> kubectl -n flyte get ing api-jwt -o jsonpath='{.spec.rules[0].http.paths[*].backend.service.name}' | tr ' ' '\n' | sort -u
> ```

**Flyte does not validate tokens itself** — it trusts whatever reaches it. A Bearer-match
condition with no validation action leaves the API wide open. Pair it with ALB-native
`jwt-validation` against the IdP JWKS, exactly as in `flyte-deploy-aws`.

## App serving (`components.app`)

`components.app.enabled` is **false by default** because it needs Knative Serving in the
cluster. Install Knative + a networking layer (Kourier) first — see the App serving section of
`flyte-deploy-aws`, which is unchanged here — then flip it on. The `app` component runs both
`AppService` and `InternalAppService` in one process, so `configuration.app.internalAppService.url`
is overridden internally and setting it does nothing.

## Known chart issues (as of `flyte-core` 0.1.0)

Verified by rendering the chart and reading the Go config structs. Check whether they are fixed
before working around them.

1. **Do NOT set `nameOverride` or `fullnameOverride`.** Service names get the prefix, but the
   inter-service URLs in `configuration.*.{runService,actionsService,eventsService,cacheService}.url`
   are hardcoded bare names (`http://runs:8080`) and do not. Every cross-service call then fails
   DNS. The values are rendered with `toYaml`, not `tpl`, so you cannot template your way out —
   you would have to hand-write all six prefixed URLs. Just leave both overrides empty.
2. **Do NOT override `configuration.webhook.{certDir,secretName,serviceName,servicePort,localCert,secretManagerTypes,embeddedSecretManagerConfig}`.** The executor configmap hardcodes those
   keys and then splats all of `configuration.webhook` into the same YAML mapping, producing a
   **duplicate key**. `yaml.v3` rejects duplicates, so the executor fails to load its config and
   crashloops. `listenPort`, `cacheInvalidationPort`, and `webhookTimeout` are safe.
3. ~~Secret cache invalidation broken~~ — **fixed as of `v2.0.45`.** The chart used to write
   `secret.webhookURL` while the Go struct expects `secret.webhook.url`; values now carry
   `secret.webhook.url` templated to the executor cache service. On an older chart the symptom
   was silent: after updating a secret, task pods kept injecting the old value until the
   webhook cache TTL expired, with only a `Warnf` in the secret pod.
4. **`SettingsService` is not routed by the ingress.** `runs` mounts
   `flyteidl2.settings.SettingsService`, but it is missing from the chart's ingress route list,
   so those RPCs 404 at the ALB. In-cluster callers are unaffected. Add it via
   `ingress.httpExtraPaths.prepend` if you need it.
5. **Empty ingress paths.** With `console.enabled=false` and both `apiJwtIngress` and
   `wellknownIngress` enabled, the main http ingress renders with an empty `paths:` list and the
   whole install fails apiserver validation (`spec.rules[0].http.paths: Required value`). Keep
   the console enabled, or add an `ingress.httpExtraPaths.prepend` entry.
6. **`kubernetes.timeout: 30s` truncates long-lived streams.** It lands on `rest.Config.Timeout`,
   which becomes `http.Client.Timeout` and therefore applies to watches **and pod-log
   following**. Informers reconnect transparently, but users tailing task logs see the stream
   drop every 30s. Set `configuration.kubernetes.timeout: ""` if that matters more to you than
   bounding ordinary API calls.

## Gotchas

1. **`helm dependency build` is mandatory when installing from a git clone** — the chart
   declares a `file://../flyteconnector` dependency. The packaged chart from the Helm repo
   bundles it, so this does not apply there.
2. **Check every pod, not just one.** Eight Deployments means eight ways to be half-up. A `200`
   from the console and a green `helm install` do not prove the API works.
3. **Default `storagePrefix` is fake.** `configuration.runs.storagePrefix` defaults to
   `s3://flyte-data`. Override it or run I/O fails. Note the key moved: this is
   `configuration.runs.*` here, not `flyte-core-components.runs.*` as in `flyte-binary`.
4. **Default ServiceAccount is named `service-account`.** Set `serviceAccount.name: flyte` to
   match the IRSA role, or every S3 operation returns `AccessDenied`.
5. **Schema/image skew across components.** `runs` and `cache` migrate the shared database
   independently. If they run different image versions, one can migrate a schema the other
   cannot scan — the symptom is `missing destination name <col> in *[]*models.Action` on
   `ListActions`/`ListRuns` while the install looks green. Keep all eight components on one tag
   or digest. On a fresh/disposable DB the fix is to reset the schema and let a single image
   version re-migrate:
   ```bash
   kubectl -n flyte scale deploy/runs deploy/cache --replicas=0
   kubectl -n flyte run pg --rm -i --restart=Never --image=postgres:16 \
     --env PGPASSWORD=<pw> --command -- psql "host=<rds> user=flyte dbname=flyte sslmode=require" \
     -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO flyte;"
   kubectl -n flyte scale deploy/runs deploy/cache --replicas=1
   ```
6. **Config lives in one ConfigMap per component**, each with a checksum annotation on its
   Deployment. Changing a shared value (`configuration.kubernetes`, `configuration.storage`)
   rolls **every** component at once — expect a fleet-wide restart on such an upgrade, and
   stage it accordingly.
7. **`configuration.externalConfigMap` / `externalSecretRef` replace ALL generated config.**
   If you set either, the external config must carry every component's service URLs plus
   database and storage settings — the chart stops generating them entirely.

## Cost

Same infrastructure as `flyte-deploy-aws` (~290–310 USD/mo for 2× `m5.large` + `db.t3.micro` +
1 ALB in us-west-2; see that skill's cost dashboard and show it to the user after a successful
deploy; that figure omits the **NAT gateway eksctl creates, ~32 USD/mo plus data processing**).
`flyte-core` adds no AWS resources — one ALB still fronts everything — but the extra
pods raise the node floor. If you scale several components past one replica, expect to add
nodes, which is where the marginal cost lands (~70 USD/mo per `m5.large`).

## Teardown

See `references/aws-infra.md`. One `flyte-core` difference: `helm uninstall` leaves
`taskactions.flyte.org` behind (Helm never deletes from `crds/`). Remove it explicitly only
once you are sure no other Flyte release in the cluster needs it:

```bash
kubectl delete crd taskactions.flyte.org     # deletes ALL TaskAction CRs cluster-wide
```
