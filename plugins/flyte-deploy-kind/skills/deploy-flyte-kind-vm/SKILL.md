---
name: deploy-flyte-kind-vm
description: Deploy Flyte on a kind cluster onto any host — your local machine, or a fresh cloud VM (DigitalOcean, AWS EC2, or GCP Compute Engine). Provisions the VM (firewall scoped to your IP), installs Docker/kind/kubectl/helm, then runs the kind Flyte deploy on that host and tunnels access back to your machine. Use when the user wants Flyte-on-kind but hasn't decided where to run it, or wants it on a cloud VM rather than locally. For evaluation only (single-node kind, static credentials). Delegates the Flyte install itself to the deploy-flyte-kind skill.
---

# Deploy Flyte on kind — local machine or a cloud VM

kind runs anywhere Docker runs, so the same Flyte-on-kind deploy works on your
own machine **or** on a cloud VM. This skill picks the **host**, provisions it if
it's a cloud VM, installs the prerequisites, and then runs the actual Flyte
deploy — the cluster, the hosted PostgreSQL + object store, the helm install, and
optional auth — by handing off to the **`deploy-flyte-kind`** skill. The only
things that change per host are *where the commands run* and *how you reach the
API afterward*.

> **For evaluation only.** Single-node kind, static credentials, no workload
> identity. On a cloud VM the stack is reachable from the public internet, so the
> provisioning steps below **restrict inbound 80/443 (and 22) to your own IP**.
> For production, use the `flyte-deploy-aws` skill instead.

This skill is guided: several steps need **human-in-the-loop** input — which host,
confirming billable VM creation, SSH keys, and (in the deploy hand-off) the
Supabase / R2 / S3 credentials. Ask; never invent account IDs, IPs, keys, or
passwords.

## Step 0: Choose the host

Ask the user where to run the cluster (use `AskUserQuestion`):

- **Local machine** — kind runs in your local Docker. Simplest; nothing to
  provision.
- **DigitalOcean** — a Droplet, provisioned with `doctl`.
- **AWS EC2** — an instance, provisioned with the `aws` CLI.
- **GCP Compute Engine** — an instance, provisioned with `gcloud`.

Then:

- **Local machine** → skip to **Step 3** (nothing to provision). The whole deploy
  runs locally.
- **A cloud VM** → do **Step 1** (provision) and **Step 2** (define how remote
  commands run), then Step 3.

kind needs a few GB of headroom, so any VM should be **at least 4 vCPU / 8 GB**.

## Step 1: Provision the cloud VM (skip for local)

First confirm the provider CLI is installed and authenticated locally, since these
commands run on **your** machine:

```bash
# DigitalOcean
command -v doctl >/dev/null && doctl account get >/dev/null 2>&1 || echo "doctl: install and run 'doctl auth init'"
# AWS
command -v aws   >/dev/null && aws sts get-caller-identity >/dev/null 2>&1 || echo "aws: install and configure credentials"
# GCP
command -v gcloud >/dev/null && gcloud auth list >/dev/null 2>&1 || echo "gcloud: install and run 'gcloud auth login'"
```

If the CLI is missing or unauthenticated, stop and have the user set it up (an
interactive login like `gcloud auth login` is easiest run by the user — suggest
they type `! gcloud auth login` so it runs in this session). **Creating a VM
incurs cost — confirm with the user before running any `create`/`run-instances`
command,** and ask for the values it needs (SSH key ID / key-pair name / zone).

Pick the tab for the chosen provider. Each: create a firewall/security rule
scoped to the user's IP, create the VM, SSH in, install Docker + kind + kubectl +
helm.

### DigitalOcean

```bash
# Create the Droplet (ask the user for their SSH key ID: `doctl compute ssh-key list`)
doctl compute droplet create flyte-kind \
  --image ubuntu-24-04-x64 --size s-4vcpu-8gb --region nyc1 \
  --ssh-keys <your-ssh-key-id>
```

