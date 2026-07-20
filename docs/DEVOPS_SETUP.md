# DevOps Setup and Deployment Guide

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.0.0                     |
| Status    | Approved                  |
| Date      | 2026-05-29                |
| Authors   | BDC Team                  |
| Reviewers | BDC Architecture Group    |

## Revision History

| Version | Date       | Author   | Description                     |
|---------|------------|----------|---------------------------------|
| 1.0.0   | 2026-05-29 | BDC Team | Initial production deployment   |

---

## 1. Overview

This document provides instructions for setting up and maintaining the production deployment of the Big Data Club (BDC) application on a single virtual machine. 

The deployment topology places the Next.js frontend and all backend microservices on the same host machine. To optimize resource usage and simplify operations, all persistent storage is delegated to serverless or external cloud providers:
*   **Relational Databases**: PostgreSQL databases are hosted on Neon Serverless Postgres.
*   **Vector Database**: Semantic search collections are hosted on Qdrant Cloud.
*   **Knowledge Graph**: Graph nodes and relationships are hosted on Neo4j Aura.
*   **Object Storage**: Media files and documents are stored on Cloudflare R2 (compatible with the S3/MinIO API).
*   **Local Infrastructure**: Only Redis (caching and job queue status) and Apache Kafka (event bus broker) run locally in containers on the host.

> [!NOTE]
> **Kubernetes (K3s) Migration**:
> If you want to migrate your environment from Docker Compose to Kubernetes (K3s) for enhanced orchestration and scaling, please refer to the [Kubernetes Migration Guide](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/DOCKER_TO_K8S_MIGRATION.md).

---

## 2. Deployment Architecture

```
+-----------------------------------------------------------------------+
|                         Public Internet / Clients                     |
+----------------------------------+------------------------------------+
                                   | HTTP/HTTPS (Ports 80/443)
                                   v
+----------------------------------+------------------------------------+
|                         Traefik Reverse Proxy                         |
+----------------------------------+------------------------------------+
                                   | Route by hostname & path
                                   v
+----------------------------------+------------------------------------+
|                      Single Virtual Machine (Host)                    |
|                                                                       |
|  +------------------+  +------------------+  +---------------------+  |
|  |     frontend     |  |     backend      |  |     lms-backend     |  |
|  | (Next.js server) |  |(Spring Boot Auth)|  | (Go LMS service)    |  |
|  |    Port 3000     |  |    Port 8080     |  |    Port 8081        |  |
|  +--------+---------+  +--------+---------+  +----------+----------+  |
|           |                     |                       |             |
|           +---------------------+-----------------------+             |
|                                 | Docker Internal Network             |
|                                 v                                     |
|  +------------------+  +------------------+  +---------------------+  |
|  |    redis-lms     |  |      kafka       |  |     ai-service      |  |
|  |     (Cache)      |  | (Message Broker) |  |   (FastAPI HTTP)    |  |
|  |    Port 6379     |  |    Port 9092     |  |    Port 8000        |  |
|  +------------------+  +------------------+  +----------+----------+  |
|                                                         |             |
|                                                         v             |
|                                              +----------+----------+  |
|                                              |      ai-worker      |  |
|                                              |   (Kafka Consumer)  |  |
|                                              +---------------------+  |
+----------------------------------+------------------------------------+
                                   |
                                   | External Cloud API calls
                                   v
+-----------------------------------------------------------------------+
|                         Serverless Storage / DB                       |
|                                                                       |
|  +------------------+  +------------------+  +---------------------+  |
|  |   Neon Postgres  |  |   Qdrant Cloud   |  |     Neo4j Aura      |  |
|  | (Auth, LMS, AI)  |  |  (Vector Store)  |  |  (Knowledge Graph)  |  |
|  +------------------+  +------------------+  +---------------------+  |
|  |  Cloudflare R2   |                                                 |
|  | (Object Storage) |                                                 |
|  +------------------+                                                 |
+-----------------------------------------------------------------------+
```

---

## 3. Server Directory Layout

To maintain security and reduce storage overhead, application source code must not reside on the production server. The deployment directory contains only configuration files, shell scripts, and local logs or data folders.

The standard path for deployment on the production server is `/home/bdc_web/codespace/bdc_deploy/`.

