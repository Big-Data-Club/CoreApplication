package com.example.demo.service.farm;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.HexFormat;
import java.util.UUID;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

@JsonIgnoreProperties(ignoreUnknown = true)
public record FarmRewardEvent(
        int version,
        @JsonProperty("event_id") String eventId,
        @JsonProperty("harvest_id") String harvestId,
        @JsonProperty("user_id") long userId,
        int delta,
        @JsonProperty("occurred_at") String occurredAt,
        String signature) {

    public void validate(String secret, String key) {
        if (version != 1 || userId <= 0 || delta != 5 || !Long.toString(userId).equals(key)) {
            throw new IllegalArgumentException("Invalid farm reward contract");
        }
        UUID.fromString(eventId);
        UUID.fromString(harvestId);
        if (!eventId.equals(harvestId)) throw new IllegalArgumentException("Invalid harvest identity");
        Instant.parse(occurredAt);
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            String input = String.join("|", eventId, Long.toString(userId), harvestId,
                    Integer.toString(delta), occurredAt, "1");
            byte[] expected = mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
            if (signature == null || !MessageDigest.isEqual(expected, HexFormat.of().parseHex(signature))) {
                throw new IllegalArgumentException("Invalid farm reward signature");
            }
        } catch (java.security.GeneralSecurityException ex) {
            throw new IllegalStateException("Cannot verify farm reward", ex);
        }
    }
}
