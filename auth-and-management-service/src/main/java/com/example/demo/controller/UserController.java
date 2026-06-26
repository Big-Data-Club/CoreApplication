package com.example.demo.controller;

import com.example.demo.dto.user.ChangePasswordRequest;
import com.example.demo.dto.user.UpdateUserRequest;
import com.example.demo.dto.user.UpdateUserRoleRequest;
import com.example.demo.dto.user.UserResponse;
import com.example.demo.service.user.UserService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

/**
 * UserController - REST API cho user management.
 *
 * Fixes:
 *   - public class (không còn package-private).
 *   - Trả UserResponse thay vì User entity - không lộ internal model.
 *   - updateUser nhận UpdateUserRequest thay vì User entity.
 *     Tránh mass assignment: client không thể tự set role, totalScore qua endpoint này.
 */
@RestController
@RequestMapping("/api/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    @GetMapping
    public ResponseEntity<List<UserResponse>> getAll() {
        return ResponseEntity.ok(userService.getAllUsers());
    }

    @GetMapping("/{id}")
    public ResponseEntity<UserResponse> getById(@PathVariable Long id) {
        return ResponseEntity.ok(userService.getUserById(id));
    }

    @PutMapping("/{id}")
    public ResponseEntity<UserResponse> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateUserRequest req) {
        return ResponseEntity.ok(userService.updateUser(id, req));
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PatchMapping("/{id}/role")
    public ResponseEntity<UserResponse> updateRole(
            @PathVariable Long id,
            @Valid @RequestBody UpdateUserRoleRequest req) {
        return ResponseEntity.ok(userService.updateRole(id, req.getRole()));
    }

    @PostMapping("/{id}/change-password")
    public ResponseEntity<Map<String, String>> changePassword(
            @PathVariable Long id,
            @Valid @RequestBody ChangePasswordRequest req) {
        userService.changePassword(id, req.getCurrentPassword(), req.getNewPassword());
        return ResponseEntity.ok(Map.of("message", "Password changed successfully"));
    }

    @PostMapping("/{id}/upload-picture")
    public ResponseEntity<Map<String, String>> uploadPicture(
            @PathVariable Long id,
            @RequestParam("file") MultipartFile file) {
        String url = userService.uploadProfilePicture(id, file);
        return ResponseEntity.ok(Map.of("profilePicture", url));
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PatchMapping("/{id}/status")
    public ResponseEntity<UserResponse> toggleStatus(@PathVariable Long id) {
        return ResponseEntity.ok(userService.toggleActive(id));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        userService.deleteUser(id);
        return ResponseEntity.noContent().build();
    }

    @PreAuthorize("hasRole('ADMIN')")
    @GetMapping("/pending")
    public ResponseEntity<List<UserResponse>> getPendingUsers() {
        return ResponseEntity.ok(userService.getPendingUsers());
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PatchMapping("/{id}/approve")
    public ResponseEntity<UserResponse> approveUser(@PathVariable Long id) {
        return ResponseEntity.ok(userService.approveUser(id));
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PatchMapping("/{id}/reject")
    public ResponseEntity<UserResponse> rejectUser(@PathVariable Long id) {
        return ResponseEntity.ok(userService.rejectUser(id));
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PostMapping("/sync-to-chat")
    public ResponseEntity<java.util.Map<String, String>> syncToChat() {
        userService.syncAllUsersToChat();
        return ResponseEntity.ok(java.util.Map.of("message", "Triggered synchronization of all users to chat service."));
    }
}
