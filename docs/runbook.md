# Laminar Runbook

## Purpose
This runbook records install, reconciliation, and validation evidence for the Laminar control-plane baseline.

Use it to capture:
- what was changed
- what commands were run
- what passed/failed
- what follow-up is required

All commands below assume execution from repo root (`~/projects/localk8s`).

## Environment Snapshot
- Date:
- Operator:
- Hostname:
- Linux distro/version:
- GPU (`nvidia-smi -L`):
- Branch/commit:

## Bootstrap Procedure
Run in order:

```bash
./scripts/setup.sh
./scripts/bootstrap.sh
./scripts/healthcheck.sh
```

If model disk is required:

```bash
./scripts/mount-ollama-model-disk.sh
```

If migrating host Ollama to in-cluster:

```bash
./scripts/remove-host-ollama.sh
```

### Model disk layout (200 Gi Ollama + 200 Gi Kuzu on polecat)

- **Ollama** uses host PV `ollama-models-pv` → `/mnt/ollama-models/ollama` on the control-plane model disk (200 Gi).
- **Kuzu** uses local PV `kuzu-graph-state-pv` → `/var/lib/localk8s/kuzu` on the **`polecat` worker only** (200 Gi). `k3s_agent` creates that directory on join; on an existing worker run: `sudo mkdir -p /var/lib/localk8s/kuzu && sudo chmod 0755 /var/lib/localk8s/kuzu`.
- If the model disk already holds legacy paths (`/mnt/ollama-models/models`, etc.), run **before** applying the updated PV path:

```bash
./scripts/migrate-ollama-model-subpath.sh
```

Then replace stale PV/PVC objects if the cluster still references the old 400 Gi `/mnt/ollama-models` PV (see Kubernetes docs for `Retain` reclaim and data safety).

If your worker’s Kubernetes node name is not `polecat`, patch `k8s/managed/kuzu-storage.yaml` `nodeAffinity` values to match `kubectl get nodes`.

For controlled node removal, use:

```bash
./scripts/remove-node.sh --node <k8s-node-name> --target <inventory-host>
```

Removal is ownership-registry gated:
- missing or corrupt `/var/lib/localk8s/node-join-owned-artifacts.yaml` fails removal by default
- remote cleanup is restricted to registry-listed artifacts
- break-glass override must be explicit: `--force-without-registry`

Before GPU worker rollout, run CPU worker canary validation:

```bash
./scripts/validate-cpu-worker.sh
./scripts/validate-cpu-worker.sh --node polecat --timeout 300s
```

After GPU worker join, run GPU worker validation:

```bash
./scripts/validate-gpu-worker.sh
./scripts/validate-gpu-worker.sh --node standpunkt --namespace ray --timeout 300s
```

## Validation Checklist
Record command + result (`PASS`/`FAIL`) for each:

```bash
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes
./scripts/validate-cpu-worker.sh
./scripts/validate-gpu-worker.sh
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml describe node "$(kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes -o jsonpath='{.items[0].metadata.name}')" | rg 'nvidia.com/gpu'
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get raycluster -n ray
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n ray get pods -l ray.io/group=cpu-workers -o wide
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n ray get pods -l ray.io/group=flenser-gpu-workers -o wide
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n ray get pods -l ray.io/group=laminarflow-gpu-workers -o wide
kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get pods -n ollama
curl -fsS "http://${LOCAL_HOSTNAME:-$(hostname -s)}/ray/" >/dev/null
curl -fsS "http://${LOCAL_HOSTNAME:-$(hostname -s)}/k3s/" >/dev/null
```

## Idempotency / Day-0 Convergence
Run and capture outcome:

```bash
./scripts/idempotency-check.sh
```

Expected: second reconciliation is clean, managed resources converge, no stale managed config remains.

## Incident Notes
- Symptom:
- Root cause:
- Resolution:
- Preventive action:

## Change Log Entries
- YYYY-MM-DD: short summary of infra/config change and validation result.
