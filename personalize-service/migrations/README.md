# SQL catalogue: personalize-service

Xem [schema đã gộp](../schema/current.sql) để đọc bảng, index và view DuckDB hiện tại.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [V20261105__notebook_annotations.sql](releases/2026-11/V20261105__notebook_annotations.sql) | Hồ sơ học tập và ghi chú |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).
