# 📚 BDC Application

> A next-generation learning management platform — microservices-based LMS built with **Next.js**, **Spring Boot**, and **Go**, moving towards an AI-powered adaptive learning ecosystem.

[![CI](https://github.com/Big-Data-Club/CoreApplication/actions/workflows/ci.yml/badge.svg)](https://github.com/Big-Data-Club/CoreApplication/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker)](./docker-compose.yml)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![Spring Boot](https://img.shields.io/badge/Spring_Boot-3.x-green?logo=springboot)](https://spring.io)
[![Go](https://img.shields.io/badge/Go-1.21-00ADD8?logo=go)](https://golang.org)

---

> 🌐 **Choose language / Chọn ngôn ngữ:**
> &nbsp;&nbsp;[🇻🇳 Tiếng Việt](./README.md) &nbsp;|&nbsp; [🇬🇧 English](./README.en.md)

---

## 📖 Developer Documentation

> New to the project? Read these documents **in order** before you start:

| Document | Description | Language |
|---|---|---|
| **[🛠️ DEVELOPER_GUIDE](./docs/DEVELOPER_GUIDE.en.md)** | Environment setup, local development, contribution workflow | [🇻🇳 VI](./docs/DEVELOPER_GUIDE.md) · [🇬🇧 EN](./docs/DEVELOPER_GUIDE.en.md) |
| **[⚠️ TECHNICAL_NOTES](./docs/TECHNICAL_NOTES.en.md)** | Critical technical issues — **read carefully before building** | [🇻🇳 VI](./docs/TECHNICAL_NOTES.md) · [🇬🇧 EN](./docs/TECHNICAL_NOTES.en.md) |
| **[🔑 .env.example](./.env.example)** | Annotated environment variable template — copy to `.env` to get started | — |

---

## 🌟 Overview

BDC Application is a **microservices-based Learning Management System (LMS)**, designed for academic organizations and student clubs. The platform provides a complete set of core features for course management, enrollment, assessment, and user administration.

The next development phase focuses on integrating **AI** to transform BDC from a traditional LMS into an **adaptive learning ecosystem** — where every student follows a personalized learning path, guided by their actual learning behavior data.

### Current Features

- 🎓 **Course Management** — Create, edit, and organize courses with multimedia content (video, documents, quizzes)
- 👥 **Course Enrollment** — Flexible enrollment system with an approval workflow
- 📝 **Quiz & Assessment** — Multiple question types, result tracking, and attempt history
- 👤 **User Management** — Role-based access: Admin, Manager, Teacher, Student
- 📢 **Announcements** — System-wide and course-specific notifications
- 📅 **Event Management** — Track club events, assignments, and deadlines
- 📁 **File Management** — Upload and serve videos, documents, images (Local or MinIO)
- 🔐 **Secure Authentication** — JWT-based auth with HTTP-only cookies
- 🔄 **User Sync** — Automatic synchronization between Auth Service and LMS Service

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      🌐 Browser / Client                      │
└──────────────────────────┬───────────────────────────────────┘
                           │ Port 3000
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              🖥️  Frontend — Next.js 14 (TypeScript)           │
│   /apiv1/*  ───────────► Auth Backend  (proxy rewrite)       │
│   /lmsapiv1/*  ─────────► LMS Backend  (proxy rewrite)       │
│   /files/*  ────────────► LMS (file serving)                 │
└──────────┬──────────────────────────────┬────────────────────┘
           │ :8080                         │ :8081
           ▼                               ▼
┌──────────────────────┐     ┌─────────────────────────────────┐
│  ⚙️  Auth Backend     │     │  ⚙️  LMS Backend                 │
│   Spring Boot 3.x    │◄────│   Go 1.21 + Gin                 │
│   - JWT / Auth       │     │   - Courses, Quizzes            │
│   - Users, Events    │     │   - Enrollments, Files          │
│   - Announcements    │     │   - User sync from Auth         │
└──────────┬───────────┘     └──────────┬──────────────────────┘
           │                             │         │
           ▼                             ▼         ▼
┌──────────────────────┐  ┌─────────────────────┐  ┌──────────┐
│ 🗄️  PostgreSQL (Auth) │  │ 🗄️  PostgreSQL (LMS) │  │  Redis   │
│   Port: 5433         │  │   Port: 5434         │  │  :6379   │
└──────────────────────┘  └─────────────────────┘  └──────────┘
                                                    ┌──────────┐
                                                    │ 📦 MinIO │
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

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** 24.0+ and **Docker Compose** 2.0+
- **Git**
- Minimum **4GB RAM** allocated to Docker

### Up and running in 3 steps

```bash
# Step 1: Clone the repository
git clone https://github.com/Big-Data-Club/CoreApplication.git
cd CoreApplication

# Step 2: Create your config file from the template
cp .env.example .env
# Open .env and fill in the required values
# (see TECHNICAL_NOTES.en.md to learn which variables matter most)

# Step 3: Build and launch the full stack
docker compose up -d --build
```

### Accessing the Application

Once all containers are healthy (about 1–2 minutes), you can access:

| Service | URL |
|---|---|
| 🌐 Frontend | http://localhost:3000 |
| ⚙️ Auth API + Swagger | http://localhost:8080/swagger-ui.html |
| ⚙️ LMS API + Swagger | http://localhost:3000/lmsapidocs/swagger/index.html |
| 📦 MinIO Console | http://localhost:9001 |

> **Default admin account** — Change immediately after first login!
> Email: `phucnhan289@gmail.com` · Password: `hehehe`
> Details: [TECHNICAL_NOTES.en.md — Section 6: DataInitializer](./docs/TECHNICAL_NOTES.en.md#6-datainitializer--default-admin-account)

---

## 📖 API Documentation

### Auth Service (`/apiv1`)

Base URL: `http://localhost:8080/api` — Full Swagger: http://localhost:8080/swagger-ui.html

| Method | Endpoint | Description | Role |
|---|---|---|---|
| POST | `/auth/login` | Log in, receive JWT token | Public |
| POST | `/auth/logout` | Log out, clear cookie | Authenticated |
| POST | `/auth/register/bulk` | Bulk create users, send password emails | Admin |
| GET | `/users` | Paginated user list | Admin/Manager |
| GET | `/events` | Event list | Authenticated |
| GET | `/tasks` | Task list | Authenticated |
| GET | `/announcements` | System announcements | Authenticated |

### LMS Service (`/lmsapiv1`)

Base URL: `http://localhost:8081/api/v1` — Full Swagger: http://localhost:3000/lmsapidocs/swagger/index.html

| Method | Endpoint | Description | Role |
|---|---|---|---|
| GET | `/courses` | List all courses | Authenticated |
| POST | `/courses` | Create a new course | Teacher/Admin |
| POST | `/enrollments` | Enroll in a course | Student |
| GET | `/quizzes` | List quizzes | Authenticated |
| POST | `/files/upload` | Upload file (video/doc/image) | Authenticated |
| GET | `/files/serve/:path` | Serve a file (public) | Public |

---

## 🔐 Authentication & Authorization

### User Roles

| Role | Permissions |
|---|---|
| **ADMIN** | Full system access — manage users, CRUD on all resources |
| **MANAGER** | Manage events, tasks, announcements |
| **TEACHER** | Create courses, create quizzes, approve enrollments |
| **STUDENT** | Enroll in courses, take quizzes, view content |

### JWT Authentication Flow

```
Client ─── POST /apiv1/auth/login ──────────────────► Auth Backend
                                                            │ validate credentials
                                                            │ generate JWT token
Client ◄── Set-Cookie (httpOnly) + JWT ─────────────────────┘

Client ─── GET /lmsapiv1/courses (Bearer token) ────► LMS Backend
                                                            │ verify JWT (same JWT_SECRET)
Client ◄── Course data ─────────────────────────────────────┘
```

> ⚠️ `JWT_SECRET` must be **identical and at least 32 characters** in both backends.
> See [TECHNICAL_NOTES.en.md — Section 1: JWT](./docs/TECHNICAL_NOTES.en.md#1-jwt--sharing-the-secret-between-two-backends).

---

## 🗄️ Database Schema

### Auth Database · PostgreSQL port 5433

Tables: `users`, `events`, `tasks`, `announcements`, `password_reset_tokens`

### LMS Database · PostgreSQL port 5434

Tables: `users` *(synced from Auth)*, `courses`, `sections`, `content`, `enrollments`, `quizzes`, `questions`, `quiz_attempts`, `answers`

---

## 📁 File Upload & Storage

| Type | Supported Formats | Max Size |
|---|---|---|
| Video | MP4, AVI, MOV, MKV, WebM, FLV | 100MB |
| Documents | PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, TXT | 100MB |
| Images | JPG, JPEG, PNG, GIF, BMP, SVG, WebP | 100MB |

Storage backend is selected via `STORAGE_TYPE`:
- **`local`** (default) — Saves to filesystem, great for development
- **`minio`** — Distributed object storage, recommended for production

See [TECHNICAL_NOTES.en.md — Section 5: Storage](./docs/TECHNICAL_NOTES.en.md#5-storage--local-vs-minio).

---

## 🔄 User Synchronization

When a user is created via the Auth Service, the system automatically syncs them to the LMS so they can immediately enroll in courses.

```bash
# Manual sync when needed (e.g., LMS was down during bulk user creation)
POST /lmsapiv1/sync/user
POST /lmsapiv1/sync/users/bulk
DELETE /lmsapiv1/sync/user/{userId}
Headers: X-Sync-Secret: {LMS_SYNC_SECRET}
```

> ⚠️ `LMS_API_SECRET` (Backend) must equal `LMS_SYNC_SECRET` (LMS). See [TECHNICAL_NOTES.en.md — Section 4](./docs/TECHNICAL_NOTES.en.md#4-user-sync--asynchronous-sync-easy-to-miss).

---

## 🐳 Docker Services

| Service | Port | Description |
|---|---|---|
| `frontend` | 3000 | Next.js application |
| `backend` | 8080 | Spring Boot Auth Service |
| `lms-backend` | 8081 | Go LMS Service |
| `postgres` | 5433 | Auth database |
| `postgres-lms` | 5434 | LMS database |
| `redis-lms` | 6379 | Cache (session, queue) |
| `minio` | 9000 / 9001 | Object storage API / Console |

```bash
docker compose up -d              # Start all services
docker compose ps                 # Check service status
docker compose logs -f            # Stream logs in real time
docker compose down               # Stop (preserves data)
docker compose down -v            # Stop + delete all data
docker compose up -d --build backend   # Rebuild a single service
```

---

## 🧪 Testing

```bash
# Frontend
cd frontend && npm run test:ci

# Backend (Java)
cd Backend && ./mvnw test

# LMS (Go)
cd LMS && go test ./...
```

---

## 📊 Health Checks

| Service | Endpoint |
|---|---|
| Frontend | `GET /api/health` |
| Auth Backend | `GET /actuator/health` |
| LMS Backend | `GET /health` |
| Metrics (Prometheus) | `GET /actuator/prometheus` |

---

## 🗺️ Roadmap — AI4Education

Next development phase: integrating AI to bridge 3 learning gaps identified through real-world surveys at the club.

| Gap | Description |
|---|---|
| **Navigation Gap** | Students don't know what to study first or what comes next |
| **Practice Gap** | The LMS only stores static content — no interactive practice or instant feedback |
| **Trust Gap** | No mechanism to verify the accuracy of AI-generated content |

### Phase 1 — AI Error Diagnosis & Deep Linking
Turn every wrong answer into a deep learning opportunity, not just "Incorrect, try again."

- [ ] **Error Pattern Analysis** — Diagnose *why* students get things wrong: conceptual confusion, missing prerequisites, or misreading
- [ ] **Deep Link to Source** — "Review" button links directly to the relevant PDF page or exact video timestamp
- [ ] **Weakness Heatmap** — Heat map of the most-missed Knowledge Nodes across the class
- [ ] **Class Analytics Report** — Auto-generated report after each quiz: per-question accuracy, score distribution

### Phase 2 — AI Smart Quiz & Active Recall
Automate high-quality quiz creation to reduce instructor workload.

- [ ] **Auto Quiz Generator** — Generate questions following Bloom's Taxonomy (6 levels) from slides and video
- [ ] **Source-cited Answers** — Each question includes a detailed explanation with a clear citation
- [ ] **Spaced Repetition Engine** — Timely review reminders based on the SM-2 algorithm
- [ ] **Instructor Quiz Review** — Instructors review and approve AI-generated quizzes before release

### Phase 3 — AI Micro-Video Creator
Address the 50–100 slide deck and 1–2 hour lecture recording problem.

- [ ] **Auto Summarizer** — Summarize slide PDFs and video transcripts into ~300-word Knowledge Node summaries
- [ ] **Script Generator** — Write 60–90 second micro-video scripts in TikTok/Reels style
- [ ] **AI Voice + Slide Video** — Automatically generate video from script + illustrated slides + AI narration
- [ ] **Video Chaptering** — Auto-split long videos into titled chapters with timestamps

### Phase 4 — AI Atomic Roadmap *(Personal Learning GPS)*
Transform every course from a static resource list into a personalized learning path.

- [ ] **Knowledge Graph Engine** — Auto-decompose course content into atomic Knowledge Nodes
- [ ] **Adaptive Sequencing** — AI orders learning based on student's diagnostic assessment
- [ ] **Progress-based Rerouting** — Automatically adjust path when knowledge gaps are detected
- [ ] **Personal Dashboard** — Progress by Knowledge Node, personal strengths and weaknesses

### Phase 5 — Integrations & Infrastructure

- [ ] WebSocket Notifications — Real-time push for quiz results, enrollment approvals
- [ ] Mobile App (React Native) — Offline learning + push notifications
- [ ] LMS Integration — Connect to Moodle, Canvas via LTI standard
- [ ] Certificate Generation — Digitally signed completion certificates
- [ ] Multi-language Support — Vietnamese / English UI
- [ ] Advanced Search — Full-text search across video transcripts and documents

---

## 🤝 Contributing

See the full contribution guide, commit message conventions, and coding standards at **[DEVELOPER_GUIDE.en.md — Section 9](./docs/DEVELOPER_GUIDE.en.md#9-contributing)**.

```bash
git checkout -b feature/your-feature-name
# ... write code ...
git commit -m "feat(lms): brief description"
git push origin feature/your-feature-name
# → Open a Pull Request targeting the develop branch
```

---

## 👥 Team & Support

**BDC Development Team** — Big Data Club, HCMUT

| Channel | Address |
|---|---|
| 🐛 Bug reports | [GitHub Issues](https://github.com/Big-Data-Club/CoreApplication/issues) — use `bug_report.md` template |
| ✨ Feature requests | [GitHub Issues](https://github.com/Big-Data-Club/CoreApplication/issues) — use `feature_request.md` template |
| 📧 Email | bdc@hcmut.edu.vn |
| 🌐 Production | https://bdc.hpcc.vn |

---

## 📝 License

This project is licensed under the [MIT License](./LICENSE).

---

## 📚 References

- [Next.js Documentation](https://nextjs.org/docs)
- [Spring Boot Documentation](https://spring.io/projects/spring-boot)
- [Gin Framework Documentation](https://gin-gonic.com/docs/)
- [Docker Documentation](https://docs.docker.com/)
- [MinIO Documentation](https://min.io/docs/)

---

<div align="center">

**Built with ❤️ by BDC Team**

[🛠️ Developer Guide](./docs/DEVELOPER_GUIDE.en.md) · [⚠️ Technical Notes](./docs/TECHNICAL_NOTES.en.md) · [🇻🇳 Vietnamese Version](./README.md) · [🌐 Production](https://bdc.hpcc.vn)

</div>