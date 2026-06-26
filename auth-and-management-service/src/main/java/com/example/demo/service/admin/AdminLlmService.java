package com.example.demo.service.admin;

import com.example.demo.exception.ExternalServiceException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.util.List;
import java.util.Map;

/**
 * Proxy client for the internal AI service LLM admin API.
 *
 * The AI service guards its {@code /ai/admin/llm/*} endpoints with a shared
 * {@code X-AI-Secret} header. This service owns that secret so the admin
 * frontend can speak JWT + RBAC to Spring and let Spring bridge the gap.
 *
 * Design notes
 *   - Responses are passed through as typed Maps/Lists. The AI service is the
 *     source of truth for schema — duplicating DTOs on both sides creates a
 *     drift risk that isn't worth the type-safety given this is an admin tool.
 *   - Upstream non-2xx responses become {@link ExternalServiceException} so
 *     the GlobalExceptionHandler converts them into 502 for the caller.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AdminLlmService {

    private static final String SERVICE_NAME = "ai-service";
    private static final String BASE_PATH    = "/ai/admin/llm";

    private final RestTemplate restTemplate;

    @Value("${ai-service.api.url}")
    private String aiServiceUrl;

    @Value("${ai-service.api.secret}")
    private String aiServiceSecret;

    // ── Catalogue ──────────────────────────────────────────────────────────
    public Map<String, Object> getCatalogue() {
        return getMap("/catalogue");
    }

    // ── Providers ──────────────────────────────────────────────────────────
    public List<Map<String, Object>> listProviders() {
        return getList("/providers");
    }

    public Map<String, Object> upsertProvider(Map<String, Object> body) {
        return postMap("/providers", body);
    }

    public Map<String, Object> updateProvider(long id, Map<String, Object> body) {
        return patchMap("/providers/" + id, body);
    }

    public void deleteProvider(long id) {
        delete("/providers/" + id);
    }

    // ── Models ─────────────────────────────────────────────────────────────
    public List<Map<String, Object>> listModels(Long providerId, Boolean onlyEnabled) {
        var uri = uri("/models",
                providerId != null ? Map.entry("provider_id", providerId.toString()) : null,
                onlyEnabled != null ? Map.entry("only_enabled", onlyEnabled.toString()) : null);
        return getList(uri);
    }

    public Map<String, Object> upsertModel(Map<String, Object> body) {
        return postMap("/models", body);
    }

    public Map<String, Object> updateModel(long id, Map<String, Object> body) {
        return patchMap("/models/" + id, body);
    }

    public void deleteModel(long id) {
        delete("/models/" + id);
    }

    // ── API keys ───────────────────────────────────────────────────────────
    public List<Map<String, Object>> listApiKeys(Long providerId) {
        var uri = uri("/keys",
                providerId != null ? Map.entry("provider_id", providerId.toString()) : null);
        return getList(uri);
    }

    public Map<String, Object> createApiKey(Map<String, Object> body) {
        return postMap("/keys", body);
    }

    public Map<String, Object> updateApiKey(long id, Map<String, Object> body) {
        return patchMap("/keys/" + id, body);
    }

    public void deleteApiKey(long id) {
        delete("/keys/" + id);
    }

    // ── Bindings ───────────────────────────────────────────────────────────
    public List<Map<String, Object>> listBindings(String taskCode) {
        var uri = uri("/bindings",
                taskCode != null ? Map.entry("task_code", taskCode) : null);
        return getList(uri);
    }

    public Map<String, Object> upsertBinding(Map<String, Object> body) {
        return postMap("/bindings", body);
    }

    public Map<String, Object> updateBinding(long id, Map<String, Object> body) {
        return patchMap("/bindings/" + id, body);
    }

    public void deleteBinding(long id) {
        delete("/bindings/" + id);
    }

    // ── Usage + test call ─────────────────────────────────────────────────
    public Map<String, Object> usage(int sinceHours, String taskCode) {
        var uri = uri("/usage",
                Map.entry("since_hours", Integer.toString(sinceHours)),
                taskCode != null ? Map.entry("task_code", taskCode) : null);
        return getMap(uri);
    }

    public Map<String, Object> testCall(Map<String, Object> body) {
        return postMap("/test-call", body);
    }

    // ── Plumbing ───────────────────────────────────────────────────────────
    private Map<String, Object> getMap(String path) {
        return getMap(uri(path));
    }

    private Map<String, Object> getMap(URI uri) {
        return exchange(uri, HttpMethod.GET, null, MAP_TYPE);
    }

    private List<Map<String, Object>> getList(String path) {
        return getList(uri(path));
    }

    private List<Map<String, Object>> getList(URI uri) {
        return exchange(uri, HttpMethod.GET, null, LIST_TYPE);
    }

    private Map<String, Object> postMap(String path, Object body) {
        return exchange(uri(path), HttpMethod.POST, body, MAP_TYPE);
    }

    private Map<String, Object> patchMap(String path, Object body) {
        return exchange(uri(path), HttpMethod.PATCH, body, MAP_TYPE);
    }

    private void delete(String path) {
        exchange(uri(path), HttpMethod.DELETE, null, VOID_TYPE);
    }

    private <T> T exchange(URI uri, HttpMethod method, Object body,
                           ParameterizedTypeReference<T> type) {
        var entity = new HttpEntity<>(body, headers(body != null));
        try {
            var response = restTemplate.exchange(uri, method, entity, type);
            if (!response.getStatusCode().is2xxSuccessful()) {
                throw new ExternalServiceException(SERVICE_NAME,
                        method + " " + uri.getPath() + " -> HTTP " + response.getStatusCode().value());
            }
            return response.getBody();
        } catch (HttpStatusCodeException ex) {
            log.warn("{} {} -> {} body={}",
                    method, uri.getPath(), ex.getStatusCode(),
                    truncate(ex.getResponseBodyAsString(), 400));
            throw new ExternalServiceException(SERVICE_NAME,
                    method + " " + uri.getPath() + " -> HTTP " + ex.getStatusCode().value(), ex);
        } catch (RestClientException ex) {
            log.error("{} {} failed: {}", method, uri.getPath(), ex.getMessage());
            throw new ExternalServiceException(SERVICE_NAME,
                    method + " " + uri.getPath() + " failed: " + ex.getMessage(), ex);
        }
    }

    @SafeVarargs
    private URI uri(String path, Map.Entry<String, String>... queryParams) {
        var builder = UriComponentsBuilder
                .fromHttpUrl(aiServiceUrl.replaceAll("/$", "") + BASE_PATH)
                .path(path);
        for (var entry : queryParams) {
            if (entry != null) builder.queryParam(entry.getKey(), entry.getValue());
        }
        return builder.build(true).toUri();
    }

    private HttpHeaders headers(boolean withJsonBody) {
        var headers = new HttpHeaders();
        headers.set("X-AI-Secret", aiServiceSecret);
        if (withJsonBody) headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private static String truncate(String s, int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max) + "…";
    }

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE =
            new ParameterizedTypeReference<>() {};
    private static final ParameterizedTypeReference<List<Map<String, Object>>> LIST_TYPE =
            new ParameterizedTypeReference<>() {};
    private static final ParameterizedTypeReference<Void> VOID_TYPE =
            new ParameterizedTypeReference<>() {};
}