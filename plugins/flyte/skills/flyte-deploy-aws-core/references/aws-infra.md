# Shared AWS infrastructure for a Flyte v2 deploy (EKS + S3 + RDS + ALB)

Neither Flyte chart provisions infrastructure. Stand up four things first: **EKS cluster,
S3 bucket, PostgreSQL (RDS), and an ingress controller.** This file is chart-agnostic —
`flyte-deploy-aws` (flyte-binary) and `flyte-deploy-aws-core` (flyte-core) both use it.
Return to the calling skill's Step 5 once these are done.

> Replace every placeholder in angle brackets with your own values.

## Prerequisites

- CLIs: `aws` v2, **`eksctl` ≥ 0.227** (older caps out at k8s 1.29 — see gotcha 1), `kubectl`, `helm`, `jq`.
- **These commands assume bash word-splitting. macOS defaults to zsh, which does not split
  unquoted variables** — so `--subnet-ids $SUBNETS` (three tab-separated ids from
  `--output text`) arrives as **one** malformed argument and the call fails. Under zsh either
  run them in `bash`, or split explicitly with `${=SUBNETS}`. The failure is easy to miss in a
  long `&&` chain: everything before it succeeds, so the chain simply stops partway with one
  error scrolled off the top.
- Admin (or EKS+RDS+IAM+S3+EC2) creds. STS/SSO works — export the 3 env vars + region.
- eksctl writes the kubeconfig context (e.g. `<user>@flyte-v2.<region>.eksctl.io`). Pass
  `kubectl --context <ctx>` (and `helm --kube-context <ctx>`) per command rather than
  `kubectl config use-context` — that way you don't mutate the operator's current context.

**Persist your variables.** This deploy spans many commands and derives values you can't
recover later — most critically the **random `DBPW`** (Step 3), plus `ACCT`, `BUCKET`,
`RDS_HOST`, `IRSA_ARN`. If your shell resets (or the AWS session token expires and you
re-auth in a fresh shell), these are gone.

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
export AWS_DEFAULT_REGION=us-west-2
ENVF=~/flyte-deploy.env                                   # source this at every step
{ echo "export PREFIX=flyte-v2 REGION=us-west-2 CLUSTER=flyte-v2"
  echo "export ACCT=$(aws sts get-caller-identity --query Account --output text)"  # confirm the RIGHT account
} >> $ENVF && source $ENVF
# Check for an existing domain/cert (empty => go ALB HTTP-only):
aws route53 list-hosted-zones --query 'HostedZones[].Name' --output text
aws acm list-certificates --region $REGION --query 'CertificateSummaryList[].DomainName' --output text
```

## Step 0 — Reuse an existing cluster?

Before creating anything, list the EKS clusters already in the account/region and **ask the
user whether to deploy onto one of them or stand up a fresh cluster**. Reusing skips Step 1
(~15-20 min + the EKS control-plane + node cost).

```bash
aws eks list-clusters --region $REGION --query 'clusters' --output text
```

If they reuse one:

```bash
CLUSTER=<chosen-cluster>
aws eks update-kubeconfig --region $REGION --name $CLUSTER --alias $CLUSTER   # writes + selects context
kubectl --context $CLUSTER get nodes                                          # confirm reachable + Ready
# Confirm IRSA is possible (the chart needs an OIDC provider on the cluster):
aws eks describe-cluster --region $REGION --name $CLUSTER \
  --query 'cluster.identity.oidc.issuer' --output text   # empty => eksctl utils associate-iam-oidc-provider --cluster $CLUSTER --approve
