# 📚 BDC Application

> Nền tảng quản lý học tập thế hệ mới — microservices-based LMS xây dựng với **Next.js**, **Spring Boot** và **Go**, hướng tới một hệ sinh thái học tập thích ứng với AI.

[![CI](https://github.com/Big-Data-Club/CoreApplication/actions/workflows/ci.yml/badge.svg)](https://github.com/Big-Data-Club/CoreApplication/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker)](./docker-compose.yml)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![Spring Boot](https://img.shields.io/badge/Spring_Boot-3.x-green?logo=springboot)](https://spring.io)
[![Go](https://img.shields.io/badge/Go-1.21-00ADD8?logo=go)](https://golang.org)

---

> 🌐 **Chọn ngôn ngữ / Language:**
> &nbsp;&nbsp;[🇻🇳 Tiếng Việt](./README.md) &nbsp;|&nbsp; [🇬🇧 English](./README.en.md)

---

## 📖 Tài Liệu Dành Cho Developer

> Bạn là dev mới hoặc contributor? Hãy đọc các tài liệu này **theo thứ tự** trước khi bắt đầu:

| Tài liệu | Mô tả | Ngôn ngữ |
|---|---|---|
| **[🛠️ DEVELOPER_GUIDE](./docs/DEVELOPER_GUIDE.md)** | Setup môi trường, chạy local, quy trình đóng góp code | [🇻🇳 VI](./docs/DEVELOPER_GUIDE.md) · [🇬🇧 EN](./docs/DEVELOPER_GUIDE.en.md) |
| **[⚠️ TECHNICAL_NOTES](./docs/TECHNICAL_NOTES.md)** | Các vấn đề kỹ thuật quan trọng — **đọc kỹ trước khi build** | [🇻🇳 VI](./docs/TECHNICAL_NOTES.md) · [🇬🇧 EN](./docs/TECHNICAL_NOTES.en.md) |
| **[🔑 .env.example](./.env.example)** | Template biến môi trường có chú thích — sao chép thành `.env` để bắt đầu | — |

---

## 🌟 Tổng Quan

BDC Application là một **Learning Management System (LMS)** dạng microservices, được thiết kế cho các tổ chức giáo dục và câu lạc bộ học thuật. Hệ thống hiện cung cấp đầy đủ tính năng cốt lõi về quản lý khoá học, đăng ký, đánh giá và quản trị người dùng.

Định hướng phát triển tiếp theo là tích hợp **AI** để chuyển đổi từ một LMS truyền thống sang một **hệ sinh thái học tập thích ứng** — nơi mỗi sinh viên có lộ trình học cá nhân hóa riêng, được dẫn dắt bởi dữ liệu hành vi học tập thực tế.

### Tính Năng Hiện Tại

- 🎓 **Quản lý khoá học** — Tạo, chỉnh sửa và tổ chức khoá học với nội dung đa phương tiện (video, tài liệu, bài kiểm tra)
- 👥 **Đăng ký khoá học** — Hệ thống đăng ký linh hoạt với quy trình xét duyệt
- 📝 **Quiz & Đánh giá** — Nhiều loại câu hỏi, theo dõi kết quả và lịch sử làm bài
- 👤 **Quản lý người dùng** — Phân quyền theo vai trò: Admin, Manager, Teacher, Student
- 📢 **Thông báo** — Thông báo toàn hệ thống và theo từng khoá học
- 📅 **Quản lý sự kiện** — Theo dõi sự kiện, nhiệm vụ và deadline của câu lạc bộ
- 📁 **Quản lý file** — Upload và serve video, tài liệu, hình ảnh (Local hoặc MinIO)
- 🔐 **Xác thực bảo mật** — JWT-based authentication với HTTP-only cookie
- 🔄 **Đồng bộ người dùng** — Tự động sync giữa Auth Service và LMS Service

---

## 🏗️ Kiến Trúc Hệ Thống

```
┌──────────────────────────────────────────────────────────────┐
│                    🌐 Trình duyệt / Client                    │
└──────────────────────────┬───────────────────────────────────┘
                           │ Port 3000
                           ▼
┌──────────────────────────────────────────────────────────────┐
│             🖥️  Frontend — Next.js 14 (TypeScript)            │
│   /apiv1/*  ──────────► Backend  (proxy rewrite)             │
│   /lmsapiv1/*  ────────► LMS Backend  (proxy rewrite)        │
│   /files/*  ───────────► LMS (file serving)                  │
└──────────┬──────────────────────────────┬────────────────────┘
           │ :8080                         │ :8081
           ▼                               ▼
┌──────────────────────┐     ┌─────────────────────────────────┐
│  ⚙️  Auth Backend     │     │  ⚙️  LMS Backend                 │
│   Spring Boot 3.x    │◄────│   Go 1.21 + Gin                 │
│   - JWT / Auth       │     │   - Khoá học, Quiz              │
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

### Technology Stack

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

## 🚀 Bắt Đầu Nhanh

### Yêu cầu tối thiểu

- **Docker Desktop** 24.0+ và **Docker Compose** 2.0+
- **Git**
- RAM tối thiểu **4GB** cho Docker

### 3 bước để chạy toàn bộ stack

```bash
# Bước 1: Clone repository
git clone https://github.com/Big-Data-Club/CoreApplication.git
cd CoreApplication

# Bước 2: Tạo file cấu hình từ template
cp .env.example .env
# Mở .env và điền các giá trị cần thiết
# (xem TECHNICAL_NOTES.md để biết biến nào quan trọng nhất)

# Bước 3: Build và khởi chạy toàn bộ stack
docker compose up -d --build
```

### Truy Cập Ứng Dụng

Sau khi tất cả container healthy (khoảng 1–2 phút), bạn có thể truy cập:

| Dịch vụ | URL |
|---|---|
| 🌐 Frontend | http://localhost:3000 |
| ⚙️ Auth API + Swagger | http://localhost:8080/swagger-ui.html |
| ⚙️ LMS API + Swagger | http://localhost:3000/lmsapidocs/swagger/index.html |
| 📦 MinIO Console | http://localhost:9001 |

> **Tài khoản admin mặc định** — Đổi ngay sau lần đăng nhập đầu tiên!
> Email: `phucnhan289@gmail.com` · Password: `hehehe`
> Chi tiết: [TECHNICAL_NOTES.md — Mục 6: DataInitializer](./docs/TECHNICAL_NOTES.md#6-datainitializer--tài-khoản-admin-mặc-định)

---

## 📖 API Documentation

### Auth Service (`/apiv1`)

Base URL: `http://localhost:8080/api` — Swagger đầy đủ: http://localhost:8080/swagger-ui.html

| Method | Endpoint | Mô tả | Role |
|---|---|---|---|
| POST | `/auth/login` | Đăng nhập, nhận JWT | Public |
| POST | `/auth/logout` | Đăng xuất, xoá cookie | Authenticated |
| POST | `/auth/register/bulk` | Tạo hàng loạt user, gửi email mật khẩu | Admin |
| GET | `/users` | Danh sách users có phân trang | Admin/Manager |
| GET | `/events` | Danh sách sự kiện | Authenticated |
| GET | `/tasks` | Danh sách nhiệm vụ | Authenticated |
| GET | `/announcements` | Thông báo hệ thống | Authenticated |

### LMS Service (`/lmsapiv1`)

Base URL: `http://localhost:8081/api/v1` — Swagger đầy đủ: http://localhost:3000/lmsapidocs/swagger/index.html

| Method | Endpoint | Mô tả | Role |
|---|---|---|---|
| GET | `/courses` | Danh sách khoá học | Authenticated |
| POST | `/courses` | Tạo khoá học mới | Teacher/Admin |
| POST | `/enrollments` | Đăng ký khoá học | Student |
| GET | `/quizzes` | Danh sách quiz | Authenticated |
| POST | `/files/upload` | Upload file (video/doc/image) | Authenticated |
| GET | `/files/serve/:path` | Serve file (public) | Public |

---

## 🔐 Xác Thực & Phân Quyền

### Vai Trò Người Dùng

| Role | Quyền hạn |
|---|---|
| **ADMIN** | Toàn quyền hệ thống — quản lý user, CRUD tất cả tài nguyên |
| **MANAGER** | Quản lý sự kiện, nhiệm vụ, thông báo |
| **TEACHER** | Tạo khoá học, tạo quiz, duyệt đăng ký |
| **STUDENT** | Đăng ký khoá học, làm quiz, xem nội dung |

### Luồng Xác Thực JWT

```
Client ─── POST /apiv1/auth/login ──────────────────► Auth Backend
                                                            │ validate credentials
                                                            │ generate JWT token
Client ◄── Set-Cookie (httpOnly) + JWT ─────────────────────┘

Client ─── GET /lmsapiv1/courses (Bearer token) ────► LMS Backend
                                                            │ verify JWT (cùng JWT_SECRET)
Client ◄── Course data ─────────────────────────────────────┘
```

> ⚠️ `JWT_SECRET` phải **giống nhau và >= 32 ký tự** giữa Backend và LMS Backend.
> Xem chi tiết tại [TECHNICAL_NOTES.md — Mục 1: JWT](./docs/TECHNICAL_NOTES.md#1-jwt--chia-sẻ-secret-giữa-2-backend).

---

## 🗄️ Database Schema

### Auth Database · PostgreSQL port 5433

Gồm các bảng: `users`, `events`, `tasks`, `announcements`, `password_reset_tokens`

### LMS Database · PostgreSQL port 5434

Gồm các bảng: `users` *(sync từ Auth)*, `courses`, `sections`, `content`, `enrollments`, `quizzes`, `questions`, `quiz_attempts`, `answers`

---

## 📁 File Upload & Storage

| Loại | Định dạng hỗ trợ | Kích thước tối đa |
|---|---|---|
| Video | MP4, AVI, MOV, MKV, WebM, FLV | 100MB |
| Tài liệu | PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, TXT | 100MB |
| Hình ảnh | JPG, JPEG, PNG, GIF, BMP, SVG, WebP | 100MB |

Hệ thống hỗ trợ 2 backend lưu trữ — chọn qua biến `STORAGE_TYPE`:
- **`local`** (mặc định) — Lưu vào filesystem, phù hợp dev
- **`minio`** — Object storage phân tán, khuyến nghị cho production

Xem cấu hình chi tiết tại [TECHNICAL_NOTES.md — Mục 5: Storage](./docs/TECHNICAL_NOTES.md#5-storage--local-vs-minio).

---

## 🔄 Đồng Bộ Người Dùng

Khi tạo user qua Auth Service, hệ thống tự động đồng bộ sang LMS để user có thể đăng ký khoá học ngay lập tức.

```bash
# Sync thủ công khi cần thiết (ví dụ: LMS bị down khi tạo user)
POST /lmsapiv1/sync/user
POST /lmsapiv1/sync/users/bulk
DELETE /lmsapiv1/sync/user/{userId}
Headers: X-Sync-Secret: {LMS_SYNC_SECRET}
```

> ⚠️ `LMS_API_SECRET` (Backend) phải bằng `LMS_SYNC_SECRET` (LMS). Xem [TECHNICAL_NOTES.md — Mục 4](./docs/TECHNICAL_NOTES.md#4-user-sync--đồng-bộ-bất-đồng-bộ-dễ-bị-bỏ-lỡ).

---

## 🐳 Docker Services

| Service | Port | Mô tả |
|---|---|---|
| `frontend` | 3000 | Next.js application |
| `backend` | 8080 | Spring Boot Auth Service |
| `lms-backend` | 8081 | Go LMS Service |
| `postgres` | 5433 | Auth database |
| `postgres-lms` | 5434 | LMS database |
| `redis-lms` | 6379 | Cache (session, queue) |
| `minio` | 9000 / 9001 | Object storage API / Console |

```bash
docker compose up -d              # Khởi chạy tất cả service
docker compose ps                 # Kiểm tra trạng thái
docker compose logs -f            # Xem log realtime
docker compose down               # Dừng (giữ nguyên data)
docker compose down -v            # Dừng + xoá toàn bộ data
docker compose up -d --build backend   # Rebuild riêng 1 service
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

Định hướng phát triển tiếp theo: tích hợp AI để giải quyết 3 khoảng trống học tập được phát hiện qua khảo sát thực tế tại câu lạc bộ.

| Khoảng trống | Mô tả |
|---|---|
| **Navigation Gap** | Sinh viên không biết nên học gì trước, học gì sau |
| **Practice Gap** | LMS chỉ lưu tài liệu tĩnh, thiếu công cụ luyện tập và phản hồi tức thì |
| **Trust Gap** | Thiếu cơ chế kiểm chứng nội dung do AI tạo ra |

### Phase 1 — AI Error Diagnosis & Deep Linking
Biến mỗi lỗi sai thành cơ hội học sâu — không chỉ hiển thị "Sai rồi, thử lại".

- [ ] **Error Pattern Analysis** — Phân tích nguyên nhân sai: nhầm khái niệm, thiếu kiến thức nền, hay đọc sai đề
- [ ] **Deep Link to Source** — Nút "Xem lại" dẫn thẳng đến trang PDF hoặc timestamp chính xác trong video
- [ ] **Weakness Heatmap** — Bản đồ nhiệt hiển thị Knowledge Node hay sai nhất của cả lớp
- [ ] **Class Analytics Report** — Báo cáo tự động sau mỗi quiz: tỷ lệ đúng/sai, phân phối điểm

### Phase 2 — AI Smart Quiz & Active Recall
Tự động hóa tạo bài kiểm tra chất lượng cao, giảm tải giảng viên.

- [ ] **Auto Quiz Generator** — Tạo câu hỏi theo Bloom's Taxonomy (6 cấp độ) từ slide và video
- [ ] **Source-cited Answers** — Mỗi câu hỏi đi kèm giải thích và trích dẫn nguồn rõ ràng
- [ ] **Spaced Repetition Engine** — Nhắc ôn tập đúng thời điểm theo thuật toán SM-2
- [ ] **Instructor Quiz Review** — Giảng viên xét duyệt quiz AI tạo trước khi phát hành

### Phase 3 — AI Micro-Video Creator
Giải quyết bài toán slide 50–100 trang và video ghi hình dài 1–2 tiếng.

- [ ] **Auto Summarizer** — Tóm tắt từ slide PDF và video transcript
- [ ] **Script Generator** — Kịch bản micro-video 60–90 giây phong cách TikTok/Reels
- [ ] **AI Voice + Slide Video** — Tạo video tự động từ kịch bản + giọng đọc AI
- [ ] **Video Chaptering** — Chia video dài thành chương có timestamp tự động

### Phase 4 — AI Atomic Roadmap *(GPS Học Tập Cá Nhân)*
Biến mỗi khoá học thành lộ trình học cá nhân hóa.

- [ ] **Knowledge Graph Engine** — Tự động chia nội dung thành các Knowledge Node nhỏ
- [ ] **Adaptive Sequencing** — AI sắp xếp thứ tự học dựa trên đánh giá đầu vào
- [ ] **Progress-based Rerouting** — Tự động điều chỉnh lộ trình khi phát hiện lỗ hổng kiến thức
- [ ] **Personal Dashboard** — Tiến độ theo Knowledge Node, điểm mạnh/yếu cá nhân

### Phase 5 — Tích Hợp & Hạ Tầng Mở Rộng

- [ ] WebSocket Notifications — Thông báo realtime
- [ ] Mobile App (React Native) — Học offline + push notification
- [ ] LMS Integration — Kết nối Moodle, Canvas qua LTI standard
- [ ] Certificate Generation — Chứng chỉ hoàn thành có chữ ký số
- [ ] Multi-language Support — Giao diện Việt/Anh
- [ ] Advanced Search — Tìm kiếm toàn văn trong video transcript và tài liệu

---

## 🤝 Đóng Góp

Xem hướng dẫn đầy đủ về quy trình đóng góp, convention commit message và coding standards tại **[DEVELOPER_GUIDE.md — Mục 9](./docs/DEVELOPER_GUIDE.md#9-hướng-dẫn-đóng-góp-code)**.

```bash
git checkout -b feature/ten-tinh-nang
# ... viết code ...
git commit -m "feat(lms): mô tả ngắn gọn"
git push origin feature/ten-tinh-nang
# → Tạo Pull Request lên branch develop
```

---

## 👥 Team & Hỗ Trợ

**BDC Development Team** — Big Data Club, HCMUT

| Kênh | Địa chỉ |
|---|---|
| 🐛 Báo lỗi | [GitHub Issues](https://github.com/Big-Data-Club/CoreApplication/issues) — dùng template `bug_report.md` |
| ✨ Đề xuất tính năng | [GitHub Issues](https://github.com/Big-Data-Club/CoreApplication/issues) — dùng template `feature_request.md` |
| 📧 Email | bdc@hcmut.edu.vn |
| 🌐 Production | https://bdc.hpcc.vn |

---

## 📝 License

Dự án được cấp phép theo [MIT License](./LICENSE).

---

## 📚 Tài Liệu Tham Khảo

- [Next.js Documentation](https://nextjs.org/docs)
- [Spring Boot Documentation](https://spring.io/projects/spring-boot)
- [Gin Framework Documentation](https://gin-gonic.com/docs/)
- [Docker Documentation](https://docs.docker.com/)
- [MinIO Documentation](https://min.io/docs/)

---

<div align="center">

**Built with ❤️ by BDC Team**

[🛠️ Developer Guide](./docs/DEVELOPER_GUIDE.md) · [⚠️ Technical Notes](./docs/TECHNICAL_NOTES.md) · [🇬🇧 English Version](./README.en.md) · [🌐 Production](https://bdc.hpcc.vn)

</div>