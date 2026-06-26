# BDC Application

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 2.0.0                     |
| Status    | Approved                  |
| Date      | 2026-04-19                |
| Authors   | BDC Team                  |
| Reviewers | @nhan2892005              |

## Revision History

| Version | Date       | Author   | Description                                   |
|---------|------------|----------|-----------------------------------------------|
| 1.0.0   | 2024-12-20 | BDC Team | Initial English draft                         |
| 1.1.0   | 2026-01-13 | BDC Team | Standardized version; removed emojis; ASCII diagrams |
| 2.0.0   | 2026-04-19 | BDC Team | Updated architecture to include AI pipeline, Kafka, Qdrant & Neo4j |

---

## Developer Documentation

Read these documents in order before commencing development:

| Document | Description |
|---|---|
| **[DEVELOPER_GUIDE](./docs/DEVELOPER_GUIDE.md)** | Environment setup, local development, contribution workflow |
| **[TECHNICAL_NOTES](./docs/TECHNICAL_NOTES.md)** | Critical technical issues, operations, AI DBs, and Kafka handling |
| **[.env.example](./.env.example)** | Annotated environment variable template |

---

## Overview

BDC Application is a microservices-based Learning Management System (LMS) designed for academic organizations and student clubs. The platform provides a complete set of core features for course management, enrollment, assessment, and user administration.

Moving beyond traditional LMS capabilities, the system operates an **Event-Driven AI Pipeline**. It features adaptive learning paths, automated AI quiz generation, semantic search for documents/videos, and spaced repetition engines driven by a deep Knowledge Graph.

### Core Features
* **Course & Content Management** - Organize courses, upload multimedia (Local/MinIO), and manage learners.
* **User & Auth Management** - Secure Spring Boot JWT authentication, role-based access, and real-time User Sync to LMS via API.
* **Event-Driven AI Pipeline** - Kafka-based asynchronous processing for document indexing, video transcription (Whisper), and AI diagnostics.
* **Semantic Search & RAG** - Powered by Qdrant (Vector Store) and BGE-M3 models for highly accurate content retrieval.
* **Knowledge Graph Linking** - Neo4j integration for tracking prerequisite concepts and cross-course learning paths.
* **Automated Diagnostics** - LLM-driven error pattern analysis and deep-linking to video timestamps/PDF pages.

---

## System Architecture