Scope inbound 22/80/443 to your own IP with a cloud firewall (do this before
exposing anything — see the evaluation-only note). Then SSH in and install the
tools (DigitalOcean's Ubuntu image logs in as `root`, so no `sudo` needed):

```bash
ssh root@<droplet-ip> 'bash -s' <<'EOF'
curl -fsSL https://get.docker.com | sh
curl -Lo /usr/local/bin/kind https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64 && chmod +x /usr/local/bin/kind
curl -Lo /usr/local/bin/kubectl "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x /usr/local/bin/kubectl
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
EOF
```

### AWS EC2

Create a security group that admits **only your IP** on 22/80/443, then launch the
instance with the current Ubuntu 24.04 AMI:

```bash
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 create-security-group --group-name flyte-kind --description "Flyte kind evaluation"
for port in 22 80 443; do
  aws ec2 authorize-security-group-ingress --group-name flyte-kind \
    --protocol tcp --port $port --cidr ${MY_IP}/32
done

aws ec2 run-instances \
  --image-id "$(aws ssm get-parameters \
      --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
      --query 'Parameters[0].Value' --output text)" \
  --instance-type t3.xlarge \
  --key-name <your-key-pair> \
  --security-groups flyte-kind
```

SSH in as `ubuntu` (installs need `sudo`) and install the tools:

```bash
ssh -i <your-key.pem> ubuntu@<instance-public-ip> 'bash -s' <<'EOF'
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo curl -Lo /usr/local/bin/kind https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64 && sudo chmod +x /usr/local/bin/kind
sudo curl -Lo /usr/local/bin/kubectl "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && sudo chmod +x /usr/local/bin/kubectl
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | sudo bash
EOF
```

The `usermod -aG docker` takes effect on the **next** login, so the Step 2 SSH
sessions can run `docker`/`kind` without `sudo`. (In a single interactive session
you'd `newgrp docker`; over one-shot `ssh` commands, just reconnect.)

### GCP Compute Engine

```bash
gcloud compute instances create flyte-kind \
  --machine-type e2-standard-4 --zone <your-zone> \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --tags flyte-kind

# GCP blocks inbound 80/443 until a rule allows them — scope to the tag + your IP:
MY_IP=$(curl -s https://checkip.amazonaws.com)
gcloud compute firewall-rules create flyte-kind-web \
  --allow tcp:80,tcp:443 --target-tags flyte-kind --source-ranges ${MY_IP}/32
```

SSH in (installs need `sudo`) and install the tools:

```bash
gcloud compute ssh flyte-kind --zone <your-zone> --command='bash -s' <<'EOF'
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo curl -Lo /usr/local/bin/kind https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64 && sudo chmod +x /usr/local/bin/kind
sudo curl -Lo /usr/local/bin/kubectl "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && sudo chmod +x /usr/local/bin/kubectl
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | sudo bash
EOF
```

## Step 2: Define how the deploy commands run on the VM (skip for local)

Every `kind`, `kubectl`, and `helm` command from the deploy runs **on the VM**,
not your machine. Fix the SSH target once and reuse it:

```bash
VM="root@<droplet-ip>"                 # DigitalOcean
# VM="ubuntu@<instance-public-ip>"     # AWS EC2 (add -i <your-key.pem> to ssh below)
# GCP: use `gcloud compute ssh flyte-kind --zone <zone> --command='...'` instead of ssh $VM
```

Then, when the `deploy-flyte-kind` skill (Step 3) says to run a command, run it on
the VM instead of locally:

- **Single command:** `ssh $VM '<command>'`
- **A block or a heredoc** (e.g. `kind create cluster --config - <<'EOF' … EOF`):
  pipe it through SSH — `ssh $VM 'bash -s' <<'EOF' … EOF`.

Alternatively, open one interactive session (`ssh $VM`) and run the deploy
commands there. Either way, **only the SDK/CLI and browser run on your machine**;
everything cluster-side runs on the VM. The access tunnel in Step 4 bridges the
two.

## Step 3: Run the Flyte deploy (hand off to `deploy-flyte-kind`)

Now do the actual install by following the **`deploy-flyte-kind`** skill. It
covers, in order:

1. **Prereqs + existing-cluster check** — you've already installed the tools; on a
   VM the `kind get clusters` / prereq checks run via `ssh $VM '...'`.
2. **Create the kind cluster** — with the two host-port mappings (`30080→80`,
   `30443→443`). On a VM these bind to the VM's public IP; `flyte.local` will point
   at that IP (not `127.0.0.1`) if you enable auth.
3. **Choose + configure dependencies** — this is the main **human-in-the-loop**
   part: PostgreSQL (**Supabase** or external) and object store (**AWS S3** or
   **Cloudflare R2**). The user creates these in their consoles and supplies the
   connection details (they can paste a screenshot). Follow that skill's guidance
   exactly — especially Supabase's **session pooler** requirement (kind is IPv4-only).
4. **Write `values-local.yaml`** and **`helm install`** the flyte-binary chart.
5. **Optional OIDC auth** via Traefik + oauth2-proxy (and the `start-dex-local`
   skill for an in-cluster Dex IdP).

**When on a cloud VM, apply the Step 2 wrapper to every command in that skill** —
create the values/config files on the VM (write them via the piped heredoc, or
edit them in the interactive session), since helm reads them there. The logic is
identical; only the execution location changes.

## Step 4: Access Flyte

The API is reached at `localhost:8090` on the machine where you run the SDK/CLI.

**Local machine** — just port-forward:

```bash
kubectl -n flyte port-forward service/flyte-http 8090:8090
```

**Cloud VM** — the port-forward runs on the VM, so tunnel it back over SSH. One
command starts the forward on the VM and exposes it at `localhost:8090` locally:

```bash
# DigitalOcean
ssh -L 8090:localhost:8090 root@<droplet-ip> \
  kubectl -n flyte port-forward service/flyte-http 8090:8090
# AWS EC2
ssh -i <your-key.pem> -L 8090:localhost:8090 ubuntu@<instance-public-ip> \
  kubectl -n flyte port-forward service/flyte-http 8090:8090
# GCP
gcloud compute ssh flyte-kind --zone <your-zone> \
  --ssh-flag="-L 8090:localhost:8090" \
  --command="kubectl -n flyte port-forward service/flyte-http 8090:8090"
```

Keep it running. Verify from your machine (a JSON response, not a connection
error, confirms Flyte is up and talking to its database):

```bash
curl -s -X POST http://localhost:8090/flyteidl2.project.ProjectService/ListProjects \
  -H 'Content-Type: application/json' -d '{}'
```

Then point the SDK at it — the `deploy-flyte-kind` "Verify access" step has the
`~/.flyte/config.yaml` block (`endpoint: dns:///localhost:8090`, `insecure: True`).
The tunnel makes the VM deploy behave exactly like a local one for the SDK. The
code-bundle upload needs no second tunnel — the S3/R2 endpoint is publicly
resolvable, so the SDK uploads to the presigned URL directly.

> If you enable **auth** (Step 3.5), the SDK reaches Flyte at `https://flyte.local`
> over the `443` mapping, not this port-forward. On a cloud VM, `flyte.local` must
> resolve to the **VM's public IP** in your local `/etc/hosts` (not `127.0.0.1`),
> and inbound 443 must be open to your IP (Step 1). Otherwise the auth flow is
> identical to `deploy-flyte-kind`.

## Optional: load a local image into kind

kind nodes can't pull from a host Docker daemon, so a custom task/Flyte image must
be loaded into the cluster:

```bash
kind load docker-image <your-image>:<tag> --name flyte     # local
```

On a cloud VM the image must be in the **VM's** Docker daemon first — either build
it on the VM, or ship it from your machine:

```bash
docker save <your-image>:<tag> | ssh $VM docker load
ssh $VM 'kind load docker-image <your-image>:<tag> --name flyte'
```

Reference that exact `<image>:<tag>` in task config; the `IfNotPresent` pull policy
then uses the loaded image.

## Tear down

```bash
kind delete cluster --name flyte          # local
ssh $VM 'kind delete cluster --name flyte'   # cloud VM
```

On a cloud VM, also delete the instance so it stops billing (confirm with the
user), and remove the firewall/security group you created:

```bash
doctl compute droplet delete flyte-kind                        # DigitalOcean
aws ec2 terminate-instances --instance-ids <instance-id>       # AWS EC2 — also: aws ec2 delete-security-group --group-name flyte-kind
gcloud compute instances delete flyte-kind --zone <your-zone>  # GCP — also: gcloud compute firewall-rules delete flyte-kind-web
```

The hosted PostgreSQL and S3/R2 bucket are untouched — clean those up in their own
consoles.
