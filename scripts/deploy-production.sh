#!/usr/bin/env bash
set -Eeuo pipefail

: "${REGISTRY_NAMESPACE:?REGISTRY_NAMESPACE is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

DEPLOY_NAMESPACE="${DEPLOY_NAMESPACE:-default}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-12m}"

deployments=(
  auth-service
  lms-service
  lab-service
  chat-service
  ai-service
  ai-worker
  personalize-service
  frontend
)

declare -A containers=(
  [auth-service]=auth-service
  [lms-service]=lms-service
  [lab-service]=lab-service
  [chat-service]=chat-service
  [ai-service]=ai-service
  [ai-worker]=ai-worker
  [personalize-service]=personalize-service
  [frontend]=frontend
)

declare -A images=(
  [auth-service]=bdc-backend
  [lms-service]=bdc-lms
  [lab-service]=bdc-lab
  [chat-service]=bdc-chat
  [ai-service]=bdc-ai
  [ai-worker]=bdc-ai
  [personalize-service]=bdc-personalize
  [frontend]=bdc-frontend
)

updated=()
declare -A previous_images=()
rollback_on_error() {
  exit_code=$?
  if (( exit_code == 0 )); then
    return
  fi
  echo "Deployment failed; rolling back workloads changed by this run." >&2
  for deployment in "${updated[@]}"; do
    kubectl set image "deployment/${deployment}" \
      "${containers[$deployment]}=${previous_images[$deployment]}" \
      --namespace "$DEPLOY_NAMESPACE" || true
  done
  exit "$exit_code"
}
trap rollback_on_error ERR

kubectl cluster-info >/dev/null
for deployment in "${deployments[@]}"; do
  kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" >/dev/null
done

for deployment in "${deployments[@]}"; do
  image="${REGISTRY_NAMESPACE}/${images[$deployment]}:${IMAGE_TAG}"
  previous_images[$deployment]="$(
    kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" \
      -o "jsonpath={.spec.template.spec.containers[?(@.name=='${containers[$deployment]}')].image}"
  )"
  if [[ "${previous_images[$deployment]}" == "$image" ]]; then
    echo "${deployment} already uses ${image}; no change needed."
    continue
  fi
  echo "Updating ${deployment} to ${image}"
  kubectl set image "deployment/${deployment}" \
    "${containers[$deployment]}=${image}" \
    --namespace "$DEPLOY_NAMESPACE"
  updated+=("$deployment")
done

for deployment in "${deployments[@]}"; do
  kubectl rollout status "deployment/${deployment}" \
    --namespace "$DEPLOY_NAMESPACE" \
    --timeout "$ROLLOUT_TIMEOUT"
done

trap - ERR

kubectl get pods --namespace "$DEPLOY_NAMESPACE" -o wide

# K3s uses containerd, not Docker. Remove only images that are no longer used
# by any container; active images and persistent volumes are preserved.
if sudo -n /usr/local/bin/k3s crictl rmi --prune; then
  echo "Pruned unused K3s/containerd images."
else
  echo "K3s image pruning was skipped (passwordless sudo rule not installed)." >&2
fi

# Clean remnants from a retained legacy Docker installation, if one exists.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker container prune --force --filter "until=168h"
  docker image prune --all --force --filter "until=168h"
  docker builder prune --all --force --filter "until=168h"
  docker network prune --force --filter "until=168h"
fi

echo "Production rollout completed for tag ${IMAGE_TAG}."