```text
+-----------------------------------------------------------------------+
|                          Browser / Client                             |
+----------------------------------+------------------------------------+
                                   | Port 3000
                                   v
+-----------------------------------------------------------------------+
|                    Frontend - Next.js 14                              |
|  /apiv1/* -> Auth Backend | /lmsapiv1/* -> LMS | /ai/* -> AI       |
+---------+------------------------+------------------------+-----------+
          | :8080                  | :8081                  | :8000
          v                        v                        v
+------------------+     +------------------+     +---------------------+
|  Auth Backend    |     |   LMS Backend    |     |     AI Service      |
| (Spring Boot 3)  |     |   (Go 1.21)      |     | (FastAPI + Python)  |
+---------+--------+     +---------+--------+     +---------+-----------+
          |                        |                        |
          v                        v                        v
+------------------+     +------------------+     +---------------------+
| PostgreSQL(Auth) |     | PostgreSQL (LMS) |     |   PostgreSQL (AI)   |
+------------------+     | Redis (Cache)    |     |   Qdrant (Vector)   |
                         | MinIO (Files)    |     |   Neo4j (Graph)     |
                         +---------+--------+     +---------+-----------+
                                   |                        |
                                   |   +----------------+   |
                                   +-->|  Kafka Broker  |<--+
                                       +----------------+
                                                |
                                                v
                                       +------------------+
                                       |    AI Worker     |
                                       | (Kafka Consumer) |
                                       +------------------+
````

### Technology Stack

| Component | Technology | Version |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, NextAuth.js | 14+ |
| Auth Backend | Spring Boot, Spring Security, JWT | 3.x (Java 21) |
| LMS Backend | Go, Gin framework, GORM | 1.21+ |
| AI Service | FastAPI, Celery (Worker), Groq LLM API | Python 3.10+ |
| Message Broker | Kafka (KRaft mode) | 3.7.0 |
| Relational DB | PostgreSQL (Split across 3 domains) | 15 |
| Vector Store | Qdrant | v1.13.6 |
| Knowledge Graph | Neo4j | 5.26+ |
| Cache & Memory | Redis | 7 |
| Object Storage | MinIO | Latest |
| Container | Docker, Docker Compose | 24+ / 2.0+ |

-----

## Quick Start

### Prerequisites

  * **Docker Desktop** 24.0+ and **Docker Compose** 2.0+
  * **Git**
  * Minimum **8GB RAM** allocated to Docker (Due to Neo4j, Qdrant, and AI models).

### Up and running in 3 steps

1.  **Clone the repository**

    ```bash
    git clone [https://github.com/Big-Data-Club/CoreApplication.git](https://github.com/Big-Data-Club/CoreApplication.git)
    cd CoreApplication
    ```

2.  **Create configuration from template**

    ```bash
    cp .env.example .env
    ```

    *Ensure critical variables are set:*

      * `JWT_SECRET` (Must be identical for Auth and LMS)
      * `LMS_API_SECRET` and `LMS_SYNC_SECRET` (Must be identical)
      * `GROQ_API_KEY` (Required for AI generation)
      * `STORAGE_TYPE=minio` (Mandatory for AI document processing)

3.  **Build and launch the stack**

    ```bash
    docker compose up -d --build
    ```

### Accessing the Application

Service availability is reached after approximately 2-3 minutes.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Auth API + Swagger | http://localhost:8080/swagger-ui.html |
| LMS API + Swagger | http://localhost:3000/lmsapidocs/swagger/index.html |
| AI API Docs | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Neo4j Browser | http://localhost:7474/browser |

**Default Admin Account:**
  * *Note: Set in `.env` before first run. Reference `docs/TECHNICAL_NOTES.md` for details.*

-----

## API Documentation

The BDC Application utilizes **Swagger (OpenAPI)** for automated API documentation across all microservices. Instead of relying on static documents, the development team should use the Swagger UI to view detailed endpoints, parameters, request/response payloads, and to test APIs directly.

To ensure Cookie synchronization (e.g., HTTP-only JWTs) and avoid CORS-related issues during local development, **it is highly recommended to access the API Docs via the Frontend Proxy paths (Port 3000)**.

### Auth Service (`/apiv1`)
* **Role:** Manages identities, JWTs, roles/permissions, events, and cross-service user synchronization.
* **Stack:** Spring Boot 3.x, Spring Security, Springdoc OpenAPI.
* **API Documentation:**
  * **Frontend Proxy Link:** [http://localhost:3000/apiv1/swagger-ui.html](http://localhost:3000/apiv1/swagger-ui.html) *(Recommended)*
  * **Direct Internal Link:** http://localhost:8080/swagger-ui.html

### LMS Service (`/lmsapiv1`)
* **Role:** Handles core learning management operations, including courses, enrollments, quizzes, forums, learning progress, and file storage workflows (MinIO).
* **Stack:** Go 1.21, Gin Framework, Swaggo.
* **API Documentation:**
  * **Frontend Proxy Link:** [http://localhost:3000/lmsapidocs/swagger/index.html](http://localhost:3000/lmsapidocs/swagger/index.html) *(Recommended)*
  * **Direct Internal Link:** http://localhost:8081/swagger/index.html

### AI Service (`/ai`)
* **Role:** Orchestrates the entire Event-Driven AI Pipeline, including document Auto-Indexing, Semantic Search (Qdrant), Knowledge Graph queries (Neo4j), Flashcards, and the AI Quiz Generator.
* **Stack:** Python 3.10+, FastAPI (auto-generated OpenAPI spec).
* **API Documentation:**
  * **Frontend Proxy Link (Swagger):** [http://localhost:3000/ai/docs](http://localhost:3000/ai/docs) *(Recommended)*
  * **Frontend Proxy Link (ReDoc):** [http://localhost:3000/ai/redoc](http://localhost:3000/ai/redoc)
  * **Direct Internal Link:** http://localhost:8000/docs

-----

## Contributing

Reference the full contribution guide and coding standards at `docs/DEVELOPER_GUIDE.md`. Read `docs/TECHNICAL_NOTES.md` before adjusting any architecture components (especially Kafka Consumer Groups and Vector Dimensions).

```bash
git checkout -b feature/your-feature-name
# ... development ...
git commit -m "feat(ai): integrate whisper fallback for video indexing"
git push origin feature/your-feature-name
```

-----

## License

This project is licensed under the [MIT License](https://www.google.com/search?q=./LICENSE).

-----

Built with formal standards by **BDC Team**