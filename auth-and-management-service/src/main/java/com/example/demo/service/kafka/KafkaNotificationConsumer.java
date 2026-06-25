package com.example.demo.service.kafka;

import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.email.EmailService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class KafkaNotificationConsumer {

    private final UserRepository userRepository;
    private final EmailService emailService;
    private final ObjectMapper objectMapper;

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
            
            User user = userRepository.findById(userId).orElse(null);
            if (user == null) {
                log.warn("User not found in database for ID: {}", userId);
                return;
            }
            
            String subject = "Cá nhân hóa học tập - ";
            if ("concept_struggle".equalsIgnoreCase(alertType)) {
                subject += "Cảnh báo lỗ hổng kiến thức!";
            } else if ("inactivity".equalsIgnoreCase(alertType)) {
                subject += "Nhắc nhở ôn tập bài học!";
            } else {
                subject += "Thông báo từ hệ thống học tập";
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
                alertMessage,
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
}
