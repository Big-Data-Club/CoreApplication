# SQL catalogue: lab-service

Xem [schema đã gộp](../schema/current.sql) để đọc định nghĩa hiện tại của bảng và index trong một file.
Các file bên dưới chỉ là lịch sử migration cần giữ cho DB đã triển khai.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [V001__lab_core.sql](releases/2026-11/V001__lab_core.sql) | Lab và thực thi |
| [V002__submissions.sql](releases/2026-11/V002__submissions.sql) | Lab và thực thi |
| [V003__virtual_stem_foundation.sql](releases/2026-11/V003__virtual_stem_foundation.sql) | Schema nền tảng |
| [V004__chemistry_lab_support.sql](releases/2026-11/V004__chemistry_lab_support.sql) | Lab và thực thi |
| [V005__runtime_tasks.sql](releases/2026-11/V005__runtime_tasks.sql) | Lab và thực thi |
| [V006__grading_compile_status.sql](releases/2026-11/V006__grading_compile_status.sql) | Lab và thực thi |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).
