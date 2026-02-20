# ⚠️ Technical Notes — What Developers Must Know Before Building

> This document dives deep into the **critical technical issues** within the codebase — things that aren't obvious at first glance but will cause the application to **fail to run**, **fail silently**, or **introduce serious security vulnerabilities** if overlooked. Read carefully before your first build.

---

> 🌐 **Choose language / Chọn ngôn ngữ:**
> &nbsp;&nbsp;[🇻🇳 Tiếng Việt](./TECHNICAL_NOTES.md) &nbsp;|&nbsp; [🇬🇧 English](./TECHNICAL_NOTES.en.md)

> 📚 **Related documents:**
> [📖 README — Project overview](../README.en.md) · [🛠️ DEVELOPER_GUIDE — Setup guide](./DEVELOPER_GUIDE.en.md)

---

## 📋 Table of Contents

1. [JWT — Sharing the Secret Between Two Backends](#1-jwt--sharing-the-secret-between-two-backends)
2. [Email — Gmail SMTP Configuration](#2-email--gmail-smtp-configuration)
3. [CORS — Configured in Three Places](#3-cors--configured-in-three-places)
4. [User Sync — Asynchronous Sync, Easy to Miss](#4-user-sync--asynchronous-sync-easy-to-miss)
5. [Storage — Local vs MinIO](#5-storage--local-vs-minio)
6. [DataInitializer — Default Admin Account](#6-datainitializer--default-admin-account)
7. [Password Reset — Token and Scheduler](#7-password-reset--token-and-scheduler)
8. [Security Issues to Fix Before Production](#8-security-issues-to-fix-before-production)

---

## 1. JWT — Sharing the Secret Between Two Backends

### The Problem

JWT tokens are **created by Spring Boot** (Auth Service) but **verified by both Spring Boot and Go** (LMS Service). Both services use the same secret to sign and verify tokens. If the secrets differ, every request from the frontend to the LMS will be rejected with `401 Unauthorized` — and this error is extremely hard to diagnose if you don't know to look for it.

### How It Works in Code

**Spring Boot** (`JwtService.java`) — signs the token on login:

```java
@Value("${jwt.secret}")
private String jwtSecret;

// Token contains: email (subject), user_id, role
public String generateToken(Long userId, String email, String role) {
    return Jwts.builder()
        .subject(email)
        .claim("user_id", userId)
        .claim("role", role)
        .signWith(secretKey)  // ← signed with JWT_SECRET
        .compact();
}
```

**Go** (`config.go`) — reads the same secret to verify:

```go
JWT: JWTConfig{
    Secret: getEnv("JWT_SECRET", "very_secret_key_change_me_please"),
},
```

Go also **validates** the secret length at startup:

```go
if len(c.JWT.Secret) < 32 {
    return fmt.Errorf("JWT secret must be at least 32 characters")
}
```

If `JWT_SECRET` is shorter than 32 characters → **the LMS service will fail to start**.

### Correct `.env` Configuration

```env
# Must be IDENTICAL and >= 32 characters in both services
JWT_SECRET=this-is-a-secret-string-at-least-32-chars-long

# Spring Boot uses milliseconds
JWT_EXPIRATION_MS=3600000       # 1 hour

# Go uses hours (a completely separate variable)
# JWT_EXPIRATION_HOURS=1        # defaults to 1, usually no need to set
```

> ⚠️ **Important note on expiration:** Spring Boot uses `JWT_EXPIRATION_MS` (in ms), Go uses `JWT_EXPIRATION_HOURS` (in hours). These are **completely independent variables**. Since tokens are created by Spring Boot, the actual expiry time is determined by `JWT_EXPIRATION_MS`.

### Quick Verification

```bash
# Step 1: Get a token from the Auth service
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'

# Step 2: Use that token to call the LMS service
curl http://localhost:8081/api/v1/courses \
  -H "Authorization: Bearer <TOKEN_FROM_STEP_1>"

# If you get 401 → JWT_SECRET doesn't match between services
```

---

## 2. Email — Gmail SMTP Configuration

### The Problem

Email is used for two key features: **sending temporary passwords** when creating users in bulk (`bulkRegister`) and **sending confirmation links** when resetting passwords (`PasswordResetService`). The dangerous part: if email is misconfigured, `bulkRegister` **still returns HTTP 200 success** but users never receive their password — they can't log in and have no way to recover access.

### Getting a Google App Password — Required

Gmail **blocks logins** from third-party apps using your regular Gmail password. You **must** use an App Password:

1. Visit https://myaccount.google.com/security
2. Enable **2-Step Verification** if not already done
3. Find **"App passwords"** → Create new
4. Select: App = "Mail", Device = "Other" → Name it "BDC Server"
5. Google generates a password like `xxxx xxxx xxxx xxxx` — **remove the spaces when using it** (16 characters total)

```env
EMAIL=your-account@gmail.com
EMAIL_PASSWORD=xxxxxxxxxxxxxxxx    # 16-char App Password, no spaces
APP_PUBLIC_URL=http://localhost:3000
```

### Verifying Email Works

```bash
# Create a test user to see if an email is sent
curl -X POST http://localhost:8080/api/auth/register/bulk \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"users":[{"name":"Test User","email":"your-test@gmail.com","role":"ROLE_USER"}]}'
```

Check the logs:

```bash
docker compose logs backend | grep -i email
# Success: INFO  AuthService - Welcome email sent to: your-test@gmail.com
# Failure: ERROR AuthService - Failed to send email to: your-test@gmail.com
```

### Running Locally Without Sending Real Emails

Use [Mailpit](https://github.com/axllent/mailpit) — a lightweight local email catcher that intercepts all outgoing mail:

```bash
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit
```

View mail at: http://localhost:8025 (clean web interface, zero extra configuration needed).

> When using Mailpit, override SMTP config via environment variables: `SPRING_MAIL_HOST=localhost`, `SPRING_MAIL_PORT=1025`.

---

## 3. CORS — Configured in Three Places

### The Problem

This is the most common gotcha. CORS is **hardcoded in two Java files** and controlled by **one environment variable in Go**. When you add a new domain, change a port, or develop on a different URL, you must update **all three places** — miss any one of them and the frontend will be blocked by CORS errors.

### The Three Places to Update

**Place 1** — `CorsConfig.java` (Spring Boot):

```java
registry.addMapping("/**")
    .allowedOrigins(
        "http://localhost:3000",
        "http://localhost:8080",
        "https://bdc.hpcc.vn",
        "http://frontend:3000"   // ← Docker internal hostname
    )
```

**Place 2** — `SecurityConfig.java` (Spring Boot):

```java
config.setAllowedOrigins(List.of(
    "http://localhost:3000",
    "http://localhost:8080",
    "https://bdc.hpcc.vn",
    "http://frontend:3000"   // ← Must match CorsConfig
));
```

> `SecurityConfig.corsConfigurationSource()` takes priority as it's registered directly in the Spring Security filter chain. Both files should have identical lists to avoid confusion.

**Place 3** — `config.go` (Go LMS), read from environment variable:

```go
AllowedOrigins: getEnvAsSlice("CORS_ALLOWED_ORIGINS", []string{
    "http://localhost:3000",
    "http://frontend:3000",
    "https://bdc.hpcc.vn",
})
```

```env
# Comma-separated, NO spaces
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://frontend:3000,https://bdc.hpcc.vn
```

### When to Update All Three Places

- Adding a new production domain
- Running the frontend on a different port (e.g., 3001)
- Adding a mobile app or new client
- Developing on a staging environment

### Symptoms of Incorrect CORS

The browser console will show:

```
Access to fetch at 'http://localhost:8080/api/...' from origin 'http://localhost:3000'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header
```

→ Check whether your origin is in the allowedOrigins list in all three places.

> 💡 **Long-term improvement:** Both Java files should read `allowedOrigins` from environment variables (like Go already does) rather than hardcoding. See [Section 8.3](#❌-83--cors-production-domain-hardcoded-in-java).

---

## 4. User Sync — Asynchronous Sync, Easy to Miss

### The Problem

When a user is created via `bulkRegister`, Spring Boot calls `userSyncService.syncUsersToLms()` to sync the user to Go LMS. This function runs **asynchronously (`@Async`)** — which means:

1. `bulkRegister` returns HTTP 200 success **immediately**
2. Sync runs in the background; if it fails, it only **logs the error — no exception is thrown**
3. The user exists in Auth DB but **does not exist in LMS DB**
4. Consequence: the user cannot enroll in any course because the LMS doesn't know they exist

### Authentication via Header

Sync requests are protected by the `X-Sync-Secret` header:

```java
// UserSyncService.java — Spring Boot sends
headers.set("X-Sync-Secret", lmsApiSecret);   // variable: LMS_API_SECRET
```

```go
// main.go — Go LMS receives and validates
syncSecret := os.Getenv("LMS_SYNC_SECRET")
sync.Use(syncHandler.SyncSecret())  // middleware checks the header
```

**`LMS_API_SECRET` (Spring Boot) must equal `LMS_SYNC_SECRET` (Go).** If they differ → every sync is rejected with `403 Forbidden`, but since the error is caught and only logged → it's extremely hard to notice.

### Correct Configuration

```env
# Values MUST be equal
LMS_API_SECRET=your-sync-secret-string
LMS_SYNC_SECRET=your-sync-secret-string
```

### Checking Whether Sync Works

```bash
# Check lms-backend logs after creating users
docker compose logs lms-backend | grep -iE "sync"

# Success:
# INFO: Successfully synced user user@example.com to LMS

# Failure (sync rejected):
# ERROR: Failed to sync user user@example.com to LMS: 403 Forbidden
```

### Manual Sync When Needed

If the LMS was down when users were created in bulk, they won't be synced. Trigger a manual sync:

```bash
# Sync a specific user
curl -X POST http://localhost:8081/api/v1/sync/user \
  -H "X-Sync-Secret: <LMS_SYNC_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":123,"email":"user@example.com","full_name":"Nguyen Van A","roles":["TEACHER","STUDENT"]}'

# Sync all users
curl -X POST http://localhost:8081/api/v1/sync/users/bulk \
  -H "X-Sync-Secret: <LMS_SYNC_SECRET>"
```

### Role Mapping During Sync

Special logic in `UserSyncService.java` — important to understand:

```java
private List<String> determineRoles(UserRole userRole) {
    List<String> roles = new ArrayList<>();
    roles.add("TEACHER");   // All users get TEACHER in LMS
    roles.add("STUDENT");   // All users get STUDENT in LMS
    if (userRole == UserRole.ROLE_ADMIN) {
        roles.add("ADMIN"); // Only ADMINs get this extra role
    }
    return roles;
}
```

This is intentional design: every club member can both teach and learn.

---

## 5. Storage — Local vs MinIO

### The Problem

The LMS Service supports two file storage backends: **local filesystem** and **MinIO**. The default is local. If you don't configure things correctly when switching to MinIO — or if you forget to mount a volume when using local — uploads will be lost or files won't be served.

### Choosing a Storage Backend

```env
# Local (default) — suitable for development
STORAGE_TYPE=local
STORAGE_LOCAL_PATH=./uploads

# MinIO — recommended for production
STORAGE_TYPE=minio
MINIO_ENDPOINT=minio:9000          # Container name in Docker network
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=lms-files
MINIO_USE_SSL=false
```

### Local Storage — Important Note

Files are saved **inside the container** at `/app/uploads`. If the container is deleted or recreated, **files are also lost**. The `docker-compose.yml` already configures a persistent volume:

```yaml
volumes:
  - lms_upload_data:/app/uploads   # Persistent Docker volume
```

When running Go directly on your machine (outside Docker), `STORAGE_LOCAL_PATH` defaults to `./uploads` in the `LMS/` directory.

### MinIO — Important Note

MinIO must be **healthy** before LMS starts. However, in the current `docker-compose.yml`, `lms-backend` does **not** have MinIO in its `depends_on`. If using MinIO, add:

```yaml
# docker-compose.yml
lms-backend:
  depends_on:
    minio:
      condition: service_healthy   # ← Add this
```

### Accessing MinIO Console

```
URL:      http://localhost:9001
Username: value of MINIO_ROOT_USER in .env
Password: value of MINIO_ROOT_PASSWORD in .env
```

MinIO automatically creates the bucket on LMS startup if it doesn't already exist.

---

## 6. DataInitializer — Default Admin Account

### The Problem

`DataInitializer.java` creates a default admin account when the database is **empty on first run**:

```java
if (userRepository.count() == 0) {
    User admin = User.builder()
        .email("phucnhan289@gmail.com")          // ← Hardcoded email
        .password(passwordEncoder.encode("hehehe"))  // ← Weak hardcoded password
        .role(UserRole.ROLE_ADMIN)
        .build();
    userRepository.save(admin);
}
```

### Workflow for New Developers

1. First run → empty database → DataInitializer creates the admin
2. Log in: `phucnhan289@gmail.com` / `hehehe`
3. **Change the email and password immediately** via the API or directly in the DB

```bash
# Connect to DB to update admin credentials
docker compose exec postgres psql -U postgres -d club_db

-- View current admin
SELECT id, email, role FROM users;

-- Update email
UPDATE users SET email = 'your-admin@example.com' WHERE role = 'ROLE_ADMIN';
```

### Workflow for Production

Before the first production deploy, update `DataInitializer.java` to read credentials from environment variables instead of hardcoding:

```java
.email(System.getenv("ADMIN_EMAIL"))
.password(passwordEncoder.encode(System.getenv("ADMIN_PASSWORD")))
```

After deploying, log in and change the password through the UI immediately. DataInitializer won't trigger again because `count() != 0`.

---

## 7. Password Reset — Token and Scheduler

### How It Works

```
User requests a password change
          │
          ▼
PasswordResetService.createToken(user)
  → Delete old tokens for this user (prevent parallel tokens)
  → Create a new UUID token
  → Token expires in 15 minutes
          │
          ▼
EmailService.sendPasswordChangeConfirmation(email, token)
  → Send link: {APP_PUBLIC_URL}/confirm-password-change?token=...
          │
          ▼
User clicks the link → confirm endpoint
  → validateAndGetToken(): check unused + not expired
  → markTokenAsUsed(): mark as used
  → Change password → Send success confirmation email
```

### Scheduled Cleanup Job

```java
@Scheduled(cron = "0 0 2 * * *")  // Runs at 2:00 AM every day
public void cleanupExpiredTokens() {
    tokenRepository.deleteByExpiryDateBefore(LocalDateTime.now());
}
```

`@EnableScheduling` must be present in your Spring Boot configuration for this job to run. Check `RestTemplateConfig.java` for this annotation if cleanup isn't working.

### Note on `APP_PUBLIC_URL`

The password reset link uses `APP_PUBLIC_URL`:

```java
String confirmUrl = appUrl + "/confirm-password-change?token=" + token;
```

If `APP_PUBLIC_URL=http://localhost:3000` → the link in the email is `http://localhost:3000/confirm-password-change?token=...`. When developing in a team environment, the email recipient must be able to reach that URL from their machine. Use your machine's IP or hostname instead of `localhost` in that scenario.

---

## 8. Security Issues to Fix Before Production

The following issues **currently exist in the code** and must be addressed before going to production.

### ❌ 8.1 — Debug logging in JwtAuthFilter

```java
// JwtAuthFilter.java — CURRENTLY IN CODE, needs to be removed
System.out.println("📥 Incoming Request: " + request.getMethod() + " " + request.getRequestURI());
System.out.println("📤 Response Status: " + response.getStatus());
```

This logs every request to stdout → excessive log noise, potentially exposing sensitive URL patterns. Remove it or replace with:

```java
log.debug("Incoming: {} {} → {}", request.getMethod(), request.getRequestURI(), response.getStatus());
```

### ❌ 8.2 — Stack trace exposed to client

```java
// GlobalExceptionHandler.java
return ResponseEntity.status(500)
    .body(Map.of(
        "error", ex.getMessage(),
        "type", ex.getClass().getName(),
        "trace", ex.getStackTrace()[0].toString()  // ← Exposes code structure!
    ));
```

Fix: hide error details in production, keep them only in development:

```java
if (isProduction) {
    return ResponseEntity.status(500).body(Map.of("error", "Internal server error"));
} else {
    // Keep full details for development
}
```

### ❌ 8.3 — CORS production domain hardcoded in Java

```java
// CorsConfig.java and SecurityConfig.java
.allowedOrigins("https://bdc.hpcc.vn", ...)  // ← Production domain hardcoded
```

Read from environment variables instead (like Go already does):

```java
@Value("${cors.allowed-origins}")
private List<String> allowedOrigins;
```

### ❌ 8.4 — `ex.printStackTrace()` in GlobalExceptionHandler

```java
ex.printStackTrace();  // ← Dumps full stack trace to logs
```

Replace with:

```java
log.error("Unhandled exception: {}", ex.getMessage(), ex);
```

### ⚠️ 8.5 — MinIO missing from `depends_on` in lms-backend

If using `STORAGE_TYPE=minio`, LMS may start before MinIO is ready and fail to initialize. Add:

```yaml
# docker-compose.yml
lms-backend:
  depends_on:
    minio:
      condition: service_healthy
```

---

## ✅ Security Checklist Before Go-Live

Run through this list before every production deployment:

- [ ] All secrets and passwords changed from defaults in `.env`
- [ ] `JWT_SECRET` is >= 32 characters and identical in both backends
- [ ] `LMS_API_SECRET` equals `LMS_SYNC_SECRET`
- [ ] Default admin account email and password have been changed
- [ ] `System.out.println` removed from `JwtAuthFilter`
- [ ] Stack trace hidden in `GlobalExceptionHandler` for production
- [ ] `MINIO_ROOT_PASSWORD` is >= 8 characters (MinIO requirement)
- [ ] `JPA_DDL_AUTO=validate` or `none` in production (never use `update`)
- [ ] `JPA_SHOW_SQL=false`
- [ ] `LOG_LEVEL=WARN` or `ERROR` in production to reduce log noise

---

## 📋 Summary — Most Often Forgotten Variables

| Variable | Service | Key Note |
|---|---|---|
| `JWT_SECRET` | Backend + LMS | **Must be identical**, >= 32 characters |
| `LMS_API_SECRET` | Backend (sends) | **Must equal** `LMS_SYNC_SECRET` |
| `LMS_SYNC_SECRET` | LMS (receives) | **Must equal** `LMS_API_SECRET` |
| `EMAIL_PASSWORD` | Backend | Gmail App Password, 16 chars — not your regular Gmail password |
| `APP_PUBLIC_URL` | Backend | Link in password reset emails — must be reachable by the user's browser |
| `CORS_ALLOWED_ORIGINS` | LMS (`config.go`) | Also update both Java files when adding new domains |
| `STORAGE_TYPE` | LMS | `local` or `minio` — defaults to `local` |
| `NEXTAUTH_URL` | Frontend | Must match actual domain — affects OAuth callbacks |

---

<div align="center">

[📖 README](../README.en.md) · [🛠️ Developer Guide](./DEVELOPER_GUIDE.en.md) · [🇻🇳 Vietnamese Version](./TECHNICAL_NOTES.md)

</div>