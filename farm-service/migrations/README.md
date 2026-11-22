# SQL catalogue: farm-service

Xem [schema đã gộp](../schema/current.sql) để đọc định nghĩa hiện tại của bảng và index trong một file.
Các file bên dưới chỉ là lịch sử migration cần giữ cho DB đã triển khai.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [V001__initial.sql](releases/2026-11/V001__initial.sql) | Schema nền tảng |
| [V002__playable_world.sql](releases/2026-11/V002__playable_world.sql) | Farm và hoạt động học |
| [V003__lms_attempt_outbox.sql](releases/2026-11/V003__lms_attempt_outbox.sql) | Schema nền tảng |
| [V004__relaxed_care_timers.sql](releases/2026-11/V004__relaxed_care_timers.sql) | Farm và hoạt động học |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).
