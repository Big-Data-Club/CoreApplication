# ⚠️ Technical Notes — Những Điều Dev Cần Biết Trước Khi Build

> Tài liệu này đi sâu vào các **vấn đề kỹ thuật quan trọng** trong codebase — những thứ không hiện ra ngay từ đầu nhưng nếu bỏ qua sẽ khiến ứng dụng **không chạy được**, **lỗi im lặng**, hoặc **có lỗ hổng bảo mật nghiêm trọng**. Đọc kỹ trước khi build lần đầu.

---

> 🌐 **Chọn ngôn ngữ / Language:**
> &nbsp;&nbsp;[🇻🇳 Tiếng Việt](./TECHNICAL_NOTES.md) &nbsp;|&nbsp; [🇬🇧 English](./TECHNICAL_NOTES.en.md)

> 📚 **Tài liệu liên quan:**
> [📖 README — Tổng quan dự án](../README.md) · [🛠️ DEVELOPER_GUIDE — Hướng dẫn setup](./DEVELOPER_GUIDE.md)

---

## 📋 Mục Lục

1. [JWT — Chia sẻ secret giữa 2 backend](#1-jwt--chia-sẻ-secret-giữa-2-backend)
2. [Email — Cấu hình Gmail SMTP](#2-email--cấu-hình-gmail-smtp)
3. [CORS — Cấu hình ở 3 nơi khác nhau](#3-cors--cấu-hình-ở-3-nơi-khác-nhau)
4. [User Sync — Đồng bộ bất đồng bộ, dễ bị bỏ lỡ](#4-user-sync--đồng-bộ-bất-đồng-bộ-dễ-bị-bỏ-lỡ)
5. [Storage — Local vs MinIO](#5-storage--local-vs-minio)
6. [DataInitializer — Tài khoản Admin mặc định](#6-datainitializer--tài-khoản-admin-mặc-định)
7. [Password Reset — Token và Scheduler](#7-password-reset--token-và-scheduler)
8. [Vấn Đề Bảo Mật Cần Sửa Trước Production](#8-vấn-đề-bảo-mật-cần-sửa-trước-production)

---

## 1. JWT — Chia sẻ secret giữa 2 backend

### Vấn đề

JWT token được **tạo bởi Spring Boot** (Auth Service) nhưng được **xác thực bởi cả Spring Boot lẫn Go** (LMS Service). Hai service dùng cùng một secret để ký và verify token. Nếu secret khác nhau, mọi request từ frontend đến LMS đều bị từ chối với lỗi `401 Unauthorized` — và lỗi này rất khó tìm nguyên nhân nếu không biết trước.

### Cách hoạt động trong code

**Spring Boot** (`JwtService.java`) — ký token khi user đăng nhập:

```java
@Value("${jwt.secret}")
private String jwtSecret;

// Token chứa: email (subject), user_id, role
public String generateToken(Long userId, String email, String role) {
    return Jwts.builder()
        .subject(email)
        .claim("user_id", userId)
        .claim("role", role)
        .signWith(secretKey)  // ← ký bằng JWT_SECRET
        .compact();
}
```

**Go** (`config.go`) — đọc cùng secret để verify:

```go
JWT: JWTConfig{
    Secret: getEnv("JWT_SECRET", "very_secret_key_change_me_please"),
},
```

Go còn **validate** độ dài secret khi khởi động:

```go
if len(c.JWT.Secret) < 32 {
    return fmt.Errorf("JWT secret must be at least 32 characters")
}
```

Nếu `JWT_SECRET` ngắn hơn 32 ký tự → **LMS service không khởi động được**.

### Cấu hình đúng trong `.env`

```env
# Phải GIỐNG NHAU và >= 32 ký tự ở cả 2 service
JWT_SECRET=day-la-mot-chuoi-bi-mat-dai-it-nhat-32-ky-tu

# Spring Boot dùng milliseconds
JWT_EXPIRATION_MS=3600000       # 1 giờ

# Go dùng hours (biến riêng, không liên quan đến trên)
# JWT_EXPIRATION_HOURS=1        # mặc định là 1, thường không cần đặt
```

> ⚠️ **Lưu ý quan trọng về thời gian hết hạn:** Spring Boot dùng `JWT_EXPIRATION_MS` (đơn vị ms), Go dùng `JWT_EXPIRATION_HOURS` (đơn vị giờ). Đây là 2 biến **hoàn toàn độc lập**. Token được tạo bởi Spring Boot, nên thời gian hết hạn thực tế do `JWT_EXPIRATION_MS` quyết định.

### Kiểm tra nhanh

```bash
# Bước 1: Lấy token từ Auth service
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'

# Bước 2: Dùng token đó gọi LMS service
curl http://localhost:8081/api/v1/courses \
  -H "Authorization: Bearer <TOKEN_VỪA_LẤY>"

# Nếu kết quả là 401 → JWT_SECRET không khớp
```

---

## 2. Email — Cấu hình Gmail SMTP

### Vấn đề

Email được dùng cho 2 tính năng chính: **gửi mật khẩu tạm thời** khi tạo user hàng loạt (`bulkRegister`) và **link xác nhận** khi đổi mật khẩu (`PasswordResetService`). Cái nguy hiểm là: nếu cấu hình email sai, `bulkRegister` **vẫn báo thành công** (HTTP 200) nhưng user không nhận được mật khẩu — họ không thể đăng nhập và không có cách nào tự lấy lại mật khẩu.

### Lấy Google App Password — Bắt buộc

Gmail **chặn đăng nhập** từ ứng dụng bên thứ ba bằng mật khẩu Gmail thông thường. Bạn **phải** dùng App Password:

1. Truy cập https://myaccount.google.com/security
2. Bật **2-Step Verification** nếu chưa bật
3. Tìm **"App passwords"** → Tạo mới
4. Chọn: App = "Mail", Device = "Other" → Đặt tên "BDC Server"
5. Google cấp mật khẩu dạng `xxxx xxxx xxxx xxxx` — **bỏ dấu cách khi dùng** (16 ký tự liền)

```env
EMAIL=your-account@gmail.com
EMAIL_PASSWORD=xxxxxxxxxxxxxxxx    # App Password 16 ký tự, không có dấu cách
APP_PUBLIC_URL=http://localhost:3000
```

### Kiểm tra email hoạt động

```bash
# Tạo 1 user test để xem email có được gửi không
curl -X POST http://localhost:8080/api/auth/register/bulk \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"users":[{"name":"Test User","email":"your-test@gmail.com","role":"ROLE_USER"}]}'
```

Kiểm tra log:

```bash
docker compose logs backend | grep -i email
# Thành công: INFO  AuthService - Welcome email sent to: your-test@gmail.com
# Thất bại:   ERROR AuthService - Failed to send email to: your-test@gmail.com
```

### Chạy local không muốn gửi email thật

Dùng [Mailpit](https://github.com/axllent/mailpit) — email catcher nhẹ, chạy local, bắt mọi email thay vì gửi đi:

```bash
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit
```

Xem mail tại: http://localhost:8025 (giao diện web đẹp, không cần cấu hình gì thêm).

> Khi dùng Mailpit, cần override cấu hình SMTP trong `application.yml` hoặc qua biến môi trường: `SPRING_MAIL_HOST=localhost`, `SPRING_MAIL_PORT=1025`.

---

## 3. CORS — Cấu hình ở 3 nơi khác nhau

### Vấn đề

Đây là cái bẫy phổ biến nhất. CORS được cấu hình **hardcode trong 2 file Java** và thêm **1 biến môi trường trong Go**. Khi bạn thêm domain mới, đổi port, hoặc phát triển trên một URL khác, bạn phải nhớ cập nhật **cả 3 chỗ** — bỏ sót bất kỳ chỗ nào là frontend bị chặn với lỗi CORS.

### 3 chỗ cần cập nhật

**Chỗ 1** — `CorsConfig.java` (Spring Boot):

```java
registry.addMapping("/**")
    .allowedOrigins(
        "http://localhost:3000",
        "http://localhost:8080",
        "https://bdc.hpcc.vn",
        "http://frontend:3000"   // ← Docker internal hostname
    )
```

**Chỗ 2** — `SecurityConfig.java` (Spring Boot):

```java
config.setAllowedOrigins(List.of(
    "http://localhost:3000",
    "http://localhost:8080",
    "https://bdc.hpcc.vn",
    "http://frontend:3000"
));
```

> `SecurityConfig.corsConfigurationSource()` được ưu tiên vì nó được đăng ký trực tiếp vào Spring Security filter chain. Cả 2 file nên có danh sách giống nhau để tránh nhầm lẫn.

**Chỗ 3** — `config.go` (Go LMS), đọc từ biến môi trường:

```go
AllowedOrigins: getEnvAsSlice("CORS_ALLOWED_ORIGINS", []string{
    "http://localhost:3000",
    "http://frontend:3000",
    "https://bdc.hpcc.vn",
})
```

```env
# Phân cách bằng dấu phẩy, KHÔNG có dấu cách
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://frontend:3000,https://bdc.hpcc.vn
```

### Khi nào cần cập nhật cả 3 chỗ

- Thêm domain production mới
- Chạy frontend ở port khác (ví dụ 3001)
- Thêm mobile app hoặc client mới
- Phát triển trên staging environment

### Triệu chứng CORS sai

Browser console sẽ hiện:

```
Access to fetch at 'http://localhost:8080/api/...' from origin 'http://localhost:3000'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header
```

→ Kiểm tra origin của bạn có nằm trong danh sách allowedOrigins ở cả 3 nơi không.

> 💡 **Cải thiện dài hạn:** Cả 2 file Java nên đọc allowedOrigins từ biến môi trường (giống Go đang làm) thay vì hardcode. Xem [Mục 8.3](#❌-83--cors-hardcode-domain-production-trong-java).

---

## 4. User Sync — Đồng bộ bất đồng bộ, dễ bị bỏ lỡ

### Vấn đề

Khi tạo user qua `bulkRegister`, Spring Boot gọi `userSyncService.syncUsersToLms()` để đồng bộ sang Go LMS. Hàm này chạy **bất đồng bộ (`@Async`)** — có nghĩa là:

1. `bulkRegister` trả về HTTP 200 thành công **ngay lập tức**
2. Sync chạy nền, nếu lỗi chỉ **log error — không throw exception**
3. User tồn tại trong Auth DB nhưng **không có trong LMS DB**
4. Hậu quả: user không thể đăng ký khoá học vì LMS không biết họ tồn tại

### Xác thực bằng header

Sync request được bảo vệ bằng header `X-Sync-Secret`:

```java
// UserSyncService.java — Spring Boot gửi
headers.set("X-Sync-Secret", lmsApiSecret);   // biến: LMS_API_SECRET
```

```go
// main.go — Go LMS nhận và xác thực
syncSecret := os.Getenv("LMS_SYNC_SECRET")
sync.Use(syncHandler.SyncSecret())  // middleware kiểm tra header
```

**`LMS_API_SECRET` (Spring Boot) phải bằng `LMS_SYNC_SECRET` (Go).** Nếu khác nhau → mọi sync đều bị từ chối với `403 Forbidden`, nhưng vì lỗi bị bắt và chỉ log → cực kỳ khó phát hiện.

### Cấu hình đúng

```env
# Giá trị PHẢI bằng nhau
LMS_API_SECRET=chuoi-bi-mat-de-sync-giua-2-service
LMS_SYNC_SECRET=chuoi-bi-mat-de-sync-giua-2-service
```

### Kiểm tra sync có hoạt động không

```bash
# Xem log của lms-backend sau khi tạo user
docker compose logs lms-backend | grep -iE "sync"

# Thành công:
# INFO: Successfully synced user user@example.com to LMS

# Thất bại (sync bị reject):
# ERROR: Failed to sync user user@example.com to LMS: 403 Forbidden
```

### Sync thủ công khi cần

Nếu LMS bị down khi tạo user hàng loạt, user sẽ không được sync. Cần sync lại thủ công:

```bash
# Sync lại một user cụ thể
curl -X POST http://localhost:8081/api/v1/sync/user \
  -H "X-Sync-Secret: <LMS_SYNC_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":123,"email":"user@example.com","full_name":"Nguyen Van A","roles":["TEACHER","STUDENT"]}'

# Sync lại toàn bộ user
curl -X POST http://localhost:8081/api/v1/sync/users/bulk \
  -H "X-Sync-Secret: <LMS_SYNC_SECRET>"
```

### Mapping Role khi sync

Logic đặc biệt trong `UserSyncService.java` — cần hiểu rõ:

```java
private List<String> determineRoles(UserRole userRole) {
    List<String> roles = new ArrayList<>();
    roles.add("TEACHER");   // Mọi user đều có TEACHER trong LMS
    roles.add("STUDENT");   // Mọi user đều có STUDENT trong LMS
    if (userRole == UserRole.ROLE_ADMIN) {
        roles.add("ADMIN"); // Chỉ ADMIN mới có thêm role này
    }
    return roles;
}
```

Thiết kế có chủ ý: mọi thành viên club đều có thể vừa dạy vừa học.

---

## 5. Storage — Local vs MinIO

### Vấn đề

LMS Service hỗ trợ 2 backend lưu file: **local filesystem** và **MinIO**. Mặc định là local. Nếu không cấu hình đúng khi chuyển sang MinIO — hoặc không mount volume khi dùng local — file upload sẽ mất hoặc không serve được.

### Chọn storage backend

```env
# Local (mặc định) — phù hợp dev
STORAGE_TYPE=local
STORAGE_LOCAL_PATH=./uploads

# MinIO — khuyến nghị cho production
STORAGE_TYPE=minio
MINIO_ENDPOINT=minio:9000          # Tên container trong Docker network
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=lms-files
MINIO_USE_SSL=false
```

### Lưu ý khi dùng Local Storage

File được lưu **trong container** vào `/app/uploads`. Nếu container bị xoá hoặc recreate, **file cũng mất**. `docker-compose.yml` đã cấu hình volume:

```yaml
volumes:
  - lms_upload_data:/app/uploads   # Volume Docker persistent
```

Khi dev local chạy Go trực tiếp (không qua Docker), `STORAGE_LOCAL_PATH` mặc định là `./uploads` trong thư mục `LMS/`.

### Lưu ý khi dùng MinIO

MinIO phải **healthy** trước khi LMS khởi động. Tuy nhiên, trong `docker-compose.yml` hiện tại, `lms-backend` **không** có `depends_on` MinIO. Nếu dùng MinIO, cần thêm:

```yaml
# docker-compose.yml
lms-backend:
  depends_on:
    minio:
      condition: service_healthy   # ← Thêm dòng này
```

### Truy cập MinIO Console

```
URL:      http://localhost:9001
Username: giá trị MINIO_ROOT_USER trong .env
Password: giá trị MINIO_ROOT_PASSWORD trong .env
```

MinIO tự động tạo bucket khi LMS khởi động nếu bucket chưa tồn tại.

---

## 6. DataInitializer — Tài khoản Admin mặc định

### Vấn đề

`DataInitializer.java` tạo tài khoản admin mặc định khi database **trống lần đầu chạy**:

```java
if (userRepository.count() == 0) {
    User admin = User.builder()
        .email("phucnhan289@gmail.com")          // ← Email hardcode
        .password(passwordEncoder.encode("hehehe"))  // ← Mật khẩu yếu hardcode
        .role(UserRole.ROLE_ADMIN)
        .build();
    userRepository.save(admin);
}
```

### Quy trình cho dev mới

1. Lần đầu chạy → database trống → DataInitializer tạo admin
2. Đăng nhập: `phucnhan289@gmail.com` / `hehehe`
3. **Đổi email và mật khẩu ngay** qua API hoặc trực tiếp trong DB

```bash
# Kết nối DB để đổi thông tin admin
docker compose exec postgres psql -U postgres -d club_db

-- Xem admin hiện tại
SELECT id, email, role FROM users;

-- Đổi email
UPDATE users SET email = 'your-admin@example.com' WHERE role = 'ROLE_ADMIN';
```

### Quy trình cho production

Trước khi deploy lần đầu, sửa `DataInitializer.java` để đọc từ biến môi trường thay vì hardcode:

```java
.email(System.getenv("ADMIN_EMAIL"))
.password(passwordEncoder.encode(System.getenv("ADMIN_PASSWORD")))
```

Sau khi deploy, đăng nhập và đổi mật khẩu ngay qua UI. DataInitializer sẽ không trigger lại vì `count() != 0`.

---

## 7. Password Reset — Token và Scheduler

### Luồng hoạt động

```
User yêu cầu đổi mật khẩu
         │
         ▼
PasswordResetService.createToken(user)
  → Xoá token cũ của user (tránh nhiều token song song)
  → Tạo UUID token mới
  → Token hết hạn sau 15 phút
         │
         ▼
EmailService.sendPasswordChangeConfirmation(email, token)
  → Gửi link: {APP_PUBLIC_URL}/confirm-password-change?token=...
         │
         ▼
User click link → confirm endpoint
  → validateAndGetToken(): kiểm tra chưa dùng + chưa hết hạn
  → markTokenAsUsed(): đánh dấu đã dùng
  → Đổi mật khẩu → Gửi email thông báo thành công
```

### Scheduled Job dọn dẹp token hết hạn

```java
@Scheduled(cron = "0 0 2 * * *")  // Chạy lúc 2:00 AM mỗi ngày
public void cleanupExpiredTokens() {
    tokenRepository.deleteByExpiryDateBefore(LocalDateTime.now());
}
```

Cần `@EnableScheduling` trong Spring Boot config để job này hoạt động. Kiểm tra `RestTemplateConfig.java` có annotation này không nếu cleanup không chạy.

### Lưu ý về `APP_PUBLIC_URL`

Link reset password dùng `APP_PUBLIC_URL`:

```java
String confirmUrl = appUrl + "/confirm-password-change?token=" + token;
```

Nếu `APP_PUBLIC_URL=http://localhost:3000` → link gửi là `http://localhost:3000/confirm-password-change?token=...`. Khi dev trong môi trường nhóm, user nhận email phải có thể truy cập URL đó từ máy của họ. Hãy dùng IP hoặc hostname thay vì `localhost` trong trường hợp này.

---

## 8. Vấn Đề Bảo Mật Cần Sửa Trước Production

Các vấn đề dưới đây **đang tồn tại trong code** và cần được xử lý trước khi đưa lên production.

### ❌ 8.1 — Debug log trong JwtAuthFilter

```java
// JwtAuthFilter.java — ĐANG CÓ trong code, cần xoá
System.out.println("📥 Incoming Request: " + request.getMethod() + " " + request.getRequestURI());
System.out.println("📤 Response Status: " + response.getStatus());
```

In thông tin mọi request vào stdout → log quá nhiều noise, có thể lộ URL nhạy cảm. Xoá đi hoặc thay bằng:

```java
log.debug("Incoming: {} {} → {}", request.getMethod(), request.getRequestURI(), response.getStatus());
```

### ❌ 8.2 — Stack trace lộ ra client

```java
// GlobalExceptionHandler.java
return ResponseEntity.status(500)
    .body(Map.of(
        "error", ex.getMessage(),
        "type", ex.getClass().getName(),
        "trace", ex.getStackTrace()[0].toString()  // ← LỘ cấu trúc code!
    ));
```

Sửa thành: ẩn chi tiết lỗi ở production, chỉ giữ khi dev:

```java
if (isProduction) {
    return ResponseEntity.status(500).body(Map.of("error", "Internal server error"));
} else {
    // Giữ chi tiết cho môi trường dev
}
```

### ❌ 8.3 — CORS hardcode domain production trong Java

```java
// CorsConfig.java và SecurityConfig.java
.allowedOrigins("https://bdc.hpcc.vn", ...)  // ← Domain production hardcode
```

Nên đọc từ biến môi trường (giống cách Go đang làm):

```java
@Value("${cors.allowed-origins}")
private List<String> allowedOrigins;
```

### ❌ 8.4 — `ex.printStackTrace()` trong GlobalExceptionHandler

```java
ex.printStackTrace();  // ← In full stack trace vào log
```

Thay bằng:

```java
log.error("Unhandled exception: {}", ex.getMessage(), ex);
```

### ⚠️ 8.5 — MinIO không có trong `depends_on` của lms-backend

Nếu dùng `STORAGE_TYPE=minio`, LMS có thể khởi động trước MinIO và fail khi kết nối. Thêm:

```yaml
# docker-compose.yml
lms-backend:
  depends_on:
    minio:
      condition: service_healthy
```

---

## ✅ Checklist Bảo Mật Trước Khi Go Live

Chạy qua danh sách này trước mỗi lần deploy production:

- [ ] Tất cả secret/password đã được đổi khỏi giá trị mặc định trong `.env`
- [ ] `JWT_SECRET` >= 32 ký tự và giống nhau ở cả 2 backend
- [ ] `LMS_API_SECRET` bằng `LMS_SYNC_SECRET`
- [ ] Tài khoản admin mặc định đã được đổi email và mật khẩu
- [ ] Xoá `System.out.println` trong `JwtAuthFilter`
- [ ] Ẩn stack trace trong `GlobalExceptionHandler` ở production
- [ ] `MINIO_ROOT_PASSWORD` >= 8 ký tự (yêu cầu của MinIO)
- [ ] `JPA_DDL_AUTO=validate` hoặc `none` ở production (không dùng `update`)
- [ ] `JPA_SHOW_SQL=false`
- [ ] `LOG_LEVEL=WARN` hoặc `ERROR` ở production

---

## 📋 Tóm Tắt — Biến Môi Trường Hay Quên Nhất

| Biến | Service | Lưu ý quan trọng |
|---|---|---|
| `JWT_SECRET` | Backend + LMS | **Phải giống nhau**, >= 32 ký tự |
| `LMS_API_SECRET` | Backend (gửi) | **Phải bằng** `LMS_SYNC_SECRET` |
| `LMS_SYNC_SECRET` | LMS (nhận) | **Phải bằng** `LMS_API_SECRET` |
| `EMAIL_PASSWORD` | Backend | App Password Gmail 16 ký tự, không phải mật khẩu thông thường |
| `APP_PUBLIC_URL` | Backend | Link trong email reset password — phải truy cập được từ máy user |
| `CORS_ALLOWED_ORIGINS` | LMS (`config.go`) | Cũng phải cập nhật 2 file Java nếu thêm domain |
| `STORAGE_TYPE` | LMS | `local` hoặc `minio` — mặc định `local` |
| `NEXTAUTH_URL` | Frontend | Phải khớp với domain thực tế, ảnh hưởng đến OAuth callback |

---

<div align="center">

[📖 README](../README.md) · [🛠️ Developer Guide](./DEVELOPER_GUIDE.md) · [🇬🇧 English Version](./TECHNICAL_NOTES.en.md)

</div>