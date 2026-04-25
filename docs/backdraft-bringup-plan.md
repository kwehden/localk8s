# Backdraft Node Bring-Up Plan

**Date:** 2026-04-19  
**Node:** `backdraft`  
**GPU:** NVIDIA Tesla M10 (Maxwell architecture, CUDA 12.x only)  
**Purpose:** Ray + Ollama capacity expansion

---

## Cluster Context

| Node | Role | GPU |
|------|------|-----|
| `laminarflow` | control-plane | RTX 5060 Ti (CUDA 13, baseline) |
| `polecat` | CPU worker | none |
| `backdraft` | GPU worker (incoming) | Tesla M10 (Maxwell, CUDA 12.x only) |

---

## Steps

### 1. Inventory Entry

Add to `packages/node-join/inventory.local.ini`:

```ini
backdraft ansible_host=<ip-or-dns> ansible_user=<user> \
  localk8s_node_name=backdraft \
  localk8s_node_profile=gpu \
  localk8s_node_labels=localk8s.io/accelerator=tesla-m10,localk8s.io/accelerator-gen=maxwell
```

### 2. SSH Key Setup

```bash
./scripts/setup-node-ssh.sh
```

### 3. Join Node

```bash
K3S_JOIN_TOKEN='<token>' ./scripts/join-node.sh \
  --target backdraft \
  --gpu \
  --inventory ./packages/node-join/inventory.local.ini
```

### 4. Validate GPU Worker

```bash
./scripts/validate-gpu-worker.sh --node backdraft --namespace ray --timeout 300s
```

Verifies: `nvidia.com/gpu` allocatable, ephemeral CUDA pod runs `nvidia-smi` successfully.

### 5. M10-Aware Manifest Updates

The M10 is CUDA 12.x only — workloads must not assume CUDA 13. Two manifests need nodeSelector/affinity changes:

#### Ray (`k8s/managed/raycluster.yaml`)

Add a second GPU worker group targeting M10, or add affinity to the existing group to prefer the RTX node for CUDA 13 workloads. Example for M10-safe group:

```yaml
- groupName: gpu-workers-m10
  replicas: 1
  minReplicas: 0
  maxReplicas: 2
  runtimeClassName: nvidia
  nodeSelector:
    localk8s.io/accelerator: tesla-m10
  resources:
    limits: {cpu: 4, memory: 16Gi, nvidia.com/gpu: 1}
    requests: {cpu: 2, memory: 8Gi, nvidia.com/gpu: 1}
```

#### Ollama (`k8s/managed/ollama.yaml`)

Decide whether Ollama should run on backdraft, laminarflow, or both:
- If backdraft only: add `nodeSelector: localk8s.io/accelerator: tesla-m10`
- If laminarflow only (status quo): add `nodeSelector: localk8s.io/accelerator-gen: ampere` (or equivalent)
- If both: change to 2 replicas with anti-affinity and verify `ollama/ollama:0.19.0` works on Maxwell/CUDA 12.x

### 6. Image Compatibility Check

Before scheduling on backdraft, verify:
- `ollama/ollama:0.19.0` — confirm CUDA 12.x compatible (Maxwell-safe)
- `rayproject/ray:2.47.1-gpu` — confirm no CUDA 13-only dependencies
- Reference: `docs/gpu-compatibility-m10.md`

---

## Key Constraint

**Tesla M10 = Maxwell architecture = CUDA 12.x only.** Any image that assumes CUDA 13 toolchain will fail on backdraft. Keep CUDA 13-heavy workloads pinned to `laminarflow`.

---

## Status (completed 2026-04-20)

- [x] Inventory entry added
- [x] SSH key configured (`~/.ssh/backdraft_ed25519`)
- [x] Node joined (k3s v1.33.1+k3s1, containerd template bootstrapped from rendered config)
- [x] GPU worker validated — 4x M10 visible, sm_50 confirmed
- [x] Ray manifest: M10 worker group added then **removed** — M10 is sm_50, incompatible with PyTorch 2.x (sm_70 minimum). Not suitable for Ray ML workloads.
- [x] Ollama: 4-pod parallel pool deployed (one pod per physical GPU, ports 11434–11437), load-balanced via `ollama-backdraft` service
- [x] Image compatibility confirmed: `ollama/ollama:0.19.0` works on Maxwell; PyTorch 2.x does not

## Lessons for next GPU node join

1. Run `setup-node-ssh.sh` **before** `join-node.sh` — missing key causes a misleading "cannot reach control-plane" error
2. Set up passwordless sudo on the target first (see `setup-node-ssh.sh` output for the one-liner)
3. Only hardware labels in `localk8s_node_labels` — `worker-class`/`ray-eligible`/`ollama-eligible` are reserved by `localk8s_node_profile`
4. k3s v1.33 does not generate `config.toml.tmpl` — the `node_gpu_runtime` role now handles this automatically
5. Expand `ray-quota` before applying new worker groups, then restart the KubeRay operator if pods are stuck
6. Confirm `nvidia-smi` CUDA capability (`sm_XX`) before routing to Ray — anything below sm_70 is Ollama-only
7. Use `ClusterIP` + `hostPort` for Ollama, not `LoadBalancer` (avoids svclb pods on CPU-only nodes)
8. Use `nvidia.com/gpu: "1"` per Ollama pod even with time-slicing — requesting more causes uneven device plugin assignment
