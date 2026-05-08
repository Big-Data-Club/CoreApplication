package com.example.demo.controller;

import com.example.demo.model.Permission;
import com.example.demo.model.Role;
import com.example.demo.service.admin.RoleManagementService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class RoleManagementController {

    private final RoleManagementService service;

    // ── Roles ────────────────────────────────────────────────────────────────

    @GetMapping("/roles")
    public ResponseEntity<List<Role>> listRoles() {
        return ResponseEntity.ok(service.listRoles());
    }

    @PostMapping("/roles")
    public ResponseEntity<Role> createRole(@RequestBody Map<String, String> body) {
        var role = service.createRole(
                body.get("name"),
                body.get("displayName"),
                body.get("description"));
        return ResponseEntity.status(HttpStatus.CREATED).body(role);
    }

    @PutMapping("/roles/{id}")
    public ResponseEntity<Role> updateRole(@PathVariable Long id,
                                           @RequestBody Map<String, String> body) {
        return ResponseEntity.ok(service.updateRole(id, body.get("displayName"), body.get("description")));
    }

    @DeleteMapping("/roles/{id}")
    public ResponseEntity<Void> deleteRole(@PathVariable Long id) {
        service.deleteRole(id);
        return ResponseEntity.noContent().build();
    }

    // ── Permissions ──────────────────────────────────────────────────────────

    @GetMapping("/permissions")
    public ResponseEntity<List<Permission>> listPermissions() {
        return ResponseEntity.ok(service.listPermissions());
    }

    @PostMapping("/permissions")
    public ResponseEntity<Permission> createPermission(@RequestBody Map<String, String> body) {
        var perm = service.createPermission(
                body.get("resource"),
                body.get("action"),
                body.get("description"));
        return ResponseEntity.status(HttpStatus.CREATED).body(perm);
    }

    // ── LMS Role Mappings ────────────────────────────────────────────────────

    @GetMapping("/lms-role-mappings")
    public ResponseEntity<Map<String, List<String>>> getLmsMappings() {
        return ResponseEntity.ok(service.getLmsMappings());
    }

    @PutMapping("/roles/{id}/lms-mappings")
    public ResponseEntity<Map<String, String>> setLmsMappings(
            @PathVariable Long id,
            @RequestBody Map<String, List<String>> body) {
        service.setLmsMappings(id, body.get("lmsRoles"));
        return ResponseEntity.ok(Map.of("message", "LMS mappings updated"));
    }
}