The directory layout on the server is configured as follows:

```
/home/bdc_web/codespace/bdc_deploy/
├── .env                              # Production environment variables (never committed)
├── docker-compose.serverless.yml     # Production Docker Compose file
├── deploy.sh                         # Bootstrap and deploy validation script
├── update.sh                         # Individual or global service update script
├── Makefile                          # Convenience wrapper commands
├── logs/                             # Host directory for container log mounts
│   ├── backend/
│   ├── lms/
│   └── frontend/
└── data/                             # Host directory for persistent local data mounts
    └── frontend/
```

---

## 4. Setup Instructions for a New Host Server

### 4.1. Install System Dependencies

Update the host operating system packages and install Docker with the Docker Compose plugin. The following commands are for Ubuntu 22.04 LTS or newer:

```bash
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release rsync

# Add Docker Official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the stable repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Verify that docker is active and the compose plugin is accessible:

```bash
docker --version
docker compose version
```

### 4.2. Create Deployment Directory Structure

Create the application folder structure and set the appropriate owner permissions:

```bash
sudo mkdir -p /home/bdc_web/codespace/bdc_deploy/logs/backend
sudo mkdir -p /home/bdc_web/codespace/bdc_deploy/logs/lms
sudo mkdir -p /home/bdc_web/codespace/bdc_deploy/logs/frontend
sudo mkdir -p /home/bdc_web/codespace/bdc_deploy/data/frontend

# Set ownership to the deploy user (e.g., bdc_web)
sudo chown -R bdc_web:bdc_web /home/bdc_web/codespace
```

### 4.3. Initialize the Environment Variables File

Create the `.env` configuration file in the target directory:

```bash
cd /home/bdc_web/codespace/bdc_deploy
touch .env
chmod 600 .env
```

Open `.env` and configure all required variables using the reference template below:

```ini
# =============================================================================
# Application Settings
# =============================================================================
SPRING_PROFILES_ACTIVE=docker
VERSION=1.0.0
APP_ENV=production

# =============================================================================
# Ports
# =============================================================================
FRONTEND_PORT=3000
BACKEND_PORT=8080
LMS_PORT=8081
REDIS_PORT=6379

# =============================================================================
# Shared JWT Security & Secrets (Must be identical across all services)
# =============================================================================
JWT_SECRET=your_secure_jwt_secret_minimum_32_characters
NEXTAUTH_SECRET=your_nextauth_session_secret_minimum_32_characters
LMS_API_SECRET=your_shared_lms_sync_secret_hash
LMS_SYNC_SECRET=your_shared_lms_sync_secret_hash
AI_SERVICE_SECRET=your_shared_ai_service_secret

# =============================================================================
# Domain Routing URLs
# =============================================================================
NEXTAUTH_URL=https://bdc.hpcc.vn
APP_PUBLIC_URL=https://bdc.hpcc.vn
CORS_ALLOWED_ORIGINS=https://bdc.hpcc.vn,http://localhost:3000
BACKEND_URL=http://backend:8080
LMS_API_URL=http://lms-backend:8081
AI_SERVICE_URL=http://ai-service:8000

# =============================================================================
# Third Party Integrations
# =============================================================================
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
EMAIL=your_system_notification_gmail_address
EMAIL_PASSWORD=your_gmail_app_16_character_secret
GOOGLE_SCRIPT_URL=https://script.google.com/macros/s/.../exec

YOUTUBE_CLIENT_ID=your_youtube_api_client_id
YOUTUBE_CLIENT_SECRET=your_youtube_api_client_secret
YOUTUBE_REDIRECT_URL=https://bdc.hpcc.vn/api/youtube/callback
YOUTUBE_REDIRECT_URI=https://bdc.hpcc.vn/api/youtube/callback
NEXT_PUBLIC_YOUTUBE_UPLOAD_ENABLED=true

# =============================================================================
# LLM Providers (FastAPI AI service)
# =============================================================================
GROQ_API_KEY=gsk_your_groq_api_key
AI_CHAT_MODEL=llama-3.1-8b-instant
AI_QUIZ_MODEL=llama-3.3-70b-versatile
AI_KEY_ENCRYPTION_SECRET=your_encryption_secret_key

