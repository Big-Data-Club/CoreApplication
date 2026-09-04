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

    // How long the startup sync waits for lms-service to answer /health.
    private static final int  STARTUP_PROBE_ATTEMPTS    = 24;
    private static final long STARTUP_PROBE_INTERVAL_MS = 5_000;

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

    /**
     * Push every known account to LMS once, at application startup.
     *
     * <p>The admin seeded by {@code DataInitializer} is written straight through the
     * repository and so passes none of the code paths that call {@link #syncUser}. On a
     * fresh database it is the only account LMS has never heard of, and logging in with
     * it lands on "Không thể truy cập LMS" until somebody POSTs /api/v1/sync/user by hand.
     *
     * <p>More patient than {@link #syncUsers}: compose starts lms-service after
     * auth-service, so the three attempts over three seconds that {@link #withRetry}
     * allows are usually spent before LMS is listening. Probe /health first, then push.
     */
    @Async("syncExecutor")
    public CompletableFuture<Void> syncUsersToLms(List<User> users) {
        if (users.isEmpty()) {
            return CompletableFuture.completedFuture(null);
        }
        if (!waitForLms()) {
            log.error("LMS did not become ready within {}s; skipping startup sync. "
                      + "Existing accounts will have no LMS role until the next user update.",
                      STARTUP_PROBE_ATTEMPTS * STARTUP_PROBE_INTERVAL_MS / 1000);
            return CompletableFuture.completedFuture(null);
        }

        int synced = 0;
        for (var user : users) {
            try {
                withRetry(() -> doPost(lmsApiUrl + "/api/v1/sync/user", buildLmsPayload(user),
                                       lmsApiSecret),
                          "lms-startup-sync " + user.getEmail());
                synced++;
            } catch (Exception ex) {
                log.error("Startup LMS sync failed for {}: {}", user.getEmail(), ex.getMessage());
            }
        }
        log.info("Startup LMS sync completed for {}/{} users", synced, users.size());
        return CompletableFuture.completedFuture(null);
    }

    /** Poll lms-service /health until it answers 2xx. Returns false once patience runs out. */
    private boolean waitForLms() {
        for (int attempt = 1; attempt <= STARTUP_PROBE_ATTEMPTS; attempt++) {
            try {
                if (restTemplate.getForEntity(lmsApiUrl + "/health", String.class)
                                .getStatusCode().is2xxSuccessful()) {
                    return true;
                }
            } catch (RestClientException ex) {
                // lms-service is not up yet; container DNS may not even resolve.
                log.debug("Waiting for lms-service ({}/{}): {}",
                          attempt, STARTUP_PROBE_ATTEMPTS, ex.getMessage());
            }
            sleep(STARTUP_PROBE_INTERVAL_MS);
        }
        return false;
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

    /** Payload for LMS service - uses "user_id" key */
    private Map<String, Object> buildLmsPayload(User user) {
        var lmsRoles = user.getLmsRoles() != null && !user.getLmsRoles().isEmpty()
                ? user.getLmsRoles().stream().distinct().toList()
                : roleStrategy.resolveAll(user.effectiveRoles());
        return Map.of(
            "user_id",   user.getId(),
            "email",     user.getEmail(),
            "full_name", user.getName(),
            "profile_picture", user.getProfilePicture() != null ? user.getProfilePicture() : "",
            "roles",     lmsRoles,
            "org",       user.getOrganization() != null ? user.getOrganization() : ""
        );
    }

    /** Payload for Chat service - uses "id" key, profile_picture field */
    private Map<String, Object> buildChatPayload(User user) {
        return Map.of(
            "id",              user.getId(),
            "email",           user.getEmail(),
            "full_name",       user.getName() != null ? user.getName() : "",
            "profile_picture", user.getProfilePicture() != null ? user.getProfilePicture() : ""
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
