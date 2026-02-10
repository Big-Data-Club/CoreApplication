# 📚 BDC Application

A comprehensive, microservices-based Learning Management System built with modern technologies including Next.js, Spring Boot, and Go. This platform provides a complete solution for course management, student enrollment, assessments, and administrative functions.

## 🌟 Overview

BDC LMS is a full-stack learning management platform designed for educational institutions and training organizations. The system features a modern, responsive frontend, robust authentication, and separate backend services for general administration and LMS-specific functionality.

### Key Features

- 🎓 **Course Management** - Create, edit, and organize courses with multimedia content
- 👥 **Student Enrollment** - Flexible enrollment system with approval workflows
- 📝 **Quiz & Assessment** - Comprehensive quiz system with multiple question types
- 👤 **User Management** - Role-based access control (Admin, Manager, Teacher, Student)
- 📢 **Announcements** - System-wide and course-specific announcements
- 📅 **Event Management** - Track events, tasks, and deadlines
- 📁 **File Management** - Upload and serve various file types (videos, documents, images)
- 🔐 **Secure Authentication** - JWT-based authentication with cookie support
- 🔄 **User Synchronization** - Automatic sync between auth and LMS services

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                    │
│                  Port 3000 - User Interface                  │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
             ▼                                ▼
┌────────────────────────┐    ┌─────────────────────────────┐
│  Backend (Spring Boot) │    │   LMS Backend (Go)          │
│  Port 8080             │    │   Port 8081                 │
│  - Authentication      │◄───┤   - Courses                 │
│  - User Management     │    │   - Quizzes                 │
│  - Events & Tasks      │    │   - Enrollments             │
│  - Announcements       │    │   - File Storage            │
└──────────┬─────────────┘    └──────────┬──────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────┐    ┌───────────────────────────────┐
│ PostgreSQL (Auth DB) │    │ PostgreSQL (LMS DB) + Redis   │
│ Port 5433            │    │ Ports 5434, 6379              │
└──────────────────────┘    └───────────────────────────────┘
```

### Technology Stack

**Frontend:**
- Next.js 14+ (React Framework)
- TypeScript
- Tailwind CSS
- Radix UI Components
- NextAuth.js for authentication

**Backend Services:**
- **Auth Service:** Spring Boot 3.x (Java)
  - Spring Security with JWT
  - PostgreSQL database
  - REST API
  
- **LMS Service:** Go 1.21+ with Gin framework
  - PostgreSQL for data persistence
  - Redis for caching
  - Swagger/OpenAPI documentation

**Infrastructure:**
- Docker & Docker Compose
- PostgreSQL 15
- Redis 7
- MinIO for object storage (optional)

## 🚀 Getting Started

### Prerequisites

- Docker 24.0+
- Docker Compose 2.0+
- Node.js 18+ (for local development)
- Java 17+ (for local development)
- Go 1.21+ (for local development)

### Quick Start with Docker

1. **Clone the repository:**
```bash
git clone https://github.com/Big-Data-Club/CoreApplication.git
cd CoreApplication
```

2. **Create environment file:**
```bash
cp .env.example .env
```

4. **Start all services:**
```bash
docker-compose up -d
```

5. **Access the application:**
- Frontend: http://localhost:3000
- Auth API: http://localhost:8080 || http://localhost:3000/apiv1
- LMS API: http://localhost:8081  || http://localhost:3000/lmsapiv1
- MinIO Console: http://localhost:9001

### Local Development Setup

#### Frontend Development
```bash
cd frontend
npm install
npm run dev
```

#### Backend (Auth Service) Development
```bash
cd Backend
./mvnw spring-boot:run
```

#### LMS Service Development
```bash
cd LMS
go mod download
go run cmd/server/main.go
```

## 📖 API Documentation

### Auth Service API (Spring Boot)
- Base URL: `http://localhost:8080/api`
- Swagger UI: `http://localhost:8080/swagger-ui.html`

**Main Endpoints:**
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `POST /api/auth/register/bulk` - Bulk user registration (Admin only)
- `GET /api/users` - Get all users
- `GET /api/events` - Get all events
- `GET /api/tasks` - Get all tasks
- `GET /api/announcements` - Get all announcements

### LMS Service API (Go)
- Base URL: `http://localhost:8081/api/v1`
- Swagger UI: `http://localhost:8081/swagger/index.html`

**Main Endpoints:**
- `GET /api/v1/courses` - Get all courses
- `POST /api/v1/courses` - Create course (Teacher/Admin)
- `POST /api/v1/enrollments` - Enroll in course
- `GET /api/v1/quizzes` - Get quizzes
- `POST /api/v1/files/upload` - Upload file
- `GET /api/v1/files/serve/{filepath}` - Serve file

## 🔐 Authentication & Authorization

### User Roles

| Role | Permissions |
|------|-------------|
| **ADMIN** | Full system access, user management, all CRUD operations |
| **MANAGER** | Event & task management, announcements, reports |
| **TEACHER** | Course creation, quiz management, student enrollment approval |
| **STUDENT** | Course enrollment, quiz taking, view content |

### Authentication Flow

1. User logs in via `/api/auth/login`
2. Backend validates credentials and generates JWT token
3. Token is set as HTTP-only cookie and returned in response
4. Frontend includes token in subsequent requests
5. Both backend services validate JWT for protected routes

## 🗄️ Database Schema

