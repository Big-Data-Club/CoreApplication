package com.example.demo.service;

import com.example.demo.dto.auth.BulkRegisterRequest;
import com.example.demo.dto.auth.LoginRequest;
import com.example.demo.enums.UserRole;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.example.demo.utils.PasswordGenerator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class AuthService {
    private final UserRepository userRepository;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;
    private final UserSyncService userSyncService;

    public User authenticate(LoginRequest request) {
        User user = userRepository.findByEmail(request.getEmail())
                .orElseThrow(() -> new RuntimeException("User not found"));

        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new RuntimeException("Invalid credentials");
        }

        return user;
    }

    public String generateToken(User user) {
        return jwtService.generateToken(user.getId(), user.getEmail(), user.getRole().name());
    }

    @Transactional
    public List<User> bulkRegister(BulkRegisterRequest request) {
        List<User> createdUsers = new ArrayList<>();
        Map<User, String> userPasswordMap = new HashMap<>();
        
        for (var reg : request.getUsers()) {
            if (userRepository.existsByEmail(reg.getEmail())) {
                throw new RuntimeException("Email already exists: " + reg.getEmail());
            }

            String randomPassword = PasswordGenerator.generateStrongPassword();
            
            User user = User.builder()
                    .name(reg.getName())
                    .email(reg.getEmail())
                    .password(passwordEncoder.encode(randomPassword))
                    .role(reg.getRole() == null ? UserRole.ROLE_USER : reg.getRole())
                    .team(reg.getTeam())
                    .code(reg.getCode())
                    .type(reg.getType())
                    .active(true)
                    .totalScore(0)
                    .build();

            User savedUser = userRepository.save(user);
            createdUsers.add(savedUser);
            userPasswordMap.put(savedUser, randomPassword);
            
            log.info("Created user: {} with email: {}", savedUser.getName(), savedUser.getEmail());
        }
        
        userPasswordMap.forEach((user, password) -> {
            try {
                emailService.sendWelcomeEmail(user.getEmail(), user.getName(), password);
                log.info("Welcome email sent to: {}", user.getEmail());
            } catch (Exception e) {
                log.error("Failed to send email to: {}", user.getEmail(), e);
            }
        });
        
        try {
            userSyncService.syncUsersToLms(createdUsers);
            log.info("Initiated sync of {} users to LMS", createdUsers.size());
        } catch (Exception e) {
            log.error("Failed to initiate LMS sync: {}", e.getMessage());
        }
        
        return createdUsers;
    }
}