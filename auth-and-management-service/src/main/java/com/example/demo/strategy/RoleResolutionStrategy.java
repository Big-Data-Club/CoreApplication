package com.example.demo.strategy;

import java.util.Collection;
import java.util.List;

public interface RoleResolutionStrategy {
    List<String> resolve(String role);

    default List<String> resolveAll(Collection<String> roles) {
        if (roles == null || roles.isEmpty()) return List.of("STUDENT");
        return roles.stream()
                .filter(role -> role != null && !role.isBlank())
                .flatMap(role -> resolve(role).stream())
                .distinct()
                .toList();
    }
}
