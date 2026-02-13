package com.example.demo.service;

import com.example.demo.enums.UserRole;
import com.example.demo.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.*;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserSyncService {
    
    private final RestTemplate restTemplate;
    
    @Value("${lms.api.url}")
    private String lmsApiUrl;
    
    @Value("${lms.api.secret}")
    private String lmsApiSecret;
    
    /**
     * Đồng bộ user sang LMS (Go backend)
     * Tất cả users đều có role TEACHER và STUDENT
     * Chỉ ADMIN mới có thêm role ADMIN
     */
    @Async
    public CompletableFuture<Void> syncUserToLms(User user) {
        try {
            syncSingleUser(user);
            log.info("Successfully synced user {} to LMS", user.getEmail());
        } catch (Exception e) {
            log.error("Failed to sync user {} to LMS: {}", user.getEmail(), e.getMessage());
        }
        return CompletableFuture.completedFuture(null);
    }
    
    /**
     * Đồng bộ nhiều users sang LMS
     */
    @Async
    public CompletableFuture<Void> syncUsersToLms(List<User> users) {
        try {
            bulkSyncUsers(users);
            log.info("Successfully synced {} users to LMS", users.size());
        } catch (Exception e) {
            log.error("Failed to bulk sync users to LMS: {}", e.getMessage());
        }
        return CompletableFuture.completedFuture(null);
    }
    
    private void syncSingleUser(User user) {
        String url = lmsApiUrl + "/api/v1/sync/user";
        
        Map<String, Object> payload = buildUserSyncPayload(user);
        
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Sync-Secret", lmsApiSecret);
        
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(payload, headers);
        
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
            url,
            HttpMethod.POST,
            request,
            new ParameterizedTypeReference<Map<String, Object>>() {}
        );
        
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new RuntimeException("LMS sync failed with status: " + response.getStatusCode());
        }
    }
    
    private void bulkSyncUsers(List<User> users) {
        String url = lmsApiUrl + "/api/v1/sync/users/bulk";
        
        List<Map<String, Object>> usersPayload = new ArrayList<>();
        for (User user : users) {
            usersPayload.add(buildUserSyncPayload(user));
        }
        
        Map<String, Object> payload = new HashMap<>();
        payload.put("users", usersPayload);
        
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Sync-Secret", lmsApiSecret);
        
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(payload, headers);
        
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
            url,
            HttpMethod.POST,
            request,
            new ParameterizedTypeReference<Map<String, Object>>() {}
        );
        
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new RuntimeException("LMS bulk sync failed with status: " + response.getStatusCode());
        }
    }
    
    private Map<String, Object> buildUserSyncPayload(User user) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("user_id", user.getId());
        payload.put("email", user.getEmail());
        payload.put("full_name", user.getName());
        
        // Xác định roles
        List<String> roles = determineRoles(user.getRole());
        payload.put("roles", roles);
        
        return payload;
    }
    
    /**
     * Xác định roles cho LMS:
     * - Tất cả users: TEACHER + STUDENT
     * - ADMIN: TEACHER + STUDENT + ADMIN
     */
    private List<String> determineRoles(UserRole userRole) {
        List<String> roles = new ArrayList<>();
        
        // Mặc định: tất cả đều có TEACHER và STUDENT
        roles.add("TEACHER");
        roles.add("STUDENT");
        
        // ADMIN thêm role ADMIN
        if (userRole == UserRole.ROLE_ADMIN) {
            roles.add("ADMIN");
        }
        
        return roles;
    }
    
    /**
     * Xóa user khỏi LMS
     */
    @Async
    public CompletableFuture<Void> deleteUserFromLms(Long userId) {
        try {
            String url = lmsApiUrl + "/api/v1/sync/user/" + userId;
            
            HttpHeaders headers = new HttpHeaders();
            headers.set("X-Sync-Secret", lmsApiSecret);
            
            HttpEntity<Void> request = new HttpEntity<>(headers);
            
            restTemplate.exchange(
                url,
                HttpMethod.DELETE,
                request,
                Void.class
            );
            
            log.info("Successfully deleted user {} from LMS", userId);
        } catch (Exception e) {
            log.error("Failed to delete user {} from LMS: {}", userId, e.getMessage());
        }
        return CompletableFuture.completedFuture(null);
    }
}