# Production CI/CD

Every push to `main` builds seven immutable `linux/amd64` application images on
GitHub-hosted runners, pushes both the commit SHA and `latest` tags to Docker
Hub, and dispatches deployment to the production self-hosted runner.

The production runner updates the existing K3s Deployments to the immutable SHA
tag, waits for every rollout, rolls changed Deployments back on failure, and
prunes only unused container images. Persistent volumes are never pruned.

## Required GitHub configuration

Create a protected GitHub Environment named `production`. Add the following as
repository-level secrets and variables because the GitHub-hosted build jobs also
need them:

| Type | Name | Purpose |
|---|---|---|
| Secret | `DOCKERHUB_USERNAME` | Docker Hub namespace |
| Secret | `DOCKERHUB_TOKEN` | Docker Hub access token with push/pull access |
| Secret | `SUBMODULE_TOKEN` | Fine-grained GitHub token with read access to `BDCHub---Frontend` |
| Secret | `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Frontend build-time public OAuth client ID |
| Variable | `NEXT_PUBLIC_CHAT_WS_URL` | Production WebSocket URL |
| Variable | `NEXTAUTH_URL` | Production application URL |

Docker Hub repositories must exist for `bdc-backend`, `bdc-lms`, `bdc-lab`,
`bdc-chat`, `bdc-ai`, `bdc-personalize`, and `bdc-frontend`.

Protect the `production` environment with required reviewers if deployments
must be manually approved.

## One-time runner installation

The server must have working outbound HTTPS, K3s, and non-root `kubectl` access.
Generate a fresh repository runner registration token, copy this repository's
`scripts/bootstrap-production-runner.sh` to the host, and enter the token without
placing it in shell history:

```bash
read -rsp 'Runner registration token: ' GITHUB_RUNNER_TOKEN && echo
export GITHUB_RUNNER_TOKEN
./bootstrap-production-runner.sh --purge-docker-engine
unset GITHUB_RUNNER_TOKEN
```

The purge option removes the legacy Docker Engine only after the script confirms
that all expected K3s Deployments exist. It does not remove K3s/containerd or
Kubernetes persistent volumes. Omit the option if Docker is still needed for an
unrelated workload.

Never save a runner registration token, Docker token, or SSH password in Git.
Runner registration tokens are short-lived and should be rotated immediately if
they are exposed.

## Manual rollback/redeploy

The workflow supports `workflow_dispatch`. Enter a previously published commit
SHA in `image_tag` to deploy that exact release without rebuilding it.

Kubernetes also retains rollout history:

```bash
kubectl rollout undo deployment/ai-service
kubectl rollout undo deployment/ai-worker
```
