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
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null
helm repo update >/dev/null
helm upgrade --install pg bitnami/postgresql -n "$NS" \
  --set auth.postgresPassword=flyte --set auth.database=flyte --wait --timeout 5m
helm upgrade --install minio bitnami/minio -n "$NS" \
  --set auth.rootUser=minio --set auth.rootPassword=miniostorage --wait --timeout 5m

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
