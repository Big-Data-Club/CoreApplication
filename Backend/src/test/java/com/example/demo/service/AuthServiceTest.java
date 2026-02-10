package com.example.demo.service;

import com.example.demo.dto.auth.BulkRegisterRequest;
import com.example.demo.dto.auth.LoginRequest;
import com.example.demo.dto.auth.RegisterRequest;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@Import({AuthService.class, JwtService.class, BCryptPasswordEncoder.class})
@ActiveProfiles("test")
@Transactional
class AuthServiceTest {

    @Autowired
    private AuthService authService;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private User testUser;

    @BeforeEach
    void setUp() {
        testUser = User.builder()
                .name("Test User")
                .email("test@example.com")
                .password(passwordEncoder.encode("password123"))
                .role(UserRole.ROLE_USER)
                .team(UserTeam.RESEARCH)
                .code("CODE001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();
        userRepository.save(testUser);
    }

    @Test
    void testAuthenticate_Success() {
        LoginRequest request = LoginRequest.builder()
                .email("test@example.com")
                .password("password123")
                .build();

        User authenticatedUser = authService.authenticate(request);

        assertNotNull(authenticatedUser);
        assertEquals("test@example.com", authenticatedUser.getEmail());
        assertEquals("Test User", authenticatedUser.getName());
    }

    @Test
    void testAuthenticate_UserNotFound() {
        LoginRequest request = LoginRequest.builder()
                .email("nonexistent@example.com")
                .password("password123")
                .build();

        assertThrows(RuntimeException.class, () -> authService.authenticate(request));
    }

    @Test
    void testAuthenticate_InvalidPassword() {
        LoginRequest request = LoginRequest.builder()
                .email("test@example.com")
                .password("wrongpassword")
                .build();

        assertThrows(RuntimeException.class, () -> authService.authenticate(request));
    }

    @Test
    void testGenerateToken_Success() {
        String token = authService.generateToken(testUser);

        assertNotNull(token);
        assertFalse(token.isEmpty());
    }

    @Test
    void testBulkRegister_Success() {
        RegisterRequest user1 = RegisterRequest.builder()
                .name("User 1")
                .email("user1@example.com")
                .role(UserRole.ROLE_USER)
                .team(UserTeam.EVENT)
                .code("CODE002")
                .type(UserType.TN)
                .build();

        RegisterRequest user2 = RegisterRequest.builder()
                .name("User 2")
                .email("user2@example.com")
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.ENGINEER)
                .code("CODE003")
                .type(UserType.CLC)
                .build();

        BulkRegisterRequest request = BulkRegisterRequest.builder()
                .users(List.of(user1, user2))
                .build();

        List<User> registeredUsers = authService.bulkRegister(request);

        assertEquals(2, registeredUsers.size());
        assertTrue(registeredUsers.stream().anyMatch(u -> u.getEmail().equals("user1@example.com")));
        assertTrue(registeredUsers.stream().anyMatch(u -> u.getEmail().equals("user2@example.com")));
    }

    @Test
    void testBulkRegister_DuplicateEmail() {
        RegisterRequest user1 = RegisterRequest.builder()
                .name("Duplicate User")
                .email("test@example.com")
                .role(UserRole.ROLE_USER)
                .team(UserTeam.RESEARCH)
                .code("CODE999")
                .type(UserType.DT)
                .build();

        BulkRegisterRequest request = BulkRegisterRequest.builder()
                .users(List.of(user1))
                .build();

        assertThrows(RuntimeException.class, () -> authService.bulkRegister(request));
    }

    @Test
    void testBulkRegister_AssignsDefaultPassword() {
        RegisterRequest user = RegisterRequest.builder()
                .name("Default Pass User")
                .email("defaultpass@example.com")
                .role(UserRole.ROLE_USER)
                .team(UserTeam.RESEARCH)
                .code("CODE004")
                .type(UserType.DT)
                .build();

        BulkRegisterRequest request = BulkRegisterRequest.builder()
                .users(List.of(user))
                .build();

        List<User> registered = authService.bulkRegister(request);

        assertEquals(1, registered.size());
        assertTrue(passwordEncoder.matches("password123", registered.get(0).getPassword()));
    }
}
