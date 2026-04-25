# Tesla M10 Compatibility Notes (Laminar)

## Purpose
Capture operational guardrails for adding a Tesla M10 worker to a mixed-GPU Laminar cluster.

## Practical Compatibility Guidance
- Treat Tesla M10 as a **legacy Maxwell-generation** GPU for planning and scheduling.
- Keep M10-targeted workloads on **CUDA 12.x-era images**.
- Avoid assuming CUDA 13 toolchain support for Maxwell-targeted builds.
- Use an NVIDIA driver branch that remains compatible with Maxwell in your environment (current Laminar baseline uses R580 on the control-plane host).

## Critical PyTorch Constraint (confirmed 2026-04-20)

**Modern PyTorch does not support the M10.**

The M10 is CUDA compute capability `sm_50` (Maxwell). PyTorch ≥ 2.x requires a minimum of `sm_70` (Volta). Any Ray workload using `torch` with a standard PyTorch installation will fail at the CUDA initialisation step with:

```
Tesla M10 with CUDA capability sm_50 is not compatible with the current PyTorch installation.
The current PyTorch install supports CUDA capabilities sm_70 sm_75 sm_80 sm_86 sm_90 sm_100 sm_120.
```

### Workload routing implications

| Workload | M10 viable? | Notes |
|----------|-------------|-------|
| Ollama (llama.cpp) | **Yes** | llama.cpp compiles CUDA kernels for sm_50; confirmed CUDA 12.x compatible |
| Ray jobs using PyTorch | **No** | sm_50 below PyTorch 2.x minimum (sm_70) |
| Raw CUDA kernels (custom) | Possible | Must target sm_50 explicitly at compile time |
| TensorFlow | No | Same sm_70 minimum from TF 2.9+ |

**In practice:** use the M10 for Ollama inference capacity only. Route all PyTorch/TF Ray jobs to laminarflow (RTX 5060 Ti, sm_120+).

## Why This Matters
- Mixed GPU generations can coexist in one Kubernetes cluster, but workload images/toolchains must match each node's GPU capability envelope.
- A container image that works on newer GPUs can fail on M10 due to architecture/toolchain assumptions.
- The sm_50 constraint is stricter than the CUDA 12.x constraint — it is enforced by the PyTorch binary, not the CUDA runtime.

## Recommended Cluster Policy
- Label M10 node(s), for example:
  - `localk8s.io/accelerator=tesla-m10`
  - `localk8s.io/accelerator-gen=maxwell`
- Use `nodeSelector`/affinity in Ray/Ollama manifests for workloads that must run on M10-compatible nodes.
- Keep newer CUDA-heavy workloads pinned to newer GPUs.

## Source References
- CUDA Toolkit, Driver, and Architecture Matrix (NVIDIA):  
  https://docs.nvidia.com/datacenter/tesla/drivers/cuda-toolkit-driver-and-architecture-matrix.html
- Supported Drivers and CUDA Toolkit Versions (NVIDIA):  
  https://docs.nvidia.com/datacenter/tesla/drivers/supported-drivers-and-cuda-toolkit-versions.html

## Maintenance Note
Re-check NVIDIA matrices before major upgrades (driver branch, CUDA major version, or base container images).
