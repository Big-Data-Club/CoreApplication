#!/usr/bin/env bash
set -Eeuo pipefail

: "${REGISTRY_NAMESPACE:?REGISTRY_NAMESPACE is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

DEPLOY_NAMESPACE="${DEPLOY_NAMESPACE:-default}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-12m}"

# Gateway access is suspended. Reject manual selection before any mutation.
IFS=',' read -r -a requested_services <<< "${SERVICES:-}"
for requested_service in "${requested_services[@]}"; do
  if [[ "$requested_service" == "ai-gateway" || "$requested_service" == "ai-gateway-info" ]]; then
    echo "AI gateway is suspended; deployment is disabled." >&2
    exit 2
  fi
done

# Keep schema/config/image changes mutually exclusive with online DB migration.
# The full production workflow acquires this before its schema/Secret steps.
if [[ -n "${BDC_OPERATION_OWNER:-}" ]]; then
  python3 scripts/db-operation-lock.py check "$BDC_OPERATION_OWNER"
else
  BDC_OPERATION_OWNER="deploy:$(python3 -c 'import uuid; print(uuid.uuid4())')"
  python3 scripts/db-operation-lock.py claim "$BDC_OPERATION_OWNER"
  trap 'python3 scripts/db-operation-lock.py release "$BDC_OPERATION_OWNER"' EXIT
fi

deployments=(
  auth-service
  lms-service
  lab-service
  chat-service
  ai-service
  ai-worker
  course-blueprint-worker
  ai-lab-authoring-worker
  personalize-service
  recommender-service
  dutylog-service
  farm-service
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
  [ai-lab-authoring-worker]=ai-lab-authoring-worker
  [personalize-service]=personalize-service
  [recommender-service]=recommender-service
  [frontend]=frontend
  [farm-service]=farm-service
  [dutylog-service]=dutylog-service
  [ai-gateway]=gateway
)

declare -A images=(
  [auth-service]=bdc-backend
  [lms-service]=bdc-lms
  [lab-service]=bdc-lab
  [chat-service]=bdc-chat
  [ai-service]=bdc-ai
  [ai-worker]=bdc-ai
  [course-blueprint-worker]=bdc-ai
  [ai-lab-authoring-worker]=bdc-ai
  [personalize-service]=bdc-personalize
  [recommender-service]=bdc-recommender
  [frontend]=bdc-frontend
  [farm-service]=bdc-farm
  [dutylog-service]=bdc-dutylog
  [ai-gateway]=bdc-ai-gateway
)

# Some workloads have deployment-level configuration (env, probes, resources)
# that must accompany a new image. Apply only their selected manifest, then set
# the immutable image immediately below; unrelated deployments are untouched.
declare -A manifests=(
  [auth-service]=k3s/base/auth-service-deployment.yaml
  [ai-service]=k3s/base/ai-service-deployment.yaml
  [ai-worker]=k3s/base/ai-service-deployment.yaml
  [chat-service]=k3s/base/chat-service-deployment.yaml
  [course-blueprint-worker]=k3s/base/course-blueprint-worker-deployment.yaml
  [ai-lab-authoring-worker]=k3s/base/ai-lab-authoring-worker-deployment.yaml
  [lab-service]=k3s/base/lab-service-deployment.yaml
  [farm-service]=k3s/base/farm-service-deployment.yaml
  [dutylog-service]=k3s/base/dutylog-service-deployment.yaml
  [ai-gateway]=k3s/base/ai-gateway-deployment.yaml
  [recommender-service]=k3s/base/recommender-service-deployment.yaml
)

for deployment in "${deployments[@]}"; do
  [[ -n "${images[$deployment]:-}" ]] || { echo "Unknown deployment: ${deployment}" >&2; exit 2; }
done

# ai-gateway shares one pod between the gateway proxy and the Autossh tunnel;
# both container images must be patched on the same rollout.
declare -A sidecars=(
  [ai-gateway]=tunnel
)
declare -A sidecar_images=(
  [ai-gateway]=bdc-ai-gateway-tunnel
)

