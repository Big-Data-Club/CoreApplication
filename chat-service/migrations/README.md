# SQL catalogue: chat-service

Xem [schema đã gộp](../schema/current.sql) để đọc định nghĩa hiện tại của bảng và index trong một file.
Các file bên dưới chỉ là lịch sử migration cần giữ cho DB đã triển khai.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [V001__chat_schema.sql](releases/2026-11/V001__chat_schema.sql) | Nhắn tin và hội thoại |
| [V002__dm_support.sql](releases/2026-11/V002__dm_support.sql) | Nhắn tin và hội thoại |
| [V003__seed_existing_channels.sql](releases/2026-11/V003__seed_existing_channels.sql) | Nhắn tin và hội thoại |
| [V004__message_replies_and_edits.sql](releases/2026-11/V004__message_replies_and_edits.sql) | Nhắn tin và hội thoại |
| [V005__chat_attachments.sql](releases/2026-11/V005__chat_attachments.sql) | Nhắn tin và hội thoại |
| [V006__chat_history_and_membership_indexes.sql](releases/2026-11/V006__chat_history_and_membership_indexes.sql) | Hiệu năng và an toàn |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).
