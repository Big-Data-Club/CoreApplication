# BDC Hub — Server Setup & Step-by-Step Deployment Guide

This guide walks through setting up a fresh VM and deploying the full BDC Hub stack:
**CoreApp (Serverless DB) + Monitoring + Performance Tests**.

Target Server: `bdc_web@10.1.8.133` (accessed via VPN + SSH)

---

## Prerequisites

| Requirement | Minimum Spec |
|-------------|-------------|
| OS | Ubuntu 20.04+ or Debian 11+ |
| CPU | 4 cores |
| RAM | 8 GB (16 GB recommended — AI service needs ~2–4 GB) |
| Disk | 40 GB free |
| Network | Outbound HTTPS to Neon, Cloudflare R2, Qdrant Cloud, Neo4j Aura, Groq API |

---

## Step 1 — Connect to the Server

On your local machine, connect via VPN first, then SSH:

```bash
ssh bdc_web@10.1.8.133
```

---

## Step 2 — Stop & Clean Up Existing Docker Stack

> You do **not** need to uninstall Docker. K3s uses its own container runtime (containerd) independently.

```bash
# Navigate to the running CoreApplication directory
cd ~/CoreApplication   # adjust path if different

# Stop all Docker Compose services and remove named volumes
docker compose -f docker-compose.serverless.yml down --volumes --remove-orphans

# Optional: prune unused Docker images to free disk space
docker image prune -af
docker volume prune -f
```

Verify all containers are stopped:

```bash
docker ps -a   # should show no running containers
```

---

## Step 3 — Install K3s (Lightweight Kubernetes)

K3s installs in a single command and ships Traefik Ingress + `kubectl` automatically:

```bash
curl -sfL https://get.k3s.io | sh -
```

Wait ~60 seconds for K3s to start. Then verify the node is ready:

```bash
sudo k3s kubectl get nodes
# Expected output:
# NAME     STATUS   ROLES                  AGE   VERSION
# <host>   Ready    control-plane,master   30s   v1.x.x+k3s1
```

---

## Step 4 — Configure kubectl Access (Non-root)

Allow the `bdc_web` user to run `kubectl` without `sudo`:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
chmod 600 ~/.kube/config
```

Test:

```bash
kubectl get nodes
# Should show the node as Ready
```

---

## Step 5 — Copy K8s Configuration to the Server

From your **local machine** (where this repo is checked out):

```bash
# Copy the entire k8s/ directory to the server
scp -r /home/phucnhan/codespace/bdc/k8s bdc_web@10.1.8.133:/home/bdc_web/k8s

# Also copy performance tests
scp -r /home/phucnhan/codespace/bdc/BDCHub---Monitoring/performance-tests \
    bdc_web@10.1.8.133:/home/bdc_web/performance-tests
