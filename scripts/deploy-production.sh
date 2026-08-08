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
  course-blueprint-worker
  personalize-service
  recommender-service
)

# A deployment job may roll out only the workloads whose image was published.
# `SERVICES=auth-service,lms-service` is intentionally explicit; it avoids
# restarting unrelated services and prevents a stale `latest` tag from being
# deployed as a side effect of an application change.
if [[ -n "${SERVICES:-}" ]]; then
  IFS=',' read -r -a deployments <<< "${SERVICES}"
fi

declare -A containers=(
  [auth-service]=auth-service
  [lms-service]=lms-service
  [lab-service]=lab-service
  [chat-service]=chat-service
  [ai-service]=ai-service
  [ai-worker]=ai-worker
  [course-blueprint-worker]=course-blueprint-worker
  [personalize-service]=personalize-service
  [recommender-service]=recommender-service
  [frontend]=frontend
)

declare -A images=(
  [auth-service]=bdc-backend
  [lms-service]=bdc-lms
  [lab-service]=bdc-lab
  [chat-service]=bdc-chat
  [ai-service]=bdc-ai
  [ai-worker]=bdc-ai
  [course-blueprint-worker]=bdc-ai
  [personalize-service]=bdc-personalize
  [recommender-service]=bdc-recommender
  [frontend]=bdc-frontend
)

# Some workloads have deployment-level configuration (env, probes, resources)
# that must accompany a new image. Apply only their selected manifest, then set
# the immutable image immediately below; unrelated deployments are untouched.
declare -A manifests=(
  [chat-service]=k3s/base/chat-service-deployment.yaml
  [course-blueprint-worker]=k3s/base/course-blueprint-worker-deployment.yaml
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
# Config changes are safe to apply in place; only deployments selected below
# are restarted, so unrelated workloads keep their current pods.
kubectl apply -f k3s/base/configmap.yaml --namespace "$DEPLOY_NAMESPACE"
# Apply manifests only for selected workloads that require spec-level changes.
# Capture the previous immutable image before apply so rollback remains correct
# even though the base manifest uses a `latest` placeholder.
for deployment in "${deployments[@]}"; do
  if [[ -n "${manifests[$deployment]:-}" ]]; then
    previous_images[$deployment]="$(
      kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" \
        -o "jsonpath={.spec.template.spec.containers[?(@.name=='${containers[$deployment]}')].image}"
    )"
    kubectl apply -f "${manifests[$deployment]}" --namespace "$DEPLOY_NAMESPACE"
  elif [[ "$deployment" == "recommender-service" ]]; then
    kubectl apply -f k3s/base/recommender-service-deployment.yaml --namespace "$DEPLOY_NAMESPACE"
  fi
done
for deployment in "${deployments[@]}"; do
  kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" >/dev/null
done

for deployment in "${deployments[@]}"; do
  [[ -n "${images[$deployment]:-}" ]] || { echo "Unknown deployment: ${deployment}" >&2; exit 2; }
  tag="$IMAGE_TAG"
  if [[ "$deployment" == "frontend" && -n "${FRONTEND_IMAGE_TAG:-}" ]]; then
    tag="$FRONTEND_IMAGE_TAG"
  fi
  image="${REGISTRY_NAMESPACE}/${images[$deployment]}:${tag}"
  if [[ -z "${previous_images[$deployment]:-}" ]]; then
    previous_images[$deployment]="$(
      kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" \
        -o "jsonpath={.spec.template.spec.containers[?(@.name=='${containers[$deployment]}')].image}"
    )"
  fi
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

echo "Production rollout completed for tag ${IMAGE_TAG}."
