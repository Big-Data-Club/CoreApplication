# Lakehouse and Personalization Integration Guide

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.0.0                     |
| Status    | Draft                     |
| Date      | 2026-06-30                |
| Authors   | BDC Team                  |
| Reviewers | -                         |

## Revision History

| Version | Date       | Author   | Description   |
|---------|------------|----------|---------------|
| 1.0.0   | 2026-06-30 | BDC Team | Initial draft |

## 1. Overview

The personalization engine of the Big Data Club (BDC) Core Application is powered by a lightweight DuckDB-based Lakehouse inside the `personalize-service`. This service collects micro-interactions (e.g., lesson views, quick check attempts, flashcard flips, AI queries) to compile real-time student personalization profiles and detect learning struggles. 

---

## 2. Architecture and Data Flow

The following ASCII diagram illustrates how student interaction data is collected, processed in the Lakehouse layers (Bronze, Silver, Gold), and used to trigger notifications.

```
  Student UI Interaction
         |
         v (HTTP API)
   [LMS Service] (Go)
     /         \
    /           \ (Publish Event)
(Postgres)    Topic: lms.analytics.interactions
  [DB Write]     \
                  v
         [personalize-service Kafka Worker] (Python)
                  |
                  v (Ingest)
            [DuckDB: bronze_interactions] (Bronze Layer)
                  |
         +--------+--------+
         | (Hourly cron)   | (Dynamic view query)
         v                 v
   (Archive task)    (Unified View)
         |                 |
         v                 v
   [Bronze Parquet]  [gold_struggle_alerts] (Gold Layer)
   (Partitioned)           |
                           v (Every 2 minutes)
                     (Notification Detector)
                           |
                           v (Publish Event)
                     Topic: personalize.notification.trigger
                           |
                           v
                     [Auth Service] (Java)
                           |
                           v (Async Task)
                     [Email Service]
                           |
                           v
                      Student Email
```

### 2.1 The Medallion Architecture

1. **Bronze Layer (`bronze_interactions`):**
   Stores raw event logs ingested from Kafka. Columns: `interaction_id`, `user_id`, `course_id`, `lesson_id`, `node_id`, `action_type`, `score`, `status`, `created_at`.
   To prevent DuckDB from growing indefinitely, active logs older than 7 days are automatically archived to partitioned Parquet files under `/app/data/lakehouse/bronze/interactions/` and pruned from the table.

2. **Silver Layer (`unified_interactions` view):**
   A dynamic union view that combines active records from the `bronze_interactions` table with the archived Parquet files using DuckDB's `read_parquet()` function.

3. **Gold Layer (Analytical Views):**
   - `gold_student_course_metrics`: Aggregates total views, completed lessons, flashcard flips, AI queries, and quick check accuracy.
   - `gold_concept_struggles`: Identifies learning nodes where a student has more incorrect quick checks than correct ones, or has failed at least twice.
   - `gold_user_item_matrix`: Computes student-to-concept affinity scores based on engagement types.
   - `gold_struggle_alerts`: Pinpoints students who have met struggle criteria or have been inactive for more than 7 days.

---

## 3. Observation and Monitoring Guide

The active database files and Parquet exports are stored in the persistent volume mapped to `/app/data` (defined as `personalize_data` volume in `docker-compose.yml`).

### 3.1 Inspecting the Lakehouse via DuckDB CLI

Run the following command on the host machine to execute SQL queries inside the DuckDB instance:

```bash
docker exec -it personalize-service duckdb /app/data/student_analytics.duckdb
```

Common diagnostic queries:

```sql
-- Show all tables and views
SHOW TABLES;

-- Inspect active struggle alerts
SELECT * FROM gold_struggle_alerts LIMIT 10;

-- Verify recent notifications sent ledger
SELECT * FROM sent_notifications ORDER BY sent_at DESC LIMIT 5;
```

### 3.2 Monitoring via Dashboard UI

The `personalize-service` serves an interactive, cosmic dark-mode Dashboard UI to monitor the Lakehouse tables in real-time and perform data exports without manual SQL commands.

#### 3.2.1 Access URLs
*   **Direct Port:** `http://localhost:8085/dashboard`
*   **Via Traefik Reverse Proxy:** `http://localhost/personalize-dashboard` or `http://bdc.hpcc.vn/personalize-dashboard`

#### 3.2.2 Authentication in UI
Because endpoints require authentication, the dashboard features a **Secret Key Manager**:
1.  Enter your `AI_SERVICE_SECRET` in the credential input field and click **Save**. The key is stored securely in the browser's `localStorage`.
2.  Alternatively, you can auto-load the secret by appending it to the query parameter: `http://localhost/personalize-dashboard?secret=YOUR_SECRET_KEY`.

#### 3.2.3 Features
*   **Tabbed Table Selector:** Swap views between Student Metrics, Concept Struggles, Affinity Matrix, and Active Alerts.
*   **Live Search:** Search and filter rows instantly.
*   **Export Gold Parquet:** Triggers the server-side Parquet generation.
*   **Download Local CSV:** Generates and downloads a `.csv` file of the active table directly to your machine.

### 3.3 Monitoring via REST API