```

SSH back into the server and verify:

```bash
ssh bdc_web@10.1.8.133
ls ~/k8s/
# Should list: base/ overlays/ monitoring/ README.md
```

---

## Step 6 — Configure Secrets

> ⚠️ **All secret values must be Base64-encoded.** Plain text values will not work.

Encode any value with:

```bash
echo -n "your-actual-value" | base64
```

Edit the secrets file:

```bash
nano ~/k8s/base/secrets.yaml
```

Replace every `VE9ET19DSEFOR0VfTUU=` placeholder with the real Base64-encoded value.
The full mapping from your `.env` file to `secrets.yaml` keys:

| `secrets.yaml` key | Your `.env` variable |
|--------------------|--------------------|
| `POSTGRES_DB` | `POSTGRES_DB` |
| `POSTGRES_USER` | `POSTGRES_USER` |
| `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD` |
| `LMS_POSTGRES_DB` | `LMS_POSTGRES_DB` |
| `LMS_POSTGRES_USER` | `LMS_POSTGRES_USER` |
| `LMS_POSTGRES_PASSWORD` | `LMS_POSTGRES_PASSWORD` |
| `LAB_POSTGRES_DB` | `LAB_POSTGRES_DB` |
| `LAB_POSTGRES_USER` | `LAB_POSTGRES_USER` |
| `LAB_POSTGRES_PASSWORD` | `LAB_POSTGRES_PASSWORD` |
| `AI_POSTGRES_DB` | `AI_POSTGRES_DB` |
| `AI_POSTGRES_USER` | `AI_POSTGRES_USER` |
| `AI_POSTGRES_PASSWORD` | `AI_POSTGRES_PASSWORD` |
| `CHAT_POSTGRES_DB` | `CHAT_POSTGRES_DB` |
| `CHAT_POSTGRES_USER` | `CHAT_POSTGRES_USER` |
| `CHAT_POSTGRES_PASSWORD` | `CHAT_POSTGRES_PASSWORD` |
| `ADMIN_EMAIL` | `ADMIN_EMAIL` |
| `ADMIN_PASSWORD` | `ADMIN_PASSWORD` |
| `MINIO_ROOT_USER` | `MINIO_ROOT_USER` (R2 Access Key ID) |
| `MINIO_ROOT_PASSWORD` | `MINIO_ROOT_PASSWORD` (R2 Secret Access Key) |
| `REDIS_PASSWORD` | `REDIS_PASSWORD` |
| `JWT_SECRET` | `JWT_SECRET` |
| `NEXTAUTH_SECRET` | `NEXTAUTH_SECRET` |
| `GROQ_API_KEY` | `GROQ_API_KEY` |
| `GOOGLE_CLIENT_ID` | `GOOGLE_CLIENT_ID` |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| `YOUTUBE_CLIENT_ID` | `YOUTUBE_CLIENT_ID` |
| `YOUTUBE_CLIENT_SECRET` | `YOUTUBE_CLIENT_SECRET` |
| `YOUTUBE_REDIRECT_URI` | `YOUTUBE_REDIRECT_URI` |
| `CLOUDINARY_CLOUD_NAME` | `CLOUDINARY_CLOUD_NAME` |
| `CLOUDINARY_API_KEY` | `CLOUDINARY_API_KEY` |
| `CLOUDINARY_API_SECRET` | `CLOUDINARY_API_SECRET` |
| `AI_SERVICE_SECRET` | `AI_SERVICE_SECRET` |
| `AI_KEY_ENCRYPTION_SECRET` | `AI_KEY_ENCRYPTION_SECRET` |
| `LMS_API_SECRET` | `LMS_API_SECRET` |
| `LMS_SYNC_SECRET` | `LMS_SYNC_SECRET` |
| `CHAT_SYNC_SECRET` | `CHAT_SYNC_SECRET` |
| `EMAIL` | `EMAIL` |
| `EMAIL_PASSWORD` | `EMAIL_PASSWORD` |
| `APP_PUBLIC_URL` | `APP_PUBLIC_URL` (e.g., `https://bdc.hpcc.vn`) |
| `NEXTAUTH_URL` | `NEXTAUTH_URL` |
| `NEXT_PUBLIC_CHAT_WS_URL` | `NEXT_PUBLIC_CHAT_WS_URL` |

---

## Step 7 — Configure External Database Endpoints (Serverless Overlay)

Edit the serverless configmap to point to your actual managed database hosts:

```bash
nano ~/k8s/overlays/serverless/configmap-serverless.yaml
```

Replace the placeholder hostnames with your real values:

| Key | Where to find it |
|-----|-----------------|
| `POSTGRES_HOST` | Neon dashboard → Auth project → Connection string host |
| `LMS_POSTGRES_HOST` | Neon dashboard → LMS project |
| `LAB_POSTGRES_HOST` | Neon dashboard → Lab project |
| `CHAT_POSTGRES_HOST` | Neon dashboard → Chat project |
| `AI_POSTGRES_HOST` | Neon dashboard → AI project |
| `QDRANT_URL` | Qdrant Cloud → Cluster → REST endpoint URL |
| `NEO4J_URI` | Neo4j Aura → Connection URL (`bolt+s://...`) |
| `R2_ENDPOINT` | Cloudflare dashboard → R2 → Bucket → S3 API URL |
| `LAB_R2_ENDPOINT` | Same as above (or separate bucket) |

Also add `QDRANT_API_KEY` to secrets.yaml (Qdrant Cloud API key).

---

## Step 8 — Deploy CoreApplication (Serverless Mode)

```bash
cd ~/k8s

# Dry-run first to verify everything resolves correctly
kubectl apply -k overlays/serverless/ --dry-run=client

# Deploy for real
kubectl apply -k overlays/serverless/
```

Watch pods start up:

```bash
kubectl get pods -w
```

Expected final state (all pods `Running`):

```
NAME                                   READY   STATUS    RESTARTS   AGE
auth-service-xxxxxxxxx-xxxxx           1/1     Running   0          5m
lms-service-xxxxxxxxx-xxxxx            1/1     Running   0          5m
lab-service-xxxxxxxxx-xxxxx            1/1     Running   0          5m
chat-service-xxxxxxxxx-xxxxx           1/1     Running   0          5m
ai-service-xxxxxxxxx-xxxxx             1/1     Running   0          8m   ← slower (loads ML models)
ai-worker-xxxxxxxxx-xxxxx              1/1     Running   0          8m
personalize-service-xxxxxxxxx-xxxxx    1/1     Running   0          5m
frontend-xxxxxxxxx-xxxxx               1/1     Running   0          5m
kafka-0                                1/1     Running   0          5m
redis-0                                1/1     Running   0          3m
```

