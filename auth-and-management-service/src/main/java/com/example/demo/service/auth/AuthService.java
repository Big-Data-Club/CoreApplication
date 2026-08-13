package com.example.demo.service.auth;

import com.example.demo.dto.auth.BulkRegisterRequest;
import com.example.demo.dto.auth.LoginRequest;
import com.example.demo.dto.auth.OrganizationAssignmentRequest;
import com.example.demo.dto.auth.RegisterRequest;
import com.example.demo.exception.BadRequestException;
import com.example.demo.model.User;
import com.example.demo.model.Organization;
import com.example.demo.model.OrganizationMember;
import com.example.demo.repository.UserRepository;
import com.example.demo.repository.RoleRepository;
import com.example.demo.repository.OrganizationRepository;
import com.example.demo.repository.OrganizationMemberRepository;
import com.example.demo.repository.TeamRepository;
import com.example.demo.repository.UserTypeOptionRepository;
import com.example.demo.service.email.EmailService;
import com.example.demo.service.org.OrganizationSyncService;
import com.example.demo.service.user.UserSyncService;
import com.example.demo.strategy.RoleResolutionStrategy;
import com.example.demo.utils.PasswordGenerator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.Locale;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;
    private final UserSyncService userSyncService;
    private final RoleResolutionStrategy roleStrategy;
    private final OrganizationRepository organizationRepository;
    private final OrganizationMemberRepository organizationMemberRepository;
    private final OrganizationSyncService organizationSyncService;
    private final TeamRepository teamRepository;
    private final UserTypeOptionRepository userTypeOptionRepository;

    @Value("${app.default-role:ROLE_USER}")
    private String defaultRole;

    public User authenticate(LoginRequest request) {
        var user = userRepository.findByEmail(request.getEmail())
                .orElseThrow(() -> new BadRequestException("Invalid email or password"));

        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BadRequestException("Invalid email or password");
        }

        if (!user.getActive()) {
            if (user.getPendingApproval()) {
                throw new BadRequestException("Tài khoản của bạn đang chờ admin duyệt. Vui lòng đợi.");
            }
            throw new BadRequestException("Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên.");
        }

        return user;
    }

    public String generateToken(User user) {
        var tokenRoles = user.getLmsRoles() != null && !user.getLmsRoles().isEmpty()
                ? user.getLmsRoles().stream().distinct().toList()
                : roleStrategy.resolveAll(user.effectiveRoles());
        return jwtService.generateToken(user.getId(), user.getEmail(),
                                        tokenRoles);
    }

    public String generateRefreshToken(User user) {
        return jwtService.generateRefreshToken(user.getId(), user.getEmail());
    }

    public boolean validateToken(String token) {
        return jwtService.validateToken(token);
    }

    public String extractEmail(String token) {
        return jwtService.extractEmail(token);
    }

    @Transactional
    public List<User> bulkRegister(BulkRegisterRequest request) {
        var registrations = request == null ? null : request.getUsers();
        if (registrations == null || registrations.isEmpty()) {
            throw new BadRequestException("Import batch must contain at least one user");
        }
        if (registrations.size() > 2000) {
            throw new BadRequestException("A single import is limited to 2000 users");
        }

        var existingRoles = roleRepository.findAll().stream()
                .map(role -> role.getName().toUpperCase(Locale.ROOT))
                .collect(Collectors.toSet());
        var organizations = organizationRepository.findAll();
        var validTeams = teamRepository.findAll().stream()
                .map(team -> team.getCode().toUpperCase(Locale.ROOT))
                .collect(Collectors.toSet());
        var validTypes = userTypeOptionRepository.findAll().stream()
                .map(type -> type.getCode().toUpperCase(Locale.ROOT))
                .collect(Collectors.toSet());
        Map<String, Organization> organizationsByIdentifier = new java.util.HashMap<>();
        organizations.forEach(org -> {
            organizationsByIdentifier.put(org.getSlug().toLowerCase(Locale.ROOT), org);
            organizationsByIdentifier.put(org.getName().toLowerCase(Locale.ROOT), org);
        });

        List<String> errors = new java.util.ArrayList<>();
        List<PreparedRegistration> prepared = new java.util.ArrayList<>();
        Set<String> seenEmails = new java.util.HashSet<>();
        Set<String> seenCodes = new java.util.HashSet<>();

        for (int index = 0; index < registrations.size(); index++) {
            RegisterRequest reg = registrations.get(index);
            int row = index + 2; // spreadsheet header is row 1
            String name = clean(reg.getName());
            String email = clean(reg.getEmail()).toLowerCase(Locale.ROOT);
            String code = clean(reg.getCode());
            String team = clean(reg.getTeam()).toUpperCase(Locale.ROOT);
            String type = clean(reg.getType()).toUpperCase(Locale.ROOT);
            if (name.isBlank()) errors.add("Row " + row + ": name is required");
            if (!email.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) errors.add("Row " + row + ": invalid email");
            if (code.isBlank()) errors.add("Row " + row + ": code is required");
            if (team.isBlank() || !validTeams.contains(team)) errors.add("Row " + row + ": unknown team " + team);
            if (type.isBlank() || !validTypes.contains(type)) errors.add("Row " + row + ": unknown type " + type);
            if (!seenEmails.add(email)) errors.add("Row " + row + ": duplicate email in file: " + email);
            if (!seenCodes.add(code)) errors.add("Row " + row + ": duplicate code in file: " + code);

            LinkedHashSet<String> roles = new LinkedHashSet<>();
            if (reg.getRoles() != null) reg.getRoles().stream().map(this::normalizeRole).forEach(roles::add);
            if (roles.isEmpty()) roles.add(normalizeRole(reg.getRole()));
            for (String role : roles) {
                if (!existingRoles.contains(role)) errors.add("Row " + row + ": unknown role " + role);
            }

            LinkedHashSet<String> lmsRoles = new LinkedHashSet<>();
            if (reg.getLmsRoles() != null) {
                reg.getLmsRoles().stream()
                        .filter(value -> value != null)
                        .flatMap(value -> java.util.Arrays.stream(value.split("[;,]")))
                        .map(this::normalizeLmsRole)
                        .filter(role -> !role.isBlank())
                        .forEach(lmsRoles::add);
            }
            for (String lmsRole : lmsRoles) {
                if (!Set.of("ADMIN", "TEACHER", "STUDENT").contains(lmsRole)) {
                    errors.add("Row " + row + ": unknown LMS role " + lmsRole);
                }
            }

            List<ResolvedOrganization> resolvedOrganizations = new java.util.ArrayList<>();
            List<OrganizationAssignmentRequest> requestedOrganizations = reg.getOrganizations();
            if ((requestedOrganizations == null || requestedOrganizations.isEmpty()) && !clean(reg.getOrganization()).isBlank()) {
                requestedOrganizations = parseLegacyOrganizations(reg.getOrganization());
            }
            if (requestedOrganizations != null) {
                Set<Long> seenOrgIds = new java.util.HashSet<>();
                for (OrganizationAssignmentRequest assignment : requestedOrganizations) {
                    String identifier = clean(assignment.getIdentifier()).toLowerCase(Locale.ROOT);
                    Organization org = organizationsByIdentifier.get(identifier);
                    String orgRole = clean(assignment.getOrgRole()).toUpperCase(Locale.ROOT);
                    if (orgRole.isBlank()) orgRole = "MEMBER";
                    if (org == null) {
                        errors.add("Row " + row + ": unknown organization " + assignment.getIdentifier());
                    } else if (!Set.of("OWNER", "ADMIN", "MEMBER").contains(orgRole)) {
                        errors.add("Row " + row + ": invalid organization role " + orgRole);
                    } else if (seenOrgIds.add(org.getId())) {
                        resolvedOrganizations.add(new ResolvedOrganization(org, orgRole));
                    }
                }
            }
            prepared.add(new PreparedRegistration(name, email, code, team, type, roles, lmsRoles, resolvedOrganizations));
        }

        var emails = prepared.stream().map(PreparedRegistration::email).toList();
        var codes = prepared.stream().map(PreparedRegistration::code).toList();
        var duplicateEmails = userRepository.findExistingEmails(emails);
        var duplicateCodes = userRepository.findExistingCodes(codes);
        if (!duplicateEmails.isEmpty()) errors.add("Emails already in database: " + String.join(", ", duplicateEmails));
        if (!duplicateCodes.isEmpty()) errors.add("Codes already in database: " + String.join(", ", duplicateCodes));
        if (!errors.isEmpty()) throw new BadRequestException(String.join("; ", errors));

        Map<String, String> emailToPassword = new java.util.LinkedHashMap<>();
        Map<String, String> emailToName    = new java.util.LinkedHashMap<>();

        List<User> users = prepared.stream()
                .map(item -> {
                    String pwd = PasswordGenerator.generateStrongPassword();
                    emailToPassword.put(item.email(), pwd);
                    emailToName.put(item.email(), item.name());
                    String primaryRole = item.roles().iterator().next();

                    return User.builder()
                            .name(item.name())
                            .email(item.email())
                            .password(passwordEncoder.encode(pwd))
                            .role(primaryRole)
                            .roles(new LinkedHashSet<>(item.roles()))
                            .lmsRoles(new LinkedHashSet<>(item.lmsRoles()))
                            .team(item.team())
                            .code(item.code())
                            .type(item.type())
                            .organization(item.organizations().stream().map(resolved -> resolved.organization().getName()).collect(Collectors.joining(", ")))
                            .active(true)
                            .totalScore(0)
                            .build();
                })
                .collect(Collectors.toList());

        List<User> saved = userRepository.saveAll(users);
        List<OrganizationMember> memberships = new java.util.ArrayList<>();
        for (int index = 0; index < saved.size(); index++) {
            User user = saved.get(index);
            for (ResolvedOrganization resolved : prepared.get(index).organizations()) {
                memberships.add(OrganizationMember.builder()
                        .organization(resolved.organization())
                        .user(user)
                        .orgRole(resolved.orgRole())
                        .build());
            }
        }
        memberships = organizationMemberRepository.saveAll(memberships);
        List<OrganizationMember> savedMemberships = List.copyOf(memberships);
        log.info("Bulk registered {} users", saved.size());

        emailService.sendWelcomeBatch(emailToPassword, emailToName)
                    .exceptionally(ex -> { log.error("Batch email error: {}", ex.getMessage()); return null; });

        userSyncService.syncUsers(saved)
                       .thenRun(() -> savedMemberships.forEach(organizationSyncService::syncMember))
                       .exceptionally(ex -> { log.error("LMS sync error: {}", ex.getMessage()); return null; });

        return saved;
    }

    private String clean(String value) {
        return value == null ? "" : value.trim();
    }

    private String normalizeRole(String role) {
        String normalized = clean(role);
        if (normalized.isBlank()) normalized = defaultRole;
        normalized = normalized.toUpperCase(Locale.ROOT);
        return normalized.startsWith("ROLE_") ? normalized : "ROLE_" + normalized;
    }

    private String normalizeLmsRole(String role) {
        return clean(role).toUpperCase(Locale.ROOT).replaceFirst("^LMS:", "");
    }

    private List<OrganizationAssignmentRequest> parseLegacyOrganizations(String value) {
        List<OrganizationAssignmentRequest> result = new java.util.ArrayList<>();
        for (String token : value.split(";")) {
            String[] parts = token.trim().split(":", 2);
            if (!parts[0].isBlank()) {
                result.add(OrganizationAssignmentRequest.builder()
                        .identifier(parts[0].trim())
                        .orgRole(parts.length > 1 ? parts[1].trim() : "MEMBER")
                        .build());
            }
        }
        return result;
    }

    private record ResolvedOrganization(Organization organization, String orgRole) {}
    private record PreparedRegistration(
            String name,
            String email,
            String code,
            String team,
            String type,
            LinkedHashSet<String> roles,
            LinkedHashSet<String> lmsRoles,
            List<ResolvedOrganization> organizations) {}
}
