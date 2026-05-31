package com.example.demo.service.auth;

import com.example.demo.dto.auth.BulkRegisterRequest;
import com.example.demo.dto.auth.LoginRequest;
import com.example.demo.exception.BadRequestException;
import com.example.demo.exception.DuplicateResourceException;
import com.example.demo.enums.UserRole;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.repository.RoleRepository;
import com.example.demo.service.email.EmailService;
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
import java.util.Map;
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
        return jwtService.generateToken(user.getId(), user.getEmail(),
                                        roleStrategy.resolve(user.getRole()));
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
        var registrations = request.getUsers();

        // 1. Collect all emails & codes from the incoming batch
        var emails = registrations.stream().map(r -> r.getEmail()).toList();
        var codes  = registrations.stream().map(r -> r.getCode()).filter(c -> c != null && !c.isBlank()).toList();

        // 2. Batch-validate: find duplicates that already exist in DB
        var duplicateEmails = userRepository.findExistingEmails(emails);
        var duplicateCodes  = codes.isEmpty() ? java.util.Set.<String>of() : userRepository.findExistingCodes(codes);

        // 3. Also check for duplicates within the batch itself
        var seenEmails = new java.util.HashSet<String>();
        var inBatchDupEmails = emails.stream().filter(e -> !seenEmails.add(e)).toList();
        var seenCodes = new java.util.HashSet<String>();
        var inBatchDupCodes = codes.stream().filter(c -> !seenCodes.add(c)).toList();

        // 4. Build error message
        List<String> errors = new java.util.ArrayList<>();
        if (!duplicateEmails.isEmpty()) {
            errors.add("Duplicate email(s) already in DB: " + String.join(", ", duplicateEmails));
        }
        if (!inBatchDupEmails.isEmpty()) {
            errors.add("Duplicate email(s) within batch: " + String.join(", ", inBatchDupEmails));
        }
        if (!duplicateCodes.isEmpty()) {
            errors.add("Duplicate code(s) already in DB: " + String.join(", ", duplicateCodes));
        }
        if (!inBatchDupCodes.isEmpty()) {
            errors.add("Duplicate code(s) within batch: " + String.join(", ", inBatchDupCodes));
        }

        // 5. Validate roles exist in DB
        var existingRoles = roleRepository.findAll().stream()
                .map(r -> r.getName().toUpperCase())
                .collect(Collectors.toSet());

        List<String> invalidRoles = new java.util.ArrayList<>();
        for (var reg : registrations) {
            String roleStr = reg.getRole() != null && !reg.getRole().trim().isEmpty() ? reg.getRole().trim() : defaultRole;
            if (!roleStr.toUpperCase().startsWith("ROLE_")) {
                roleStr = "ROLE_" + roleStr.toUpperCase();
            } else {
                roleStr = roleStr.toUpperCase();
            }
            if (!existingRoles.contains(roleStr)) {
                invalidRoles.add(roleStr);
            }
        }

        if (!invalidRoles.isEmpty()) {
            errors.add("Invalid role(s): " + String.join(", ", invalidRoles.stream().distinct().toList()));
        }

        if (!errors.isEmpty()) {
            if (!invalidRoles.isEmpty()) {
                throw new BadRequestException(String.join("; ", errors));
            }
            throw new DuplicateResourceException("User", "email/code", String.join("; ", errors));
        }

        Map<String, String> emailToPassword = new java.util.LinkedHashMap<>();
        Map<String, String> emailToName    = new java.util.LinkedHashMap<>();

        List<User> users = registrations.stream()
                .map(reg -> {
                    String pwd = PasswordGenerator.generateStrongPassword();
                    emailToPassword.put(reg.getEmail(), pwd);
                    emailToName.put(reg.getEmail(), reg.getName());
                    String roleStr = reg.getRole() != null && !reg.getRole().trim().isEmpty() ? reg.getRole().trim() : defaultRole;
                    if (!roleStr.toUpperCase().startsWith("ROLE_")) {
                        roleStr = "ROLE_" + roleStr.toUpperCase();
                    } else {
                        roleStr = roleStr.toUpperCase();
                    }

                    return User.builder()
                            .name(reg.getName())
                            .email(reg.getEmail())
                            .password(passwordEncoder.encode(pwd))
                            .role(roleStr)
                            .team(reg.getTeam())
                            .code(reg.getCode())
                            .type(reg.getType())
                            .organization(reg.getOrganization())
                            .active(true)
                            .totalScore(0)
                            .build();
                })
                .collect(Collectors.toList());

        List<User> saved = userRepository.saveAll(users);
        log.info("Bulk registered {} users", saved.size());

        emailService.sendWelcomeBatch(emailToPassword, emailToName)
                    .exceptionally(ex -> { log.error("Batch email error: {}", ex.getMessage()); return null; });

        userSyncService.syncUsers(saved)
                       .exceptionally(ex -> { log.error("LMS sync error: {}", ex.getMessage()); return null; });

        return saved;
    }
}