# =============================================================================
# Docker Hub Access Details
# =============================================================================
DOCKER_USERNAME=your_dockerhub_username
DOCKER_PASSWORD=your_dockerhub_token_or_password
IMAGE_TAG=latest

# =============================================================================
# Relational Databases (Neon Serverless PostgreSQL)
# =============================================================================
POSTGRES_HOST=ep-your-auth-db.ap-southeast-1.aws.neon.tech
POSTGRES_DB=auth
POSTGRES_USER=your_auth_db_username
POSTGRES_PASSWORD=your_auth_db_password

LMS_POSTGRES_HOST=ep-your-lms-db.ap-southeast-1.aws.neon.tech
LMS_POSTGRES_DB=lms
LMS_POSTGRES_USER=your_lms_db_username
LMS_POSTGRES_PASSWORD=your_lms_db_password

AI_POSTGRES_HOST=ep-your-ai-db.ap-southeast-1.aws.neon.tech
AI_POSTGRES_DB=ai
AI_POSTGRES_USER=your_ai_db_username
AI_POSTGRES_PASSWORD=your_ai_db_password
AI_DB_SSL=require

# =============================================================================
# Caching (Redis Stack in Container)
# =============================================================================
REDIS_PASSWORD=your_redis_container_password

# =============================================================================
# Vector Database (Qdrant Serverless)
# =============================================================================
QDRANT_URL=https://your-qdrant-instance.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_cloud_api_key

# =============================================================================
# Knowledge Graph (Neo4j Aura Serverless)
# =============================================================================
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_aura_password

# =============================================================================
# Cloud Storage (Cloudflare R2 API compatibility)
# =============================================================================
STORAGE_TYPE=minio
R2_ENDPOINT=your_cloudflare_account_id.r2.cloudflarestorage.com
MINIO_ROOT_USER=your_r2_access_key_id
MINIO_ROOT_PASSWORD=your_r2_secret_access_key
```

### 4.4. Set Up the Self-Hosted GitHub Actions Runner

To run CD actions directly on the server without SSH port exposures, configure a self-hosted runner:

1.  Navigate to your GitHub Repository -> **Settings** -> **Actions** -> **Runners** -> **New self-hosted runner**.
2.  Select **Linux** and architecture **x64**.
3.  Execute the download and configuration command scripts shown on the screen under the `bdc_web` user.
4.  Configure the runner as a background service:
    ```bash
    sudo ./svc.sh install bdc_web
    sudo ./svc.sh start
    ```
5.  Ensure the runner label includes `self-hosted`, `linux`, `production`, `deploy` to match the target criteria in `.github/workflows/cd-production.yml`.

---

## 5. CI/CD Pipeline Operation

```
  Developer          GitHub Actions (CI)       Docker Hub       Self-Hosted Runner (CD)
      |                       |                     |                      |
      |-- git push to main -->|                     |                      |
      |                       |-- compile & test -->|                      |
      |                       |-- build images ---->|                      |
      |                       |-- push images ----->|                      |
      |                       |                     |                      |
      |                       |-- trigger CD ----------------------------->|
      |                       |                     |                      |  sparse checkout server/
      |                       |                     |                      |  rsync config to APP_DIR
      |                       |                     |                      |  clean actions runner temp
      |                       |                     |                      |-- docker login & pull --->
      |                       |                     |                      |-- recreate containers --->
      |                       |                     |                      |-- verify health check --->
```

### 5.1. Continuous Integration (CI)
When code is pushed to `main` or a pull request is merged, the `CI - Build, Test & Push` pipeline:
1.  Detects which directories have changed (e.g. `frontend/`, `lms-service/`, `auth-and-management-service/`).
2.  Initializes isolated compiler runtimes to build binaries and run unit tests.
3.  Builds production-ready Docker images and tags them with the branch/commit details.
4.  Pushes the compiled Docker images to your configured Docker Hub registry.

#### Next.js Build-Time vs Runtime Variables
Next.js distinguishes between client-side and server-side variables:
*   **Server-Side Variables** (`BACKEND_URL`, `LMS_API_URL`, `AI_SERVICE_URL`): These are retrieved dynamically at runtime by Next.js `rewrites()`. They do **not** need to be baked into the image at build time. When both frontend and backend run on the same server, the container reads the runtime values (`http://backend:8080`, etc.) configured in `docker-compose.serverless.yml`.
*   **Client-Side Variables** (prefixed with `NEXT_PUBLIC_`, e.g. `NEXT_PUBLIC_GOOGLE_CLIENT_ID`): These are inlined at compile time. They must be supplied as Docker `--build-arg` variables during the build process. In GitHub Actions, add these values as Repository Secrets (e.g., `NEXT_PUBLIC_GOOGLE_CLIENT_ID`) to automatically embed them.

