package com.example.demo.strategy;

import com.example.demo.model.LmsRoleMapping;
import com.example.demo.repository.LmsRoleMappingRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Resolves an Auth-side role name (e.g. "ROLE_ADMIN") into one or more
 * LMS-side role names (e.g. ["ADMIN"]) by looking up the dynamic mappings
 * stored in the {@code lms_role_mappings} table.
 *
 * Results are cached per role name; the cache is evicted when an admin
 * updates the mappings via {@code RoleManagementService}.
 */
@Component
@RequiredArgsConstructor
public class LmsRoleStrategy implements RoleResolutionStrategy {

    private final LmsRoleMappingRepository mappingRepo;

    @Cacheable(value = "lmsRoleMappings", key = "#role")
    @Override
    public List<String> resolve(String role) {
        var mappings = mappingRepo.findByAuthRoleName(role);
        if (mappings.isEmpty()) {
            return List.of("STUDENT"); // safe fallback
        }
        return mappings.stream()
                .map(LmsRoleMapping::getLmsRole)
                .toList();
    }
}
