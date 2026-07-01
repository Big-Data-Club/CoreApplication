package com.example.demo.service.kafka;

import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.auth.JwtService;
import com.example.demo.service.email.EmailService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class KafkaNotificationConsumer {

    private final UserRepository userRepository;
    private final EmailService emailService;
    private final ObjectMapper objectMapper;
    private final JwtService jwtService;
    private final RestTemplate restTemplate;

    @Value("${lms.api.url}")
    private String lmsApiUrl;

    @KafkaListener(topics = "personalize.notification.trigger", groupId = "auth-notification-group")
    public void consumeNotificationTrigger(String message) {
        log.info("Received notification trigger message from Kafka: {}", message);
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> event = objectMapper.readValue(message, Map.class);
            
            Number userIdNum = (Number) event.get("user_id");
            if (userIdNum == null) {
                log.warn("Missing user_id in notification trigger event: {}", message);
                return;
            }
            Long userId = userIdNum.longValue();
            String alertType = (String) event.get("alert_type");
            String alertMessage = (String) event.get("alert_message");
            
            Number courseIdNum = (Number) event.get("course_id");
            Long courseId = courseIdNum != null ? courseIdNum.longValue() : null;
            
            User user = userRepository.findById(userId).orElse(null);
            if (user == null) {
                log.warn("User not found in database for ID: {}", userId);
                return;
            }
            
            String courseName = fetchCourseName(courseId);
            String finalMessage = alertMessage;
            if (courseId != null && courseName != null) {
                finalMessage = finalMessage.replace("(Course ID: " + courseId + ")", "\"" + courseName + "\"");
            }
            
            String subject = "Cá nhân hóa học tập - ";
            if ("concept_struggle".equalsIgnoreCase(alertType)) {
                subject += "Cảnh báo lỗ hổng kiến thức!";
            } else if ("inactivity".equalsIgnoreCase(alertType)) {
                subject += "Nhắc nhở ôn tập bài học!";
            } else {
                subject += "Thông báo từ hệ thống học tập";
            }
            
            if (courseName != null && !courseName.startsWith("Khóa học (ID:")) {
                subject += " [" + courseName + "]";
            }
            
            log.info("Sending struggle email notification to student: {} <{}>", user.getName(), user.getEmail());
            
            // Render HTML content using cosmic template
            String emailBody = String.format(
                "<p>Xin chào <strong>%s</strong>,</p>" +
                "<p>Hệ thống hỗ trợ học tập cá nhân hóa BDC Hub nhận thấy:</p>" +
                "<div style='background-color: #1e293b; border-left: 4px solid #3b82f6; padding: 15px; margin: 15px 0; border-radius: 4px; color: #cbd5e1;'>" +
                "  <strong>Chi tiết:</strong> %s" +
                "</div>" +
                "<p>Hãy truy cập ngay vào hệ thống học tập để ôn luyện lại kiến thức và tiếp tục chặng đường học tập của mình nhé!</p>" +
                "<div style='text-align: center; margin-top: 30px;'>" +
                "  <a href='%s' style='background: linear-gradient(90deg, #3b82f6, #8b5cf6); color: white; padding: 12px 24px; text-decoration: none; font-weight: bold; border-radius: 8px; box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3); display: inline-block;'>Quay Lại Học Tập Ngay</a>" +
                "</div>",
                user.getName(),
                finalMessage,
                "https://bdc.hpcc.vn"
            );
            
            emailService.sendAdminMailAsync(
                user.getEmail(),
                List.of(),
                List.of(),
                subject,
                emailBody,
                "bdc-1", // Signature type
                "cosmic" // Template type
            );
            
        } catch (Exception e) {
            log.error("Failed to process notification trigger event message", e);
        }
    }

    private String fetchCourseName(Long courseId) {
        if (courseId == null) {
            return null;
        }
        try {
            String token = jwtService.generateToken(0L, "system@bdc.internal", List.of("ADMIN"));
            HttpHeaders headers = new HttpHeaders();
            headers.setBearerAuth(token);
            headers.setContentType(MediaType.APPLICATION_JSON);
            
            HttpEntity<Void> entity = new HttpEntity<>(headers);
            String url = lmsApiUrl + "/api/v1/courses/" + courseId;
            
            @SuppressWarnings("unchecked")
            ResponseEntity<Map> response = restTemplate.exchange(
                url,
                HttpMethod.GET,
                entity,
                Map.class
            );
            
            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                Map<String, Object> body = response.getBody();
                Map<String, Object> data = (Map<String, Object>) body.get("data");
                if (data != null && data.containsKey("title")) {
                    return (String) data.get("title");
                }
            }
        } catch (Exception e) {
            log.error("Failed to fetch course details for ID: {}", courseId, e);
        }
        return "Khóa học (ID: " + courseId + ")";
    }
}
