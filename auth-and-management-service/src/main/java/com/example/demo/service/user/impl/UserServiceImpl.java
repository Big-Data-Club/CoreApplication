package com.example.demo.service.user.impl;

import com.example.demo.dto.auth.PasswordChangeRequest;
import com.example.demo.dto.user.UpdateUserRequest;
import com.example.demo.dto.user.UserResponse;
import com.example.demo.exception.BadRequestException;
import com.example.demo.exception.InvalidPasswordException;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.email.EmailService;
import com.example.demo.service.user.PasswordResetService;
import com.example.demo.service.user.UserService;
import com.example.demo.service.user.UserSyncService;
import com.example.demo.enums.UserRole;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.*;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserServiceImpl implements UserService {

    private final UserRepository     userRepository;
    private final PasswordEncoder    passwordEncoder;
    private final EmailService       emailService;
    private final PasswordResetService passwordResetService;
    private final UserSyncService    userSyncService;

    @Value("${app.upload.dir:uploads/profiles/}")
    private String uploadDir;

    // Reads

    @Override
    public List<UserResponse> getAllUsers() {
        return userRepository.findAll().stream()
                .map(UserResponse::fromEntity)
                .toList();
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
        var saved = userRepository.save(user);
        userSyncService.syncUser(saved);
        return UserResponse.fromEntity(saved);
    }

    @Override
    @Transactional
    public UserResponse updateRole(Long id, UserRole role) {
        var user = findUserEntity(id);
        user.setRole(role);
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

            String url = uploadDir + filename;
            user.setProfilePicture(url);
            userRepository.save(user);
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
    }

    @Override
    @Transactional
    public UserResponse toggleActive(Long id) {
        var user = findUserEntity(id);
        user.setActive(!user.getActive());
        var saved = userRepository.save(user);
        log.info("User {} active status toggled to: {}", user.getEmail(), user.getActive());
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
}
