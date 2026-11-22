# SQL catalogue: ai-service

Xem [schema đã gộp](../schema/current.sql) để đọc định nghĩa hiện tại của bảng và index trong một file.
Các file bên dưới chỉ là lịch sử migration cần giữ cho DB đã triển khai.

Các file đã có tới ngày 2026-11-22 được gom vào release [`2026-11`](releases/2026-11/).
Đây là cách tổ chức source; không phải migration mới hoặc script gộp để chạy lại.
Tên file, thứ tự áp dụng và nội dung SQL được giữ nguyên.

| Migration | Nghiệp vụ |
|---|---|
| [004_graphrag_indexes.sql](releases/2026-11/004_graphrag_indexes.sql) | Hiệu năng và an toàn |
| [V001__schema.sql](releases/2026-11/V001__schema.sql) | Schema nền tảng |
| [V002__performance_indexes.sql](releases/2026-11/V002__performance_indexes.sql) | Hiệu năng và an toàn |
| [V003__student_facts.sql](releases/2026-11/V003__student_facts.sql) | Hồ sơ học tập và ghi chú |
| [V004__expand_relation_types.sql](releases/2026-11/V004__expand_relation_types.sql) | Đồ thị và truy xuất tri thức |
| [V005__user_concept_mastery.sql](releases/2026-11/V005__user_concept_mastery.sql) | Hồ sơ học tập và ghi chú |
| [V006__flashcard_dedup.sql](releases/2026-11/V006__flashcard_dedup.sql) | Ôn tập và đánh giá |
| [V007__agent_telemetry.sql](releases/2026-11/V007__agent_telemetry.sql) | Agent, phản hồi và theo dõi |
| [V008__course_blueprints.sql](releases/2026-11/V008__course_blueprints.sql) | Soạn học liệu và worker |
| [V009__course_blueprint_processing.sql](releases/2026-11/V009__course_blueprint_processing.sql) | Soạn học liệu và worker |
| [V010__course_blueprint_worker_leases.sql](releases/2026-11/V010__course_blueprint_worker_leases.sql) | Soạn học liệu và worker |
| [V011__course_material_routing_jobs.sql](releases/2026-11/V011__course_material_routing_jobs.sql) | Soạn học liệu và worker |
| [V012__agent_message_feedback.sql](releases/2026-11/V012__agent_message_feedback.sql) | Agent, phản hồi và theo dõi |
| [V013__studio_projects.sql](releases/2026-11/V013__studio_projects.sql) | Soạn học liệu và worker |
| [V014__mcp_api_keys.sql](releases/2026-11/V014__mcp_api_keys.sql) | Schema nền tảng |
| [V015__document_chunks_search_indexes.sql](releases/2026-11/V015__document_chunks_search_indexes.sql) | Hiệu năng và an toàn |
| [V016__personal_flashcard_library.sql](releases/2026-11/V016__personal_flashcard_library.sql) | Ôn tập và đánh giá |
| [V017__flashcard_library_course_scope.sql](releases/2026-11/V017__flashcard_library_course_scope.sql) | Ôn tập và đánh giá |
| [V018__content_study_jobs.sql](releases/2026-11/V018__content_study_jobs.sql) | Soạn học liệu và worker |
| [V019__lab_authoring_jobs.sql](releases/2026-11/V019__lab_authoring_jobs.sql) | Soạn học liệu và worker |
| [V020__studio_worker_jobs.sql](releases/2026-11/V020__studio_worker_jobs.sql) | Soạn học liệu và worker |
| [V021__speech_jobs.sql](releases/2026-11/V021__speech_jobs.sql) | Soạn học liệu và worker |
| [V022__studio_temporary_media_and_youtube.sql](releases/2026-11/V022__studio_temporary_media_and_youtube.sql) | Soạn học liệu và worker |
| [V023__course_knowledge_map.sql](releases/2026-11/V023__course_knowledge_map.sql) | Đồ thị và truy xuất tri thức |
| [V024__quiz_insight_results.sql](releases/2026-11/V024__quiz_insight_results.sql) | Quiz và ngân hàng câu hỏi |
| [V025__review_delivery_receipts.sql](releases/2026-11/V025__review_delivery_receipts.sql) | Agent, phản hồi và theo dõi |

`manifest.json` lưu SHA-256 của từng file đã đóng release. Kiểm tra bằng
`python3 scripts/check-sql-releases.py` từ root repository.

Thay đổi mới: thêm SQL trong release tiếp theo (ví dụ `releases/2026-12/`),
giữ tên migration duy nhất trong service và thứ tự version hiện có. Không sửa
file đã chạy hoặc chèn SQL của một service vào database của service khác.
Xem [quy ước chung](../../docs/operations/SQL_RELEASES.md).
