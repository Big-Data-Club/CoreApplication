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

    @Value("${lms.api.url}")
    private String lmsApiUrl;

    @Value("${lms.api.secret}")
    private String lmsApiSecret;

    private static final int MAX_RETRIES = 3;

    // Public API

    @Async("syncExecutor")
    public CompletableFuture<Void> syncUser(User user) {
        return CompletableFuture.runAsync(() ->
            withRetry(() -> doPost(lmsApiUrl + "/api/v1/sync/user", buildPayload(user)),
                      "sync user " + user.getEmail())
        );
    }

    @Async("syncExecutor")
    public CompletableFuture<Void> syncUsers(List<User> users) {
        var futures = users.stream()
                .map(u -> CompletableFuture
                        .runAsync(() ->
                            withRetry(() -> doPost(lmsApiUrl + "/api/v1/sync/user", buildPayload(u)),
                                      "sync user " + u.getEmail()))
                        .exceptionally(ex -> {
                            log.error("Sync failed for user {}: {}", u.getEmail(), ex.getMessage());
                            return null;
                        }))
                .toArray(CompletableFuture[]::new);

        return CompletableFuture.allOf(futures)
                .thenRun(() -> log.info("Bulk sync completed for {} users", users.size()));
    }

    @Async("syncExecutor")
    public CompletableFuture<Void> deleteUser(Long userId) {
        return CompletableFuture.runAsync(() -> {
            try {
                restTemplate.exchange(
                    lmsApiUrl + "/api/v1/sync/user/" + userId,
                    HttpMethod.DELETE,
                    new HttpEntity<>(authHeaders()),
                    Void.class
                );
                log.info("Deleted user {} from LMS", userId);
            } catch (RestClientException ex) {
                log.error("Failed to delete user {} from LMS: {}", userId, ex.getMessage());
            }
        });
    }

    // Helpers
    private Map<String, Object> buildPayload(User user) {
        return Map.of(
            "user_id",   user.getId(),
            "email",     user.getEmail(),
            "full_name", user.getName(),
            "roles",     roleStrategy.resolve(user.getRole()),
            "org",       user.getOrganization() != null ? user.getOrganization() : ""
        );
    }

    private void doPost(String url, Object payload) {
        var response = restTemplate.exchange(
            url, HttpMethod.POST,
            new HttpEntity<>(payload, jsonAuthHeaders()),
            new ParameterizedTypeReference<Map<String, Object>>() {}
        );
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new com.example.demo.exception.ExternalServiceException(
                "LMS", "HTTP " + response.getStatusCode());
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

    private HttpHeaders authHeaders() {
        var headers = new HttpHeaders();
        headers.set("X-Sync-Secret", lmsApiSecret);
        return headers;
    }

    private HttpHeaders jsonAuthHeaders() {
        var headers = authHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private void sleep(long ms) {
        try { Thread.sleep(ms); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }
}