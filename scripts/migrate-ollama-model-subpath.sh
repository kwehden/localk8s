#!/usr/bin/env bash
set -Eeuo pipefail

# One-time: move legacy in-cluster Ollama data from /mnt/ollama-models/* into
# /mnt/ollama-models/ollama/ before applying the split PV (200Gi models subpath).
#
# Run on the control-plane host with the model disk mounted. Stops the Ollama
# Deployment for the duration of the move.

MOUNT_POINT="${OLLAMA_MODEL_MOUNT_POINT:-/mnt/ollama-models}"
SUB="${MOUNT_POINT}/ollama"
KUBECONFIG_PATH="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

log() {
  printf '[%s] [migrate-ollama-subpath] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

run_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

main() {
  findmnt -rn "${MOUNT_POINT}" >/dev/null 2>&1 || {
    log "mount ${MOUNT_POINT} not found; run ./scripts/mount-ollama-model-disk.sh first"
    exit 1
  }

  if [[ -d "${SUB}/models" ]]; then
    log "already migrated (${SUB}/models exists); nothing to do"
    exit 0
  fi

  command -v kubectl >/dev/null 2>&1 || {
    log "kubectl required"
    exit 1
  }

  log "scaling down ollama"
  kubectl --kubeconfig "${KUBECONFIG_PATH}" scale deployment/ollama -n ollama --replicas=0
  kubectl --kubeconfig "${KUBECONFIG_PATH}" rollout status deployment/ollama -n ollama --timeout=120s || true

  run_root mkdir -p "${SUB}"

  shopt -s nullglob
  local moved=0
  for path in "${MOUNT_POINT}/"*; do
    local base
    base="$(basename "${path}")"
    case "${base}" in
      ollama | lost+found)
        continue
        ;;
      *)
        log "moving ${base} -> ollama/"
        run_root mv "${path}" "${SUB}/"
        moved=1
        ;;
    esac
  done
  shopt -u nullglob

  if [[ "${moved}" -eq 0 ]]; then
    log "no top-level items moved (empty disk or already using subpaths)"
  fi

  run_root chmod 0775 "${SUB}"

  log "scaling ollama back up"
  kubectl --kubeconfig "${KUBECONFIG_PATH}" scale deployment/ollama -n ollama --replicas=1

  log "done; reconcile Kubernetes PV/PVC if you have not applied the new manifests yet"
}

main "$@"
