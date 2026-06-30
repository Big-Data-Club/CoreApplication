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
import com.example.demo.repository.TeamRepository;
import com.example.demo.repository.UserTypeOptionRepository;
import com.example.demo.repository.OrganizationRepository;
import com.example.demo.model.Team;
import com.example.demo.model.UserTypeOption;
import com.example.demo.model.Organization;
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
    private final TeamRepository teamRepository;
    private final UserTypeOptionRepository typeRepository;
    private final OrganizationRepository organizationRepository;
    private final org.springframework.jdbc.core.JdbcTemplate jdbcTemplate;
    private final com.example.demo.service.user.UserSyncService userSyncService;

    @org.springframework.beans.factory.annotation.Value("${app.admin.password:hehehe}")
    private String adminPassword;

    @org.springframework.beans.factory.annotation.Value("${app.admin.email:phucnhan289@gmail.com}")
    private String adminEmail;

    @Override
    public void run(String... args) {
        try {
            log.info("Dropping database check constraints for dynamic fields...");
            jdbcTemplate.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check");
            jdbcTemplate.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_type_check");
            jdbcTemplate.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_team_check");
            log.info("Successfully dropped check constraints.");
        } catch (Exception e) {
            log.error("Failed to drop check constraints: {}", e.getMessage());
        }
        seedOrganizations();
        seedRoles();
        seedTeams();
        seedTypes();
        seedAdminUser();

        log.info("Triggering automatic startup sync of existing users to chat-service...");
        try {
            userSyncService.syncUsersToChat(userRepository.findAll());
        } catch (Exception e) {
            log.error("Startup user sync to chat failed: {}", e.getMessage());
        }
    }

    private void seedOrganizations() {
        if (organizationRepository.existsBySlug("bdc")) return;

        organizationRepository.save(Organization.builder()
                .name("Big Data Club")
                .slug("bdc")
                .description("Default organization")
                .isActive(true)
                .settings("{\"allow_cross_org_courses\": true, \"default_course_visibility\": \"PUBLIC\"}")
                .build());
        log.info("Seeded default organization (Big Data Club)");
    }

    /**
     * Seed the dynamic roles table and default LMS mappings.
     * Idempotent - skips if roles already exist.
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

        log.info("Seeded role {} -> LMS [{}]", roleName, defaultLmsRole);
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

    private void seedTeams() {
        if (teamRepository.count() > 0) return;

        teamRepository.save(Team.builder().code("RESEARCH").name("Research").description("Research Division").build());
        teamRepository.save(Team.builder().code("ENGINEER").name("Engineer").description("Engineering & Development Division").build());
        teamRepository.save(Team.builder().code("EVENT").name("Event").description("Event Planning Division").build());
        teamRepository.save(Team.builder().code("MEDIA").name("Media").description("Media & Marketing Division").build());

        log.info("Default teams seeded successfully.");
    }

    private void seedTypes() {
        if (typeRepository.count() > 0) return;

        typeRepository.save(UserTypeOption.builder().code("CLC").name("CLC").description("Cử nhân chất lượng cao").build());
        typeRepository.save(UserTypeOption.builder().code("TN").name("TN").description("Cử nhân tài năng").build());
        typeRepository.save(UserTypeOption.builder().code("DT").name("DT").description("Đại trà").build());

        log.info("Default user types seeded successfully.");
    }
}