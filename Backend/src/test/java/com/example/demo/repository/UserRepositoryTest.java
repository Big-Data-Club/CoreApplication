package com.example.demo.repository;

import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@ActiveProfiles("test")
class UserRepositoryTest {

    @Autowired
    private UserRepository userRepository;

    @BeforeEach
    void setUp() {
        User user = User.builder()
                .name("Test User")
                .email("test@example.com")
                .password("encrypted_password")
                .role(UserRole.ROLE_USER)
                .team(UserTeam.RESEARCH)
                .code("CODE001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();
        userRepository.save(user);
    }

    @Test
    void testSaveUser_Success() {
        User user = User.builder()
                .name("New User")
                .email("newuser@example.com")
                .password("encrypted_password")
                .role(UserRole.ROLE_USER)
                .team(UserTeam.EVENT)
                .code("CODE002")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build();

        User saved = userRepository.save(user);

        assertNotNull(saved.getId());
        assertEquals("New User", saved.getName());
        assertEquals("newuser@example.com", saved.getEmail());
    }

    @Test
    void testFindById_Success() {
        User user = userRepository.findByEmail("test@example.com").get();

        Optional<User> found = userRepository.findById(user.getId());

        assertTrue(found.isPresent());
        assertEquals("Test User", found.get().getName());
    }

    @Test
    void testFindByEmail_Success() {
        Optional<User> found = userRepository.findByEmail("test@example.com");

        assertTrue(found.isPresent());
        assertEquals("Test User", found.get().getName());
        assertEquals("test@example.com", found.get().getEmail());
    }

    @Test
    void testFindByEmail_NotFound() {
        Optional<User> found = userRepository.findByEmail("nonexistent@example.com");

        assertFalse(found.isPresent());
    }

    @Test
    void testFindByEmail_ReturnsCorrectCode() {
        Optional<User> found = userRepository.findByEmail("test@example.com");

        assertTrue(found.isPresent());
        assertEquals("CODE001", found.get().getCode());
    }

    @Test
    void testFindByEmail_CodeMismatch() {
        Optional<User> found = userRepository.findByEmail("test@example.com");

        assertTrue(found.isPresent());
        assertNotEquals("NONEXISTENT", found.get().getCode());
    }

    @Test
    void testExistsByEmail_True() {
        boolean exists = userRepository.existsByEmail("test@example.com");

        assertTrue(exists);
    }

    @Test
    void testExistsByEmail_False() {
        boolean exists = userRepository.existsByEmail("nonexistent@example.com");

        assertFalse(exists);
    }

    @Test
    void testFindByEmail_VerifyRole() {
        User admin = User.builder()
                .name("Admin")
                .email("admin@example.com")
                .password("encrypted_password")
                .role(UserRole.ROLE_ADMIN)
                .team(UserTeam.RESEARCH)
                .code("ADMIN001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();
        userRepository.save(admin);

        Optional<User> found = userRepository.findByEmail("admin@example.com");

        assertTrue(found.isPresent());
        assertEquals(UserRole.ROLE_ADMIN, found.get().getRole());
    }

    @Test
    void testDelete_Success() {
        User user = userRepository.findByEmail("test@example.com").get();

        userRepository.delete(user);

        assertFalse(userRepository.existsById(user.getId()));
    }

    @Test
    void testUpdate_Success() {
        User user = userRepository.findByEmail("test@example.com").get();

        user.setName("Updated Name");
        user.setTotalScore(100);
        user.setActive(false);

        User updated = userRepository.save(user);

        assertEquals("Updated Name", updated.getName());
        assertEquals(100, updated.getTotalScore());
        assertFalse(updated.getActive());
    }
}
