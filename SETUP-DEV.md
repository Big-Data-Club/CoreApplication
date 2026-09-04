# Chạy hệ thống trên máy phát triển

Tài liệu này chỉ nói về `docker-compose.dev.yml`. Compose gốc
(`docker-compose.yml`) khai báo khoảng 17.8 GB mem limit trên ~20 container nên
không chạy được trên máy phát triển thông thường.

## Bố cục thư mục

Repo frontend nằm **ngoài** repo này, ngang hàng với nó:

```
tn/
├── backend/    repo này (datn-hk252/CoreApplication)
└── frontend/   datn-hk252/frontend
```

Compose build frontend từ `../frontend`. Thư mục `backend/frontend/` rỗng là
bình thường: nó là vỏ submodule còn sót của repo gốc, đã bị `deinit`, không dùng.

## Khởi động

```bash
cp .env.dev.example .env.dev   # nếu chưa có; .env.dev không đưa vào git
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d
```

Lần đầu build cả Java, Go lẫn Next.js nên khá lâu. Muốn tách làm hai bước cho nhẹ
thì dựng backend trước, đợi xanh rồi mới dựng frontend:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d backend lms-backend
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d frontend
```

## Cổng

| Địa chỉ | |
|---|---|
| http://localhost:3000 | Ứng dụng, đi qua Traefik |
| http://localhost:8080 | auth-service, gọi trực tiếp để thử API |
| http://localhost:8081 | lms-service, gọi trực tiếp để thử API |
| http://localhost:9001 | MinIO console |
| localhost:5433 / 5434 | PostgreSQL của auth / lms |

## Quyền LMS của tài khoản

Hai service dùng hai cơ sở dữ liệu riêng. Muốn vào được `/lms`, tài khoản phải
có dòng trong `lms_db.user_roles`, do auth-service đẩy sang.

Việc này **tự động**. Auth-service đồng bộ toàn bộ tài khoản sang LMS lúc khởi
động, và đồng bộ từng tài khoản mỗi khi tạo, duyệt, đổi vai trò hay bật lại.
Log của `dev-auth-service` sẽ có dòng:

```
Startup LMS sync completed for 1/1 users
```

Nếu dòng đó báo `did not become ready` thì lms-service chưa lên kịp trong hai
phút. Khởi động lại auth-service là nó thử lại:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev restart backend
```

Kiểm tra kết quả:

```bash
docker exec dev-postgres-lms psql -U lms_user -d lms_db -c "SELECT u.email, r.role FROM users u JOIN user_roles r ON r.user_id = u.id;"
```

Vai trò hợp lệ: `ADMIN`, `TEACHER`, `STUDENT`. Nếu vừa đổi vai trò của một
tài khoản đang đăng nhập thì phải **đăng xuất rồi đăng nhập lại**, vì phiên
NextAuth giữ vai trò từ lúc đăng nhập.

> Trước đây phải gọi tay `POST /api/v1/sync/user`. Đó là lỗi có sẵn trong repo
> gốc, đã sửa ở nhánh `fix/lms-role-sync`.

## Những gì đã lược bỏ và hệ quả

Không chạy: Kafka, Neo4j, Qdrant, ai-service, lab-service, chat-service,
personalize-service, recommender-service.

- **Kafka**: bỏ được an toàn. `kafka.InitProducer()` của lms-service chỉ dựng
  struct chứ không mở kết nối, các consumer chạy trong goroutine riêng; phía
  Spring dùng `@KafkaListener` nên tự thử lại nền. Hai service khởi động bình
  thường, chỉ ghi cảnh báo trong log.
- **ai-service**: vẫn phải khai `AI_SERVICE_URL` và `AI_SERVICE_SECRET` vì
  `application.yaml` của auth-service tham chiếu chúng không kèm giá trị mặc
  định, thiếu là Spring sập lúc tạo bean `AdminLlmService`. Mọi chức năng quản
  trị LLM sẽ lỗi khi gọi.
- **Traefik thì không bỏ được.** Frontend gọi API bằng đường dẫn tương đối
  (`/apiv1`, `/lmsapiv1`, `/files`, `/uploads`); Traefik là thứ viết lại và
  chuyển tiếp. Thiếu nó thì mọi lời gọi rơi vào Next.js và trả 404.

## Migration của lms_db

lms-service không tự chạy migration, và Dockerfile của nó cũng không copy thư mục
`migrations`. Container `lms-migrate` áp các file `V0xx__*.sql` theo thứ tự rồi
ghi tên file vào bảng `schema_migrations` để lần sau bỏ qua.

Cần bảng ghi này vì các migration **không** idempotent hoàn toàn:
`V009__section_overview_logs.sql` dùng `ALTER TABLE ADD COLUMN` không kèm
`IF NOT EXISTS`, chạy lại là lỗi. Mà `lms-backend` đợi
`service_completed_successfully`, nên lỗi ở đây chặn luôn lms-service.

Thêm migration mới thì chỉ cần bỏ file vào `lms-service/migrations/`, lần `up`
kế tiếp sẽ tự áp.

Schema của auth-service không cần bước này: Hibernate chạy `ddl-auto=update`.

## Chẩn đoán nhanh

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev ps
docker logs dev-auth-service --tail 50
docker logs dev-lms-service --tail 50
docker logs dev-lms-migrate
```

`/actuator/health` của auth-service báo `DOWN` là bình thường khi chưa cấu hình
SMTP: thành phần `mail` down, còn `db` và `liveness` vẫn up. Điền `EMAIL` và
`EMAIL_PASSWORD` trong `.env.dev` khi cần chức năng khôi phục mật khẩu.
