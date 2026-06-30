package com.example.demo.controller;

import com.example.demo.dto.org.*;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.OrganizationService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/organizations")
@RequiredArgsConstructor
public class OrganizationController {

    private final OrganizationService orgService;
    private final UserRepository userRepository;

    private User getCurrentUser() {
        String email = (String) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        return userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + email));
    }

    @GetMapping
    public ResponseEntity<List<OrgResponse>> getAll() {
        return ResponseEntity.ok(orgService.getAllOrganizations());
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrgResponse> getById(@PathVariable Long id) {
        return ResponseEntity.ok(orgService.getOrganizationById(id));
    }

    @GetMapping("/slug/{slug}")
    public ResponseEntity<OrgResponse> getBySlug(@PathVariable String slug) {
        return ResponseEntity.ok(orgService.getOrganizationBySlug(slug));
    }

    @GetMapping("/my")
    public ResponseEntity<List<OrgResponse>> getMyOrganizations() {
        User user = getCurrentUser();
        return ResponseEntity.ok(orgService.getOrganizationsByUser(user.getId()));
    }

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<OrgResponse> create(@RequestBody CreateOrgRequest req) {
        User user = getCurrentUser();
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(orgService.createOrganization(req, user.getId()));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<OrgResponse> update(@PathVariable Long id, @RequestBody UpdateOrgRequest req) {
        return ResponseEntity.ok(orgService.updateOrganization(id, req));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        orgService.deleteOrganization(id);
        return ResponseEntity.noContent().build();
    }

    // ── Membership Endpoints ─────────────────────────────────────────────────

    @GetMapping("/{id}/members")
    public ResponseEntity<List<OrgMemberResponse>> getMembers(@PathVariable Long id) {
        return ResponseEntity.ok(orgService.getOrganizationMembers(id));
    }

    @PostMapping("/{id}/members")
    public ResponseEntity<Void> addMember(@PathVariable Long id, @RequestBody AddMemberRequest req) {
        orgService.addMember(id, req);
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @PutMapping("/{id}/members/{userId}/role")
    public ResponseEntity<Void> updateMemberRole(
            @PathVariable Long id,
            @PathVariable Long userId,
            @RequestBody UpdateMemberRoleRequest req) {
        orgService.updateMemberRole(id, userId, req);
        return ResponseEntity.ok().build();
    }

    @DeleteMapping("/{id}/members/{userId}")
    public ResponseEntity<Void> removeMember(@PathVariable Long id, @PathVariable Long userId) {
        orgService.removeMember(id, userId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{id}/members/bulk")
    public ResponseEntity<BulkAddMembersResponse> bulkAddMembers(
            @PathVariable Long id,
            @RequestBody BulkAddMembersRequest req) {
        return ResponseEntity.ok(orgService.bulkAddMembers(id, req));
    }
}