updated=()
created=()
declare -A previous_images=()
declare -A previous_sidecars=()
rollback_on_error() {
  exit_code=$?
  if (( exit_code == 0 )); then
    return
  fi
  # ERR is inherited by command substitutions; the parent owns rollback.
  if (( BASH_SUBSHELL > 0 )); then
    return "$exit_code"
  fi
  echo "Deployment failed; rolling back workloads changed by this run." >&2
  for deployment in "${updated[@]}"; do
    # A newly-created workload has no meaningful previous image.  It is
    # removed below instead of being pointed back at the manifest placeholder.
    [[ " ${created[*]} " == *" ${deployment} "* ]] && continue
    kubectl set image "deployment/${deployment}" \
      "${containers[$deployment]}=${previous_images[$deployment]}" \
      --namespace "$DEPLOY_NAMESPACE" || true
    if [[ -n "${sidecars[$deployment]:-}" && -n "${previous_sidecars[$deployment]:-}" ]]; then
      kubectl set image "deployment/${deployment}" \
        "${sidecars[$deployment]}=${previous_sidecars[$deployment]}" \
        --namespace "$DEPLOY_NAMESPACE" || true
    fi
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
    echo "--- ${pod}: current logs ---" >&2
    kubectl logs --namespace "$DEPLOY_NAMESPACE" "$pod" --all-containers --tail=150 >&2 || true
    while IFS= read -r container; do
      [[ -z "$container" ]] && continue
      kubectl logs --namespace "$DEPLOY_NAMESPACE" "$pod" -c "$container" --previous --tail=150 >&2 || true
    done < <(kubectl get pod "$pod" --namespace "$DEPLOY_NAMESPACE" \
      -o 'jsonpath={range .status.containerStatuses[?(@.lastState.terminated)]}{.name}{"\n"}{end}' 2>/dev/null || true)
  done < <(kubectl get pods --namespace "$DEPLOY_NAMESPACE" -l "app=${deployment}" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null || true)
}

# Sync configuration before any application rollout. Normal farm changes select Auth too
# so its env-based consumer flag is picked up by the new pod.
if [[ " ${deployments[*]} " == *" farm-service "* ]]; then
  if [[ " ${deployments[*]} " != *" auth-service "* ]]; then
    echo "Farm rollout must include auth-service (SERVICES=auth-service,farm-service)." >&2
    exit 2
  fi
fi

kubectl cluster-info >/dev/null
./scripts/k3s-maintenance.sh --namespace "$DEPLOY_NAMESPACE" --phase pre
# Applying other workloads must never revive the suspended SSH tunnel.
for paused in ai-gateway ai-gateway-info; do
  if [[ -n "$(kubectl get deployment "$paused" --namespace "$DEPLOY_NAMESPACE" --ignore-not-found -o name)" ]]; then
    kubectl scale deployment "$paused" --replicas=0 --namespace "$DEPLOY_NAMESPACE"
    kubectl rollout status deployment/"$paused" --namespace "$DEPLOY_NAMESPACE" --timeout=90s
  fi
done
# Config changes are safe to apply in place; only deployments selected below
# are restarted, so unrelated workloads keep their current pods.
python3 scripts/apply-runtime-config.py
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
# The AI Gateway rollout also owns the static marketing site pod. Its manifest
# carries no image from this registry (upstream nginx), so it stays outside the
# set-image loop; applying and verifying here keeps it versioned with the
# ai-gateway change set.
if [[ ",${SERVICES:-}," == *",ai-gateway,"* ]]; then
  kubectl apply -f k3s/base/ai-gateway-info.yaml --namespace "$DEPLOY_NAMESPACE"
  kubectl rollout status deployment/ai-gateway-info \
    --namespace "$DEPLOY_NAMESPACE" \
    --timeout "$ROLLOUT_TIMEOUT"
fi
# Establish the restricted, default-deny namespace before any future executor
# image can be rolled out. Applying this declarative policy is idempotent and
# does not start learner workloads by itself.
if [[ ",${SERVICES:-}," == *",lab-service,"* ]]; then
  kubectl apply -f k3s/base/lab-sandbox-policy.yaml
fi
if [[ " ${deployments[*]} " == *" farm-service "* ]]; then
  farm_config_revision="$(python3 scripts/sync-farm-config.py)"
  kubectl apply -f k3s/base/farm-topic-job.yaml --namespace "$DEPLOY_NAMESPACE"
  kubectl wait --for=condition=complete job/farm-reward-topic-v1 --namespace "$DEPLOY_NAMESPACE" --timeout=180s
