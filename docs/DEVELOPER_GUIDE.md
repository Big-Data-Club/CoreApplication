# 🛠️ Hướng Dẫn Developer — BDC Application

> Tài liệu này dành cho **developer**, **contributor** và bất kỳ ai muốn chạy dự án ở local, tìm hiểu cấu trúc codebase, hoặc đóng góp tính năng mới. Đọc từ đầu đến cuối một lần — bạn sẽ tiết kiệm rất nhiều thời gian debug về sau.

---

> 🌐 **Chọn ngôn ngữ / Language:**
> &nbsp;&nbsp;[🇻🇳 Tiếng Việt](./DEVELOPER_GUIDE.md) &nbsp;|&nbsp; [🇬🇧 English](./DEVELOPER_GUIDE.en.md)

> 📚 **Tài liệu liên quan:**
> [📖 README — Tổng quan dự án](../README.md) · [⚠️ TECHNICAL_NOTES — Các vấn đề kỹ thuật quan trọng](./TECHNICAL_NOTES.md)

---

## 📋 Mục Lục

1. [Tổng Quan Dự Án](#1-tổng-quan-dự-án)
2. [Cấu Trúc Thư Mục](#2-cấu-trúc-thư-mục)
3. [Yêu Cầu Cài Đặt](#3-yêu-cầu-cài-đặt)
4. [Chạy Toàn Bộ Dự Án với Docker](#4-chạy-toàn-bộ-dự-án-với-docker)
5. [Chạy Từng Service Riêng Lẻ](#5-chạy-từng-service-riêng-lẻ)
6. [Cấu Hình Biến Môi Trường](#6-cấu-hình-biến-môi-trường)
7. [Luồng Hoạt Động Của Hệ Thống](#7-luồng-hoạt-động-của-hệ-thống)
8. [API Endpoints Tham Khảo Nhanh](#8-api-endpoints-tham-khảo-nhanh)
9. [Hướng Dẫn Đóng Góp Code](#9-hướng-dẫn-đóng-góp-code)
10. [Quy Trình CI/CD](#10-quy-trình-cicd)
11. [Xử Lý Sự Cố Thường Gặp](#11-xử-lý-sự-cố-thường-gặp)
12. [Câu Hỏi Thường Gặp](#12-câu-hỏi-thường-gặp)

---

## 1. Tổng Quan Dự Án

BDC Application là một **Learning Management System (LMS)** dạng microservices gồm 3 service chính giao tiếp với nhau qua mạng Docker nội bộ. Hiểu rõ sơ đồ dưới đây sẽ giúp bạn debug nhanh hơn rất nhiều khi gặp sự cố.

```
┌──────────────────────────────────────────────────────────────┐
│                    🌐 Trình duyệt / Client                    │
└──────────────────────────┬───────────────────────────────────┘
                           │ Port 3000
                           ▼
┌──────────────────────────────────────────────────────────────┐
│             🖥️  Frontend — Next.js 14 (TypeScript)            │
│   /apiv1/*  ──► Spring Boot Backend  (proxy rewrite)        │
│   /lmsapiv1/* ──► Go LMS Backend     (proxy rewrite)        │
│   /files/*  ──► LMS file serving                            │
└──────────┬──────────────────────────────┬────────────────────┘
           │ :8080                         │ :8081
           ▼                               ▼
┌──────────────────────┐     ┌─────────────────────────────────┐
│  ⚙️  Auth Backend     │     │  ⚙️  LMS Backend                 │
│   Spring Boot 3.x    │◄────│   Go 1.21 + Gin                 │
│   - Auth / JWT       │     │   - Khoá học, Quiz              │
│   - Users, Events    │     │   - Enroll, File upload         │
│   - Announcements    │     │   - Đồng bộ user từ Auth        │
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

### Công Nghệ Sử Dụng

| Thành phần | Công nghệ | Phiên bản |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, NextAuth.js | 14+ |
| Auth Backend | Spring Boot, Spring Security, JWT | 3.x (Java 21) |
| LMS Backend | Go, Gin framework, GORM | 1.21+ |
| Database | PostgreSQL | 15 |
| Cache | Redis | 7 |
| Object Storage | MinIO | Latest |
| Container | Docker, Docker Compose | 24+ / 2.0+ |

---

## 2. Cấu Trúc Thư Mục

```
CoreApplication/
│
├── 📁 frontend/                     # Next.js application
│   ├── src/
│   │   ├── app/                     # App Router (Next.js 14)
│   │   ├── components/              # React components tái sử dụng
│   │   └── lib/                     # Utility functions, custom hooks
│   ├── next.config.ts               # Cấu hình Next.js + proxy rewrites ← QUAN TRỌNG
│   └── Dockerfile
│
├── 📁 Backend/                      # Spring Boot (Auth Service)
│   ├── src/main/java/com/example/demo/
│   │   ├── controller/              # REST Controllers
│   │   ├── service/                 # Business logic
│   │   ├── repository/              # JPA Repositories
│   │   ├── model/                   # Entity / Domain models
│   │   └── config/                  # Security, CORS, JWT config
│   ├── src/main/resources/
│   │   └── application.yml          # Cấu hình Spring Boot
│   ├── init-scripts/                # SQL khởi tạo Auth database
│   ├── pom.xml
│   └── Dockerfile
│
├── 📁 LMS/                          # Go (LMS Service)
│   ├── cmd/server/main.go           # Entry point
│   ├── internal/
│   │   ├── handler/                 # HTTP handlers (Gin)
│   │   ├── service/                 # Business logic
│   │   ├── repository/              # Database queries (GORM)
│   │   └── model/                   # Data models
│   ├── migrations/                  # SQL migrations LMS database
│   ├── go.mod
│   └── Dockerfile
│
├── 📁 docs/                         # Tài liệu kỹ thuật ← BẠN ĐANG Ở ĐÂY
│   ├── DEVELOPER_GUIDE.md           # File này (Tiếng Việt)
│   ├── DEVELOPER_GUIDE.en.md        # Phiên bản Tiếng Anh
│   ├── TECHNICAL_NOTES.md           # Vấn đề kỹ thuật quan trọng (VI)
│   └── TECHNICAL_NOTES.en.md        # Vấn đề kỹ thuật quan trọng (EN)
│
├── 📁 .github/
│   ├── workflows/
│   │   ├── ci.yml                   # CI: Build, Test, Push Docker image
│   │   └── cd-production.yml        # CD: Deploy lên production
│   └── ISSUE_TEMPLATE/
│
├── docker-compose.yml               # Khởi chạy toàn bộ stack
├── .env.example                     # Template biến môi trường ← COPY CÁI NÀY
├── .env                             # File thực tế (KHÔNG bao giờ commit!)
└── README.md
```

> ⚠️ **Quan trọng:** File `.env` chứa thông tin bí mật (mật khẩu, JWT secret...) và đã được thêm vào `.gitignore`. Tuyệt đối **không commit** file này lên repository.

---

## 3. Yêu Cầu Cài Đặt

### Chạy bằng Docker — Khuyến nghị cho dev mới

Đây là cách đơn giản nhất. Bạn chỉ cần cài:

| Công cụ | Phiên bản tối thiểu | Link tải |
|---|---|---|
| Docker Desktop | 24.0+ | https://docs.docker.com/get-docker/ |
| Docker Compose | 2.0+ | Đi kèm Docker Desktop |
| Git | Bất kỳ | https://git-scm.com/ |

> Đảm bảo Docker Desktop đang chạy và được cấp ít nhất **4GB RAM** trong phần Settings → Resources.

### Chạy từng service riêng lẻ — Cho dev nâng cao

Nếu bạn muốn hot-reload và debug trực tiếp trên máy:

| Công cụ | Phiên bản | Dùng cho |
|---|---|---|
| Node.js + npm | 20 LTS | Frontend |
| JDK (Temurin) | 21 | Backend Java |
| Go | 1.21+ | LMS Service |

---

## 4. Chạy Toàn Bộ Dự Án với Docker

Đây là cách **nhanh nhất** để có môi trường đầy đủ hoạt động trên máy bạn.

### Bước 1 — Clone repository

```bash
git clone https://github.com/Big-Data-Club/CoreApplication.git
cd CoreApplication
```

### Bước 2 — Tạo file biến môi trường

```bash
cp .env.example .env
```

Mở `.env` và điền các giá trị quan trọng. Xem [Mục 6](#6-cấu-hình-biến-môi-trường) để hiểu từng biến, và [TECHNICAL_NOTES.md](./TECHNICAL_NOTES.md) để biết những biến nào nếu sai sẽ gây lỗi im lặng.

### Bước 3 — Build và khởi chạy

```bash
# Lần đầu tiên — sẽ pull image và build, mất 3-5 phút
docker compose up -d --build

# Những lần sau khi không có thay đổi code
docker compose up -d
```

### Bước 4 — Kiểm tra trạng thái

```bash
# Xem tất cả container (STATUS phải là "healthy", không phải "starting")
docker compose ps

# Xem log realtime của từng service
docker compose logs -f frontend
docker compose logs -f backend
docker compose logs -f lms-backend
```

### Bước 5 — Truy cập ứng dụng

| Dịch vụ | URL |
|---|---|
| 🌐 Frontend | http://localhost:3000 |
| ⚙️ Auth API | http://localhost:3000/apiv1 hoặc http://localhost:8080 |
| ⚙️ LMS API | http://localhost:3000/lmsapiv1 hoặc http://localhost:8081 |
| 📚 Swagger Auth | http://localhost:8080/swagger-ui.html |
| 📚 Swagger LMS | http://localhost:8081/swagger/index.html |
| 📦 MinIO Console | http://localhost:9001 |

### Dừng và dọn dẹp

```bash
docker compose down           # Dừng tất cả, giữ nguyên data
docker compose down -v        # Dừng + xoá toàn bộ data (volumes)
docker compose restart backend         # Restart riêng một service
docker compose up -d --build frontend  # Rebuild sau khi sửa code
```

---

## 5. Chạy Từng Service Riêng Lẻ

Phương pháp này phù hợp khi bạn đang **tập trung phát triển một service** và muốn hot-reload nhanh hơn.

**Chiến lược:** Giữ các service infrastructure (database, Redis, MinIO) chạy bằng Docker, còn service đang phát triển thì chạy trực tiếp trên máy.

```bash
# Chỉ khởi động infrastructure — không cần build lại code
docker compose up -d postgres postgres-lms redis-lms minio
```

### 5.1 Frontend (Next.js)

```bash
cd frontend

npm install

# Tạo file env local (trỏ BACKEND_URL về localhost thay vì Docker container)
cp .env.local.example .env.local
# Chỉnh: BACKEND_URL=http://localhost:8080, LMS_API_URL=http://localhost:8081

npm run dev    # Dev server với hot-reload tự động
```

Frontend chạy tại **http://localhost:3000**

**Các script hữu ích:**

| Lệnh | Mô tả |
|---|---|
| `npm run dev` | Dev server với hot-reload |
| `npm run build` | Build production |
| `npm run lint` | Kiểm tra lỗi ESLint |
| `npm run test:ci` | Chạy unit tests |

> **Về proxy:** File `next.config.ts` đã cấu hình rewrite để route `/apiv1/*` → Spring Boot và `/lmsapiv1/*` → Go. Khi chạy local, bạn cần đảm bảo các backend service đang lắng nghe đúng port.

### 5.2 Auth Backend (Spring Boot)

```bash
cd Backend

# Đảm bảo PostgreSQL đang chạy (từ Docker): docker compose ps postgres

# Chạy bằng Maven Wrapper (không cần cài Maven)
./mvnw spring-boot:run

# Hoặc chỉ định profile local
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Backend chạy tại **http://localhost:8080**

Nếu muốn kết nối database local, tạo file `src/main/resources/application-local.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5433/club_db
    username: postgres
    password: 123456
```

**Các lệnh Maven hữu ích:**

| Lệnh | Mô tả |
|---|---|
| `./mvnw spring-boot:run` | Chạy dev |
| `./mvnw test` | Chạy tests |
| `./mvnw clean package -DskipTests` | Build JAR |
| `./mvnw clean package` | Build + test |

### 5.3 LMS Backend (Go + Gin)

```bash
cd LMS

go mod download

go run cmd/server/main.go
```

LMS Service chạy tại **http://localhost:8081**

Các biến môi trường cần thiết khi chạy local (tạo file `.env` trong thư mục `LMS/` hoặc export):

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

**Các lệnh Go hữu ích:**

| Lệnh | Mô tả |
|---|---|
| `go run cmd/server/main.go` | Chạy dev |
| `go test ./...` | Chạy toàn bộ tests |
| `go test -v ./... -coverprofile=coverage.out` | Test + coverage report |
| `go build -v ./...` | Build kiểm tra lỗi compile |
| `go vet ./...` | Static analysis |

---

## 6. Cấu Hình Biến Môi Trường

Sao chép `.env.example` thành `.env` và điền các giá trị. Dưới đây là giải thích theo nhóm.

### 🔐 Bảo mật — Bắt buộc phải đổi

```env
# JWT: Khoá bí mật dùng để ký và xác thực token
# PHẢI giống nhau giữa Backend và LMS — PHẢI >= 32 ký tự!
JWT_SECRET=thay-bang-chuoi-ngau-nhien-dai-hon-32-ky-tu

# NextAuth: Khoá mã hoá session của Next.js
NEXTAUTH_SECRET=thay-bang-chuoi-ngau-nhien-khac-hoàn-toàn

# Secret đồng bộ user giữa 2 service backend (PHẢI bằng nhau)
LMS_API_SECRET=chuoi-bi-mat-sync
LMS_SYNC_SECRET=chuoi-bi-mat-sync   # phải bằng LMS_API_SECRET
```

> 💡 Tạo chuỗi ngẫu nhiên an toàn: `openssl rand -base64 32`

### 🌐 URL — Tuỳ theo môi trường

```env
# Dev local
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:3000/apiv1
NEXT_PUBLIC_LMS_API_URL=http://localhost:3000/lmsapiv1
APP_PUBLIC_URL=http://localhost:3000    # Dùng trong link email reset password

# Giao tiếp nội bộ Docker network (giữ nguyên khi dùng Docker Compose)
BACKEND_URL=http://backend:8080
LMS_API_URL=http://lms-backend:8081
```

### 🗄️ Database

```env
# Auth Database (PostgreSQL)
POSTGRES_DB=club_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=mat-khau-manh-cua-ban
POSTGRES_PORT=5433

# LMS Database (PostgreSQL)
LMS_POSTGRES_DB=lms_db
LMS_POSTGRES_USER=lms_user
LMS_POSTGRES_PASSWORD=mat-khau-lms-manh
LMS_POSTGRES_PORT=5434
```

### ⚡ Redis & MinIO

```env
REDIS_PASSWORD=mat-khau-redis-manh
REDIS_PORT=6379

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=mat-khau-minio-dai-hon-8-ky-tu  # MinIO yêu cầu >= 8 ký tự
```

### 📧 Email

```env
EMAIL=your-email@gmail.com
EMAIL_PASSWORD=google-app-password-16-ky-tu   # Xem TECHNICAL_NOTES.md Mục 2

APP_PUBLIC_URL=http://localhost:3000   # Link trong email, phải truy cập được từ máy user
```

> ⚠️ Cấu hình email sai sẽ khiến `bulkRegister` vẫn tạo user thành công nhưng user không nhận được mật khẩu — không thể đăng nhập. Xem chi tiết tại [TECHNICAL_NOTES.md — Mục 2](./TECHNICAL_NOTES.md#2-email--cấu-hình-gmail-smtp).

---

## 7. Luồng Hoạt Động Của Hệ Thống

### Luồng Xác Thực (Authentication)

```
Client           Frontend                Backend (Spring)
  │                 │                          │
  │── POST /apiv1/auth/login ────────────────►│
  │                 │                          │ Validate credentials
  │                 │                          │ Generate JWT token
  │◄── Set-Cookie (httpOnly) + JWT ────────────│
  │                 │                          │
  │── GET /apiv1/users (Bearer token) ────────►│
  │                 │                          │ Validate JWT
  │◄── User data ───────────────────────────────│
```

### Luồng Đồng Bộ User (User Sync)

Khi Admin tạo user mới, hệ thống tự động sync sang LMS để user có thể đăng ký khoá học ngay:

```
Admin tạo user
      │
      ▼
Backend (Spring) ─── POST /api/v1/sync/user ───► LMS Backend (Go)
     (kèm X-Sync-Secret header)                         │
                                              Lưu user vào LMS DB
                                              (chạy async, không block response)
```

> Vì sync chạy **bất đồng bộ**, lỗi sync chỉ hiện trong log, không throw exception về client. Xem [TECHNICAL_NOTES.md — Mục 4](./TECHNICAL_NOTES.md#4-user-sync--đồng-bộ-bất-đồng-bộ-dễ-bị-bỏ-lỡ).

### Luồng Upload File

```
Client ─── POST /lmsapiv1/files/upload ────► LMS Backend
                                                   │ Lưu vào /app/uploads
                                                   │ Trả về filepath
Client ─── GET /files/{filepath} ──────────► Next.js (proxy)
                                                   │
                                        ──────► LMS /api/v1/files/serve/{filepath}
```

---

## 8. API Endpoints Tham Khảo Nhanh

### Auth Service (`/apiv1`)

| Method | Endpoint | Mô tả | Role |
|---|---|---|---|
| POST | `/api/auth/login` | Đăng nhập | Public |
| POST | `/api/auth/logout` | Đăng xuất | Authenticated |
| POST | `/api/auth/register/bulk` | Tạo hàng loạt user | Admin |
| GET | `/api/users` | Danh sách users | Admin/Manager |
| GET | `/api/events` | Danh sách sự kiện | Authenticated |
| GET | `/api/tasks` | Danh sách nhiệm vụ | Authenticated |
| GET | `/api/announcements` | Thông báo hệ thống | Authenticated |

### LMS Service (`/lmsapiv1`)

| Method | Endpoint | Mô tả | Role |
|---|---|---|---|
| GET | `/api/v1/courses` | Danh sách khoá học | Authenticated |
| POST | `/api/v1/courses` | Tạo khoá học | Teacher/Admin |
| PUT | `/api/v1/courses/:id` | Cập nhật khoá học | Teacher/Admin |
| POST | `/api/v1/enrollments` | Đăng ký khoá học | Student |
| GET | `/api/v1/quizzes` | Danh sách quiz | Authenticated |
| POST | `/api/v1/quizzes` | Tạo quiz | Teacher/Admin |
| POST | `/api/v1/files/upload` | Upload file | Authenticated |
| GET | `/api/v1/files/serve/:path` | Serve file | Public |
| POST | `/api/v1/sync/user` | Sync một user | Internal (Sync Secret) |
| POST | `/api/v1/sync/users/bulk` | Sync nhiều user | Internal (Sync Secret) |

> Xem đầy đủ tại Swagger UI: http://localhost:8080/swagger-ui.html (Auth) và http://localhost:8081/swagger/index.html (LMS)

---

## 9. Hướng Dẫn Đóng Góp Code

### Quy Tắc Đặt Tên Branch

```
feature/ten-tinh-nang-moi       # Tính năng mới
fix/mo-ta-bug-can-sua           # Sửa bug
hotfix/van-de-khẩn-cap          # Sửa lỗi production khẩn cấp
refactor/phan-can-cai-thien     # Cải thiện code không đổi behaviour
docs/cap-nhat-tai-lieu          # Cập nhật tài liệu
```

### Quy Trình Đóng Góp

```bash
# 1. Fork repo trên GitHub (nhấn nút "Fork")

# 2. Clone về máy
git clone https://github.com/YOUR_USERNAME/CoreApplication.git
cd CoreApplication

# 3. Thêm upstream để sync với repo gốc
git remote add upstream https://github.com/Big-Data-Club/CoreApplication.git

# 4. Tạo branch mới
git checkout -b feature/quiz-timer

# 5. Viết code, commit thường xuyên
git add .
git commit -m "feat(lms): add countdown timer for quiz"

# 6. Sync với upstream trước khi push để tránh conflict
git fetch upstream
git rebase upstream/develop

# 7. Push lên fork của bạn
git push origin feature/quiz-timer

# 8. Tạo Pull Request lên branch develop của repo gốc
```

### Format Commit Message

Tuân theo [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <mô tả ngắn gọn>

# type: feat | fix | docs | style | refactor | test | chore | hotfix
# scope: frontend | backend | lms | docker | ci

# Ví dụ thực tế:
feat(lms): add video upload progress bar
fix(backend): resolve JWT expiration not refreshing
docs(readme): update local setup instructions
refactor(frontend): extract quiz component into separate file
test(lms): add unit tests for enrollment service
```

### Checklist Trước Khi Tạo Pull Request

- [ ] Code chạy được ở local không có lỗi
- [ ] Đã test tính năng vừa thêm/sửa thủ công
- [ ] Không có `console.log` hay `fmt.Println` debug còn sót lại
- [ ] Không commit file `.env` hoặc bất kỳ secret nào
- [ ] Đã cập nhật tài liệu nếu thay đổi API hoặc cấu hình
- [ ] Title PR rõ ràng, mô tả đủ những gì thay đổi và lý do
- [ ] Code tuân theo coding conventions của project

### Coding Conventions

**Frontend (TypeScript/Next.js):**
- TypeScript strict mode — tránh dùng `any`
- Components dùng arrow function và named export
- Tên file component: `PascalCase.tsx` · Tên hook/utility: `camelCase.ts`
- Styling hoàn toàn bằng Tailwind CSS, tránh inline style

**Backend (Java/Spring Boot):**
- Tuân theo Spring Boot conventions — Controller chỉ nhận/trả request, business logic trong Service
- Dùng `@Slf4j` (Lombok) để logging, không dùng `System.out.println`
- Viết Javadoc cho public methods

**LMS (Go):**
- Tuân theo [Effective Go](https://go.dev/doc/effective_go)
- Error handling rõ ràng — không bỏ qua error với `_`
- Chạy `go vet ./...` trước khi commit

---

## 10. Quy Trình CI/CD

### CI — Kích hoạt khi có Pull Request hoặc Push

```
Code push / PR mở
        │
        ▼
🔍 Detect Changes
        │ (Chỉ build service nào có file thay đổi — tiết kiệm thời gian)
        ▼
🔨 Build & Test  (chạy song song)
  ├── Backend : ./mvnw test
  ├── Frontend: npm run test:ci
  └── LMS     : go test ./...
        │
        ▼
🔒 Security Scan (Trivy — quét lỗ hổng bảo mật trong Docker image)
        │
        ▼
🐳 Push Docker Image
        └── Chỉ thực hiện khi merge vào main hoặc develop
```

### CD — Deploy Production (khi merge vào main)

Workflow `cd-production.yml` tự động:
1. Pull Docker image mới từ Docker Hub
2. SSH vào server production
3. Chạy `docker compose pull && docker compose up -d`

### GitHub Secrets cần thiết

Vào **Settings → Secrets and variables → Actions** của repo và thêm:

| Secret | Mô tả |
|---|---|
| `DOCKER_USERNAME` | Username Docker Hub |
| `DOCKER_PASSWORD` | Password hoặc Access Token Docker Hub |
| `SSH_HOST` | IP hoặc hostname server production |
| `SSH_USER` | Username SSH |
| `SSH_PRIVATE_KEY` | Nội dung private key SSH |

---

## 11. Xử Lý Sự Cố Thường Gặp

### ❌ Container không khởi động hoặc mãi ở trạng thái "starting"

```bash
# Xem log chi tiết để tìm nguyên nhân
docker compose logs backend
docker compose logs lms-backend
docker compose logs frontend

# Kiểm tra trạng thái tất cả service
docker compose ps
```

### ❌ Backend báo lỗi kết nối database

```bash
# Kiểm tra postgres có healthy không
docker compose ps postgres

# Thử kết nối thủ công
docker compose exec postgres psql -U postgres -d club_db

# Nếu lần đầu chạy, đảm bảo init-scripts được chạy (chỉ chạy khi volume trống)
# CẢNH BÁO: Lệnh dưới đây xoá toàn bộ data!
docker compose down -v && docker compose up -d
```

### ❌ Frontend không gọi được API — lỗi CORS hoặc 502

1. Kiểm tra biến `BACKEND_URL` trong `.env` (phải là `http://backend:8080` khi dùng Docker)
2. Xác nhận backend đang healthy: `docker compose ps backend`
3. Test trực tiếp: `curl http://localhost:8080/actuator/health`
4. Kiểm tra `CORS_ALLOWED_ORIGINS` phải chứa URL frontend của bạn

Xem thêm chi tiết CORS tại [TECHNICAL_NOTES.md — Mục 3](./TECHNICAL_NOTES.md#3-cors--cấu-hình-ở-3-nơi-khác-nhau).

### ❌ Lỗi "Port already in use"

```bash
# Tìm process đang chiếm port (ví dụ port 3000)
lsof -i :3000           # macOS / Linux
netstat -ano | findstr :3000  # Windows

# Giải phóng port
kill -9 <PID>           # macOS / Linux
taskkill /PID <PID> /F  # Windows

# Hoặc đổi port trong .env
FRONTEND_PORT=3001
BACKEND_PORT=8082
```

### ❌ LMS Service lỗi kết nối Redis

```bash
docker compose ps redis-lms

# Test kết nối Redis
docker compose exec redis-lms redis-cli -a redis_password ping
# Kết quả mong đợi: PONG
```

### ❌ LMS không thể upload file hoặc file mất sau restart

Kiểm tra `docker-compose.yml` đã mount volume cho `/app/uploads` chưa, và xác nhận `STORAGE_TYPE` trong `.env` (local hoặc minio). Xem [TECHNICAL_NOTES.md — Mục 5](./TECHNICAL_NOTES.md#5-storage--local-vs-minio).

### ❌ Docker build lỗi do hết memory

```bash
# Kiểm tra resource: Docker Desktop → Settings → Resources
# Khuyến nghị: RAM >= 4GB, Swap >= 2GB

# Build từng service thay vì toàn bộ cùng lúc
docker compose build backend
docker compose build frontend
docker compose build lms-backend
```

---

## 12. Câu Hỏi Thường Gặp

**Q: Tôi chỉ cần dev Frontend, có cần chạy LMS Backend không?**

Tuỳ vào tính năng bạn đang làm. Nếu chỉ làm UI không liên quan đến LMS, chạy `docker compose up -d postgres backend` là đủ. Nếu cần dữ liệu giả, có thể dùng mock data hoặc MSW (Mock Service Worker).

**Q: JWT_SECRET có cần giống nhau giữa Backend và LMS không?**

Có, **bắt buộc**. Cả hai service cùng verify JWT bằng một secret. Nếu khác nhau, LMS sẽ từ chối toàn bộ request có token từ Auth service với lỗi `401`. Xem [TECHNICAL_NOTES.md — Mục 1](./TECHNICAL_NOTES.md#1-jwt--chia-sẻ-secret-giữa-2-backend).

**Q: Tại sao có 2 database PostgreSQL riêng biệt?**

Đây là thiết kế microservices — mỗi service sở hữu database riêng để độc lập và dễ scale. Auth service quản lý `users`, `events`, `announcements`. LMS service quản lý `courses`, `quizzes`, `enrollments`. User data được sync giữa 2 hệ thống qua API nội bộ.

**Q: Làm sao để xem database trực tiếp?**

Dùng bất kỳ PostgreSQL client nào (DBeaver, TablePlus, pgAdmin...):
- Auth DB: host `localhost`, port `5433`, user/pass từ `.env`
- LMS DB: host `localhost`, port `5434`, user/pass từ `.env`

**Q: Làm sao để thêm database migration?**

Với **Backend (Spring Boot):** Hiện tại `JPA_DDL_AUTO=update` nên Hibernate tự tạo/sửa bảng theo Entity. Để migration có kiểm soát hơn, thêm Flyway vào `pom.xml`. Với **LMS (Go):** Thêm file `.sql` vào `LMS/migrations/` và dùng `golang-migrate`.

**Q: Làm sao debug Spring Boot trong IntelliJ IDEA?**

```bash
./mvnw spring-boot:run \
  -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005"
```

Sau đó trong IntelliJ: Run → Attach to Process, chọn port 5005.

---

## 📞 Liên Hệ & Hỗ Trợ

- **Issues:** Tạo issue trên GitHub với template tương ứng
- **Discussions:** Dùng GitHub Discussions cho câu hỏi chung
- **Email:** bdc@hcmut.edu.vn

---

<div align="center">

[📖 README](../README.md) · [⚠️ Technical Notes](./TECHNICAL_NOTES.md) · [🇬🇧 English Version](./DEVELOPER_GUIDE.en.md)

*Tài liệu này được cập nhật lần cuối: 02/2026. Nếu bạn phát hiện thông tin lỗi thời, vui lòng tạo PR để cập nhật!* 🙏

</div>