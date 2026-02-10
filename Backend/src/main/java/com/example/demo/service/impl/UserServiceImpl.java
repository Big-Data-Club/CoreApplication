package com.example.demo.service.impl;

import com.example.demo.dto.auth.PasswordChangeRequest;
import com.example.demo.model.PasswordResetToken;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.EmailService;
import com.example.demo.service.PasswordResetService;
import com.example.demo.service.UserService;
import com.example.demo.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserServiceImpl implements UserService {
    
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;
    private final PasswordResetService passwordResetService;
    
    private static final String UPLOAD_DIR = "uploads/profiles/";

    @Override
    public List<User> getAllUsers() {
        return userRepository.findAll();
    }

    @Override
    public User getUserById(Long id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with id: " + id));
    }
    
    @Override
    public User getUserByEmail(String email) {
        return userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with email: " + email));
    }

    @Override
    @Transactional
    public User updateUser(Long id, User userDetails) {
        User user = getUserById(id);
        
        user.setName(userDetails.getName());
        user.setEmail(userDetails.getEmail());
        
        if (userDetails.getTeam() != null) {
            user.setTeam(userDetails.getTeam());
        }
        if (userDetails.getType() != null) {
            user.setType(userDetails.getType());
        }
        if (userDetails.getProfilePicture() != null) {
            user.setProfilePicture(userDetails.getProfilePicture());
        }
        
        return userRepository.save(user);
    }

    @Override
    @Transactional
    public void changePassword(Long userId, String currentPassword, String newPassword) {
        User user = getUserById(userId);
        
        if (!passwordEncoder.matches(currentPassword, user.getPassword())) {
            throw new IllegalArgumentException("Current password is incorrect");
        }
        
        validatePassword(newPassword);
        
        user.setPassword(passwordEncoder.encode(newPassword));
        userRepository.save(user);
        
        // Gửi email thông báo
        try {
            emailService.sendPasswordChangedNotification(user.getEmail(), user.getName());
        } catch (Exception e) {
            log.error("Failed to send password changed notification", e);
        }
    }
    
    @Override
    @Transactional
    public void requestPasswordChange(PasswordChangeRequest request) {
        User user = getUserByEmail(request.getEmail());
        
        if (!passwordEncoder.matches(request.getCurrentPassword(), user.getPassword())) {
            throw new IllegalArgumentException("Mật khẩu hiện tại không đúng");
        }
        
        validatePassword(request.getNewPassword());
        
        PasswordResetToken token = passwordResetService.createToken(user);
        
        emailService.sendPasswordChangeConfirmation(
            user.getEmail(), 
            user.getName(), 
            token.getToken()
        );
        
        log.info("Password change requested for user: {}", user.getEmail());
    }
    
    @Override
    @Transactional
    public void confirmPasswordChange(String tokenValue, String newPassword) {
        PasswordResetToken token = passwordResetService.validateAndGetToken(tokenValue);
        User user = token.getUser();
        
        validatePassword(newPassword);
        
        user.setPassword(passwordEncoder.encode(newPassword));
        userRepository.save(user);
        
        passwordResetService.markTokenAsUsed(token);
        
        emailService.sendPasswordChangedNotification(user.getEmail(), user.getName());
        
        log.info("Password changed successfully for user: {}", user.getEmail());
    }
    
    private void validatePassword(String password) {
        if (password == null || password.length() < 8) {
            throw new IllegalArgumentException("Mật khẩu phải có ít nhất 8 ký tự");
        }
        
        boolean hasUpper = password.chars().anyMatch(Character::isUpperCase);
        boolean hasLower = password.chars().anyMatch(Character::isLowerCase);
        boolean hasDigit = password.chars().anyMatch(Character::isDigit);
        
        if (!hasUpper || !hasLower || !hasDigit) {
            throw new IllegalArgumentException(
                "Mật khẩu phải chứa ít nhất 1 chữ hoa, 1 chữ thường và 1 số"
            );
        }
    }

    @Override
    @Transactional
    public String uploadProfilePicture(Long userId, MultipartFile file) {
        User user = getUserById(userId);
        
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File is empty");
        }
        
        String contentType = file.getContentType();
        if (contentType == null || !contentType.startsWith("image/")) {
            throw new IllegalArgumentException("Only image files are allowed");
        }
        
        try {
            Path uploadPath = Paths.get(UPLOAD_DIR);
            if (!Files.exists(uploadPath)) {
                Files.createDirectories(uploadPath);
            }
            
            String originalFilename = file.getOriginalFilename();
            String extension = originalFilename != null && originalFilename.contains(".") 
                ? originalFilename.substring(originalFilename.lastIndexOf("."))
                : ".jpg";
            String filename = "user_" + userId + "_" + UUID.randomUUID() + extension;
            
            Path filePath = uploadPath.resolve(filename);
            Files.copy(file.getInputStream(), filePath, StandardCopyOption.REPLACE_EXISTING);
            
            if (user.getProfilePicture() != null && !user.getProfilePicture().isEmpty()) {
                try {
                    Path oldFilePath = Paths.get(user.getProfilePicture());
                    Files.deleteIfExists(oldFilePath);
                } catch (IOException e) {
                    log.error("Failed to delete old profile picture: {}", e.getMessage());
                }
            }
            
            String pictureUrl = UPLOAD_DIR + filename;
            user.setProfilePicture(pictureUrl);
            userRepository.save(user);
            
            return pictureUrl;
            
        } catch (IOException e) {
            throw new RuntimeException("Failed to upload file: " + e.getMessage());
        }
    }

    @Override
    @Transactional
    public void deleteUser(Long id) {
        User user = getUserById(id);
        
        if (user.getProfilePicture() != null && !user.getProfilePicture().isEmpty()) {
            try {
                Path filePath = Paths.get(user.getProfilePicture());
                Files.deleteIfExists(filePath);
            } catch (IOException e) {
                log.error("Failed to delete profile picture: {}", e.getMessage());
            }
        }
        
        userRepository.deleteById(id);
    }
}