### 5.2. Continuous Delivery (CD)
Upon successful completion of the CI workflow, the `CD - Deploy Production` pipeline:
1.  Triggers the runner environment on the production server.
2.  Performs a **sparse checkout** to only download the `server` directory configuration files into a temporary workspace.
3.  Synchronizes only the `server` files into `/home/bdc_web/codespace/bdc_deploy/` using `rsync` (preventing any overwrite of the persistent `.env` file).
4.  Completely deletes all cloned files in the temporary runner workspace to ensure no source code is left behind.
5.  Logs into Docker Hub using the credentials stored in `/home/bdc_web/codespace/bdc_deploy/.env`.
6.  Pulls the latest images for the services from Docker Hub.
7.  Starts/restarts updated containers in detached mode.
8.  Verifies health check endpoints of all services (Frontend, Auth, LMS, AI) on localhost ports.

### 5.3. Manual Local Build (Optional for Administrators)
If you need to build and push the images manually without relying on GitHub Actions, use the `build-local.sh` utility:

1.  Make sure your local machine contains the full source code repository.
2.  Populate your local `.env` file in the root workspace folder with your `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `IMAGE_TAG`, and any required compile-time variables (like `NEXT_PUBLIC_GOOGLE_CLIENT_ID`).
3.  Execute the local build script inside the `server/` directory:
    ```bash
    cd server
    bash build-local.sh
    ```
    This script automatically reads your `.env` configuration, logs into Docker Hub, builds all service images (injecting the correct Next.js compile-time arguments), and pushes the built images to Docker Hub.

    To build and push a specific service only:
    ```bash
    bash build-local.sh frontend
    ```

---

## 6. Standard Operating Commands on the Server

All administrative commands must be executed within the deployment folder `/home/bdc_web/codespace/bdc_deploy/`.

### 6.1. Deployment Commands

*   **Deploy Stack / Update All Services**:
    Reads the `.env` variables, logs in to Docker Hub, pulls the latest images, and recreates the containers:
    ```bash
    make deploy
    # OR
    bash deploy.sh
    ```

*   **Check Running Container Status**:
    ```bash
    make status
    ```

*   **View Real-Time Container Logs**:
    To watch logs for all containers:
    ```bash
    make logs
    ```
    To watch logs for a specific service:
    ```bash
    make logs SERVICE=frontend
    ```

*   **Stop the Stack**:
    Stops all containers but preserves local volumes (named and host-mapped):
    ```bash
    make stop
    ```

*   **Restart a Specific Service**:
    ```bash
    make restart SERVICE=lms-backend
    ```

*   **Execute Health Check curl Verification**:
    ```bash
    make health
    ```

*   **Clean Unused Docker Resources**:
    Stops container instances with removed configurations and prunes dangling images safely:
    ```bash
    make clean
    ```

### 6.2. Service Update Script (`update.sh`)

Use the update script to pull and restart specific containers without restarting the entire stack.

*   **Update a single service** (e.g., Auth service):
    ```bash
    make update-service SERVICE=backend
    # OR
    bash update.sh backend
    ```

*   **Update multiple specific services**:
    ```bash
    bash update.sh frontend lms-backend
    ```

*   **Update all services**:
    ```bash
    make update
    # OR
    bash update.sh
    ```

---

## 7. Required Secrets in GitHub Actions

For the CI/CD pipeline to function correctly, the following Secrets must be defined in your GitHub Repository under **Settings** -> **Secrets and variables** -> **Actions**:

| Secret Key | Description |
|---|---|
| `DOCKER_USERNAME` | Your Docker Hub account username |
| `DOCKER_PASSWORD` | Your Docker Hub Personal Access Token (PAT) with read/write access |

No server SSH secrets are required because the runner is self-hosted on the host and runs locally behind your firewall.