```

Then **skip Step 1**. S3 (Step 2), RDS (Step 3), and the ALB controller (Step 4) may already
exist — check before recreating (`aws s3 ls`, `aws rds describe-db-instances`,
`kubectl -n kube-system get deploy aws-load-balancer-controller`) and reuse what's there.

## Step 0.5 — Confirm deployment parameters (ASK up front, never assume)

**Before provisioning or installing anything, gather the deploy parameters by ASKING the
user — do NOT silently reuse values you happen to find.** A previous deploy leaves identifiers
lying around (an old values file with `HOST=`/`certificate-arn`/`password`, a live
`*-console-oidc` k8s Secret, a memory of the last run). These are **suggestions to confirm,
not defaults.** Silently reusing the prior hostname, OIDC client ID/secret, or cert is the #1
way these skills do the wrong thing.

For each parameter, **discover any prior value, then present it as a choice** — e.g. "reuse
previous (`test.example.run`, loaded from the old values file), enter a new one, or pick a
different existing one". Restate the final set back to the user before `helm install`.

| Parameter | Where a prior value hides | Notes |
|---|---|---|
| Region / name prefix / cluster | Step 0, current kube-context | |
| Exposure (HTTP-only / TLS / TLS+SSO) | — | drives which params below apply |
| Hostname | old values file; existing Route53 record | drives cert, OIDC redirect URI, DNS |
| ACM cert ARN | old values `certificate-arn`; `aws acm list-certificates` | must match the chosen hostname |
| OIDC issuer / client ID / **client secret** | old values; `*-console-oidc` Secret; the IdP app | **never echo/ask for the secret in chat** — have the user create the Secret themselves |
| OIDC CLI/PKCE client ID | `authMetadata.flyteClient.clientId` in old values | |
| S3 bucket / RDS host+password | Step 2/3 outputs; old values | reuse the live infra's real values |

## Step 1 — EKS cluster (eksctl)

**This config has no `vpc:` block, which means eksctl builds its own**: a dedicated VPC, three
public + three private subnets across three AZs, an internet gateway, a NAT gateway, and the
`kubernetes.io/role/elb` / `internal-elb` subnet tags the ALB controller looks for. Everything
after this step depends on that — Step 3 finds the VPC by eksctl's own tag, and Step 4 hands
its id to the ALB controller.

> [!WARNING] Landing-zone accounts may not allow this
> In an AWS Control Tower / landing-zone account the account often ships with a pre-made VPC
> that has **no internet gateway and no NAT** (check: `aws ec2 describe-internet-gateways`,
> `describe-nat-gateways`, and whether the route tables hold anything but `local` and an S3
> endpoint). That VPC cannot pull images or front an internet-facing ALB.
>
> Letting eksctl build its own VPC sidesteps it entirely — the account's VPC just sits unused —
> **but only if the account's SCPs permit it.** Probe before provisioning anything; each of
> these creates and immediately deletes one resource:
> ```bash
> aws ec2 create-vpc --cidr-block 10.99.0.0/16 --query Vpc.VpcId --output text        # then delete-vpc
> aws ec2 create-internet-gateway --query InternetGateway.InternetGatewayId --output text  # then delete
> aws ec2 allocate-address --domain vpc --query AllocationId --output text            # NAT needs one; then release
> aws iam create-role --role-name probe --assume-role-policy-document '{"Version":"2012-10-17","Statement":[]}'
> ```
> An `explicit deny in a service control policy` on the IGW or address means no outbound path,
> so the deploy needs a private EKS cluster (VPC interface endpoints for ECR/EC2/STS/logs/ELB,
> an **internal** ALB reached over VPN or a bastion, and every image mirrored into this
> account's ECR) — a materially different deploy. A deny on `iam:CreateRole` means no IRSA;
> ask the org for that permission rather than working around it.

`cluster.yaml` — `iam.withOIDC: true` is what makes IRSA possible:

```yaml
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata: { name: flyte-v2, region: us-west-2, version: "1.33" }
iam: { withOIDC: true }
managedNodeGroups:
  - name: ng-default
    instanceType: m5.large
    desiredCapacity: 2
    minSize: 2
    maxSize: 3
    volumeSize: 50
    iam: { withAddonPolicies: { ebs: true } }