> **Note:** `ai-service` and `ai-worker` may take 2–5 minutes to become `Ready` because they download and load the embedding model (`BAAI/bge-m3`) on first start. This is expected — the `startupProbe` allows up to 150 seconds.

Check service endpoints:

```bash
kubectl get svc
kubectl get ingress
```

Test health endpoints:

```bash
# From inside the server (internal cluster DNS)
curl http://auth-service:8080/actuator/health
curl http://lms-service:8081/health
curl http://ai-service:8000/health

# From outside (via domain)
curl https://bdc.hpcc.vn/apiv1/actuator/health
```

---

## Step 9 — Deploy Monitoring Stack

```bash
cd ~/k8s

kubectl apply -k monitoring/
```

Verify monitoring pods:

```bash
kubectl get pods -l app=prometheus
kubectl get pods -l app=grafana
kubectl get pods -l app=node-exporter
```

Access Grafana dashboard in your browser:

```
https://bdc.hpcc.vn/monitor
```

Default login: `admin` / `admin` — **change this immediately** after first login.

Prometheus is reachable internally at `http://prometheus-service:9090`.

### Verify Prometheus is scraping targets

Open the Prometheus UI (you can port-forward temporarily):

```bash
kubectl port-forward svc/prometheus-service 9090:9090
# Open http://localhost:9090/targets in your browser
```

All configured targets should show `UP`:
- `prometheus` (self-scrape)
- `node-exporter` (host metrics)
- `auth-service` (`/actuator/prometheus`)
- `lms-service`, `lab-service`, `chat-service`, `ai-service` (`/metrics`)

---

## Step 10 — Deploy BDCHub Frontend (Standalone Repo)

The `BDCHub---Frontend` repo is a **separate Next.js project** that can be deployed either:
- As a **K8s Deployment** (add to your cluster)
- Or as a **Vercel/Netlify static deployment** pointing its API calls back to the K3s VM

### Option A — Deploy as K8s Deployment (recommended for VPN-only access)

Build and push the Docker image first:

```bash
# From your local machine inside BDCHub---Frontend/
cd /home/phucnhan/codespace/bdc/BDCHub---Frontend

docker build \
  --build-arg NEXT_PUBLIC_GOOGLE_CLIENT_ID=your-google-client-id \
  -t your-dockerhub-username/bdc-standalone-frontend:latest .

docker push your-dockerhub-username/bdc-standalone-frontend:latest
```

Create a minimal K8s deployment on the server:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend-standalone
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend-standalone
  template:
    metadata:
      labels:
        app: frontend-standalone
    spec:
      containers:
      - name: frontend
        image: your-dockerhub-username/bdc-standalone-frontend:latest
        ports:
        - containerPort: 3000
        env:
        - name: PORT
          value: "3000"
        - name: BACKEND_URL
          value: "http://auth-service:8080"
        - name: LMS_API_URL
          value: "http://lms-service:8081"
        - name: AI_SERVICE_URL
          value: "http://ai-service:8000"
        - name: NEXTAUTH_URL
          value: "https://bdc.hpcc.vn"
        - name: NEXTAUTH_SECRET
          valueFrom:
            secretKeyRef:
              name: bdc-secrets
              key: NEXTAUTH_SECRET
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-standalone
spec:
  ports:
  - port: 3000
    targetPort: 3000
  selector:
    app: frontend-standalone
EOF
```

### Option B — Deploy to Vercel (zero-server)

```bash
cd /home/phucnhan/codespace/bdc/BDCHub---Frontend
npx vercel --prod
```

Set environment variables in the Vercel dashboard pointing to your K3s VM's public IP/domain.

---

## Step 11 — Performance Testing with k6

The performance tests are located in `BDCHub---Monitoring/performance-tests/`.

### Available Test Scripts

| Script | Description |
|--------|-------------|
| `k6_student_flow.js` | Simulates student browsing courses, viewing content |
| `k6_teacher_flow.js` | Simulates teacher creating/managing courses |
| `k6_admin_flow.js` | Simulates admin user management |
| `k6_multi_role_flow.js` | All roles running simultaneously (most realistic) |

### Test Types (controlled via `TEST_TYPE` env var)

| `TEST_TYPE` | Description |
|-------------|-------------|
| `smoke` | 1 VU, 1 iteration — quick sanity check |
| `load` | Ramp up to moderate concurrent users over 5 min |
| `stress` | Ramp up to maximum load to find breaking point |

### Option A — Run with Docker (easiest, from monitoring server or local machine)

```bash
cd ~/performance-tests  # or /path/to/BDCHub---Monitoring/performance-tests

