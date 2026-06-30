package com.example.demo.service.org.impl;

import com.example.demo.dto.org.*;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.Organization;
import com.example.demo.model.OrganizationMember;
import com.example.demo.model.User;
import com.example.demo.repository.OrganizationMemberRepository;
import com.example.demo.repository.OrganizationRepository;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.OrganizationService;
import com.example.demo.service.org.OrganizationSyncService;
import com.example.demo.service.user.UserSyncService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class OrganizationServiceImpl implements OrganizationService {

    private final OrganizationRepository orgRepo;
    private final OrganizationMemberRepository memberRepo;
    private final UserRepository userRepo;
    private final OrganizationSyncService syncService;
    private final UserSyncService userSyncService;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional(readOnly = true)
    public List<OrgResponse> getAllOrganizations() {
        return orgRepo.findAll().stream()
                .map(this::toResponse)
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    public OrgResponse getOrganizationById(Long id) {
        Organization org = orgRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + id));
        return toResponse(org);
    }

    @Override
    @Transactional(readOnly = true)
    public OrgResponse getOrganizationBySlug(String slug) {
        Organization org = orgRepo.findBySlug(slug)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with slug: " + slug));
        return toResponse(org);
    }

    @Override
    @Transactional
    public OrgResponse createOrganization(CreateOrgRequest req, Long creatorId) {
        if (orgRepo.existsBySlug(req.getSlug())) {
            throw new IllegalArgumentException("Organization with slug '" + req.getSlug() + "' already exists");
        }

        Organization org = Organization.builder()
                .name(req.getName())
                .slug(req.getSlug())
                .description(req.getDescription())
                .logoUrl(req.getLogoUrl())
                .isActive(true)
                .settings(serializeSettings(req.getSettings()))
                .createdBy(creatorId)
                .build();

        org = orgRepo.save(org);
        syncService.syncOrganization(org);

        return toResponse(org);
    }

    @Override
    @Transactional
    public OrgResponse updateOrganization(Long id, UpdateOrgRequest req) {
        Organization org = orgRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + id));

        if (req.getName() != null) org.setName(req.getName());
        if (req.getSlug() != null && !req.getSlug().equals(org.getSlug())) {
            if (orgRepo.existsBySlug(req.getSlug())) {
                throw new IllegalArgumentException("Organization with slug '" + req.getSlug() + "' already exists");
            }
            org.setSlug(req.getSlug());
        }
        if (req.getDescription() != null) org.setDescription(req.getDescription());
        if (req.getLogoUrl() != null) org.setLogoUrl(req.getLogoUrl());
        if (req.getSettings() != null) org.setSettings(serializeSettings(req.getSettings()));

        org = orgRepo.save(org);
        syncService.syncOrganization(org);

        return toResponse(org);
    }

    @Override
    @Transactional
    public void deleteOrganization(Long id) {
        if (!orgRepo.existsById(id)) {
            throw new ResourceNotFoundException("Organization not found with ID: " + id);
        }

        // Before deleting, find all members to clear their User.organization column
        List<OrganizationMember> members = memberRepo.findByOrganization(
            Organization.builder().id(id).build()
        );

        orgRepo.deleteById(id);
        syncService.deleteOrganization(id);

        // Update each affected user's flat organization representation
        for (OrganizationMember m : members) {
            updateUserFlatOrg(m.getUser());
        }
    }

    @Override
    @Transactional(readOnly = true)
    public List<OrgResponse> getOrganizationsByUser(Long userId) {
        User user = userRepo.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));
        return memberRepo.findByUser(user).stream()
                .map(m -> toResponse(m.getOrganization()))
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    public List<OrgMemberResponse> getOrganizationMembers(Long orgId) {
        Organization org = orgRepo.findById(orgId)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + orgId));

        return memberRepo.findByOrganization(org).stream()
                .map(this::toMemberResponse)
                .toList();
    }

    @Override
    @Transactional
    public void addMember(Long orgId, AddMemberRequest req) {
        Organization org = orgRepo.findById(orgId)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + orgId));

        User user = userRepo.findById(req.getUserID())
                .orElseThrow(() -> new ResourceNotFoundException("User not found with ID: " + req.getUserID()));

        if (memberRepo.existsByOrganizationAndUser(org, user)) {
            return; // Already a member
        }

        OrganizationMember member = OrganizationMember.builder()
                .organization(org)
                .user(user)
                .orgRole(req.getOrgRole() != null ? req.getOrgRole() : "MEMBER")
                .build();

        member = memberRepo.save(member);
        syncService.syncMember(member);

        // Update User flat organization representation
        updateUserFlatOrg(user);
    }

    @Override
    @Transactional
    public void updateMemberRole(Long orgId, Long userId, UpdateMemberRoleRequest req) {
        Organization org = orgRepo.findById(orgId)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + orgId));

        User user = userRepo.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with ID: " + userId));

        OrganizationMember member = memberRepo.findByOrganizationAndUser(org, user)
                .orElseThrow(() -> new ResourceNotFoundException("Membership not found"));

        member.setOrgRole(req.getOrgRole());
        member = memberRepo.save(member);
        syncService.syncMember(member);
    }

    @Override
    @Transactional
    public void removeMember(Long orgId, Long userId) {
        Organization org = orgRepo.findById(orgId)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + orgId));

        User user = userRepo.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with ID: " + userId));

        memberRepo.deleteByOrganizationAndUser(org, user);
        syncService.removeMember(orgId, userId);

        // Update User flat organization representation
        updateUserFlatOrg(user);
    }

    @Override
    @Transactional
    public BulkAddMembersResponse bulkAddMembers(Long orgId, BulkAddMembersRequest req) {
        Organization org = orgRepo.findById(orgId)
                .orElseThrow(() -> new ResourceNotFoundException("Organization not found with ID: " + orgId));

        List<String> emailsToProcess = new ArrayList<>();
        if (req.getEmails() != null) {
            emailsToProcess.addAll(req.getEmails());
        }

        if (req.getRawInput() != null && !req.getRawInput().isBlank()) {
            // Split raw input by comma, newline, or space
            String[] tokens = req.getRawInput().split("[,\\s\\n\\r]+");
            for (String t : tokens) {
                String clean = t.trim();
                if (!clean.isEmpty() && clean.contains("@")) {
                    emailsToProcess.add(clean);
                }
            }
        }

        List<String> added = new ArrayList<>();
        List<String> notFound = new ArrayList<>();

        for (String email : emailsToProcess) {
            Optional<User> userOpt = userRepo.findByEmail(email);
            if (userOpt.isPresent()) {
                User user = userOpt.get();
                if (!memberRepo.existsByOrganizationAndUser(org, user)) {
                    OrganizationMember member = OrganizationMember.builder()
                            .organization(org)
                            .user(user)
                            .orgRole(req.getOrgRole() != null ? req.getOrgRole() : "MEMBER")
                            .build();

                    member = memberRepo.save(member);
                    syncService.syncMember(member);
                    updateUserFlatOrg(user);
                }
                added.add(email);
            } else {
                notFound.add(email);
            }
        }

        return BulkAddMembersResponse.builder()
                .added(added)
                .notFound(notFound)
                .build();
    }

    // ── Helper Mappers ─────────────────────────────────────────────────────────

    private OrgResponse toResponse(Organization org) {
        return OrgResponse.builder()
                .id(org.getId())
                .name(org.getName())
                .slug(org.getSlug())
                .description(org.getDescription())
                .logoUrl(org.getLogoUrl())
                .isActive(org.isActive())
                .settings(deserializeSettings(org.getSettings()))
                .createdBy(org.getCreatedBy())
                .createdAt(org.getCreatedAt())
                .updatedAt(org.getUpdatedAt())
                .build();
    }

    private OrgMemberResponse toMemberResponse(OrganizationMember member) {
        return OrgMemberResponse.builder()
                .userID(member.getUser().getId())
                .fullName(member.getUser().getName())
                .email(member.getUser().getEmail())
                .orgRole(member.getOrgRole())
                .joinedAt(member.getJoinedAt())
                .build();
    }

    private String serializeSettings(OrgSettingsDTO dto) {
        if (dto == null) {
            return "{\"allow_cross_org_courses\": true, \"default_course_visibility\": \"PUBLIC\"}";
        }
        try {
            return objectMapper.writeValueAsString(dto);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize organization settings: {}", e.getMessage());
            return "{\"allow_cross_org_courses\": true, \"default_course_visibility\": \"PUBLIC\"}";
        }
    }

    private OrgSettingsDTO deserializeSettings(String settingsJson) {
        if (settingsJson == null || settingsJson.isBlank()) {
            return OrgSettingsDTO.builder()
                    .allowCrossOrgCourses(true)
                    .defaultCourseVisibility("PUBLIC")
                    .build();
        }
        try {
            return objectMapper.readValue(settingsJson, OrgSettingsDTO.class);
        } catch (JsonProcessingException e) {
            log.error("Failed to deserialize organization settings: {}", e.getMessage());
            return OrgSettingsDTO.builder()
                    .allowCrossOrgCourses(true)
                    .defaultCourseVisibility("PUBLIC")
                    .build();
        }
    }

    /**
     * Determines user's primary/active organization name and updates flat User.organization
     * and triggers a full User synchronization to LMS.
     */
    private void updateUserFlatOrg(User user) {
        List<OrganizationMember> memberships = memberRepo.findByUser(user);
        String orgName = "";
        if (!memberships.isEmpty()) {
            // Pick first org as primary name
            orgName = memberships.get(0).getOrganization().getName();
        }

        user.setOrganization(orgName);
        userRepo.save(user);

        // Sync user profile change (including the updated flat organization string) to LMS/Chat
        userSyncService.syncUser(user);
    }
}
