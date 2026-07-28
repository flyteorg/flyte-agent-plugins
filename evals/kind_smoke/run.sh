#!/usr/bin/env bash
# Real kind-in-Docker smoke test for the kind deploy skills (deploy-flyte-kind,
# start-dex-local). Runs on a PRIVILEGED GitHub Actions runner — NOT as a Flyte
# task (privileged DinD pods aren't assumed on the demo cluster).
#
# This is a coarse "does the skill's documented path actually stand up a cluster"
# check, independent of the LLM: it runs the canonical commands the skill teaches
# and asserts the flyte-binary pod becomes Ready. The trajectory tier separately
# judges whether the *agent* produces these steps.
#
# Requires: docker, kind, kubectl, helm on PATH. Env:
#   PG_CONN     external Postgres connection (defaults to an in-cluster throwaway)
#   OBJ_*       object-store creds (defaults to an in-cluster minio)
set -euo pipefail

CLUSTER="${KIND_CLUSTER:-flyte-smoke}"
NS="${FLYTE_NS:-flyte}"

cleanup() { kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> preflight"
for t in docker kind kubectl helm; do command -v "$t" >/dev/null || { echo "MISSING: $t"; exit 1; }; done

echo "==> create kind cluster with ingress port mappings (per deploy-flyte-kind Step 1)"
kind create cluster --name "$CLUSTER" --config - <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 80
        protocol: TCP
      - containerPort: 30443
        hostPort: 443
        protocol: TCP
EOF

echo "==> in-cluster minio + postgres (throwaway deps for the smoke test)"
# Plain pinned manifests with official upstream images instead of the Bitnami
# Helm charts: Bitnami deprecated its free image catalog (Aug 2025), so those
# charts now pull rolling ':latest' tags from a shrinking registry, which is
# slow/flaky on 2-CPU CI runners (minio was hitting 'context deadline
# exceeded'). These are throwaway deps — the skill itself uses external hosted
# Postgres + S3/R2 — so determinism matters more than fidelity here. The
# Postgres Service keeps the name 'pg-postgresql' the flyte-binary step wires to.
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n "$NS" -f - <<'EOF'
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
kubectl rollout status -n "$NS" deploy/pg --timeout=5m
kubectl rollout status -n "$NS" deploy/minio --timeout=5m

echo "==> install flyte-binary (per deploy-flyte-kind flyte-binary step)"
helm repo add flyteorg https://flyteorg.github.io/flyte >/dev/null
helm repo update >/dev/null
# NOTE: values wiring (db + storage endpoints) mirrors the skill; kept minimal here.
helm upgrade --install flyte-binary flyteorg/flyte-binary -n "$NS" \
  --set configuration.database.host="pg-postgresql.${NS}.svc.cluster.local" \
  --set configuration.database.password=flyte \
  --set configuration.storage.provider=s3 \
  --wait --timeout 10m || true

echo "==> assert flyte-binary pod is present"
kubectl get pods -n "$NS"
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=flyte-binary \
  -n "$NS" --timeout=5m

echo "SMOKE OK: flyte-binary is Ready on kind cluster '$CLUSTER'"
