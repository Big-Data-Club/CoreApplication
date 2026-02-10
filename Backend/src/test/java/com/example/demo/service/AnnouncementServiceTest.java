package com.example.demo.service;

import com.example.demo.dto.announcement.AnnouncementRequest;
import com.example.demo.dto.announcement.AnnouncementResponse;
import com.example.demo.enums.StatusPermission;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.mapper.AnnouncementMapper;
import com.example.demo.model.Announcement;
import com.example.demo.model.User;
import com.example.demo.repository.AnnouncementRepository;
import com.example.demo.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@Import({AnnouncementService.class, AnnouncementMapper.class})
@ActiveProfiles("test")
@Transactional
class AnnouncementServiceTest {

    @Autowired
    private AnnouncementService announcementService;

    @Autowired
    private AnnouncementRepository announcementRepository;

    @Autowired
    private UserRepository userRepository;

    private User admin, manager;

    @BeforeEach
    void setUp() {
        admin = User.builder()
                .name("Admin")
                .email("admin@test.com")
                .password("password")
                .role(UserRole.ROLE_ADMIN)
                .team(UserTeam.RESEARCH)
                .code("ADMIN001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();

        manager = User.builder()
                .name("Manager")
                .email("manager@test.com")
                .password("password")
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.ENGINEER)
                .code("MANAGER001")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build();

        userRepository.save(admin);
        userRepository.save(manager);
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testCreateAnnouncement_Success() {
        AnnouncementRequest request = AnnouncementRequest.builder()
                .title("Test Announcement")
                .content("Test content")
                .images(List.of("image1.jpg", "image2.jpg"))
                .status(StatusPermission.APPROVED)
                .build();

        AnnouncementResponse response = announcementService.create(request);

        assertNotNull(response);
        assertNotNull(response.getId());
        assertEquals("Test Announcement", response.getTitle());
        assertEquals("Test content", response.getContent());
        assertEquals(StatusPermission.APPROVED, response.getStatus());
    }

    @Test
    @WithMockUser(username = "manager@test.com", roles = "MANAGER")
    void testUpdateAnnouncement_Success() {
        Announcement announcement = Announcement.builder()
                .title("Original Title")
                .content("Original Content")
                .images(List.of("image1.jpg"))
                .status(StatusPermission.PENDING)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();
        announcementRepository.save(announcement);

        AnnouncementRequest updateRequest = AnnouncementRequest.builder()
                .title("Updated Title")
                .content("Updated Content")
                .images(List.of("image1.jpg", "image2.jpg", "image3.jpg"))
                .status(StatusPermission.APPROVED)
                .build();

        AnnouncementResponse response = announcementService.update(announcement.getId(), updateRequest);

        assertEquals("Updated Title", response.getTitle());
        assertEquals("Updated Content", response.getContent());
        assertEquals(3, response.getImages().size());
        assertEquals(StatusPermission.APPROVED, response.getStatus());
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testUpdateAnnouncement_NotFound() {
        AnnouncementRequest request = AnnouncementRequest.builder()
                .title("Title")
                .content("Content")
                .status(StatusPermission.PENDING)
                .build();

        assertThrows(Exception.class, () -> announcementService.update(999L, request));
    }

    @Test
    void testGetAnnouncementById_Success() {
        Announcement announcement = Announcement.builder()
                .title("Get Announcement")
                .content("Content")
                .images(List.of())
                .status(StatusPermission.APPROVED)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();
        announcementRepository.save(announcement);

        AnnouncementResponse response = announcementService.getById(announcement.getId());

        assertNotNull(response);
        assertEquals("Get Announcement", response.getTitle());
    }

    @Test
    void testGetAnnouncementById_NotFound() {
        assertThrows(Exception.class, () -> announcementService.getById(999L));
    }

    @Test
    void testGetAllAnnouncements_Success() {
        Announcement ann1 = Announcement.builder()
                .title("Announcement 1")
                .content("Content 1")
                .status(StatusPermission.APPROVED)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();

        Announcement ann2 = Announcement.builder()
                .title("Announcement 2")
                .content("Content 2")
                .status(StatusPermission.PENDING)
                .createdBy(manager)
                .createdAt(LocalDateTime.now())
                .build();

        announcementRepository.save(ann1);
        announcementRepository.save(ann2);

        List<AnnouncementResponse> responses = announcementService.getAll();

        assertEquals(2, responses.size());
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testDeleteAnnouncement_Success() {
        Announcement announcement = Announcement.builder()
                .title("To Delete")
                .content("Content")
                .status(StatusPermission.APPROVED)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();
        announcementRepository.save(announcement);

        announcementService.delete(announcement.getId());

        assertFalse(announcementRepository.existsById(announcement.getId()));
    }
}
