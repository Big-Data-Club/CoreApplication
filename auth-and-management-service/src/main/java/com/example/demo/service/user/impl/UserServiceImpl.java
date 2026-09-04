package com.example.demo.service.user.impl;

import com.example.demo.dto.auth.PasswordChangeRequest;
import com.example.demo.dto.user.UpdateUserRequest;
import com.example.demo.dto.user.UserResponse;
import com.example.demo.dto.common.PageResponse;
import com.example.demo.exception.BadRequestException;
import com.example.demo.exception.InvalidPasswordException;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.repository.RoleRepository;
import com.example.demo.repository.OrganizationMemberRepository;
import com.example.demo.service.email.EmailService;
import com.example.demo.service.user.PasswordResetService;
import com.example.demo.service.user.UserService;
import com.example.demo.service.user.UserSyncService;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.*;
import java.util.List;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserServiceImpl implements UserService {

    private static final long MAX_PROFILE_PICTURE_BYTES = 1024L * 1024L;

    private final UserRepository     userRepository;
    private final OrganizationMemberRepository organizationMemberRepository;
    private final RoleRepository     roleRepository;
    private final PasswordEncoder    passwordEncoder;
    private final EmailService       emailService;
    private final PasswordResetService passwordResetService;
    private final UserSyncService    userSyncService;

    @Value("${app.upload.dir:uploads/profiles/}")
    private String uploadDir;

    @Value("${app.default-role:ROLE_USER}")
    private String defaultRole;

    // Reads

    @Override
    public PageResponse<UserResponse> getUsers(
            int page, int pageSize, String query, String team, String type,
            String role, String sortBy, String sortDirection) {
        int safePage = Math.max(0, page);
        int safePageSize = Math.min(100, Math.max(1, pageSize));
        Set<String> sortableFields = Set.of(
                "id", "name", "role", "team", "organization", "totalScore", "active");
        String safeSortBy = sortableFields.contains(sortBy) ? sortBy : "id";
        Sort.Direction direction = "asc".equalsIgnoreCase(sortDirection)
                ? Sort.Direction.ASC : Sort.Direction.DESC;
        var pageable = PageRequest.of(safePage, safePageSize, Sort.by(direction, safeSortBy));

        String normalizedQuery = query == null ? "" : query.trim();
        Page<User> userPage = userRepository.searchPage(
                normalizedQuery,
                team == null ? "" : team.trim(),
                type == null ? "" : type.trim(),
                role == null ? "" : role.trim(),
                pageable);

        List<Long> userIds = userPage.getContent().stream().map(User::getId).toList();
        Map<Long, List<String>> organizationsByUser = new HashMap<>();
        if (!userIds.isEmpty()) {
            for (var row : organizationMemberRepository.findOrganizationNamesByUserIds(userIds)) {
                organizationsByUser
                        .computeIfAbsent(row.getUserId(), ignored -> new ArrayList<>())
                        .add(row.getOrganizationName());
            }
        }

        List<UserResponse> items = userPage.getContent().stream()
                .map(user -> UserResponse.fromEntity(
                        user,
                        organizationsByUser.getOrDefault(user.getId(), List.of())))
                .toList();

        return new PageResponse<>(items, safePage, safePageSize,
                userPage.getTotalElements(), userPage.getTotalPages(), userPage.hasNext());
    }

    @Override
    public UserResponse getUserById(Long id) {
        return userRepository.findById(id)
                .map(UserResponse::fromEntity)
                .orElseThrow(() -> new ResourceNotFoundException("User", id));
    }

    /** Internal use only */
    @Override
    public User getUserByEmail(String email) {
        return userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + email));
    }

    // Writes

    @Override
    @Transactional
    public UserResponse updateUser(Long id, UpdateUserRequest req) {
        var user = findUserEntity(id);
        user.setName(req.getName());
        user.setEmail(req.getEmail());
        if (req.getTeam() != null)           user.setTeam(req.getTeam());
        if (req.getType() != null)           user.setType(req.getType());
        if (req.getProfilePicture() != null) user.setProfilePicture(req.getProfilePicture());
        if (req.getOrganization() != null)   user.setOrganization(req.getOrganization());
        var saved = userRepository.save(user);
        userSyncService.syncUser(saved);
        return UserResponse.fromEntity(saved);
    }

    @Override
    @Transactional
    public UserResponse updateRole(Long id, String role) {
        var user = findUserEntity(id);
        String normalizedRole = role != null && !role.trim().isEmpty() ? role.trim() : defaultRole;
        if (!normalizedRole.toUpperCase().startsWith("ROLE_")) {
            normalizedRole = "ROLE_" + normalizedRole.toUpperCase();
        } else {
            normalizedRole = normalizedRole.toUpperCase();
        }

        if (!roleRepository.existsByName(normalizedRole)) {
            throw new BadRequestException("Role '" + normalizedRole + "' does not exist in the system.");
        }

        user.setRole(normalizedRole);
        user.getRoles().clear();
        user.getRoles().add(normalizedRole);
        var saved = userRepository.save(user);
        userSyncService.syncUser(saved);
        return UserResponse.fromEntity(saved);
    }

    @Override
    @Transactional
    public void changePassword(Long userId, String current, String newPwd) {
        var user = findUserEntity(userId);

        if (!passwordEncoder.matches(current, user.getPassword())) {
            throw new BadRequestException("Current password is incorrect");
        }
        validatePassword(newPwd);

        user.setPassword(passwordEncoder.encode(newPwd));
        userRepository.save(user);

        emailService.sendPasswordChangedNotificationAsync(user.getEmail(), user.getName())
                .exceptionally(ex -> {
                    log.warn("Notification email failed: {}", ex.getMessage());
                    return null;
                });
    }

    @Override
    @Transactional
    public void requestPasswordChange(PasswordChangeRequest req) {
        var user = getUserByEmail(req.getEmail());

        if (!passwordEncoder.matches(req.getCurrentPassword(), user.getPassword())) {
            throw new BadRequestException("Mật khẩu hiện tại không đúng");
        }
        validatePassword(req.getNewPassword());

        var token = passwordResetService.createToken(user);
        emailService.sendPasswordChangeConfirmationAsync(user.getEmail(), user.getName(), token.getToken())
                .exceptionally(ex -> {
                    log.error("Confirmation email failed for {}: {}", user.getEmail(), ex.getMessage());
                    return null;
                });
    }

    @Override
    @Transactional
    public void confirmPasswordChange(String tokenValue, String newPwd) {
        var token = passwordResetService.validateAndGetToken(tokenValue);
        var user  = token.getUser();

        validatePassword(newPwd);
        user.setPassword(passwordEncoder.encode(newPwd));
        userRepository.save(user);
        passwordResetService.markTokenAsUsed(token);

        emailService.sendPasswordChangedNotificationAsync(user.getEmail(), user.getName())
                .exceptionally(ex -> {
                    log.warn("Notification email failed: {}", ex.getMessage());
                    return null;
                });

        log.info("Password changed for user: {}", user.getEmail());
    }

    @Override
    @Transactional
    public void forgotPassword(String email) {
        // Silent fail: never reveal whether the email exists (security best practice)
        var optUser = userRepository.findByEmail(email);
        if (optUser.isEmpty()) {
            log.info("Forgot-password requested for unknown email: {}", email);
            return;
        }

        var user  = optUser.get();
        var token = passwordResetService.createToken(user);

        emailService.sendForgotPasswordEmailAsync(user.getEmail(), user.getName(), token.getToken())
                .exceptionally(ex -> {
                    log.error("Forgot-password email failed for {}: {}", user.getEmail(), ex.getMessage());
                    return null;
                });

        log.info("Forgot-password email queued for user: {}", user.getEmail());
    }

    @Override
    @Transactional
    public void resetPassword(String tokenValue, String newPwd) {
        var token = passwordResetService.validateAndGetToken(tokenValue);
        var user  = token.getUser();

        validatePassword(newPwd);
        user.setPassword(passwordEncoder.encode(newPwd));
        userRepository.save(user);
        passwordResetService.markTokenAsUsed(token);

        emailService.sendPasswordChangedNotificationAsync(user.getEmail(), user.getName())
                .exceptionally(ex -> {
                    log.warn("Notification email failed after reset: {}", ex.getMessage());
                    return null;
                });

        log.info("Password reset completed for user: {}", user.getEmail());
    }

    @Override
    @Transactional
    public String uploadProfilePicture(Long userId, MultipartFile file) {
        var user = findUserEntity(userId);
        validateImageFile(file);

        try {
            var uploadPath = Paths.get(uploadDir);
            Files.createDirectories(uploadPath);

            String ext      = extractExtension(file.getOriginalFilename());
            String filename = "user_%d_%s%s".formatted(userId, UUID.randomUUID(), ext);
            Path   filePath = uploadPath.resolve(filename);

            Files.copy(file.getInputStream(), filePath, StandardCopyOption.REPLACE_EXISTING);
            deleteOldPicture(user.getProfilePicture());

            // Store a WEB-SERVED absolute path. WebConfig maps "/uploads/**"
            // to file:uploads/, so the URL is simply "/" + the relative dir.
            // Storing the raw filesystem dir made browsers resolve the avatar
            // relative to the current page (e.g. /lms/student/uploads/...)
            // and every avatar surface fell back to initials.
            String cleanDir = uploadDir
                    .replace("\\", "/")
                    .replaceAll("^\\.?/?", "")
                    .replaceAll("/+$", "");
            String url = "/" + cleanDir + "/" + filename;
            user.setProfilePicture(url);
            User saved = userRepository.save(user);
            // Keep LMS/course and chat projections in sync immediately, so
            // participant lists can use the uploaded image without extra lookups.
            userSyncService.syncUser(saved);
            return url;

        } catch (IOException ex) {
            throw new RuntimeException("Failed to upload file: " + ex.getMessage(), ex);
        }
    }

    @Override
    @Transactional
    public void deleteUser(Long id) {
        var user = findUserEntity(id);
        deleteOldPicture(user.getProfilePicture());
        userRepository.deleteById(id);
        userSyncService.deleteUser(id)
                .exceptionally(ex -> {
                    log.warn("Cross-service cleanup failed for deleted user {}: {}", id, ex.getMessage());
                    return null;
                });
    }

    @Override
    @Transactional
    public UserResponse toggleActive(Long id) {
        var user = findUserEntity(id);
        user.setActive(!user.getActive());
        var saved = userRepository.save(user);
        log.info("User {} active status toggled to: {}", user.getEmail(), user.getActive());

        // Activating here bypasses approveUser(), the only other route that turns an
        // account usable. Without this the user can log in but holds no role in LMS.
        // Deactivation sends nothing: the sync payload has no active flag, and pushing
        // it would just recreate the account on the LMS side.
        if (Boolean.TRUE.equals(saved.getActive())) {
            userSyncService.syncUser(saved)
                    .exceptionally(ex -> {
                        log.error("LMS sync failed for activated user {}: {}",
                                  saved.getEmail(), ex.getMessage());
                        return null;
                    });
        }
        return UserResponse.fromEntity(saved);
    }

    @Override
    public List<UserResponse> getPendingUsers() {
        return userRepository.findByPendingApprovalTrue().stream()
                .map(UserResponse::fromEntity)
                .toList();
    }

    @Override
    @Transactional
    public UserResponse approveUser(Long id) {
        var user = findUserEntity(id);
        if (!user.getPendingApproval()) {
            throw new BadRequestException("User is not pending approval");
        }

        // Generate a random password and update the user
        String randomPassword = com.example.demo.utils.PasswordGenerator.generateStrongPassword();
        user.setPassword(passwordEncoder.encode(randomPassword));
        user.setActive(true);
        user.setPendingApproval(false);
        var saved = userRepository.save(user);

        // Send welcome email with the generated password
        emailService.sendWelcomeEmailAsync(user.getEmail(), user.getName(), randomPassword)
                .exceptionally(ex -> {
                    log.error("Welcome email failed for approved user {}: {}", user.getEmail(), ex.getMessage());
                    return null;
                });

        // Sync to LMS
        userSyncService.syncUser(saved)
                .exceptionally(ex -> {
                    log.error("LMS sync failed for approved user {}: {}", user.getEmail(), ex.getMessage());
                    return null;
                });

        log.info("User {} approved by admin", user.getEmail());
        return UserResponse.fromEntity(saved);
    }

    @Override
    @Transactional
    public UserResponse rejectUser(Long id) {
        var user = findUserEntity(id);
        if (!user.getPendingApproval()) {
            throw new BadRequestException("User is not pending approval");
        }

        user.setActive(false);
        user.setPendingApproval(false);
        var saved = userRepository.save(user);

        log.info("User {} rejected by admin (blocked)", user.getEmail());
        return UserResponse.fromEntity(saved);
    }

    // Helpers

    /** Entity-level lookup */
    private User findUserEntity(Long id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("User", id));
    }

    private void validatePassword(String pwd) {
        if (pwd == null || pwd.length() < 8) {
            throw new InvalidPasswordException("Mật khẩu phải có ít nhất 8 ký tự");
        }
        boolean hasUpper = pwd.chars().anyMatch(Character::isUpperCase);
        boolean hasLower = pwd.chars().anyMatch(Character::isLowerCase);
        boolean hasDigit = pwd.chars().anyMatch(Character::isDigit);

        if (!hasUpper || !hasLower || !hasDigit) {
            throw new InvalidPasswordException(
                    "Mật khẩu phải chứa ít nhất 1 chữ hoa, 1 chữ thường và 1 số");
        }
    }

    private void validateImageFile(MultipartFile file) {
        if (file.isEmpty()) {
            throw new BadRequestException("File is empty");
        }
        if (file.getSize() > MAX_PROFILE_PICTURE_BYTES) {
            throw new BadRequestException("Ảnh đại diện phải nhỏ hơn hoặc bằng 1 MB");
        }
        String ct = file.getContentType();
        if (ct == null || !ct.startsWith("image/")) {
            throw new BadRequestException("Only image files are allowed");
        }
    }

    private void deleteOldPicture(String path) {
        if (path == null || path.isBlank()) return;
        try {
            Files.deleteIfExists(Paths.get(path));
        } catch (IOException ex) {
            log.warn("Could not delete old profile picture [{}]: {}", path, ex.getMessage());
        }
    }

    private String extractExtension(String filename) {
        if (filename != null && filename.contains(".")) {
            return filename.substring(filename.lastIndexOf('.'));
        }
        return ".jpg";
    }

    @Override
    @org.springframework.transaction.annotation.Transactional(readOnly = true)
    public void syncAllUsersToChat() {
        var users = userRepository.findAll();
        userSyncService.syncUsersToChat(users)
                .exceptionally(ex -> {
                    log.error("Manual bulk chat sync failed: {}", ex.getMessage());
                    return null;
                });
    }
}