### Auth Database (PostgreSQL)
- **users** - User accounts and profiles
- **events** - System events
- **tasks** - User tasks
- **announcements** - System announcements

### LMS Database (PostgreSQL)
- **users** - Synchronized user data
- **courses** - Course information
- **lessons** - Lesson content
- **enrollments** - Student course enrollments
- **quizzes** - Quiz definitions
- **questions** - Quiz questions
- **quiz_attempts** - Student quiz attempts
- **answers** - Student quiz answers

## 📁 File Upload & Storage

### Supported File Types

**Videos:**
- Formats: MP4, AVI, MOV, MKV, WebM, FLV, WMV, M4V
- Max size: 100MB

**Documents:**
- Formats: PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, TXT, CSV
- Max size: 100MB

**Images:**
- Formats: JPG, JPEG, PNG, GIF, BMP, SVG, WebP
- Max size: 100MB

### File Endpoints
```bash
# Upload file
POST /lmsapiv1/files/upload
Content-Type: multipart/form-data
Body: file, type (video|document|image)

# Serve file (public)
GET /files/{filepath}

# Download file (authenticated)
GET /lmsapiv1/files/download/{filepath}

# Delete file (admin/teacher)
DELETE /lmsapiv1/files/delete/{filepath}
```

## 🔄 User Synchronization

The system maintains user data synchronization between Auth and LMS services:

### Sync Endpoints
```bash
# Sync single user
POST /lmsapiv1/sync/user
Headers: X-Sync-Secret: {secret}
Body: {user_id, email, name, role}

# Bulk sync users
POST /lmsapiv1/sync/users/bulk
Headers: X-Sync-Secret: {secret}

# Delete user from LMS
DELETE /lmsapiv1/sync/user/{userId}
Headers: X-Sync-Secret: {secret}
```

## 🐳 Docker Services

### Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | Next.js application |
| Backend | 8080 | Spring Boot auth service |
| LMS Backend | 8081 | Go LMS service |
| PostgreSQL (Auth) | 5433 | Auth database |
| PostgreSQL (LMS) | 5434 | LMS database |
| Redis | 6379 | Cache service |
| MinIO | 9000 | Object storage API |
| MinIO Console | 9001 | MinIO web interface |

### Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f [service-name]

# Stop all services
docker-compose down

# Rebuild services
docker-compose up -d --build

# Reset everything (including volumes)
docker-compose down -v
```

## 🛠️ Configuration

### Frontend Configuration (next.config.ts)

The frontend uses Next.js rewrites to proxy API requests:
- `/apiv1/*` → Auth Backend (8080)
- `/lmsapiv1/*` → LMS Backend (8081)
- `/files/*` → LMS file serving
- `/uploads/*` → Auth file serving

### Backend Configuration

**Spring Boot (application.yml):**
- Database connection settings
- JWT configuration
- CORS allowed origins
- Email configuration
- Hikari connection pool

**Go Service (environment variables):**
- Database and Redis settings
- File upload configuration
- JWT secret (shared with auth service)
- CORS settings

## 🚀 Deployment

### Production Checklist

- [ ] Change all default passwords and secrets
- [ ] Set `NODE_ENV=production`
- [ ] Enable HTTPS/SSL certificates
- [ ] Configure proper CORS origins
- [ ] Set up database backups
- [ ] Configure Redis persistence
- [ ] Set up monitoring and logging
- [ ] Configure rate limiting
- [ ] Review security headers
- [ ] Set up CDN for static assets

### Environment-specific Builds

```bash
# Build for production
docker-compose build --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') --build-arg VERSION=1.0.0

# Push to registry
docker-compose push
```

## 🧪 Testing

### Frontend Tests
```bash
cd frontend
npm run test
npm run test:e2e
```

### Backend Tests
```bash
cd Backend
./mvnw test
```

### LMS Service Tests
```bash
cd LMS
go test ./...
```

## 📊 Monitoring & Health Checks

### Health Check Endpoints

- Frontend: `GET /api/health`
- Backend: `GET /actuator/health`
- LMS: `GET /health`

### Metrics & Monitoring

- Spring Boot Actuator: `http://localhost:8080/actuator`
- Prometheus metrics available at `/actuator/prometheus`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Coding Standards

- **Frontend:** Follow Next.js and React best practices
- **Backend (Java):** Follow Spring Boot conventions
- **Backend (Go):** Follow effective Go guidelines
- Use meaningful commit messages
- Write tests for new features
- Update documentation

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Team & Support

**Project Maintainers:**
- Development Team: BDC Development Team

**Support:**
- Documentation: [Project Wiki]
- Issues: [GitHub Issues]
- Email: support@example.com

## 🗺️ Roadmap

### Upcoming Features

- [ ] Real-time notifications with WebSocket
- [ ] Advanced analytics dashboard
- [ ] Mobile application (React Native)
- [ ] Video streaming optimization
- [ ] AI-powered content recommendations
- [ ] Integration with external LMS (Moodle, Canvas)
- [ ] Multi-language support
- [ ] Certificate generation
- [ ] Payment gateway integration

## 📚 Additional Resources

- [Next.js Documentation](https://nextjs.org/docs)
- [Spring Boot Documentation](https://spring.io/projects/spring-boot)
- [Gin Framework Documentation](https://gin-gonic.com/docs/)
- [Docker Documentation](https://docs.docker.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

**Built with ❤️ by BDC Team**

For questions or feedback, please open an issue or contact the development team.