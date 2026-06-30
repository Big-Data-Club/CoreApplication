package com.example.demo.service.org;

import com.example.demo.model.Organization;
import com.example.demo.model.OrganizationMember;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class OrganizationSyncService {

    private final RestTemplate restTemplate;

    @Value("${lms.api.url}")
    private String lmsApiUrl;

    @Value("${lms.api.secret}")
    private String lmsApiSecret;

    @Async("syncExecutor")
    public void syncOrganization(Organization org) {
        try {
            Map<String, Object> payload = Map.of(
                "id", org.getId(),
                "name", org.getName(),
                "slug", org.getSlug(),
                "description", org.getDescription() != null ? org.getDescription() : "",
                "logo_url", org.getLogoUrl() != null ? org.getLogoUrl() : "",
                "is_active", org.isActive(),
                "settings", org.getSettings()
            );

            restTemplate.exchange(
                lmsApiUrl + "/api/v1/sync/organizations",
                HttpMethod.POST,
                new HttpEntity<>(payload, jsonAuthHeaders()),
                Void.class
            );
            log.info("Synced organization {} (ID: {}) to LMS", org.getName(), org.getId());
        } catch (RestClientException ex) {
            log.error("Failed to sync organization {} to LMS: {}", org.getId(), ex.getMessage());
        }
    }

    @Async("syncExecutor")
    public void deleteOrganization(Long orgId) {
        try {
            restTemplate.exchange(
                lmsApiUrl + "/api/v1/sync/organizations/" + orgId,
                HttpMethod.DELETE,
                new HttpEntity<>(jsonAuthHeaders()),
                Void.class
            );
            log.info("Synced organization delete (ID: {}) to LMS", orgId);
        } catch (RestClientException ex) {
            log.error("Failed to sync organization delete {} to LMS: {}", orgId, ex.getMessage());
        }
    }

    @Async("syncExecutor")
    public void syncMember(OrganizationMember member) {
        try {
            Map<String, Object> payload = Map.of(
                "org_id", member.getOrganization().getId(),
                "user_id", member.getUser().getId(),
                "org_role", member.getOrgRole()
            );

            restTemplate.exchange(
                lmsApiUrl + "/api/v1/sync/organization-members",
                HttpMethod.POST,
                new HttpEntity<>(payload, jsonAuthHeaders()),
                Void.class
            );
            log.info("Synced membership for user {} in org {} to LMS", member.getUser().getId(), member.getOrganization().getId());
        } catch (RestClientException ex) {
            log.error("Failed to sync membership to LMS: {}", ex.getMessage());
        }
    }

    @Async("syncExecutor")
    public void removeMember(Long orgId, Long userId) {
        try {
            restTemplate.exchange(
                lmsApiUrl + "/api/v1/sync/organization-members/" + orgId + "/users/" + userId,
                HttpMethod.DELETE,
                new HttpEntity<>(jsonAuthHeaders()),
                Void.class
            );
            log.info("Synced membership removal for user {} from org {} to LMS", userId, orgId);
        } catch (RestClientException ex) {
            log.error("Failed to sync membership removal to LMS: {}", ex.getMessage());
        }
    }

    private HttpHeaders jsonAuthHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Sync-Secret", lmsApiSecret);
        return headers;
    }
}
