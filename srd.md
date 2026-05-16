Dưới đây là phiên bản SRD (Software Requirements Document) hoàn chỉnh và tổng nhất, kết hợp cả Backend và Frontend. Tài liệu này được tối ưu hóa cấu trúc để phục vụ trực tiếp cho quá trình vibe code cùng các AI Agents, cung cấp bối cảnh rõ ràng, nguyên tắc thiết kế và luồng thực thi từng bước.

---

# 📄 SRD Toàn Tập: Dynamic Permission Management cho LMS

## 1. Tổng quan (Overview)

* **Ngữ cảnh hiện tại:** Hệ thống LMS đang hỗ trợ Role động (bảng `role_definitions`) và đã ánh xạ role từ Auth Service. Tuy nhiên, logic kiểm tra quyền (Authorization) vẫn đang bị hardcode theo tên Role (VD: `if role == "ADMIN"`).
* **Mục tiêu:** Xây dựng module "Policy Management" hoàn chỉnh từ Backend đến Frontend. Cho phép cấp quyền linh hoạt (granular permissions) cho từng Role thông qua giao diện Settings, và kiểm soát truy cập API tự động bằng Middleware dựa trên dữ liệu động.
* **Nguyên tắc cốt lõi:** Cấu trúc mã nguồn cần tuân thủ nghiêm ngặt các nguyên tắc clean code và SOLID trong Golang. Về mặt UI/UX, áp dụng triết lý thiết kế **"Basic is the best"** — giao diện trang trọng, tối giản và tập trung hoàn toàn vào công năng cốt lõi.

---

## 2. Thiết kế Database (Backend)

Tạo file migration mới (VD: `lms-service/migrations/V004__dynamic_permissions.sql`):

* **Bảng `permissions`:** (Master data các quyền khả dụng trong hệ thống)
* `id` (UUID, PK)
* `code` (VARCHAR, Unique, Not Null) - Định dạng: `[MODULE]_[ACTION]`. VD: `COURSE_CREATE`, `QUIZ_DELETE`, `ROLE_MANAGE`.
* `description` (VARCHAR)
* `created_at`, `updated_at` (TIMESTAMP)


* **Bảng `role_permissions`:** (Bảng trung gian N-N)
* `role_id` (UUID, FK tham chiếu `role_definitions(id)`, Cascade Delete)
* `permission_id` (UUID, FK tham chiếu `permissions(id)`, Cascade Delete)
* `assigned_at` (TIMESTAMP)
* **PK:** `(role_id, permission_id)`



*(Yêu cầu Agent seed sẵn một số permission cơ bản như `COURSE_VIEW`, `COURSE_EDIT`, `ROLE_MANAGE` trong file migration).*

---

## 3. Kiến trúc Backend (Golang)

### 3.1. Models & DTOs

* **`internal/models/permission.go`**: Struct `Permission` và `RolePermission`.
* **`internal/dto/permission_dto.go`**: `PermissionResponse` và `AssignPermissionsRequest` (chứa `role_id` và mảng `permission_ids`).

### 3.2. Repository (`internal/repository/permission_repo.go`)

* `FindAll()`: Lấy toàn bộ permissions.
* `FindByRoleId(roleID string)`: Lấy các quyền hiện có của một role.
* `AssignToRole(roleID string, permissionIDs []string)`: Xóa các quyền cũ và insert quyền mới trong cùng một **DB Transaction**.
* `HasPermission(roleName string, permissionCode string)`: Kiểm tra quyền trực tiếp từ DB.

### 3.3. Service & Caching (`internal/service/permission_service.go`)

* Chứa logic gọi Repository.
* **Tích hợp Caching (Bắt buộc):** Sử dụng `pkg/cache/redis.go`.
* Hàm `CheckRoleHasPermission`: Ưu tiên đọc từ Redis (Key: `role_permissions:{role_name}`). Nếu Miss Cache -> truy vấn DB -> Set lại Cache với TTL.
* Khi gọi `AssignToRole` thành công, Service phải thực hiện lệnh **xóa/invalidate cache** của role tương ứng.



### 3.4. API Handlers (`internal/handler/permission_handler.go`)

* `GET /api/v1/admin/permissions`: Danh sách tất cả quyền (dành cho UI).
* `GET /api/v1/admin/roles/:id/permissions`: Lấy quyền của 1 role.
* `PUT /api/v1/admin/roles/:id/permissions`: Cập nhật danh sách quyền cho 1 role.