The `personalize-service` exposes the Gold views via HTTP REST endpoints on host port `8085` (internally `8082`), and via Traefik under the `/personalize` prefix path. All requests must include the `X-AI-Secret` header containing the system's `AI_SERVICE_SECRET`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/personalize/analytics/gold/student-metrics` | GET | Returns aggregated student activity metrics. |
| `/personalize/analytics/gold/concept-struggles` | GET | Returns weak spots per student per course. |
| `/personalize/analytics/gold/interaction-matrix` | GET | Returns the User-Item affinity matrix. |
| `/personalize/analytics/gold/struggle-alerts` | GET | Returns active struggle alerts (optional filter `?user_id=1`). |

Example request:
```bash
curl -H "X-AI-Secret: <AI_SERVICE_SECRET>" http://localhost:8085/personalize/analytics/gold/struggle-alerts
```

---

## 4. Data Extraction for Recommender Systems

Data Analysts (DAs) and Machine Learning (ML) engineers can extract processed interaction weights to train recommendation engines.

### 4.1 Gold User-Item Matrix Definition

The affinity score is computed in the `gold_user_item_matrix` view using the following weight scheme:
- `lesson_view` / `lesson_viewed`: `1.0`
- `lesson_complete` / `lesson_completed`: `2.0`
- `flashcard_flip`: `1.0`
- `quick_check_correct`: `2.0`
- `quick_check_incorrect`: `0.5`
- `ask_ai`: `1.5`
- Other actions: `0.5`

### 4.2 Automated Parquet Export

To export the current snapshot of all Gold tables to highly optimized Parquet files, send a POST request:

```bash
curl -X POST -H "X-AI-Secret: <AI_SERVICE_SECRET>" http://localhost:8085/personalize/analytics/gold/export
```

This command generates the following files on the server:
- `/app/data/lakehouse/gold/gold_student_course_metrics.parquet`
- `/app/data/lakehouse/gold/gold_concept_struggles.parquet`
- `/app/data/lakehouse/gold/gold_user_item_matrix.parquet`
- `/app/data/lakehouse/gold/gold_struggle_alerts.parquet`

### 4.3 Querying the Data in Python

A Data Analyst can read these Parquet files directly or query the active DuckDB database file using Python:

```python
import duckdb
import pandas as pd

# Method A: Direct Parquet Read
df_matrix = pd.read_parquet("d:/CodeSpace/BDCApp/data/lakehouse/gold/gold_user_item_matrix.parquet")

# Method B: Direct DuckDB File connection
conn = duckdb.connect("d:/CodeSpace/BDCApp/data/student_analytics.duckdb")
df_struggles = conn.execute("SELECT * FROM gold_concept_struggles").df()
```

---

## 5. AI Service Integration (Data Feed)

The AI Mentor (`ai-service` and `ai-worker`) consumes the student profile dynamically to personalize responses.

When a student queries the AI Mentor, the `ai-service` planner evaluates the request. If the request is progress-based (e.g. "what should I study next?"), it makes an internal synchronous HTTP call:

```
GET http://personalize-service:8082/personalize/student/{user_id}/course/{course_id}
```

The returned profile containing weak concept nodes and completed lessons is injected into the LLM context to generate targeted learning roadmaps.

---

## 6. Personalization Notification Mechanics

The personalization alert system operates on an event-driven mechanism:

1. **Detection:** A background loop in the Kafka worker (`run_notification_detector()`) executes every 2 minutes, querying active entries in `gold_struggle_alerts`.
2. **Criteria:**
   - **Concept Struggle:** Triggered if a student has failed at least 3 quick check attempts on a concept (`incorrect_checks_count >= 3`) and has never answered it correctly (`correct_checks_count = 0`).
   - **Inactivity:** Triggered if a student has not interacted with a course for more than 7 days.
3. **Cooldown:** To prevent spamming the user, a 24-hour cooldown is enforced using the `sent_notifications` table in DuckDB.
4. **Delivery:** If not throttled by cooldown, the worker publishes an event to the `personalize.notification.trigger` topic. The Java `auth-and-management-service` consumes this message and delivers an email notification asynchronously.

### 6.1 Diagnostic Checklist for Missing Notifications
If notifications are not being displayed or received:
- Check the student's email inbox. The system does not use in-app notifications; it sends emails.
- Verify that the SMTP settings in `auth-and-management-service` environment variables are properly configured.
- Check the docker compose logs for Kafka connection issues:
  ```bash
  docker compose logs -f personalize-service
  docker compose logs -f backend
  ```
- Inspect the `sent_notifications` ledger in DuckDB to see if an alert has been throttled by the 24-hour cooldown.

---

## 7. Data Analyst (DA) Integration Pathway

Once a DA completes a new machine learning model (e.g., collaborative filtering or neural recommendation), the model can be integrated into the system using two primary patterns.

### Pattern A: Batch Score Export (Push Model)
Ideal for daily/weekly recommendation updates.
1. The DA runs a scheduled training/inference job.
2. The job exports calculated recommendations as a table or Parquet file.
3. The data is pushed to a designated PostgreSQL table in `postgres-lms` or imported into DuckDB.
4. The LMS frontend or backend queries the table directly to show personalized widgets.

### Pattern B: Microservice Endpoint (Pull Model)
Ideal for real-time recommendation updates.
1. The DA wraps the trained model (or rule-based algorithm) in a lightweight API endpoint (e.g., inside the existing `personalize-service` or a new FastAPI container).
2. The endpoint reads active metrics from DuckDB to generate recommendations.
3. The LMS backend or AI Mentor calls this API synchronously to retrieve recommendations on-demand.
