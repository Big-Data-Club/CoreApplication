#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/Big-Data-Club/CoreApplication}"
RUNNER_ROOT="${RUNNER_ROOT:-/opt/actions-runner}"
RUNNER_USER="${RUNNER_USER:-bdc_web}"
RUNNER_LABELS="${RUNNER_LABELS:-production}"
PURGE_DOCKER_ENGINE=false

usage() {
  echo "Usage: GITHUB_RUNNER_TOKEN=<one-time-token> $0 [--purge-docker-engine]"
}

for arg in "$@"; do
  case "$arg" in
    --purge-docker-engine) PURGE_DOCKER_ENGINE=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

: "${GITHUB_RUNNER_TOKEN:?Set the one-time GITHUB_RUNNER_TOKEN without saving it to disk}"

if [[ "$(id -un)" != "$RUNNER_USER" ]]; then
  echo "Run this script as ${RUNNER_USER}; it will use sudo only where required." >&2
  exit 1
fi

for command in curl tar python3 kubectl sudo; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

kubectl get node >/dev/null
for deployment in auth-service lms-service lab-service chat-service ai-service ai-worker personalize-service frontend; do
  kubectl get "deployment/${deployment}" >/dev/null
  kubectl rollout status "deployment/${deployment}" --timeout=2m >/dev/null
done

runner_version="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')"
architecture="$(uname -m)"
case "$architecture" in
  x86_64) runner_arch=x64 ;;
  aarch64|arm64) runner_arch=arm64 ;;
  *) echo "Unsupported architecture: $architecture" >&2; exit 1 ;;
esac

archive="actions-runner-linux-${runner_arch}-${runner_version}.tar.gz"
temporary_archive="$(mktemp "/tmp/${archive}.XXXXXX")"
trap 'rm -f "$temporary_archive"' EXIT

sudo install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_ROOT"
curl -fsSL "https://github.com/actions/runner/releases/download/v${runner_version}/${archive}" -o "$temporary_archive"
tar -xzf "$temporary_archive" -C "$RUNNER_ROOT"

cd "$RUNNER_ROOT"
if [[ -f .runner ]]; then
  echo "Runner is already configured at ${RUNNER_ROOT}; leaving registration unchanged."
else
  ./config.sh --unattended \
    --url "$REPOSITORY_URL" \
    --token "$GITHUB_RUNNER_TOKEN" \
    --name "$(hostname)-production" \
    --labels "$RUNNER_LABELS" \
    --work _work \
    --replace
fi

sudo ./svc.sh install "$RUNNER_USER" || true
sudo ./svc.sh start

echo "${RUNNER_USER} ALL=(root) NOPASSWD: /usr/local/bin/k3s crictl rmi --prune" \
  | sudo tee /etc/sudoers.d/bdc-actions-runner-k3s-cleanup >/dev/null
sudo chmod 0440 /etc/sudoers.d/bdc-actions-runner-k3s-cleanup
sudo visudo -cf /etc/sudoers.d/bdc-actions-runner-k3s-cleanup

# Docker is not used by K3s. Clean legacy objects only after confirming the
# Kubernetes production deployments above are present.
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    docker_command=(docker)
  else
    docker_command=(sudo docker)
  fi
  "${docker_command[@]}" ps -q | xargs --no-run-if-empty "${docker_command[@]}" stop
  "${docker_command[@]}" ps -aq | xargs --no-run-if-empty "${docker_command[@]}" rm
  "${docker_command[@]}" image prune --all --force
  "${docker_command[@]}" builder prune --all --force || true
  "${docker_command[@]}" network prune --force

  if [[ "$PURGE_DOCKER_ENGINE" == true ]]; then
    sudo systemctl disable --now docker.service docker.socket containerd.service 2>/dev/null || true
    sudo apt-get purge -y docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin docker.io 2>/dev/null || true
    sudo apt-get autoremove -y
  fi
fi

echo "Production runner installed with labels: self-hosted, Linux, ${runner_arch}, ${RUNNER_LABELS}"
