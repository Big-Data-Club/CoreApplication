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
  [ai-service]=k3s/base/ai-service-deployment.yaml
  [chat-service]=k3s/base/chat-service-deployment.yaml
  [course-blueprint-worker]=k3s/base/course-blueprint-worker-deployment.yaml
  [lab-service]=k3s/base/lab-service-deployment.yaml
)

updated=()
created=()
declare -A previous_images=()
rollback_on_error() {
  exit_code=$?
  if (( exit_code == 0 )); then
    return
  fi
  echo "Deployment failed; rolling back workloads changed by this run." >&2
  for deployment in "${updated[@]}"; do
    # A newly-created workload has no meaningful previous image.  It is
    # removed below instead of being pointed back at the manifest placeholder.
    [[ " ${created[*]} " == *" ${deployment} "* ]] && continue
    kubectl set image "deployment/${deployment}" \
      "${containers[$deployment]}=${previous_images[$deployment]}" \
      --namespace "$DEPLOY_NAMESPACE" || true
  done
  for deployment in "${created[@]}"; do
    kubectl delete deployment "${deployment}" --namespace "$DEPLOY_NAMESPACE" --ignore-not-found || true
  done
  exit "$exit_code"
}
trap rollback_on_error ERR

diagnose_rollout() {
  local deployment="$1"
  echo "Deployment ${deployment} did not become ready; diagnostics follow." >&2
  kubectl describe "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" >&2 || true
  kubectl get pods --namespace "$DEPLOY_NAMESPACE" -l "app=${deployment}" -o wide >&2 || true
  while IFS= read -r pod; do
    [[ -z "$pod" ]] && continue
    echo "--- ${pod}: previous/current logs ---" >&2
    kubectl logs --namespace "$DEPLOY_NAMESPACE" "$pod" --all-containers --tail=150 >&2 || true
    kubectl logs --namespace "$DEPLOY_NAMESPACE" "$pod" --all-containers --previous --tail=150 >&2 || true
  done < <(kubectl get pods --namespace "$DEPLOY_NAMESPACE" -l "app=${deployment}" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null || true)
}

clear_terminating_pods() {
  local deployment="$1"
  local pods=()
  mapfile -t pods < <(
    kubectl get pods --namespace "$DEPLOY_NAMESPACE" -l "app=${deployment}" \
      -o custom-columns=NAME:.metadata.name,DELETING:.metadata.deletionTimestamp --no-headers 2>/dev/null \
      | awk '$2 != "<none>" && $2 != "" { print $1 }'
  )
  if ((${#pods[@]})); then
    echo "Removing ${#pods[@]} pod(s) already marked Terminating for ${deployment}." >&2
    kubectl delete pod --namespace "$DEPLOY_NAMESPACE" --grace-period=0 --force "${pods[@]}" >&2 || true
  fi
}

kubectl cluster-info >/dev/null
./scripts/k3s-maintenance.sh \
  --namespace "$DEPLOY_NAMESPACE" \
  --phase pre
# Config changes are safe to apply in place; only deployments selected below
# are restarted, so unrelated workloads keep their current pods.
kubectl apply -f k3s/base/configmap.yaml --namespace "$DEPLOY_NAMESPACE"
kubectl apply -f k3s/base/ingress.yaml --namespace "$DEPLOY_NAMESPACE"
# Kafka is shared infrastructure for the AI workers. Applying an unchanged
# StatefulSet is a no-op; applying a changed one performs the controlled
# one-broker rollout required for heap/probe/resource fixes.
if [[ ",${SERVICES:-}," == *",ai-worker,"* ]]; then
  kubectl apply -f k3s/base/kafka-statefulset.yaml --namespace "$DEPLOY_NAMESPACE"
  kubectl rollout status statefulset/kafka \
    --namespace "$DEPLOY_NAMESPACE" \
    --timeout "$ROLLOUT_TIMEOUT"
fi
# Establish the restricted, default-deny namespace before any future executor
# image can be rolled out. Applying this declarative policy is idempotent and
# does not start learner workloads by itself.
if [[ ",${SERVICES:-}," == *",lab-service,"* ]]; then
  kubectl apply -f k3s/base/lab-sandbox-policy.yaml
fi
# Apply manifests only for selected workloads that require spec-level changes.
# Capture the previous immutable image before apply so rollback remains correct
# even though the base manifest uses a `latest` placeholder.
for deployment in "${deployments[@]}"; do
  if [[ -n "${manifests[$deployment]:-}" ]]; then
    if kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" >/dev/null 2>&1; then
      previous_images[$deployment]="$(
        kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" \
          -o "jsonpath={.spec.template.spec.containers[?(@.name=='${containers[$deployment]}')].image}"
      )"
    else
      created+=("$deployment")
    fi
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
  if ! kubectl rollout status "deployment/${deployment}" \
    --namespace "$DEPLOY_NAMESPACE" \
    --timeout "$ROLLOUT_TIMEOUT"; then
    # A pod with deletionTimestamp is already being removed.  On a constrained
    # single-node K3s host it can otherwise hold a rollout hostage forever.
    # Never force-delete a live pod; only retry after clearing such stale
    # terminating objects, then emit actionable diagnostics on a real failure.
    clear_terminating_pods "$deployment"
    if ! kubectl rollout status "deployment/${deployment}" \
      --namespace "$DEPLOY_NAMESPACE" \
      --timeout 2m; then
      diagnose_rollout "$deployment"
      exit 1
    fi
  fi
done

trap - ERR

kubectl get pods --namespace "$DEPLOY_NAMESPACE" -o wide

./scripts/k3s-maintenance.sh \
  --namespace "$DEPLOY_NAMESPACE" \
  --phase post

echo "Production rollout completed for tag ${IMAGE_TAG}."
