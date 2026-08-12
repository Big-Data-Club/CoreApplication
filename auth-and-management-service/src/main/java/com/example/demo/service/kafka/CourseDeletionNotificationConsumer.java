package com.example.demo.service.kafka;

import com.example.demo.service.email.EmailService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

import java.util.List;

@Service
@RequiredArgsConstructor
@Slf4j
public class CourseDeletionNotificationConsumer {

    private final EmailService emailService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "lms.course.deleted", groupId = "auth-course-deletion-notification-group")
    public void consume(String message) {
        try {
            JsonNode event = objectMapper.readTree(message);
            long courseId = event.path("course_id").asLong();
            String courseTitle = event.path("course_title").asText("Khóa học #" + courseId);
            String reason = event.path("reason").asText("").trim();
            JsonNode instructors = event.path("instructors");

            if (reason.isBlank() || !instructors.isArray()) {
                log.warn("Ignoring invalid course deletion event: {}", message);
                return;
            }

            for (JsonNode instructor : instructors) {
                String email = instructor.path("email").asText("").trim();
                if (email.isBlank()) {
                    continue;
                }
                String name = instructor.path("full_name").asText("Giáo viên");
                sendDeletionEmail(email, name, courseId, courseTitle, reason);
            }
        } catch (Exception exception) {
            // Throwing lets Spring Kafka apply its configured retry/error handling
            // instead of silently acknowledging a notification that was not sent.
            log.error("Failed to process course deletion notification", exception);
            throw new IllegalStateException("Could not process course deletion notification", exception);
        }
    }

    private void sendDeletionEmail(String email, String name, long courseId, String courseTitle, String reason) {
        String safeName = HtmlUtils.htmlEscape(name);
        String safeTitle = HtmlUtils.htmlEscape(courseTitle);
        String safeReason = HtmlUtils.htmlEscape(reason).replace("\n", "<br>");
        String body = """
                <p>Xin chào <strong>%s</strong>,</p>
                <p>Quản trị viên đã xóa khóa học mà bạn tham gia giảng dạy:</p>
                <div style='background:#f8fafc;border-left:4px solid #ef4444;padding:16px;margin:16px 0;border-radius:6px'>
                  <p style='margin:0 0 8px'><strong>Khóa học:</strong> %s (ID: %d)</p>
                  <p style='margin:0'><strong>Lý do:</strong> %s</p>
                </div>
                <p>Nếu cần làm rõ hoặc khôi phục nội dung từ bản sao lưu, vui lòng liên hệ Ban Quản Trị BDC Hub.</p>
                """.formatted(safeName, safeTitle, courseId, safeReason);

        emailService.sendAdminMailAsync(
                email,
                List.of(),
                List.of(),
                "[BDC Hub] Khóa học đã bị quản trị viên xóa: " + courseTitle,
                body,
                "bdc-1",
                "default"
        ).join();
        log.info("Sent course deletion notification for course {} to {}", courseId, email);
    }
}
