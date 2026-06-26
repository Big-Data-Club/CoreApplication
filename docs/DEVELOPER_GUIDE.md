# Developer Guide — BDC Application

> This guide is for **developers**, **contributors**, and anyone who wants to run the project locally, understand the codebase structure, or add new features. Read it once from top to bottom — it will save you a lot of debugging time later.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [Prerequisites](#3-prerequisites)
4. [Running the Full Stack with Docker](#4-running-the-full-stack-with-docker)
5. [Running Individual Services Locally](#5-running-individual-services-locally)
6. [Environment Variable Configuration](#6-environment-variable-configuration)
7. [System Workflows](#7-system-workflows)
8. [API Quick Reference](#8-api-quick-reference)
9. [Contributing](#9-contributing)
10. [CI/CD Pipeline](#10-cicd-pipeline)
11. [Troubleshooting](#11-troubleshooting)
12. [FAQ](#12-faq)

---

## 1. Project Overview

BDC Application is a **microservices-based Learning Management System (LMS)** consisting of 3 main services that communicate over an internal Docker network. Understanding the diagram below will help you debug problems much faster.

```
┌──────────────────────────────────────────────────────────────┐
│                      Browser / Client                        │
└──────────────────────────┬───────────────────────────────────┘
                           │ Port 3000
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Frontend — Next.js 14                           │
│   /apiv1/*  ────────► Spring Boot Backend  (proxy rewrite)   │
│   /lmsapiv1/* ──────► Go LMS Backend       (proxy rewrite)   │
│   /files/*  ────────► LMS file serving                       │
└──────────┬──────────────────────────────┬────────────────────┘
           │ :8080                         │ :8081
           ▼                               ▼
┌──────────────────────┐     ┌─────────────────────────────────┐
│   Auth Backend       │     │   LMS Backend                   │
│   Spring Boot 3.x    │◄────│   Go 1.21 + Gin                 │
│   - JWT / Auth       │     │   - Courses, Quizzes            │
│   - Users, Events    │     │   - Enrollments, File upload    │
│   - Announcements    │     │   - User sync from Auth         │
└──────────┬───────────┘     └──────────┬──────────────────────┘
           │                             │         │
           ▼                             ▼         ▼
┌──────────────────────┐  ┌─────────────────────┐  ┌──────────┐
│  PostgreSQL (Auth)   │  │  PostgreSQL (LMS)   │  │  Redis   │
│   Port: 5433         │  │   Port: 5434        │  │  :6379   │
└──────────────────────┘  └─────────────────────┘  └──────────┘
                                                   ┌──────────┐
                                                   │  MinIO   │
                                                   │ :9000/01 │
                                                   └──────────┘
```

### Technology Stack

| Component | Technology | Version |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, NextAuth.js | 14+ |
| Auth Backend | Spring Boot, Spring Security, JWT | 3.x (Java 21) |
| LMS Backend | Go, Gin framework, GORM | 1.21+ |
| Database | PostgreSQL | 15 |
| Cache | Redis | 7 |
| Object Storage | MinIO | Latest |
| Container | Docker, Docker Compose | 24+ / 2.0+ |

---

## 2. Directory Structure

```
CoreApplication/
│
├── 📁 frontend/           # Next.js application
│  ├── src/
│  │  ├── app/           # App Router (Next.js 14)
│  │  ├── components/       # Reusable React components
│  │  └── lib/           # Utility functions, custom hooks
│  ├── next.config.ts        # Next.js config + proxy rewrites ← IMPORTANT
│  └── Dockerfile
│
├── 📁 auth-and-management-service/           # Spring Boot (Auth Service)
│  ├── src/main/java/com/example/demo/
│  │  ├── controller/       # REST Controllers
│  │  ├── service/         # Business logic
│  │  ├── repository/       # JPA Repositories
│  │  ├── model/          # Entity / Domain models
│  │  └── config/         # Security, CORS, JWT config
│  ├── src/main/resources/
│  │  └── application.yml     # Spring Boot configuration
│  ├── init-scripts/        # SQL for Auth database initialization
│  ├── pom.xml
│  └── Dockerfile
│
├── 📁 lms-service/             # Go (LMS Service)
│  ├── cmd/server/main.go      # Entry point
│  ├── internal/
│  │  ├── handler/         # HTTP handlers (Gin)
│  │  ├── service/         # Business logic
│  │  ├── repository/       # Database queries (GORM)
│  │  └── model/          # Data models
│  ├── migrations/         # SQL migrations for LMS database
│  ├── go.mod
│  └── Dockerfile
│
├── 📁 docs/             # Technical documentation ← YOU ARE HERE
│  ├── DEVELOPER_GUIDE.md      # Setup and contribution workflow
│  ├── DEVELOPER_GUIDE.en.md    # English version
│  ├── TECHNICAL_NOTES.md      # Critical technical issues (VI)
│  └── TECHNICAL_NOTES.md    # Critical technical issues (EN)
│
├── 📁 .github/
│  ├── workflows/
│  │  ├── ci.yml          # CI: Build, Test, Push Docker image
│  │  └── cd-production.yml    # CD: Deploy to production
│  └── ISSUE_TEMPLATE/
│
├── docker-compose.yml        # Launch the full stack
├── .env.example           # Environment variable template ← COPY THIS
├── .env               # Actual config (NEVER commit this!)
```

> **Important:** `.env` contains sensitive information (passwords, JWT secrets...) and is listed in `.gitignore`. **Never commit** this file to the repository.

---

## 3. Prerequisites

### Running with Docker — Recommended for new developers

The simplest approach. You only need:

| Tool | Minimum Version | Download |
|---|---|---|
| Docker Desktop | 24.0+ | https://docs.docker.com/get-docker/ |
| Docker Compose | 2.0+ | Bundled with Docker Desktop |
| Git | Any | https://git-scm.com/ |

> Make sure Docker Desktop is running and has at least **4GB RAM** allocated under Settings -> Resources.

### Running services individually — For advanced development

If you want hot-reload and direct debugging on your machine:

| Tool | Version | Used For |
|---|---|---|
| Node.js + npm | 20 LTS | Frontend |
| JDK (Temurin) | 21 | Java Backend |
| Go | 1.21+ | LMS Service |

---

## 4. Running the Full Stack with Docker

This is the **fastest** way to get a complete working environment on your machine.

### Step 1 — Clone the repository

```bash
git clone https://github.com/Big-Data-Club/CoreApplication.git
cd CoreApplication
```

### Step 2 — Create your environment file

```bash
cp .env.example .env
```

Open `.env` and fill in the required values. See [Section 6](#6-environment-variable-configuration) for an explanation of each variable, and [TECHNICAL_NOTES.md](./TECHNICAL_NOTES.md) to learn which ones cause silent failures when set incorrectly.

### Step 3 — Build and launch

```bash
# First time — pulls images and builds, takes 3–5 minutes
docker compose up -d --build

# Subsequent launches with no code changes
docker compose up -d
```

### Step 4 — Check service status

```bash
# All STATUS values should be "healthy", not "starting"
docker compose ps

# Stream logs for specific services
docker compose logs -f frontend
docker compose logs -f backend
docker compose logs -f lms-backend
```

### Step 5 — Access the application

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Auth API | http://localhost:3000/apiv1 or http://localhost:8080 |
| LMS API | http://localhost:3000/lmsapiv1 or http://localhost:8081 |
| Swagger Auth | http://localhost:8080/swagger-ui.html |
| Swagger LMS | http://localhost:8081/swagger/index.html |
| MinIO Console | http://localhost:9001 |

### Stopping and cleaning up

```bash
docker compose down          # Stop all services, keep data
docker compose down -v         # Stop + delete all data (volumes)
docker compose restart backend     # Restart a single service
docker compose up -d --build frontend # Rebuild after code changes
```

---

## 5. Running Individual Services Locally

This approach is best when you are **focused on developing one service** and want faster hot-reload.

**Strategy:** Keep infrastructure services (database, Redis, MinIO) running in Docker, and run your target service directly on your machine.

```bash
# Start only infrastructure — no code rebuild needed
docker compose up -d postgres postgres-lms redis-lms minio
```

### 5.1 Frontend (Next.js)

```bash
cd frontend

npm install

# Create a local env file pointing URLs to localhost instead of Docker containers
cp .env.local.example .env.local
# Set: BACKEND_URL=http://localhost:8080, LMS_API_URL=http://localhost:8081

npm run dev  # Dev server with automatic hot-reload
```

Frontend runs at **http://localhost:3000**

**Useful scripts:**

| Command | Description |
|---|---|
| `npm run dev` | Dev server with hot-reload |
| `npm run build` | Production build |
| `npm run lint` | ESLint check |
| `npm run test:ci` | Run unit tests |

> **About proxy:** `next.config.ts` configures rewrites so `/apiv1/*` -> Spring Boot and `/lmsapiv1/*` -> Go. When running locally, make sure the backend services are listening on the expected ports.

### 5.2 Auth Backend (Spring Boot)

```bash
cd Backend

# Ensure PostgreSQL is running via Docker: docker compose ps postgres

# Run using Maven Wrapper (no Maven installation needed)
./mvnw spring-boot:run

# Or specify a specific profile
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Backend runs at **http://localhost:8080**

To connect to the local database, create `src/main/resources/application-local.yml`:

```yaml
spring:
 datasource:
  url: jdbc:postgresql://localhost:5433/club_db
  username: postgres
  password: 123456
```

**Useful Maven commands:**

| Command | Description |
|---|---|
| `./mvnw spring-boot:run` | Run dev server |
| `./mvnw test` | Run tests |
| `./mvnw clean package -DskipTests` | Build JAR without tests |
| `./mvnw clean package` | Build + test |

### 5.3 LMS Backend (Go + Gin)

```bash
cd LMS

go mod download

go run cmd/server/main.go
```

LMS Service runs at **http://localhost:8081**

Required environment variables when running locally (create a `.env` file in `lms-service/` or export):

```bash
export DB_HOST=localhost
export DB_PORT=5434
export DB_USER=lms_user
export DB_PASSWORD=lms_password
export DB_NAME=lms_db
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_PASSWORD=redis_password
export JWT_SECRET=your-dev-secret-min-32-chars
export APP_PORT=8081
```

**Useful Go commands:**

| Command | Description |
|---|---|
| `go run cmd/server/main.go` | Run dev server |
| `go test ./...` | Run all tests |
| `go test -v ./... -coverprofile=coverage.out` | Test + coverage report |
| `go build -v ./...` | Build with compile error check |
| `go vet ./...` | Static analysis |

---

## 6. Environment Variable Configuration

Copy `.env.example` to `.env` and fill in the values. Here's an explanation by group.

### Security — Must be changed

```env
# JWT: Secret key used to sign and verify tokens
# MUST be identical between Backend and LMS — MUST be >= 32 characters!
JWT_SECRET=replace-with-a-random-string-longer-than-32-chars

# NextAuth: Session encryption key for Next.js
NEXTAUTH_SECRET=replace-with-a-completely-different-random-string

# Shared secret for user sync between the two backends (must match)
LMS_API_SECRET=your-sync-secret
LMS_SYNC_SECRET=your-sync-secret  # must equal LMS_API_SECRET
```

> Generate a secure random string: `openssl rand -base64 32`

### URLs — Environment-dependent

```env
# Local development
NEXTAUTH_URL=http://localhost:3000
APP_PUBLIC_URL=http://localhost:3000  # Used in password reset emails

# Internal Docker network communication (keep as-is when using Docker Compose)
BACKEND_URL=http://backend:8080
LMS_API_URL=http://lms-backend:8081
```

### Database

```env
# Auth Database (PostgreSQL)
POSTGRES_DB=club_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-strong-password
POSTGRES_PORT=5433

# LMS Database (PostgreSQL)
LMS_POSTGRES_DB=lms_db
LMS_POSTGRES_USER=lms_user
LMS_POSTGRES_PASSWORD=your-strong-lms-password
LMS_POSTGRES_PORT=5434
```

### Redis & MinIO

```env
REDIS_PASSWORD=your-strong-redis-password
REDIS_PORT=6379

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=your-minio-password-8-plus-chars  # MinIO requires >= 8 chars
```

### Email

```env
EMAIL=your-email@gmail.com
EMAIL_PASSWORD=google-app-password-16-chars  # See TECHNICAL_NOTES.md Section 2

APP_PUBLIC_URL=http://localhost:3000  # Must be reachable by the email recipient's browser
```

> Incorrect email config will cause `bulkRegister` to create users silently without sending passwords — they cannot log in. See [TECHNICAL_NOTES.md — Section 2](./TECHNICAL_NOTES.md#2-email--gmail-smtp-configuration).

---

## 7. System Workflows

### Authentication Flow

```
Client      Frontend        Auth Backend (Spring)
 │         │             │
 │── POST /apiv1/auth/login ────────────────►│
 │         │             │ Validate credentials
 │         │             │ Generate JWT token
 │◄── Set-Cookie (httpOnly) + JWT ────────────│
 │         │             │
 │── GET /apiv1/users (Bearer token) ────────►│
 │         │             │ Validate JWT
 │◄── User data ───────────────────────────────│
```

### User Sync Flow

When an Admin creates a new user, the system automatically syncs them to the LMS:

```
Admin creates user
    │
    ▼
Auth Backend (Spring) ─── POST /api/v1/sync/user ───► LMS Backend (Go)
   (with X-Sync-Secret header)               │
                          Save user to LMS DB
                          (runs async, does not block response)
```

> Because sync runs **asynchronously**, sync failures only appear in logs — no exception is thrown to the client. See [TECHNICAL_NOTES.md — Section 4](./TECHNICAL_NOTES.md#4-user-sync--asynchronous-sync-easy-to-miss).

### File Upload Flow

```
Client ─── POST /lmsapiv1/files/upload ────► LMS Backend
                          │ Save to /app/uploads
                          │ Return filepath
Client ─── GET /files/{filepath} ──────────► Next.js (proxy)
                          │
                    ──────► LMS /api/v1/files/serve/{filepath}
```

---

## 8. API Quick Reference

### Auth Service (`/apiv1`)

| Method | Endpoint | Description | Role |
|---|---|---|---|
| POST | `/api/auth/login` | Log in, receive JWT | Public |
| POST | `/api/auth/logout` | Log out, clear cookie | Authenticated |
| POST | `/api/auth/register/bulk` | Bulk create users | Admin |
| GET | `/api/users` | Paginated user list | Admin/Manager |
| GET | `/api/events` | Event list | Authenticated |
| GET | `/api/tasks` | Task list | Authenticated |
| GET | `/api/announcements` | System announcements | Authenticated |

### LMS Service (`/lmsapiv1`)

| Method | Endpoint | Description | Role |
|---|---|---|---|
| GET | `/api/v1/courses` | List all courses | Authenticated |
| POST | `/api/v1/courses` | Create a new course | Teacher/Admin |
| PUT | `/api/v1/courses/:id` | Update a course | Teacher/Admin |
| POST | `/api/v1/enrollments` | Enroll in a course | Student |
| GET | `/api/v1/quizzes` | List quizzes | Authenticated |
| POST | `/api/v1/quizzes` | Create a quiz | Teacher/Admin |
| POST | `/api/v1/files/upload` | Upload a file | Authenticated |
| GET | `/api/v1/files/serve/:path` | Serve a file | Public |
| POST | `/api/v1/sync/user` | Sync a single user | Internal (Sync Secret) |
| POST | `/api/v1/sync/users/bulk` | Bulk sync users | Internal (Sync Secret) |

> Full API docs via Swagger UI: http://localhost:8080/swagger-ui.html (Auth) and http://localhost:8081/swagger/index.html (LMS)

---

## 9. Contributing

### Branch Naming Conventions

```
feature/new-feature-name    # New feature
fix/description-of-bug     # Bug fix
hotfix/critical-issue      # Urgent production fix
refactor/part-to-improve    # Code improvement without behavior change
docs/update-documentation    # Documentation update
```

### Contribution Workflow

```bash
# 1. Fork the repo on GitHub (click the "Fork" button)

# 2. Clone locally
git clone https://github.com/YOUR_USERNAME/CoreApplication.git
cd CoreApplication

# 3. Add upstream to sync with the original repo
git remote add upstream https://github.com/Big-Data-Club/CoreApplication.git

# 4. Create a new branch
git checkout -b feature/quiz-timer

# 5. Write code, commit frequently
git add .
git commit -m "feat(lms): add countdown timer for quiz"

# 6. Sync with upstream before pushing to avoid conflicts
git fetch upstream
git rebase upstream/develop

# 7. Push to your fork
git push origin feature/quiz-timer

# 8. Open a Pull Request targeting the develop branch of the original repo
```

### Commit Message Format

Following [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

# type: feat | fix | docs | style | refactor | test | chore | hotfix
# scope: frontend | backend | lms | docker | ci

# Real examples:
feat(lms): add video upload progress bar
fix(backend): resolve JWT expiration not refreshing
docs(readme): update local setup instructions
refactor(frontend): extract quiz component into separate file
test(lms): add unit tests for enrollment service
```

### Pull Request Checklist

- [ ] Code runs locally without errors
- [ ] Manually tested the feature or bug fix
- [ ] No leftover `console.log` or `fmt.Println` debug statements
- [ ] No `.env` file or secrets committed
- [ ] Documentation updated if API or configuration changed
- [ ] PR title is clear and the description explains what changed and why
- [ ] Code follows project coding conventions

### Coding Conventions

**Frontend (TypeScript/Next.js):**
- TypeScript strict mode — avoid using `any`
- Components use arrow functions and named exports
- File names: `PascalCase.tsx` for components, `camelCase.ts` for hooks/utilities
- Styling exclusively with Tailwind CSS — avoid inline styles

**Backend (Java/Spring Boot):**
- Follow Spring Boot conventions — Controllers handle HTTP, business logic lives in Services
- Use `@Slf4j` (Lombok) for logging — never use `System.out.println`
- Write Javadoc for all public methods

**LMS (Go):**
- Follow [Effective Go](https://go.dev/doc/effective_go)
- Explicit error handling — never discard errors with `_`
- Run `go vet ./...` before committing

---

## 10. CI/CD Pipeline

### CI — Triggered on Pull Requests and Pushes

```
Code push / PR opened
    │
    ▼
 Detect Changes
    │ (Only build services with changed files — saves time)
    ▼
 Build & Test (run in parallel)
 ├── Backend : ./mvnw test
 ├── Frontend: npm run test:ci
 └── LMS   : go test ./...
    │
    ▼
 Security Scan (Trivy — scans Docker images for vulnerabilities)
    │
    ▼
 Push Docker Image
    └── Only when merging into main or develop
```

### CD — Production Deploy (on merge to main)

`cd-production.yml` automatically:
1. Pulls the new Docker image from Docker Hub
2. SSHs into the production server
3. Runs `docker compose pull && docker compose up -d`

### Required GitHub Secrets

Go to **Settings -> Secrets and variables -> Actions** and add:

| Secret | Description |
|---|---|
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub password or Access Token |
| `SSH_HOST` | Production server IP or hostname |
| `SSH_USER` | SSH username |
| `SSH_PRIVATE_KEY` | SSH private key content |

---

## 11. Troubleshooting

### Container will not start or stays in "starting" state

```bash
# View detailed logs to find the root cause
docker compose logs backend
docker compose logs lms-backend
docker compose logs frontend

# Check all service statuses
docker compose ps
```

### Backend reports database connection error

```bash
# Check if postgres is healthy
docker compose ps postgres

# Connect manually
docker compose exec postgres psql -U postgres -d club_db

# First-time setup: make sure init-scripts ran (they only run on empty volumes)
# WARNING: This deletes all data!
docker compose down -v && docker compose up -d
```

### Frontend cannot reach the API — CORS error or 502

1. Check `BACKEND_URL` in `.env` (should be `http://backend:8080` when using Docker)
2. Confirm the backend is healthy: `docker compose ps backend`
3. Test directly: `curl http://localhost:8080/actuator/health`
4. Check that `CORS_ALLOWED_ORIGINS` includes your frontend URL

See [TECHNICAL_NOTES.md — Section 3](./TECHNICAL_NOTES.md#3-cors--configured-in-three-places) for CORS details.

### "Port already in use" error

```bash
# Find the process using the port (e.g., port 3000)
lsof -i :3000      # macOS / Linux
netstat -ano | findstr :3000 # Windows

# Kill the process
kill -9 <PID>      # macOS / Linux
taskkill /PID <PID> /F # Windows

# Or change the port in .env
FRONTEND_PORT=3001
BACKEND_PORT=8082
```

### LMS Service cannot connect to Redis

```bash
docker compose ps redis-lms

# Test Redis connection
docker compose exec redis-lms redis-cli -a redis_password ping
# Expected output: PONG
```

### Files disappear after container restart

Check that `docker-compose.yml` mounts a volume for `/app/uploads`, and verify `STORAGE_TYPE` in `.env` (`local` or `minio`). See [TECHNICAL_NOTES.md — Section 5](./TECHNICAL_NOTES.md#5-storage--local-vs-minio).

### Docker build fails due to memory

```bash
# Check allocation: Docker Desktop -> Settings -> Resources
# Recommended: RAM >= 4GB, Swap >= 2GB

# Build services one at a time instead of all at once
docker compose build backend
docker compose build frontend
docker compose build lms-backend
```

---

## 12. FAQ

**Q: I am only working on the Frontend — do I need the LMS Backend?**

It depends on what you are building. If you are working on UI unrelated to LMS features, `docker compose up -d postgres backend` is sufficient. For API mocking, consider using MSW (Mock Service Worker).

**Q: Does JWT_SECRET really need to be the same in both backends?**

Yes, **it is mandatory**. Both services verify JWTs with the same secret. If they differ, the LMS will reject all requests carrying Auth-issued tokens with `401 Unauthorized`. See [TECHNICAL_NOTES.md — Section 1](./TECHNICAL_NOTES.md#1-jwt--sharing-the-secret-between-two-backends).

**Q: Why are there two separate PostgreSQL databases?**

This is a microservices design principle — each service owns its data to remain independent and scalable. The Auth service manages `users`, `events`, `announcements`. The LMS manages `courses`, `quizzes`, `enrollments`. User data flows between the two systems via an internal sync API.

**Q: How do I view the database directly?**

Use any PostgreSQL client (DBeaver, TablePlus, pgAdmin...):
- Auth DB: host `localhost`, port `5433`, credentials from `.env`
- LMS DB: host `localhost`, port `5434`, credentials from `.env`

**Q: How do I add a database migration?**

For **Backend (Spring Boot):** Currently `JPA_DDL_AUTO=update` so Hibernate auto-manages schema. For controlled migrations, add Flyway to `pom.xml`. For **LMS (Go):** Add `.sql` files to `lms-service/migrations/` and use `golang-migrate`.

**Q: How do I debug Spring Boot in IntelliJ IDEA?**

```bash
./mvnw spring-boot:run \
 -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005"
```

Then in IntelliJ: Run -> Attach to Process, select port 5005.

---

## Contact & Support

- **Issues:** Create a GitHub issue using the appropriate template
- **Discussions:** Use GitHub Discussions for general questions
- **Email:** bdc@hcmut.edu.vn

---

<div align="center">

[ README](../README.md) · [ Technical Notes](./TECHNICAL_NOTES.md) 

*Last updated: 02/2026. If you find outdated information, please open a PR to fix it!* 

</div>