# Smoke test (quick sanity check)
docker run --rm -i \
  -e BASE_URL=https://bdc.hpcc.vn \
  -e TEST_TYPE=smoke \
  -e AI_SERVICE_SECRET=your-ai-service-secret \
  -v $(pwd):/io \
  grafana/k6:latest run /io/k6_multi_role_flow.js

# Load test
docker run --rm -i \
  -e BASE_URL=https://bdc.hpcc.vn \
  -e TEST_TYPE=load \
  -e AI_SERVICE_SECRET=your-ai-service-secret \
  -e COURSE_ID=1 \
  -e NODE_ID=1 \
  -v $(pwd):/io \
  grafana/k6:latest run /io/k6_multi_role_flow.js

# Stress test
docker run --rm -i \
  -e BASE_URL=https://bdc.hpcc.vn \
  -e TEST_TYPE=stress \
  -e AI_SERVICE_SECRET=your-ai-service-secret \
  -v $(pwd):/io \
  grafana/k6:latest run /io/k6_multi_role_flow.js
```

### Option B — Install k6 natively on the server

```bash
# Install k6
sudo gpg -k
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
  sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6 -y

# Run test
cd ~/performance-tests
BASE_URL=https://bdc.hpcc.vn \
TEST_TYPE=load \
AI_SERVICE_SECRET=your-ai-service-secret \
k6 run k6_multi_role_flow.js
```

### Seed Test Users into the Database (Required Before Running Tests)

The k6 tests require pre-seeded users. Run the SQL seed script against your Auth database:

```bash
# Connect to Neon Auth DB
psql "postgresql://USER:PASS@your-neon-host.neon.tech/auth?sslmode=require" \
  -f ~/performance-tests/seed_users.sql
```

After testing, clean up:

```bash
psql "postgresql://USER:PASS@your-neon-host.neon.tech/auth?sslmode=require" \
  -f ~/performance-tests/cleanup_users.sql
```

### Viewing Test Results in Grafana

k6 can write results directly to Prometheus (via remote write) so they appear in Grafana:

```bash
K6_PROMETHEUS_RW_SERVER_URL=http://prometheus-service:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM=true \
BASE_URL=https://bdc.hpcc.vn \
TEST_TYPE=load \
k6 run --out experimental-prometheus-rw k6_multi_role_flow.js
```

The Grafana dashboard `k6-performance.json` (already provisioned) will show request rates, response times, error rates, and VU counts in real time.

---

## Troubleshooting

### Pod stuck in `Pending`
```bash
kubectl describe pod <pod-name>
```
Most common cause: insufficient memory. Check `kubectl top nodes`.

### Pod stuck in `CrashLoopBackOff`
```bash
kubectl logs <pod-name> --previous
```

### AI service slow to start / `startupProbe` failing
This is expected on first boot — the model cache is empty and `BAAI/bge-m3` (~1.2 GB) must be downloaded. Wait up to 5 minutes. On subsequent restarts it loads from the emptyDir cache.

> **For production:** Pre-bake the model into the Docker image during CI/CD to eliminate this startup delay entirely.

### Ingress / Traefik Middlewares not applying
K3s Traefik must be version 2.x for `traefik.io/v1alpha1` CRDs. Verify:
```bash
kubectl get pod -n kube-system | grep traefik
kubectl logs -n kube-system deploy/traefik
```

### Check all services are up
```bash
kubectl get pods,svc,ingress
```

---

## Updating Deployments (Rolling Update)

To update an image after a new build is pushed:

```bash
# Force a rollout restart to pull the latest image (if tag is 'latest')
kubectl rollout restart deployment/lms-service
kubectl rollout restart deployment/ai-service
kubectl rollout restart deployment/frontend

# Watch the rollout
kubectl rollout status deployment/lms-service
```

---

## Tear Down

```bash
# Remove all CoreApp resources
kubectl delete -k ~/k8s/overlays/serverless/

# Remove monitoring resources
kubectl delete -k ~/k8s/monitoring/

# Remove K3s entirely (if needed)
/usr/local/bin/k3s-uninstall.sh
```