### 3.5. Middleware (`internal/middleware/permission.go`)

* Khởi tạo `RequirePermission(requiredPermission string)` trả về Gin handler.
* **Luồng xử lý:** 1. Trích xuất Role của user từ Context.
2. Pass tự động nếu là `SUPER_ADMIN`.
3. Gọi `PermissionService.CheckRoleHasPermission(role, requiredPermission)`.
4. Pass (`c.Next()`) nếu true, block (HTTP 403) nếu false.

---

## 4. Thiết kế Frontend (React/Settings UI)

### 4.1. Điều hướng & Phân quyền

* **Route:** Bổ sung path `/settings/permissions` (hoặc một Tab mới trong trang Settings hiện tại).
* **Truy cập:** Chỉ render menu này khi user hiện tại có quyền `ROLE_MANAGE` (hoặc role ADMIN).

### 4.2. Giao diện người dùng (UI Components)

Tuân thủ phong cách tối giản, sử dụng bảng trắng, text đen, border mảnh, độ tương phản rõ ràng:

1. **Role Listing Panel (Bên trái/Phía trên):**
* Danh sách đơn giản hoặc dạng bảng hiển thị các Role hiện có (Tên, Mã Role).
* Khi click vào một Role, sẽ mở ra vùng cấu hình chi tiết bên cạnh/bên dưới.


2. **Permission Matrix Editor (Vùng cấu hình chi tiết):**
* Hiển thị tiêu đề trang trọng: *"Cấu hình quyền hạn cho vai trò: [Tên Role]"*.
* Danh sách các Checkbox hoặc Toggle Switches, được nhóm theo từng module (Ví dụ: Nhóm *Quản lý Khóa học* chứa View/Create/Edit/Delete).
* Phản ánh đúng trạng thái hiện tại (checked/unchecked) lấy từ API fetch permission của role đó.


3. **Thao tác & Trạng thái:**
* Nút "Lưu thay đổi" (Save Changes) rõ ràng.
* Tích hợp Loading Spinner khi fetch dữ liệu/lưu dữ liệu.
* Hiển thị Toast Notification nhẹ nhàng khi cập nhật thành công hoặc có lỗi.



### 4.3. Luồng kết nối (Data Flow)

* `Mount`: Fetch `GET /roles` và `GET /permissions` (Master list).
* `Select Role`: Fetch `GET /roles/{id}/permissions` -> Cập nhật state của các toggle.
* `Submit`: Gom các ID quyền đang bật -> Gọi `PUT /roles/{id}/permissions`.

---

## 5. Action Plan cho Agent (Trình tự Prompt)

Khi bắt đầu code, hãy nạp tài liệu này và yêu cầu Agent thực hiện tuần tự:

1. **Phase 1 (Database & DTO):** "Tạo file migration V004 định nghĩa bảng `permissions`, `role_permissions` và seed data cơ bản. Sau đó tạo Go struct Models và DTOs tương ứng."
2. **Phase 2 (Data Access):** "Implement `PermissionRepository` sử dụng DB transaction để gán quyền. Viết `PermissionService` tích hợp Redis cache để tối ưu read-heavy."
3. **Phase 3 (API & Auth):** "Viết `PermissionHandler`, khai báo route và tạo `PermissionMiddleware` (`RequirePermission`)."
4. **Phase 4 (Refactor):** "Rà soát các handler hiện tại (Course, Quiz...), xóa logic hardcode `if role == 'ADMIN'` và thay bằng việc bọc `middleware.RequirePermission(...)` ở file router."
5. **Phase 5 (Frontend UI):** "Tạo trang `/settings/permissions` với phong cách UI tối giản. Triển khai danh sách Role và nhóm Checkbox phân quyền, đấu nối 3 APIs vừa tạo."

---

## 6. Tiêu chí nghiệm thu (Acceptance Criteria)

1. Cơ sở dữ liệu và Cache Redis đồng bộ chuẩn xác khi cấu hình quyền bị thay đổi.
2. Admin có thể thay đổi quyền trực quan trên giao diện Settings mà không gặp lỗi giật lag (Handle loading states tốt).
3. Middleware chặn/cho phép request tức thời (< 5ms) dựa trên quyền động, không truy vấn trực tiếp vào DB trên mỗi request.
4. Mọi logic hardcode tên Role trong backend cũ đã được loại bỏ hoàn toàn.