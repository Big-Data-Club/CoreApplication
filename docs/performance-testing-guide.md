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

1.  **Install k6** locally or on the target virtual machine:
    ```bash
    # Debian/Ubuntu
    sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
    echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
    sudo apt-get update
    sudo apt-get install k6
    ```

2.  **Seed Test Accounts**:
    Execute the [seed_users.sql](file:///D:/CodeSpace/BDCHub/BDCmonitoring/performance-tests/seed_users.sql) script in your databases to seed 100 students, 10 teachers, and 5 admins:
    - Run the **PART 1** section on the Auth database (`postgres` on port `5433`, database `auth`).
    - Run the **PART 2** section on the LMS database (`postgres-lms` on port `5434`, database `lms`).

### Running the Test

The performance scripts are located in the [BDCmonitoring performance-tests](file:///D:/CodeSpace/BDCHub/BDCmonitoring/performance-tests/) directory. Navigate to `D:/CodeSpace/BDCHub/BDCmonitoring/` before running tests.

Since Virtual Users (VUs) map dynamically to the seeded accounts and logins are cached per VU lifecycle, you do not need to provide individual emails. All scripts support the environment variable `TEST_TYPE` to select the type of concurrency scenario to execute:
- `smoke`: Syntax/script verification (1 VU, 1 iteration, 10 seconds).
- `load`: Gradually ramp up to expected normal/peak load.
- `stress`: Heavy concurrency pushing the boundaries to find the "lag breakpoint".
- `spike`: Sudden massive traffic burst within seconds, followed by a rapid drop-off.
- `soak`: Prolonged constant moderate load to detect memory leaks or resource creep.

#### Student Workload
Simulates student learning activities (reading content, micro-interactions, personalization profile reading):
```bash
# Navigate to monitoring folder and run student stress test
cd D:/CodeSpace/BDCHub/BDCmonitoring
TEST_TYPE="stress" \
BASE_URL="http://localhost:3000" \
COURSE_ID="19" \
NODE_ID="2221" \
AI_SERVICE_SECRET="ai-service-secret-change-me" \
k6 run performance-tests/k6_student_flow.js
```

#### Teacher Workload
Simulates teacher operations (dashboard monitoring, progress checks, course contents updates):
```bash
# Navigate to monitoring folder and run teacher load test
cd D:/CodeSpace/BDCHub/BDCmonitoring
TEST_TYPE="load" \
BASE_URL="http://localhost:3000" \
COURSE_ID="19" \
k6 run performance-tests/k6_teacher_flow.js
```

#### Admin Workload
Simulates management operations (user listing, DuckDB analytical gold queries, heavy parquet exports):
```bash
# Navigate to monitoring folder and run admin soak test
cd D:/CodeSpace/BDCHub/BDCmonitoring
TEST_TYPE="soak" \
BASE_URL="http://localhost:3000" \
AI_SERVICE_SECRET="ai-service-secret-change-me" \
k6 run performance-tests/k6_admin_flow.js
```

#### Multi-Role Combined Workload
Simulates a complete production mix (85% Students, 12% Teachers, 3% Admins running concurrently):
```bash
# Navigate to monitoring folder and run multi-role load test
cd D:/CodeSpace/BDCHub/BDCmonitoring
TEST_TYPE="load" \
BASE_URL="http://localhost:3000" \
COURSE_ID="19" \
NODE_ID="2221" \
AI_SERVICE_SECRET="ai-service-secret-change-me" \
k6 run performance-tests/k6_multi_role_flow.js
```

#### HTML Report
Upon completion, the test automatically outputs a self-contained interactive HTML dashboard named `summary.html` in the directory where the command was run. Open this file in any web browser to view visual charts of response times, request rates, VUs, error rates, and check statuses.

### Cleaning Up Test Data

Once testing is complete, execute the [cleanup_users.sql](file:///D:/CodeSpace/BDCHub/BDCmonitoring/performance-tests/cleanup_users.sql) script in your databases to cleanly wipe all test users and their dependent records:
- Run the **PART 1** section on the LMS database (`postgres-lms` on port `5434`, database `lms`).
- Run the **PART 2** section on the Auth database (`postgres` on port `5433`, database `auth`).

This ensures that zero dangling records remain in the tables.

---

## 6. Identifying Performance Bottlenecks (Lag Diagnosis)

When running the load test, monitor these telemetry signs to identify lag:

1.  **k6 Terminal & HTML Report Outputs**:
    - Look for `http_req_duration` metrics. If the `p(95)` value jumps above 800ms (or 1000ms for multi-role), the system is lagging.
    - Check `http_req_failed` rate. A value above 0% indicates container failures or database timeouts.
2.  **Container Resource Consumption**:
    - Monitor resource usage on the server using `docker stats`.
    - If `lms-service` or `personalize-service` CPU hits 100%, the bottleneck is compute capacity.
    - If `postgres-lms` or `postgres-ai` CPU is high, check for missing indexes in database query paths.
3.  **Database Connection Pooling**:
    - Check if the HikariCP or Go database connection pool size is exhausted. Look for `Connection timeout` or `Too many connections` in the service logs.
4.  **DuckDB Lock Contention**:
    - Under massive concurrent write interactions, check for lock contention or SQLite/DuckDB lock failures in the `personalize-service` logs.

---

## 7. Comparative Analysis of Load Testing Tools

To understand where k6 fits in the enterprise performance engineering ecosystem, the following table compares common concurrency testing tools:

| Category / Feature | Grafana k6 (Used here) | Apache JMeter | Gatling | Locust | Tricentis NeoLoad |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Scripting Style** | Code-centric (JavaScript) | GUI / XML Config | Code-centric (Java/Scala/Kotlin) | Code-centric (Python) | GUI / Visual drag-and-drop |
| **Execution Performance** | Extremely high (Go-based runner) | Moderate (JVM-based thread-per-VU) | Very High (Asynchronous non-blocking Scala/Netty) | High (Event-driven Python gevent) | High (Optimized Java load generator) |
| **Microservices / DevOps Integration** | Native (Excellent for CI/CD pipelines) | Poor (Bulky XML, CLI runs are clunky) | Good (Build tool plugin native) | Good (Python framework friendly) | Enterprise-focused |
| **Protocol Support** | HTTP, WebSockets, gRPC, Redis | Unmatched (HTTP, JDBC, JMS, gRPC, etc.) | HTTP, WebSockets, gRPC, JMS | HTTP (others via custom clients) | Web, SAP, Citrix, REST, MQ |
| **Observability Integration** | Native integration with Grafana / Prometheus | Requires custom backend listeners | Gatling Enterprise / Custom plugins | Live web dashboard | Built-in analytics dashboard |

### Why k6 is Preferred for the BDC Microservices Stack:
- **Developer-Friendly (As-Code)**: Writing tests in JavaScript allows the same development team to manage, review, and version-control the performance suite in the main codebase.
- **Ultra-Lightweight**: A single k6 load generator container can run thousands of VUs with low footprint compared to JMeter's high JVM thread overhead.
- **CI/CD Native**: Running `k6 run` returns shell status codes and generates reports out-of-the-box, integrating smoothly with GitHub Actions pipelines.
- **observability Integration**: k6 outputs metrics natively to Prometheus/Grafana, matching BDC's Docker monitoring setup.

---

## 8. Running k6 with Docker & Integrating with BDCmonitoring

### 8.1 Running k6 via Docker

If you do not want to install k6 locally, you can run the tests using the official Docker image. Mount your local workspace folder into the container's `/io` workspace and run the test:

```bash
docker run --rm -i \
  --network=app-network \
  -v "$PWD:/io" \
  -w /io \
  -e TEST_TYPE="load" \
  -e BASE_URL="http://host.docker.internal:3000" \
  -e COURSE_ID="19" \
  -e NODE_ID="2221" \
  -e AI_SERVICE_SECRET="ai-service-secret-change-me" \
  grafana/k6 run performance-tests/k6_student_flow.js
```
*Note: `http://host.docker.internal:3000` allows the containerized k6 executor to communicate with host-exposed ports.*

### 8.2 Real-time Monitoring with Grafana & Prometheus

By integrating with the [BDCmonitoring](file:///D:/CodeSpace/BDCHub/BDCmonitoring) stack, k6 can output metrics to Prometheus in real-time to view on a dedicated Grafana dashboard.

#### Step 1: Enable Remote Write in Prometheus
We have modified the `docker-compose.yml` in the `BDCmonitoring` stack to include the `--web.enable-remote-write-receiver` flag on the `prometheus` service. Re-deploy the Prometheus container to apply this change:
```bash
# Navigate to D:/CodeSpace/BDCHub/BDCmonitoring and run:
docker compose up -d --force-recreate prometheus
```

#### Step 2: Execute k6 with Prometheus Output
Run the k6 container within the same `app-network` and target the internal Prometheus receiver endpoint:
```bash
docker run --rm -i \
  --network=app-network \
  -v "$PWD:/io" \
  -w /io \
  -e TEST_TYPE="load" \
  -e BASE_URL="http://host.docker.internal:3000" \
  -e COURSE_ID="19" \
  -e NODE_ID="2221" \
  -e AI_SERVICE_SECRET="ai-service-secret-change-me" \
  grafana/k6 run -o experimental-prometheus-rw=server-url=http://bdc-prometheus:9090/api/v1/write performance-tests/k6_student_flow.js
```

#### Step 3: Access Grafana Dashboard
We have provisioned the dashboard at [k6-performance.json](file:///D:/CodeSpace/BDCHub/BDCmonitoring/grafana/dashboards/k6-performance.json).
1. Open Grafana (`https://bdc.hpcc.vn/monitor/` or local port `3010`).
2. Go to **Dashboards** -> **k6 Performance Test Dashboard**.
3. View live metrics: Active VUs, request rate, error rate, and response times (P95, P99, average latency).

### 8.3 Standalone Execution via Docker Compose

To run the performance tests as a standalone setup completely isolated from the application's main Docker initialization, we have created a dedicated [docker-compose.k6.yml](../performance-tests/docker-compose.k6.yml) configuration inside the `performance-tests/` directory.

This allows you to execute testing commands cleanly using Docker Compose without copy-pasting long CLI arguments:

```bash
# Run the default Student Load Test (runs k6_student_flow.js)
docker compose -f performance-tests/docker-compose.k6.yml run --rm k6

# Run a Teacher Stress Test
TEST_TYPE="stress" docker compose -f performance-tests/docker-compose.k6.yml run --rm k6 run k6_teacher_flow.js

# Run an Admin Soak Test
TEST_TYPE="soak" docker compose -f performance-tests/docker-compose.k6.yml run --rm k6 run k6_admin_flow.js

# Run and stream metrics to Prometheus in real-time
docker compose -f performance-tests/docker-compose.k6.yml run --rm --network=app-network k6 run -o experimental-prometheus-rw=server-url=http://bdc-prometheus:9090/api/v1/write k6_student_flow.js
```


