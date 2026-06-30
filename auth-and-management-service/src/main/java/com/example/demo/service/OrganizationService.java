package com.example.demo.service;

import com.example.demo.dto.org.*;
import java.util.List;

public interface OrganizationService {
    List<OrgResponse> getAllOrganizations();
    OrgResponse getOrganizationById(Long id);
    OrgResponse getOrganizationBySlug(String slug);
    OrgResponse createOrganization(CreateOrgRequest req, Long creatorId);
    OrgResponse updateOrganization(Long id, UpdateOrgRequest req);
    void deleteOrganization(Long id);

    // User's organizations
    List<OrgResponse> getOrganizationsByUser(Long userId);

    // Membership management
    List<OrgMemberResponse> getOrganizationMembers(Long orgId);
    void addMember(Long orgId, AddMemberRequest req);
    void updateMemberRole(Long orgId, Long userId, UpdateMemberRoleRequest req);
    void removeMember(Long orgId, Long userId);
    BulkAddMembersResponse bulkAddMembers(Long orgId, BulkAddMembersRequest req);
}