addons: [{name: vpc-cni},{name: coredns},{name: kube-proxy},{name: aws-ebs-csi-driver}]
```

```bash
eksctl create cluster -f cluster.yaml     # ~15-20 min; writes kubeconfig + sets context
kubectl get nodes                          # expect Ready
```

The VPC + private subnets exist within ~2 min (before the control plane finishes), so you can
start RDS (Step 3) in parallel.

> **Sizing note for flyte-core:** the split chart runs 8 component Deployments + console
> instead of 1 pod. Two `m5.large` nodes still fit the default single-replica layout, but
> check `kubectl get pods -n flyte` for `Pending` and scale `desiredCapacity` if you raise
> `replicaCount` on several components.

## Step 2 — S3 bucket + IRSA role

The `--namespace`/`--name` pair below must match the **Kubernetes ServiceAccount the chart
actually creates** — the two charts differ here, so take the SA name from the calling skill:

- flyte-binary: `serviceAccount.name: flyte` → `system:serviceaccount:flyte:flyte`
- flyte-core: default SA name is literally `service-account`; set `serviceAccount.name: flyte`
  in your values to match the command below.

```bash
BUCKET=$PREFIX-data-$ACCT       # account-id suffix => globally unique
aws s3api create-bucket --bucket $BUCKET --region $REGION \
  --create-bucket-configuration LocationConstraint=$REGION
