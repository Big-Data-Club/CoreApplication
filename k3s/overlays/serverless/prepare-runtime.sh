#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-$HOME/codespace/core/.env}"
namespace="${BDC_NAMESPACE:-default}"

if [[ ! -r "$env_file" ]]; then
  echo "Cannot read environment file: $env_file" >&2
  exit 1
fi

required_keys=(
  POSTGRES_HOST POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  LMS_POSTGRES_HOST LMS_POSTGRES_DB LMS_POSTGRES_USER LMS_POSTGRES_PASSWORD
  LAB_POSTGRES_HOST LAB_POSTGRES_DB LAB_POSTGRES_USER LAB_POSTGRES_PASSWORD
  CHAT_POSTGRES_HOST CHAT_POSTGRES_DB CHAT_POSTGRES_USER CHAT_POSTGRES_PASSWORD
  AI_POSTGRES_HOST AI_POSTGRES_DB AI_POSTGRES_USER AI_POSTGRES_PASSWORD
  REDIS_PASSWORD JWT_SECRET NEXTAUTH_SECRET QDRANT_URL QDRANT_API_KEY
  NEO4J_URI NEO4J_USERNAME NEO4J_PASSWORD R2_ENDPOINT
  MINIO_ROOT_USER MINIO_ROOT_PASSWORD AI_SERVICE_SECRET
  DOCKER_USERNAME DOCKER_PASSWORD
)

missing=()
for key in "${required_keys[@]}"; do
  if ! awk -F= -v wanted="$key" '$1 == wanted && length(substr($0, index($0, "=") + 1)) > 0 { found=1 } END { exit !found }' "$env_file"; then
    missing+=("$key")
  fi
done

if ((${#missing[@]})); then
  printf 'Missing required environment keys:' >&2
  printf ' %s' "${missing[@]}" >&2
  printf '\n' >&2
  exit 1
fi

override_file="$(mktemp)"
secret_file="$(mktemp)"
chmod 600 "$override_file" "$secret_file"
trap 'rm -f "$override_file" "$secret_file"' EXIT

# Use Compose's parser so duplicate keys, quotes, interpolation, and inline
# comments have exactly the same meaning as the currently running stack.
compose_file="$(dirname "$env_file")/docker-compose.serverless.yml"
if [[ ! -r "$compose_file" ]]; then
  echo "Cannot read Compose file: $compose_file" >&2
  exit 1
fi
docker compose --env-file "$env_file" -f "$compose_file" config --environment >"$secret_file"

# Only non-sensitive runtime settings are copied to this ConfigMap.
awk -F= '
  $1 ~ /^(SPRING_PROFILES_ACTIVE|VERSION|APP_ENV|LOG_LEVEL|POSTGRES_HOST|LMS_POSTGRES_HOST|LAB_POSTGRES_HOST|CHAT_POSTGRES_HOST|AI_POSTGRES_HOST|QDRANT_URL|NEO4J_URI|NEO4J_USERNAME|R2_ENDPOINT|AI_DB_SSL|CHAT_DB_SSL_MODE|MINIO_USE_SSL|LAB_MINIO_USE_SSL|HIKARI_MAX_POOL_SIZE|HIKARI_MIN_IDLE|HIKARI_CONNECTION_TIMEOUT|HIKARI_IDLE_TIMEOUT|HIKARI_MAX_LIFETIME|JPA_DDL_AUTO|JPA_SHOW_SQL|REDIS_POOL_SIZE|REDIS_MIN_IDLE_CONNS|REDIS_DIAL_TIMEOUT|REDIS_READ_TIMEOUT|REDIS_WRITE_TIMEOUT|REDIS_POOL_TIMEOUT|DB_MAX_OPEN_CONNS|DB_MAX_IDLE_CONNS|DB_CONN_MAX_LIFETIME|DB_CONN_MAX_IDLE_TIME|STORAGE_TYPE|LLM_PROVIDER|LLM_QUIZ_PROVIDER|EMBEDDING_MODEL|EMBEDDING_DIMENSIONS|EMBEDDING_PREFIX_MODE|RERANKER_MODEL|REINDEX_BATCH_SIZE|RERANK_FETCH_K|NEXT_PUBLIC_YOUTUBE_UPLOAD_ENABLED)$/ { print }
' "$secret_file" >"$override_file"

kubectl -n "$namespace" create secret generic bdc-secrets \
  --from-env-file="$secret_file" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "$namespace" create configmap bdc-env-overrides \
  --from-env-file="$override_file" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

docker_user="$(awk -F= '$1 == "DOCKER_USERNAME" { print substr($0, index($0, "=") + 1) }' "$secret_file")"
docker_password="$(awk -F= '$1 == "DOCKER_PASSWORD" { print substr($0, index($0, "=") + 1) }' "$secret_file")"
kubectl -n "$namespace" create secret docker-registry dockerhub-registry \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username="$docker_user" \
  --docker-password="$docker_password" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
unset docker_user docker_password

kubectl -n "$namespace" patch serviceaccount default \
  --type=merge \
  -p '{"imagePullSecrets":[{"name":"dockerhub-registry"}]}' >/dev/null

echo "Runtime Secrets and non-sensitive ConfigMap prepared in namespace $namespace."
