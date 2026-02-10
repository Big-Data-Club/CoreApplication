package com.example.demo.controller;

import com.example.demo.dto.announcement.AnnouncementRequest;
import com.example.demo.enums.StatusPermission;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class AnnouncementControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private User admin, manager, user;

    @BeforeEach
    void setUp() {
        admin = User.builder()
                .name("Admin")
                .email("admin@test.com")
                .password(passwordEncoder.encode("adminpass"))
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
                .password(passwordEncoder.encode("managerpass"))
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.ENGINEER)
                .code("MANAGER001")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build();

        user = User.builder()
                .name("Regular User")
                .email("user@test.com")
                .password(passwordEncoder.encode("userpass"))
                .role(UserRole.ROLE_USER)
                .team(UserTeam.EVENT)
                .code("USER001")
                .type(UserType.CLC)
                .active(true)
                .totalScore(0)
                .build();

        userRepository.save(admin);
        userRepository.save(manager);
        userRepository.save(user);
    }

    @Test
    void testGetAllAnnouncements_Success() throws Exception {
        mockMvc.perform(get("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    void testGetAnnouncementById_Success() throws Exception {
        mockMvc.perform(get("/api/announcements/1")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(result -> {
                    int statusCode = result.getResponse().getStatus();
                    org.junit.jupiter.api.Assertions.assertTrue(
                        statusCode == 404 || statusCode == 200,
                        "Expected status 404 or 200 but got " + statusCode
                    );
                });
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testCreateAnnouncement_ByAdmin() throws Exception {
        AnnouncementRequest request = AnnouncementRequest.builder()
                .title("Important Announcement")
                .content("This is an important announcement")
                .images(List.of("image1.jpg", "image2.jpg"))
                .status(StatusPermission.APPROVED)
                .build();

        mockMvc.perform(post("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.title").value("Important Announcement"))
                .andExpect(jsonPath("$.content").value("This is an important announcement"))
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    @Test
    @WithMockUser(username = "manager@test.com", roles = "MANAGER")
    void testCreateAnnouncement_ByManager() throws Exception {
        AnnouncementRequest request = AnnouncementRequest.builder()
                .title("Manager Announcement")
                .content("Announcement from manager")
                .images(List.of())
                .status(StatusPermission.PENDING)
                .build();

        mockMvc.perform(post("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Manager Announcement"));
    }

    @Test
    @WithMockUser(username = "user@test.com", roles = "USER")
    void testCreateAnnouncement_UnauthorizedForUser() throws Exception {
        AnnouncementRequest request = AnnouncementRequest.builder()
                .title("User Announcement")
                .content("User trying to create")
                .status(StatusPermission.PENDING)
                .build();

        mockMvc.perform(post("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden());
    }

    @Test
    void testCreateAnnouncement_Unauthorized() throws Exception {
        AnnouncementRequest request = AnnouncementRequest.builder()
                .title("Announcement")
                .content("Content")
                .status(StatusPermission.PENDING)
                .build();

        mockMvc.perform(post("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testUpdateAnnouncement_Success() throws Exception {
        AnnouncementRequest createRequest = AnnouncementRequest.builder()
                .title("Original Title")
                .content("Original Content")
                .status(StatusPermission.PENDING)
                .build();

        String createResponse = mockMvc.perform(post("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Long announcementId = objectMapper.readTree(createResponse).get("id").asLong();

        AnnouncementRequest updateRequest = AnnouncementRequest.builder()
                .title("Updated Title")
                .content("Updated Content")
                .images(List.of("new_image.jpg"))
                .status(StatusPermission.APPROVED)
                .build();

        mockMvc.perform(put("/api/announcements/{id}", announcementId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(updateRequest)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated Title"))
                .andExpect(jsonPath("$.content").value("Updated Content"))
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testDeleteAnnouncement_Success() throws Exception {
        AnnouncementRequest createRequest = AnnouncementRequest.builder()
                .title("To Delete")
                .content("Content")
                .status(StatusPermission.APPROVED)
                .build();

        String createResponse = mockMvc.perform(post("/api/announcements")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Long announcementId = objectMapper.readTree(createResponse).get("id").asLong();

        mockMvc.perform(delete("/api/announcements/{id}", announcementId)
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNoContent());
    }
}
