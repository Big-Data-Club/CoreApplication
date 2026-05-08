package com.example.demo.config;

import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.LmsRoleMapping;
import com.example.demo.model.Role;
import com.example.demo.model.User;
import com.example.demo.repository.LmsRoleMappingRepository;
import com.example.demo.repository.RoleRepository;
import com.example.demo.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;

@Slf4j
@Configuration
@RequiredArgsConstructor
@Order(1)
public class DataInitializer implements CommandLineRunner {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final LmsRoleMappingRepository lmsMappingRepository;
    private final PasswordEncoder passwordEncoder;

    @org.springframework.beans.factory.annotation.Value("${app.admin.password:hehehe}")
    private String adminPassword;

    @org.springframework.beans.factory.annotation.Value("${app.admin.email:phucnhan289@gmail.com}")
    private String adminEmail;

    @Override
    public void run(String... args) {
        seedRoles();
        seedAdminUser();
    }

    /**
     * Seed the dynamic roles table and default LMS mappings.
     * Idempotent — skips if roles already exist.
     */
    private void seedRoles() {
        seedRole(UserRole.ROLE_ADMIN, "Administrator", "ADMIN");
        seedRole(UserRole.ROLE_MANAGER, "Manager", "TEACHER");
        seedRole(UserRole.ROLE_USER, "Member", "STUDENT");
        log.debug("Role seeding complete");
    }

    private void seedRole(String roleName, String displayName, String defaultLmsRole) {
        if (roleRepository.existsByName(roleName)) return;

        var role = roleRepository.save(Role.builder()
                .name(roleName)
                .displayName(displayName)
                .isSystem(true)
                .build());

        lmsMappingRepository.save(LmsRoleMapping.builder()
                .authRole(role)
                .lmsRole(defaultLmsRole)
                .build());

        log.info("Seeded role {} → LMS [{}]", roleName, defaultLmsRole);
    }

    private void seedAdminUser() {
        if (userRepository.count() > 0) {
            log.debug("Database already seeded, skipping admin user creation");
            return;
        }

        var admin = User.builder()
                .name("Nguyễn Phúc Nhân")
                .email(adminEmail)
                .password(passwordEncoder.encode(adminPassword))
                .role(UserRole.ROLE_ADMIN)
                .team(UserTeam.RESEARCH)
                .code("000000")
                .type(UserType.DT)
                .totalScore(10000)
                .active(true)
                .build();

        userRepository.save(admin);
        log.info("Default admin user created: {}", adminEmail);
    }
}