fi
# Interactive AI jobs get their own topic and consumer group. Ensure the topic
# exists with enough partitions before the worker starts consuming it.
if [[ " ${deployments[*]} " == *" ai-worker "* ]]; then
  kubectl delete job kafka-ai-topics --ignore-not-found --namespace "$DEPLOY_NAMESPACE"
  kubectl apply -f k3s/base/kafka-ai-topics-job.yaml --namespace "$DEPLOY_NAMESPACE"
  kubectl wait --for=condition=complete job/kafka-ai-topics --namespace "$DEPLOY_NAMESPACE" --timeout=180s
fi
# Render the final image before apply, then finish each selected rollout before
# starting the next. Shared manifests must not restart unselected Deployments.
for deployment in "${deployments[@]}"; do
  if [[ "$deployment" == "farm-service" && " ${deployments[*]} " == *" lms-service "* ]]; then
    # Farm requests private grading content from LMS; let the new LMS schema
    # and endpoint become ready before starting the Farm image.
    kubectl rollout status deployment/lms-service --namespace "$DEPLOY_NAMESPACE" --timeout "$ROLLOUT_TIMEOUT"
  fi
  tag="$IMAGE_TAG"
  if [[ "$deployment" == "frontend" && -n "${FRONTEND_IMAGE_TAG:-}" ]]; then
    tag="$FRONTEND_IMAGE_TAG"
  fi
  image="${REGISTRY_NAMESPACE}/${images[$deployment]}:${tag}"
  existing="$(kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" --ignore-not-found -o name)"
  if [[ -n "$existing" ]]; then
    previous_images[$deployment]="$(
      kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" \
        -o "jsonpath={.spec.template.spec.containers[?(@.name=='${containers[$deployment]}')].image}"
    )"
  elif [[ -n "${manifests[$deployment]:-}" ]]; then
    created+=("$deployment")
  else
    echo "Deployment ${deployment} does not exist and has no manifest." >&2
    false
  fi
  if [[ -n "${manifests[$deployment]:-}" ]]; then
    render_args=("${manifests[$deployment]}" "$deployment" "${containers[$deployment]}" "$image" --namespace "$DEPLOY_NAMESPACE")
    if [[ -n "${farm_config_revision:-}" && ( "$deployment" == "auth-service" || "$deployment" == "farm-service" ) ]]; then
      render_args+=(--config-revision "$farm_config_revision")
    fi
    manifest="$(python3 scripts/render-deployment.py "${render_args[@]}")"
    updated+=("$deployment")
    printf '%s\n' "$manifest" | kubectl apply -f - --namespace "$DEPLOY_NAMESPACE"
  elif [[ "${previous_images[$deployment]}" != "$image" ]]; then
    updated+=("$deployment")
    kubectl set image "deployment/${deployment}" \
      "${containers[$deployment]}=${image}" --namespace "$DEPLOY_NAMESPACE"
  fi
  if [[ -n "${sidecars[$deployment]:-}" ]]; then
    sidecar_tag="$IMAGE_TAG"
    sidecar_image="${REGISTRY_NAMESPACE}/${sidecar_images[$deployment]}:${sidecar_tag}"
    if [[ -z "${previous_sidecars[$deployment]:-}" ]]; then
      previous_sidecars[$deployment]="$(
        kubectl get "deployment/${deployment}" --namespace "$DEPLOY_NAMESPACE" \
          -o "jsonpath={.spec.template.spec.containers[?(@.name=='${sidecars[$deployment]}')].image}" 2>/dev/null || true
      )"
    fi
    if [[ "${previous_sidecars[$deployment]}" != "$sidecar_image" ]]; then
      kubectl set image "deployment/${deployment}" \
        "${sidecars[$deployment]}=${sidecar_image}" \
        --namespace "$DEPLOY_NAMESPACE"
    fi
  fi
  if ! kubectl rollout status "deployment/${deployment}" \
    --namespace "$DEPLOY_NAMESPACE" \
    --timeout "$ROLLOUT_TIMEOUT"; then
    diagnose_rollout "$deployment"
    false # Trigger ERR/rollback; explicit exit would bypass the ERR trap.
  fi
done

trap - ERR

kubectl get pods --namespace "$DEPLOY_NAMESPACE" -o wide

./scripts/k3s-maintenance.sh \
  --namespace "$DEPLOY_NAMESPACE" \
  --phase post

echo "Production rollout completed for tag ${IMAGE_TAG}."
