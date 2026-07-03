# BDC Performance Testing Guide

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.0.0                     |
| Status    | Approved                  |
| Date      | 2026-07-02                |
| Authors   | BDC Team                  |
| Reviewers | -                         |

## Revision History

| Version | Date       | Author   | Description   |
|---------|------------|----------|---------------|
| 1.0.0   | 2026-07-02 | BDC Team | Initial draft |

## 1. Overview
This document defines the technical load testing methodology for the Big Data Club (BDC) LMS microservices architecture. It aims to determine the system concurrency limit, identify degradation thresholds (lag points), and establish scalable load testing practices using Grafana k6.

## 2. Load Testing Architecture
The load testing framework executes mock student journeys simulating concurrent virtual users (VUs) communicating with the Traefik Gateway or direct service ports.

```
+---------------------------------------------------------+
|                    Grafana k6 Runner                    |
|  - Virtual Users (VUs) pool                              |
|  - JavaScript user flows                                |
+---------------------------------------------------------+
                            |
                            | HTTP Request Sequence
                            v
+---------------------------------------------------------+
|                  Traefik Gateway (:3000)                |
+---------------------------------------------------------+
         |                       |                 |
         | /apiv1/*              | /lmsapiv1/*     | /personalize/*
         v                       v                 v
+-----------------+     +-----------------+  +----------------------+
|  Auth Service   |     |   LMS Service   |  | Personalize Service  |
|  (Spring Boot)  |     |   (Go + Gin)    |  | (FastAPI + DuckDB)   |
|  :8080          |     |   :8081         |  | :8082                |
+-----------------+     +-----------------+  +----------------------+
```

## 3. Concurrency & Performance Thresholds (SLAs)
To identify the "lag breakpoint," we establish Service Level Agreements (SLAs) in the k6 configuration:

*   **Error Rate**: Under 1.0% of total HTTP requests (status codes other than 2xx).
*   **P95 Latency**: Below 800 milliseconds for operational endpoints.
*   **P99 Latency**: Below 2000 milliseconds for complex transactions.
*   **DuckDB Lock Contention**: Zero write transaction aborts on the personalize ledger.

## 4. Performance Test Scenarios
Four test topologies are used to validate the platform resilience:

### Smoke Testing
*   **Objective**: Validate test scripts compile and endpoints return 200 OK without database errors.
*   **Configuration**: 1 VU executing for 1 minute.

### Load Testing
*   **Objective**: Verify performance under typical peak student traffic.
*   **Configuration**: Ramp up to 50 concurrent journeys over 3 minutes, hold for 5 minutes, ramp down.

### Stress Testing (Lag Breakpoint Hunt)
*   **Objective**: Identify the system breakpoint where resource limits are saturated, response times exceed SLA, or services crash.
*   **Configuration**: Ramping up from 1 to 200 VUs over 5 minutes until thresholds fail.

### Soak Testing
*   **Objective**: Detect memory leaks, slow DuckDB storage growth anomalies, and connection leaks in PostgreSQL/Redis.
*   **Configuration**: Constant 25 VUs executing continuously for 2 hours.

## 5. Test Execution Guide

### Prerequisites
1. Install k6 locally or on the target virtual machine:
   ```bash
   # Debian/Ubuntu
   sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
   echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
   sudo apt-get update
   sudo apt-get install k6
   ```

2. Verify that test accounts are synced in the database:
   - Ensure the student account `student@example.com` exists in the `users` table.
   - Ensure the teacher account `teacher@example.com` and admin account `admin@example.com` are present with their respective roles.

### Running the Test

#### Single Role (Student Flow)
Execute the test script [k6_student_flow.js](../performance-tests/k6_student_flow.js) using terminal environment variables:

```bash
# Set variables and run student load test
BASE_URL="http://localhost:3000" \
TEST_EMAIL="student@example.com" \
TEST_PASSWORD="password" \
COURSE_ID="19" \
NODE_ID="2221" \
AI_SERVICE_SECRET="ai-service-secret-change-me" \
k6 run performance-tests/k6_student_flow.js
```

#### Multi-Role (Student, Teacher, Admin Workloads)
Execute the multi-role k6 script [k6_multi_role_flow.js](../performance-tests/k6_multi_role_flow.js) to simulate a complete production workload (85% Students, 12% Teachers, 3% Admins running concurrently):

```bash
# Set variables and run multi-role load test
BASE_URL="http://localhost:3000" \
STUDENT_EMAIL="student@example.com" \
TEACHER_EMAIL="teacher@example.com" \
ADMIN_EMAIL="admin@example.com" \
TEST_PASSWORD="password" \
COURSE_ID="19" \
NODE_ID="2221" \
AI_SERVICE_SECRET="ai-service-secret-change-me" \
k6 run performance-tests/k6_multi_role_flow.js
```

## 6. Identifying Performance Bottlenecks (Lag Diagnosis)
When running the load test, monitor these telemetry signs to identify lag:

1.  **k6 Terminal Outputs**:
    - Look for `http_req_duration` metrics. If the `p(95)` value jumps above 800ms, the system is lagging.
    - Check `http_req_failed` rate. A value above 0% indicates container failures or database timeouts.
2.  **Container Resource Consumption**:
    - Monitor resource usage on the server using `docker stats`.
    - If `lms-service` or `personalize-service` CPU hits 100%, the bottleneck is compute capacity.
    - If `postgres-lms` or `postgres-ai` CPU is high, check for missing indexes in database query paths.
3.  **Database Connection Pooling**:
    - Check if the HikariCP or Go database connection pool size is exhausted. Look for `Connection timeout` or `Too many connections` in the service logs.
4.  **DuckDB Lock Contention**:
    - The personalization service uses a single DuckDB instance (`student_analytics.duckdb`). 
    - Write operations require a table lock. Under massive concurrent write interactions, check for lock contention or SQLite/DuckDB lock failures in the `personalize-service` logs.
