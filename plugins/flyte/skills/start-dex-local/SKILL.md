---
name: start-dex-local
description: Deploy Dex as a local in-cluster OIDC provider (IdP stand-in) for a kind-based Flyte deployment, so oauth2-proxy can be tested with no cloud account or real users. Use when the user wants to stand up Dex locally for testing Flyte authentication. For local testing only — in-memory storage, static test passwords.
---

# Start a local IdP with Dex (for testing)

Replace the **external** OIDC provider (Okta, Google, …) that oauth2-proxy
expects with [Dex](https://dexidp.io/) running **inside the same kind cluster**,
so you can test the whole Flyte auth flow with no cloud account and no real
users.

This assumes a kind cluster with Flyte and Traefik already up (steps 1–6 of the
kind deployment / the `deploy-flyte-kind` skill's OIDC section), about to wire
oauth2-proxy. Deploy Dex first, then point oauth2-proxy at it.

> **For local testing only.** Dex here uses in-memory storage and a static test
> password baked into its config. Never use this configuration anywhere real.

## The issuer-URL constraint (why the setup looks the way it does)

OIDC requires the **issuer URL to be identical everywhere it's seen**:
- oauth2-proxy (in-cluster) reaches Dex over a Kubernetes service name.
- The browser reaches Dex to log in, and must land on the *same* issuer the
  token was minted for, or validation fails.

A service name (`dex.flyte.svc.cluster.local`) isn't resolvable from the
browser; a `localhost` URL isn't resolvable from inside the cluster. The fix:
serve Dex under the **same host as Flyte** (`flyte.local`) at a sub-path
(`/dex`), routed through Traefik. One URL — `http://flyte.local/dex` — works
from both sides.

## Step 0: Prerequisites

```bash
for t in kubectl helm; do command -v $t >/dev/null || echo "MISSING: $t"; done
kubectl --context kind-flyte -n traefik get deploy traefik >/dev/null 2>&1 || echo "MISSING: traefik"
kubectl --context kind-flyte -n flyte get svc flyte-http >/dev/null 2>&1 || echo "MISSING: flyte"
docker ps --filter name=flyte-control-plane --format '{{.Ports}}' | grep -q '80->30080' \
  || echo "MISSING: hostPort 80->30080 mapping (recreate the cluster — see deploy-flyte-kind Step 1)"
```

If anything is `MISSING`, stop. Flyte + Traefik must already be deployed, and the
cluster must have been created with the `hostPort: 80 → 30080` mapping — Dex's
issuer (`http://flyte.local/dex`) is unreachable from the browser without it, and
the mapping can't be added to an existing cluster. Also confirm `127.0.0.1
flyte.local` is in `/etc/hosts`.

## Step 1: Write the Dex config

Write `dex-config.yaml` in the working directory. The issuer is the
through-Traefik URL; the two static clients are oauth2-proxy (confidential, with
a secret) and the Flyte CLI (public, for SDK login). `staticPasswords` gives a
login with no external user store:

```yaml
# dex-config.yaml
issuer: http://flyte.local/dex

storage:
  type: memory

web:
  http: 0.0.0.0:5556

oauth2:
  skipApprovalScreen: true        # auto-approve, no consent screen in dev

staticClients:
  # oauth2-proxy — confidential client (matches the secret passed to oauth2-proxy)
  - id: oauth2-proxy
    name: oauth2-proxy
    secret: oauth2-proxy-secret
    redirectURIs:
      - 'http://flyte.local/oauth2/callback'
      - 'https://flyte.local/oauth2/callback'   # console opened over TLS (websecure)

  # Flyte CLI — public client for SDK/CLI PKCE login
  - id: flytectl
    name: 'Flyte CLI'
    public: true
    redirectURIs:
      - 'http://localhost:53593/callback'

enablePasswordDB: true
staticPasswords:
  # login: admin@example.com / password
  - email: "admin@example.com"
    username: "admin"
    userID: "08a8684b-db88-4b73-90a9-3cd1661f5466"
    # bcrypt hash of the literal string "password" — see the warning below
    hash: "$2a$10$wi77Jcsjw08l416Q4./OCu6qNvYMaNSvA3Jbo30QeyZAvq9b4BSRK"
```

**`hash` must be a complete 60-character bcrypt string.** Dex crashes
(`CrashLoopBackOff`) with `malformed bcrypt hash: hashedSecret too short` if it's
even one char short. The hash above is for `password` and is known-good — but
**verify length 60 before pasting** (`echo -n "$HASH" | wc -c`), a char lost in
transit looks fine and crashes Dex. To use a different password:

```bash
htpasswd -bnBC 10 "" 'your-password' | tr -d ':\n' | sed 's/^\$2y/\$2a/'
```

## Step 2: Deploy Dex

The Dex chart renders whatever you pass under its `config` value into a Secret and
mounts it as `config.yaml`. So nest the Step 1 config under a top-level `config:`
key in a values file and hand that to the chart — don't mount your own ConfigMap
volume (the chart already defines a `config` volume; adding another collides with
`Duplicate value: "config"`).

Write `dex-values.yaml` (the Step 1 YAML indented one level under `config:`):

```yaml
# dex-values.yaml
config:
  issuer: http://flyte.local/dex
  storage:
    type: memory
  web:
    http: 0.0.0.0:5556
  oauth2:
    skipApprovalScreen: true
  staticClients:
    - id: oauth2-proxy
      name: oauth2-proxy
      secret: oauth2-proxy-secret
      redirectURIs:
        - 'http://flyte.local/oauth2/callback'
        - 'https://flyte.local/oauth2/callback'   # console opened over TLS (websecure)
    - id: flytectl
      name: 'Flyte CLI'
      public: true
      redirectURIs:
        - 'http://localhost:53593/callback'
  enablePasswordDB: true
  staticPasswords:
    - email: "admin@example.com"
      username: "admin"
      userID: "08a8684b-db88-4b73-90a9-3cd1661f5466"
      hash: "$2a$10$wi77Jcsjw08l416Q4./OCu6qNvYMaNSvA3Jbo30QeyZAvq9b4BSRK"
```

```bash
helm repo add dex https://charts.dexidp.io
helm repo update

helm install dex dex/dex -n flyte --kube-context kind-flyte -f dex-values.yaml
```

Confirm Dex came up (if it `CrashLoopBackOff`s, check the logs — a bad `hash` is
the usual cause, see Step 1):

```bash
kubectl --context kind-flyte -n flyte rollout status deploy/dex
kubectl --context kind-flyte -n flyte get svc dex     # note the port (5556 by default)
```

## Step 3: Route the issuer path through Traefik

Apply an ingress so `http://flyte.local/dex` reaches the Dex service — this is
what makes the single issuer URL resolve from the browser:

```bash
kubectl --context kind-flyte apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dex
  namespace: flyte
spec:
  ingressClassName: traefik
  rules:
  - host: flyte.local
    http:
      paths:
      - path: /dex
        pathType: Prefix
        backend:
          service:
            name: dex
            port:
              number: 5556
EOF
```

Check discovery works through the host path (the URL oauth2-proxy will fetch):

```bash
curl -s http://flyte.local/dex/.well-known/openid-configuration | head
```

A JSON doc with `"issuer":"http://flyte.local/dex"` confirms Dex is reachable at
the issuer it advertises.

## Step 4: Point oauth2-proxy at Dex

Use these values for the oauth2-proxy install (instead of external-IdP
placeholders). If oauth2-proxy is already installed against a placeholder IdP,
`helm upgrade` it with these flags. The `hostAliases` setting is the one
addition Dex needs that an external IdP doesn't — see the warning below:

```bash
# Dex's issuer is flyte.local, which the pod can't otherwise resolve — point it at Traefik.
TRAEFIK_IP=$(kubectl -n traefik --context kind-flyte get svc traefik -o jsonpath='{.spec.clusterIP}')

helm install oauth2-proxy oauth2-proxy/oauth2-proxy -n flyte --kube-context kind-flyte \
  --set config.clientID='oauth2-proxy' \
  --set config.clientSecret='oauth2-proxy-secret' \
  --set config.cookieSecret="$(openssl rand -base64 32)" \
  --set extraArgs.provider=oidc \
  --set extraArgs.oidc-issuer-url='http://flyte.local/dex' \
  --set extraArgs.upstream='static://202' \
  --set extraArgs.reverse-proxy='true' \
  --set extraArgs.set-xauthrequest='true' \
  --set extraArgs.email-domain='*' \
  --set extraArgs.cookie-secure='false' \
  --set extraArgs.ssl-insecure-skip-verify='true' \
  --set "hostAliases[0].ip=$TRAEFIK_IP" \
  --set "hostAliases[0].hostnames[0]=flyte.local"   # resolve the issuer in-cluster
```

> **Why `hostAliases` is required for Dex.** Dex's issuer is `flyte.local`, a
> name that resolves on your host (via `/etc/hosts`) but **not inside the
> cluster** — CoreDNS doesn't know it, and it isn't a Kubernetes service name. So
> oauth2-proxy hangs on `Performing OIDC Discovery...` at startup and
> `CrashLoopBackOff`s. The `hostAliases` flag adds `flyte.local → Traefik's
> ClusterIP` to the pod's `/etc/hosts`, so `flyte.local/dex` resolves to the same
> issuer from both the pod and the browser, as OIDC requires. Quote the
> `hostAliases[0]...` args — in zsh the unquoted `[0]` is a glob and errors with
> `no matches found`. This pins the current ClusterIP; if Traefik's service is
> recreated with a new IP, `helm upgrade` with the new value.

Then continue with the rest of the oauth2-proxy wiring (the ForwardAuth
middlewares and the Flyte ingress) from the kind deployment guide.

## Step 5: Advertise Dex to the SDK/CLI

oauth2-proxy gates the **browser** path, but the SDK/CLI discover where to log in
from Flyte's auth metadata. Point it at Dex using the public `flytectl` client
from Step 1, then `helm upgrade flyte … -f values-local.yaml`. V2 has no auth
server of its own — it just advertises Dex:

```yaml
# add to values-local.yaml
flyte-core-components:
  runs:
    authMetadata:
      externalAuthServerBaseUrl: http://flyte.local/dex
      flyteClient:
        clientId: flytectl
        redirectUri: http://localhost:53593/callback
        scopes:
          - openid
          - profile
          - offline_access
```

This is the same `authMetadata` block as a real IdP — only the issuer URL points
at the in-cluster Dex.

## Step 6: Verify the flow

With Dex, oauth2-proxy, and the Flyte ingress all in place, check the flow from
the command line first. These use `curl --resolve` to point `flyte.local` at the
local Traefik node port, so they work **without** editing `/etc/hosts` (the
browser still needs the hosts entry):

```bash
# 1. The console is gated — an unauthenticated request is rejected by the auth middleware:
curl -s -o /dev/null -w "%{http_code}\n" --resolve flyte.local:80:127.0.0.1 \
  http://flyte.local/v2
# → 401   (oauth2-auth ForwardAuth rejects it; a browser is then redirected by
#          the oauth2-signin error middleware)

# 2. The sign-in page is served:
curl -s -o /dev/null -w "%{http_code}\n" --resolve flyte.local:80:127.0.0.1 \
  "http://flyte.local/oauth2/sign_in?rd=http://flyte.local/v2"
# → 200

# 3. Starting login redirects all the way to Dex's login page:
curl -s -o /dev/null -w "%{url_effective}\n" -L --max-redirs 5 \
  --resolve flyte.local:80:127.0.0.1 "http://flyte.local/oauth2/start?rd=http://flyte.local/v2"
# → http://flyte.local/dex/auth/local/login?...   (oauth2-proxy → Dex)
```

A raw `curl` to `/v2` returns `401`, not a `302` — Traefik's `oauth2-signin`
middleware turns the 401 into a sign-in redirect via its `errors` handler, which
a browser follows but `curl` shows raw. The 401 still confirms the request is
gated; checks 2 and 3 confirm the redirect itself.

### Add the hosts entry for browser access

The `curl --resolve` checks above bypass DNS, but a browser can't — it needs
`flyte.local` to resolve to the local Traefik node port. Editing `/etc/hosts`
needs sudo, so **have the user run it themselves** rather than running it for
them:

```bash
echo "127.0.0.1 flyte.local" | sudo tee -a /etc/hosts
```

First check whether it's already there (idempotent — don't add a duplicate):

```bash
grep -q "flyte.local" /etc/hosts && echo "present" || echo "absent"
```

- **`present`** → nothing to do, continue.
- **`absent`** → tell the user to run the `tee` line above (suggest they type it
  as `! echo "127.0.0.1 flyte.local" | sudo tee -a /etc/hosts` so it runs in this
  session), then **ask whether they've added it or want to skip for now.**
  - **Added** → re-run the `grep` to confirm it's present, then continue to the
    browser step.
  - **Skip** → that's fine; the deployment is complete and the `curl --resolve`
    checks already proved the flow. Note that browser login won't work until the
    entry is added, and stop here.

Don't reach for `127.0.0.1` as a workaround: Traefik has no route for that host
(404), and the OIDC issuer is minted as `flyte.local`, so login fails on an
issuer mismatch. The hostname must be `flyte.local` end to end.

Once the entry is present, open `http://flyte.local/v2` in a browser and log in
as **`admin@example.com` / `password`**. You should land in the console. The
`X-Auth-Request-Email` header Dex supplies flows through oauth2-proxy to Flyte
and populates `executed_by` on runs.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| oauth2-proxy `CrashLoopBackOff`, logs stuck on `Performing OIDC Discovery...` | The pod can't resolve `flyte.local` in-cluster. Confirm the `hostAliases` from Step 4 are set (`kubectl -n flyte get deploy oauth2-proxy -o jsonpath='{.spec.template.spec.hostAliases}'`) and point at Traefik's current ClusterIP. |
| oauth2-proxy `CrashLoopBackOff`, logs show `could not fetch .well-known` | oauth2-proxy can't reach the issuer. Confirm Step 3's curl returns the discovery doc and that `oidc-issuer-url` matches `issuer` in `dex-config.yaml` **exactly**. |
| Browser: `Unregistered redirect_uri` / `redirect_uri did not match` | The `oauth2-proxy` static client's `redirectURIs` must list the callback for the scheme you open the console with — `http://flyte.local/oauth2/callback` **and** `https://flyte.local/oauth2/callback` (opening `/v2` over TLS uses the `https` one). List both. |
| Login succeeds but loops back to sign-in | Issuer mismatch between what the browser saw and what oauth2-proxy validated. Both must be `http://flyte.local/dex` — not a service name, not `localhost`. |

## Tear down

```bash
helm uninstall dex -n flyte --kube-context kind-flyte
kubectl --context kind-flyte -n flyte delete ingress dex
```
