#!/usr/bin/env bash
set -Eeuo pipefail

namespace="${DEPLOY_NAMESPACE:-default}"
phase=post
disk_threshold="${K3S_PRUNE_DISK_THRESHOLD:-82}"

usage() {
  echo "Usage: $0 [--namespace NAME] [--phase pre|post] [--disk-threshold PERCENT]"
}

while (($#)); do
  case "$1" in
    --namespace) shift; namespace="${1:?--namespace requires a value}" ;;
    --phase) shift; phase="${1:?--phase requires a value}" ;;
    --disk-threshold) shift; disk_threshold="${1:?--disk-threshold requires a value}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

[[ "$phase" == pre || "$phase" == post ]] || { echo "phase must be pre or post" >&2; exit 2; }
[[ "$disk_threshold" =~ ^[0-9]+$ ]] && ((disk_threshold >= 50 && disk_threshold <= 99)) || {
  echo "disk threshold must be between 50 and 99" >&2
  exit 2
}

kubectl cluster-info >/dev/null

# Completed one-shot pods no longer provide runtime value. Failed pods are kept
# for diagnostics; containerd/kubelet garbage collection handles their layers.
mapfile -t completed_pods < <(
  kubectl -n "$namespace" get pods \
    --field-selector=status.phase=Succeeded \
    -o name 2>/dev/null || true
)
if ((${#completed_pods[@]})); then
  kubectl -n "$namespace" delete "${completed_pods[@]}" --wait=false >/dev/null
  echo "K3s maintenance (${phase}): removed ${#completed_pods[@]} completed pod object(s)."
fi

disk_path=/var/lib/rancher/k3s
[[ -d "$disk_path" ]] || disk_path=/
disk_used="$(df -P "$disk_path" | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
[[ "$disk_used" =~ ^[0-9]+$ ]] || { echo "Cannot determine K3s disk usage" >&2; exit 1; }

if [[ "$phase" == post && "$disk_used" -ge "$disk_threshold" ]]; then
  echo "K3s disk usage is ${disk_used}% (threshold ${disk_threshold}%); pruning unused containerd images."
  if command -v k3s >/dev/null 2>&1 && sudo -n /usr/local/bin/k3s crictl rmi --prune; then
    echo "Unused K3s images pruned."
  else
    echo "WARNING: image prune was required but the runner lacks the approved sudo rule." >&2
  fi
else
  echo "K3s maintenance (${phase}): disk=${disk_used}%; image prune skipped below ${disk_threshold}%."
fi

df -h "$disk_path" | tail -n 1
