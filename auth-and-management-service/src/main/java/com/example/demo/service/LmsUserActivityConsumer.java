package com.example.demo.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
@Slf4j
public class LmsUserActivityConsumer {

    private final UserProfileService userProfileService;
    private final ObjectMapper objectMapper;

    @KafkaListener(
            topics = "${app.kafka.topic.lms-user-activity:lms.user.activity}",
            groupId = "${spring.kafka.consumer.group-id:auth-hub-group}",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void consumeUserActivity(String message) {
        log.info("Received LMS user activity event: {}", message);
        try {
            JsonNode root = objectMapper.readTree(message);
            if (root.has("user_id") && root.has("data")) {
                Long userId = root.get("user_id").asLong();
                String statsJson = root.get("data").toString();
                userProfileService.updateUserStatsCache(userId, statsJson);
            }
        } catch (Exception e) {
            log.error("Failed to process LMS user activity event: {}", message, e);
        }
    }
}
