# SQL catalogue: workspace-service

Xem [schema đã gộp](../schema/current.sql) để đọc định nghĩa hiện tại của bảng và index trong một file.
Các file bên dưới chỉ là lịch sử migration cần giữ cho DB đã triển khai.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [001_workspace.sql](releases/2026-11/001_workspace.sql) | Workspace và cộng tác |
| [002_ticket_session_expiry.sql](releases/2026-11/002_ticket_session_expiry.sql) | Workspace và cộng tác |
| [003_page_links.sql](releases/2026-11/003_page_links.sql) | Workspace và cộng tác |
| [004_user_fields.sql](releases/2026-11/004_user_fields.sql) | Workspace và cộng tác |
| [005_block_activity.sql](releases/2026-11/005_block_activity.sql) | Workspace và cộng tác |
| [006_page_analytics.sql](releases/2026-11/006_page_analytics.sql) | Workspace và cộng tác |
| [007_page_cover_image.sql](releases/2026-11/007_page_cover_image.sql) | Workspace và cộng tác |
| [008_library.sql](releases/2026-11/008_library.sql) | Workspace và cộng tác |
| [009_bounded_versions.sql](releases/2026-11/009_bounded_versions.sql) | Schema nền tảng |
| [010_notebook_destinations.sql](releases/2026-11/010_notebook_destinations.sql) | Hồ sơ học tập và ghi chú |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).
