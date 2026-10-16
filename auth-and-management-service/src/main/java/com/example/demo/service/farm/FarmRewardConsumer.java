package com.example.demo.service.farm;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.farm.rewards-enabled", havingValue = "true")
public class FarmRewardConsumer {
    private final ObjectMapper mapper;
    private final FarmRewardService service;
    private final String secret;
    public FarmRewardConsumer(ObjectMapper mapper, FarmRewardService service,
            @Value("${app.farm.event-secret:}") String secret) {
        if (secret.getBytes(java.nio.charset.StandardCharsets.UTF_8).length < 32) {
            throw new IllegalStateException("FARM_EVENT_SECRET must contain at least 32 bytes");
        }
        this.mapper = mapper;
        this.service = service;
        this.secret = secret;
    }
    @KafkaListener(topics = "farm.harvest.reward.v1", groupId = "auth-farm-rewards-v1",
            containerFactory = "farmRewardContainerFactory")
    public void consume(ConsumerRecord<String, String> record) throws Exception {
        FarmRewardEvent event = mapper.readValue(record.value(), FarmRewardEvent.class);
        event.validate(secret, record.key());
        service.apply(event);
    }
}
