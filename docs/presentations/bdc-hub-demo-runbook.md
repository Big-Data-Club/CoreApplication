# BDC Hub — Demo Runbook

## Mục tiêu

Trong 8–10 phút, chứng minh BDC Hub là một LMS hoàn chỉnh có AI được quản trị,
không phải một chatbot gắn vào giao diện.

Giữ xuyên suốt một câu chuyện duy nhất:

- **Admin An** quản trị model và quyền.
- **Giảng viên Lan** dùng `kafka.pdf` để tạo course “Kafka Foundations”.
- **Học viên Minh** học course đó, hỏi AI Mentor và nhận gợi ý cho 20 phút tiếp theo.

Mỗi màn hình chỉ cần trả lời một câu: **người dùng vừa giải quyết được việc gì?**

## Chuẩn bị trước khi trình bày

1. Dùng một course demo đã có tối thiểu một file được index và một quiz.
2. Có sẵn một file ngắn (5–15 trang) để upload, tránh PDF scan nặng.
3. Đăng nhập sẵn ở ba tab/browser profile: Admin, Teacher, Student.
4. Chuẩn bị một course đang học có progress và, nếu có thể, một content mới
   được publish để badge recommendation xuất hiện.
5. Nếu mạng/model chậm, ưu tiên demo course đã index; upload mới chỉ để minh
   hoạ job workflow, không chờ toàn bộ indexing.

## Kịch bản trình diễn

| Thời lượng | Role | Thao tác | Câu nói chính |
|---|---|---|---|
| 0:00–0:40 | — | Mở dashboard/slide 1 | “Ta bắt đầu từ bài toán vận hành việc học, không bắt đầu từ model.” |
| 0:40–1:20 | Admin | Mở LLM Registry | “Model được bind theo task; key, fallback và usage được quản trị tập trung.” |
| 1:20–3:40 | Teacher | Upload file, mở trạng thái index | “Request trả job nhanh; worker xử lý dài ở phía sau.” |
| 3:40–5:20 | Teacher | Tạo course/quiz draft, chỉnh một mục, approve | “AI tạo draft có source; teacher vẫn là người quyết định publish.” |
| 5:20–7:30 | Student | Mở course đã index, hỏi Mentor, làm concept check/flashcard | “Câu trả lời dùng learning context của course, không phải trả lời kiến thức chung.” |
| 7:30–8:40 | Student | Mở Discover và dashboard | “Recommendation có lý do: mục tiêu, level, progress, activity và nội dung mới.” |
| 8:40–10:00 | — | Quay lại slide Closing | “Ba lớp: LMS, AI, Data tạo flywheel cải tiến trải nghiệm học.” |

## Câu chuyển giữa các phần

- **LMS → AI:** “Course đã vận hành được. Bây giờ hãy xem Lan giảm thời gian tạo nội dung như thế nào.”
- **AI → kiến trúc:** “Đây không chỉ là một câu trả lời đẹp. Ta mở bên dưới để xem file, retrieval và worker đã chạy thế nào.”
- **Kiến trúc → scale:** “API trả nhanh vì việc nặng đã tách sang Kafka. Khi tải tăng, ta tăng đúng worker đang nghẽn.”
- **Scale → demo:** “Giờ quay lại đúng câu chuyện của An, Lan và Minh trên hệ thống thật.”

## Prompt nên dùng

### Teacher

> Từ tài liệu này, hãy đề xuất 4 chương cho khóa học Nhập môn Data Engineering, nêu prerequisite của từng chương và giữ lại source tương ứng.

> Tạo 5 câu quiz mức apply về Apache Kafka từ các phần đã index. Cho tôi xem draft trước khi publish.

### Student

> Giải thích sự khác nhau giữa Kafka topic và consumer group bằng ví dụ từ bài giảng này. Sau đó cho tôi một mini challenge 3 phút.

> Tôi chỉ có 20 phút hôm nay. Nên tiếp tục course nào và vì sao? Nếu có bài mới, hãy chỉ rõ.

## Phương án dự phòng

- **Index chậm:** chuyển ngay sang course đã index; giải thích processing là async qua Kafka và status có thể quan sát.
- **LLM response không đẹp:** chỉ ra draft và human approval thay vì cố generate lại nhiều lần.
- **Không có badge bài mới:** demo “Học tiếp” hoặc “Sắp hoàn thành”, sau đó giải thích badge mới chỉ xuất hiện khi LMS có signal source-grounded.
- **Mất mạng:** dùng slide 7, 9, 10, 13 để giải thích pipeline; không cố live call.

## Câu trả lời cho các câu hỏi thường gặp

- **AI có tự publish không?** Không. Workflow tạo draft, teacher review/approve rồi LMS mới materialize/publish.
- **Document lớn có làm treo UI không?** Không. HTTP trả job reference; AI worker xử lý async qua Kafka và client theo dõi status.
- **Dữ liệu của service nào thuộc service đó?** Mỗi service sở hữu state của mình; tích hợp qua authenticated APIs hoặc versioned events, không query DB chéo.
- **Recommendation có phải chỉ sort course phổ biến?** Không. Nó lọc eligibility trước, dùng goal/level/progress/activity/freshness và ghi outcome để đánh giá policy.
