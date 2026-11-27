# SQL catalogue: lms-service

Xem [schema đã gộp](../schema/current.sql) để đọc định nghĩa hiện tại của bảng và index trong một file.
Các file bên dưới chỉ là lịch sử migration cần giữ cho DB đã triển khai.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [V001__core_schema.sql](releases/2026-11/V001__core_schema.sql) | Schema nền tảng |
| [V002__performance_indexes.sql](releases/2026-11/V002__performance_indexes.sql) | Hiệu năng và an toàn |
| [V003__dynamic_roles.sql](releases/2026-11/V003__dynamic_roles.sql) | Tổ chức, phân quyền và tenant |
| [V003__micro_quizzes.sql](releases/2026-11/V003__micro_quizzes.sql) | Ôn tập và đánh giá |
| [V004__dynamic_permissions.sql](releases/2026-11/V004__dynamic_permissions.sql) | Tổ chức, phân quyền và tenant |
| [V005__organizations.sql](releases/2026-11/V005__organizations.sql) | Tổ chức, phân quyền và tenant |
| [V006__organization_indexes.sql](releases/2026-11/V006__organization_indexes.sql) | Hiệu năng và an toàn |
| [V007__add_organization_to_users.sql](releases/2026-11/V007__add_organization_to_users.sql) | Tổ chức, phân quyền và tenant |
| [V008__section_overview.sql](releases/2026-11/V008__section_overview.sql) | Schema nền tảng |
| [V009__section_overview_logs.sql](releases/2026-11/V009__section_overview_logs.sql) | Schema nền tảng |
| [V010__course_co_teachers.sql](releases/2026-11/V010__course_co_teachers.sql) | Schema nền tảng |
| [V011__teacher_dashboard_indexes.sql](releases/2026-11/V011__teacher_dashboard_indexes.sql) | Hiệu năng và an toàn |
| [V012__course_listing_indexes.sql](releases/2026-11/V012__course_listing_indexes.sql) | Hiệu năng và an toàn |
| [V013__user_profile_picture.sql](releases/2026-11/V013__user_profile_picture.sql) | Schema nền tảng |
| [V014__course_archive_restore_status.sql](releases/2026-11/V014__course_archive_restore_status.sql) | Schema nền tảng |
| [V015__personalized_learning_schema.sql](releases/2026-11/V015__personalized_learning_schema.sql) | Hồ sơ học tập và ghi chú |
| [V016__competency_framework_model.sql](releases/2026-11/V016__competency_framework_model.sql) | Schema nền tảng |
| [V017__question_bank.sql](releases/2026-11/V017__question_bank.sql) | Quiz và ngân hàng câu hỏi |
| [V018__question_bank_backfill.sql](releases/2026-11/V018__question_bank_backfill.sql) | Quiz và ngân hàng câu hỏi |
| [V019__farm_learning_attempts.sql](releases/2026-11/V019__farm_learning_attempts.sql) | Farm và hoạt động học |
| [V020__quiz_focus_summary.sql](releases/2026-11/V020__quiz_focus_summary.sql) | Quiz và ngân hàng câu hỏi |
| [V021__learning_notifications.sql](releases/2026-11/V021__learning_notifications.sql) | Thông báo và xuất bản |
| [V022__lms_request_safety.sql](releases/2026-11/V022__lms_request_safety.sql) | Hiệu năng và an toàn |
| [V023__always_publish_learning_resources.sql](releases/2026-11/V023__always_publish_learning_resources.sql) | Thông báo và xuất bản |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).

New additive release: [V024__quiz_assessment_snapshot.sql](releases/2026-11-27/V024__quiz_assessment_snapshot.sql), quiz indexing / historical assessment attribution.
