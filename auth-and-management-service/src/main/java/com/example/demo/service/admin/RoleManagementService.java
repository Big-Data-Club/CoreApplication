package com.example.demo.service.admin;

import com.example.demo.exception.BadRequestException;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.LmsRoleMapping;
import com.example.demo.model.Permission;
import com.example.demo.model.Role;
import com.example.demo.repository.LmsRoleMappingRepository;
import com.example.demo.repository.PermissionRepository;
import com.example.demo.repository.RoleRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RoleManagementService {

    private final RoleRepository roleRepo;
    private final PermissionRepository permissionRepo;
    private final LmsRoleMappingRepository lmsMappingRepo;

    // ── Roles CRUD ───────────────────────────────────────────────────────────

    public List<Role> listRoles() {
        return roleRepo.findAll();
    }

    @Transactional
    public Role createRole(String name, String displayName, String description) {
        if (roleRepo.existsByName(name)) {
            throw new BadRequestException("Role already exists: " + name);
        }
        var role = Role.builder()
                .name(name.toUpperCase())
                .displayName(displayName)
                .description(description)
                .isSystem(false)
                .build();
        log.info("Created role: {}", name);
        return roleRepo.save(role);
    }

    @Transactional
    public Role updateRole(Long id, String displayName, String description) {
        var role = findRole(id);
        if (displayName != null) role.setDisplayName(displayName);
        if (description != null) role.setDescription(description);
        return roleRepo.save(role);
    }

    @Transactional
    public void deleteRole(Long id) {
        var role = findRole(id);
        if (Boolean.TRUE.equals(role.getIsSystem())) {
            throw new BadRequestException("Cannot delete system role: " + role.getName());
        }
        roleRepo.delete(role);
        log.info("Deleted role: {}", role.getName());
    }

    // ── Permissions CRUD ─────────────────────────────────────────────────────

    public List<Permission> listPermissions() {
        return permissionRepo.findAll();
    }

    @Transactional
    public Permission createPermission(String resource, String action, String description) {
        var existing = permissionRepo.findByResourceAndAction(resource, action);
        if (existing.isPresent()) {
            throw new BadRequestException("Permission already exists: " + resource + ":" + action);
        }
        return permissionRepo.save(Permission.builder()
                .resource(resource)
                .action(action)
                .description(description)
                .build());
    }

    // ── LMS Role Mappings ────────────────────────────────────────────────────

    /** Returns all mappings grouped by auth role name. */
    public Map<String, List<String>> getLmsMappings() {
        return lmsMappingRepo.findAll().stream()
                .collect(Collectors.groupingBy(
                        m -> m.getAuthRole().getName(),
                        Collectors.mapping(LmsRoleMapping::getLmsRole, Collectors.toList())
                ));
    }

    /**
     * Replace all LMS mappings for a given auth role.
     * Evicts the cached LmsRoleStrategy results so the next sync uses fresh data.
     */
    @Transactional
    @CacheEvict(value = "lmsRoleMappings", allEntries = true)
    public void setLmsMappings(Long authRoleId, List<String> lmsRoles) {
        var authRole = findRole(authRoleId);
        lmsMappingRepo.deleteByAuthRoleId(authRoleId);
        lmsMappingRepo.flush();

        if (lmsRoles == null) {
            log.info("Updated LMS mappings for {}: [] (null input)", authRole.getName());
            return;
        }

        for (String lmsRole : lmsRoles) {
            lmsMappingRepo.save(LmsRoleMapping.builder()
                    .authRole(authRole)
                    .lmsRole(lmsRole.toUpperCase())
                    .build());
        }
        log.info("Updated LMS mappings for {}: {}", authRole.getName(), lmsRoles);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private Role findRole(Long id) {
        return roleRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Role", id));
    }
}