aws s3api put-public-access-block --bucket $BUCKET --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket $BUCKET --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Scoped S3 policy: ListBucket on the bucket, Get/Put/Delete on its objects.
cat > s3-policy.json <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::$BUCKET"},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":"arn:aws:s3:::$BUCKET/*"}]}
EOF
POLICY_ARN=$(aws iam create-policy --policy-name $PREFIX-s3-access \
  --policy-document file://s3-policy.json --query Policy.Arn --output text)

# --role-only: create the IAM role with OIDC trust, but NOT the k8s SA (the chart creates
# + annotates it). Works before the namespace exists.
eksctl create iamserviceaccount --cluster $CLUSTER --region $REGION \
  --namespace flyte --name flyte --role-name $PREFIX-irsa \
  --attach-policy-arn "$POLICY_ARN" --role-only --approve
IRSA_ARN=$(aws iam get-role --role-name $PREFIX-irsa --query Role.Arn --output text)
echo "export BUCKET=$BUCKET IRSA_ARN=$IRSA_ARN" >> $ENVF
```

## Step 3 — RDS PostgreSQL (can run in parallel with Step 1)

```bash
VPC=$(aws ec2 describe-vpcs --region $REGION \
  --filters "Name=tag:alpha.eksctl.io/cluster-name,Values=$CLUSTER" --query 'Vpcs[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --region $REGION --filters "Name=vpc-id,Values=$VPC" \
  "Name=tag:kubernetes.io/role/internal-elb,Values=1" --query 'Subnets[].SubnetId' --output text)
aws rds create-db-subnet-group --region $REGION --db-subnet-group-name $PREFIX-db-subnets \
  --db-subnet-group-description "Flyte v2 private DB subnets" --subnet-ids $SUBNETS
RDSSG=$(aws ec2 create-security-group --region $REGION --group-name $PREFIX-rds-sg \
  --description "Flyte v2 RDS 5432 from cluster nodes" --vpc-id $VPC --query GroupId --output text)
DBPW=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 28)
echo "export DBPW='$DBPW' RDSSG=$RDSSG VPC=$VPC" >> $ENVF   # persist (DBPW is unrecoverable)
aws rds create-db-instance --region $REGION --db-instance-identifier $PREFIX-db \
  --engine postgres --db-instance-class db.t3.micro --allocated-storage 20 --storage-type gp3 \
  --master-username flyte --master-user-password "$DBPW" --db-name flyte \
  --vpc-security-group-ids $RDSSG --db-subnet-group-name $PREFIX-db-subnets \
  --no-publicly-accessible --backup-retention-period 1
RDS_HOST=$(aws rds describe-db-instances --region $REGION --db-instance-identifier $PREFIX-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)   # once status=available
echo "export RDS_HOST=$RDS_HOST" >> $ENVF
```

**Open 5432 from the nodes — do this once the nodegroup is up** (`kubectl get nodes` Ready),
not before: pod egress uses the **EKS-managed cluster SG on the nodes** (`eks-cluster-sg-*`),
NOT `ClusterSharedNodeSecurityGroup` (gotcha 2).

```bash
NODESG=$(aws ec2 describe-instances --region $REGION \
  --filters "Name=tag:eks:cluster-name,Values=$CLUSTER" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].SecurityGroups[?contains(GroupName,`eks-cluster-sg`)].GroupId' --output text)
[ -n "$NODESG" ] || { echo "no running nodes yet — wait for the nodegroup, then re-run"; }
aws ec2 authorize-security-group-ingress --region $REGION --group-id $RDSSG \
  --protocol tcp --port 5432 --source-group $NODESG   # init container retries until this lands
```

## Step 4 — AWS Load Balancer Controller (for ALB ingress)

```bash
# Use the policy matching the controller version the chart installs — currently v3.x.
curl -sL https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v3.4.0/docs/install/iam_policy.json -o alb-iam-policy.json
ALB_POLICY_ARN=$(aws iam create-policy --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://alb-iam-policy.json --query Policy.Arn --output text)
eksctl create iamserviceaccount --cluster $CLUSTER --region $REGION \
  --namespace kube-system --name aws-load-balancer-controller \
  --role-name $PREFIX-alb-controller --attach-policy-arn "$ALB_POLICY_ARN" --approve
helm repo add eks https://aws.github.io/eks-charts && helm repo update eks
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system \
  --set clusterName=$CLUSTER --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller --set region=$REGION --set vpcId=$VPC
kubectl -n kube-system rollout status deploy/aws-load-balancer-controller
```

If the controller image is newer than the policy you fetched, you'll see `AccessDenied` on
actions like `elasticloadbalancing:DescribeListenerAttributes`. Fix WITHOUT reinstalling:

```bash
curl -sL .../aws-load-balancer-controller/v<INSTALLED>/docs/install/iam_policy.json -o p.json
aws iam create-policy-version --policy-arn $ALB_POLICY_ARN --policy-document file://p.json --set-as-default
```

(Check version: `kubectl -n kube-system get deploy aws-load-balancer-controller -o jsonpath='{..image}'`.)

## Infrastructure gotchas

1. **eksctl too old → "unsupported Kubernetes version".** eksctl 0.175 only offers up to 1.29,
   but EKS has dropped 1.29 from standard support → CFN `ControlPlane` fails ~30s in and rolls
   back. Use eksctl ≥ 0.227; pin a supported version (1.33 worked). After a failed create,
   delete the `ROLLBACK_COMPLETE` stack before retrying.
2. **RDS unreachable: wrong source SG.** The pod stays `Init:0/1` (`wait-for-db ... no
   response`). EKS managed-nodegroup nodes run with the **EKS-managed cluster SG**
   (`eks-cluster-sg-<cluster>-*`), NOT `ClusterSharedNodeSecurityGroup`. Pod egress (VPC CNI
   secondary IPs on the primary ENI) uses the node-ENI SG. Authorize 5432 from the actual node
   SG. The init container retries on its own once the rule lands.
3. **ALB controller IAM lag.** The eks chart installs the latest controller (v3.x), which needs
   newer IAM actions than older policy JSON. Match `iam_policy.json` to the installed controller
   version (`create-policy-version --set-as-default`; no reinstall needed).
4. Postgres default major from RDS is fine (the charts need ≥12).

## Teardown

```bash
helm uninstall <release> -n flyte
kubectl delete ns flyte
eksctl delete cluster --name $CLUSTER --region $REGION      # also removes the VPC + NAT gateway
aws rds delete-db-instance --db-instance-identifier $PREFIX-db --skip-final-snapshot --region $REGION
aws s3 rm s3://$BUCKET --recursive && aws s3api delete-bucket --bucket $BUCKET --region $REGION
aws iam delete-policy --policy-arn $POLICY_ARN              # after roles detach
```

The NAT gateway and ALB bill by the hour whether or not anything runs — tear down when idle.
