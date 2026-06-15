package com.example.demo.service.user;

import com.example.demo.model.User;
import com.example.demo.strategy.RoleResolutionStrategy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.*;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserSyncService {

    private final RestTemplate restTemplate;
    private final RoleResolutionStrategy roleStrategy;

    // ── LMS service ───────────────────────────────────────────────────────────
    @Value("${lms.api.url}")
    private String lmsApiUrl;

    @Value("${lms.api.secret}")
    private String lmsApiSecret;

    // ── Chat service ──────────────────────────────────────────────────────────
    @Value("${chat.api.url:#{null}}")
    private String chatApiUrl;

    @Value("${chat.api.secret:#{null}}")
    private String chatApiSecret;

    private static final int MAX_RETRIES = 3;

    // ── Public API ────────────────────────────────────────────────────────────

    @Async("syncExecutor")
    public CompletableFuture<Void> syncUser(User user) {
        // Run LMS and Chat syncs in parallel; failures are isolated
        var lmsFuture = CompletableFuture.runAsync(() ->
            withRetry(() -> doPost(lmsApiUrl + "/api/v1/sync/user", buildLmsPayload(user),
                                   lmsApiSecret),
                      "lms-sync user " + user.getEmail())
        ).exceptionally(ex -> { log.error("LMS sync failed for {}: {}", user.getEmail(), ex.getMessage()); return null; });

        var chatFuture = syncUserToChat(user);

        return CompletableFuture.allOf(lmsFuture, chatFuture);
    }

    @Async("syncExecutor")
    public CompletableFuture<Void> syncUsers(List<User> users) {
        var futures = users.stream()
                .map(u -> CompletableFuture
                        .runAsync(() ->
                            withRetry(() -> doPost(lmsApiUrl + "/api/v1/sync/user", buildLmsPayload(u),
                                                   lmsApiSecret),
                                      "lms-sync user " + u.getEmail()))
                        .exceptionally(ex -> {
                            log.error("LMS sync failed for user {}: {}", u.getEmail(), ex.getMessage());
                            return null;
                        }))
                .toArray(CompletableFuture[]::new);

        var chatFuture = syncUsersToChat(users);

        return CompletableFuture.allOf(
            CompletableFuture.allOf(futures)
                .thenRun(() -> log.info("LMS bulk sync completed for {} users", users.size())),
            chatFuture
        );
    }

    @Async("syncExecutor")
    public CompletableFuture<Void> deleteUser(Long userId) {
        // Delete from both LMS and Chat in parallel
        var lmsFuture = CompletableFuture.runAsync(() -> {
            try {
                restTemplate.exchange(
                    lmsApiUrl + "/api/v1/sync/user/" + userId,
                    HttpMethod.DELETE,
                    new HttpEntity<>(authHeaders(lmsApiSecret)),
                    Void.class
                );
                log.info("Deleted user {} from LMS", userId);
            } catch (RestClientException ex) {
                log.error("Failed to delete user {} from LMS: {}", userId, ex.getMessage());
            }
        });

        var chatFuture = CompletableFuture.runAsync(() -> {
            if (chatApiUrl == null || chatApiUrl.isBlank()) return;
            try {
                restTemplate.exchange(
                    chatApiUrl + "/api/v1/sync/user/" + userId,
                    HttpMethod.DELETE,
                    new HttpEntity<>(authHeaders(chatApiSecret)),
                    Void.class
                );
                log.info("Deleted user {} from Chat", userId);
            } catch (RestClientException ex) {
                log.warn("Failed to delete user {} from Chat (non-critical): {}", userId, ex.getMessage());
            }
        });

        return CompletableFuture.allOf(lmsFuture, chatFuture);
    }

    // ── Chat-specific sync ────────────────────────────────────────────────────

    private CompletableFuture<Void> syncUserToChat(User user) {
        if (chatApiUrl == null || chatApiUrl.isBlank()) {
            return CompletableFuture.completedFuture(null);
        }
        return CompletableFuture.runAsync(() -> {
            try {
                withRetry(() -> doPost(chatApiUrl + "/api/v1/sync/user", buildChatPayload(user),
                                       chatApiSecret),
                          "chat-sync user " + user.getEmail());
            } catch (Exception ex) {
                log.warn("Chat sync failed for {} (non-critical): {}", user.getEmail(), ex.getMessage());
            }
        });
    }

    public CompletableFuture<Void> syncUsersToChat(List<User> users) {
        if (chatApiUrl == null || chatApiUrl.isBlank()) {
            return CompletableFuture.completedFuture(null);
        }
        return CompletableFuture.runAsync(() -> {
            try {
                var payloads = users.stream().map(this::buildChatPayload).toList();
                withRetry(() -> doPost(chatApiUrl + "/api/v1/sync/users/bulk", Map.of("users", payloads),
                                       chatApiSecret),
                          "chat-bulk-sync");
                log.info("Chat bulk sync completed for {} users", users.size());
            } catch (Exception ex) {
                log.warn("Chat bulk sync failed (non-critical): {}", ex.getMessage());
            }
        });
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /** Payload for LMS service — uses "user_id" key */
    private Map<String, Object> buildLmsPayload(User user) {
        return Map.of(
            "user_id",   user.getId(),
            "email",     user.getEmail(),
            "full_name", user.getName(),
            "roles",     roleStrategy.resolve(user.getRole()),
            "org",       user.getOrganization() != null ? user.getOrganization() : ""
        );
    }

    /** Payload for Chat service — uses "id" key, profile_picture field */
    private Map<String, Object> buildChatPayload(User user) {
        return Map.of(
            "id",              user.getId(),
            "email",           user.getEmail(),
            "full_name",       user.getName() != null ? user.getName() : "",
            "profile_picture", ""  // auth-service has no avatar URL yet; chat falls back to DiceBear
        );
    }

    private void doPost(String url, Object payload, String secret) {
        var response = restTemplate.exchange(
            url, HttpMethod.POST,
            new HttpEntity<>(payload, jsonAuthHeaders(secret)),
            new ParameterizedTypeReference<Map<String, Object>>() {}
        );
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new com.example.demo.exception.ExternalServiceException(
                "Sync", "HTTP " + response.getStatusCode());
        }
    }

    private void withRetry(Runnable task, String taskName) {
        for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                task.run();
                return;
            } catch (Exception ex) {
                if (attempt == MAX_RETRIES) {
                    log.error("All {} retries failed for [{}]: {}", MAX_RETRIES, taskName, ex.getMessage());
                    throw ex;
                }
                long backoff = (long) Math.pow(2, attempt - 1) * 1000;
                log.warn("Attempt {}/{} failed for [{}], retrying in {}ms: {}",
                         attempt, MAX_RETRIES, taskName, backoff, ex.getMessage());
                sleep(backoff);
            }
        }
    }

    private HttpHeaders authHeaders(String secret) {
        var headers = new HttpHeaders();
        headers.set("X-Sync-Secret", secret);
        return headers;
    }

    private HttpHeaders jsonAuthHeaders(String secret) {
        var headers = authHeaders(secret);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private void sleep(long ms) {
        try { Thread.sleep(ms); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }
}