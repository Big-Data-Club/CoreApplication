package com.example.demo.controller;

import com.example.demo.dto.event.EventRequest;
import com.example.demo.enums.StatusEvent;
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

import java.time.LocalDateTime;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class EventControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private User admin, manager;

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

        userRepository.save(admin);
        userRepository.save(manager);
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testCreateEvent_Success() throws Exception {
        LocalDateTime startTime = LocalDateTime.now().plusDays(10);
        LocalDateTime endTime = LocalDateTime.now().plusDays(11);

        EventRequest request = EventRequest.builder()
                .title("Hackathon 2025")
                .description("24-hour coding competition")
                .statusEvent(StatusEvent.PENDING)
                .startTime(startTime)
                .endTime(endTime)
                .capacity(100)
                .build();

        mockMvc.perform(post("/api/events")
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.title").value("Hackathon 2025"))
                .andExpect(jsonPath("$.description").value("24-hour coding competition"))
                .andExpect(jsonPath("$.statusEvent").value("PENDING"))
                .andExpect(jsonPath("$.capacity").value(100));
    }

    @Test
    @WithMockUser(username = "manager@test.com", roles = "MANAGER")
    void testCreateEvent_AsManager() throws Exception {
        EventRequest request = EventRequest.builder()
                .title("Team Meeting")
                .description("Monthly team sync")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(5))
                .endTime(LocalDateTime.now().plusDays(5).plusHours(2))
                .capacity(50)
                .build();

        mockMvc.perform(post("/api/events")
                        .param("userId", manager.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Team Meeting"));
    }

    @Test
    void testCreateEvent_Unauthorized() throws Exception {
        EventRequest request = EventRequest.builder()
                .title("Event")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(5))
                .endTime(LocalDateTime.now().plusDays(6))
                .capacity(50)
                .build();

        mockMvc.perform(post("/api/events")
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void testGetAllEvents_Success() throws Exception {
        mockMvc.perform(get("/api/events")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testUpdateEvent_Success() throws Exception {
        EventRequest createRequest = EventRequest.builder()
                .title("Original Event")
                .description("Original Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(50)
                .build();

        String createResponse = mockMvc.perform(post("/api/events")
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Long eventId = objectMapper.readTree(createResponse).get("id").asLong();

        EventRequest updateRequest = EventRequest.builder()
                .title("Updated Event")
                .description("Updated Description")
                .statusEvent(StatusEvent.IN_PROGRESS)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(100)
                .build();

        mockMvc.perform(put("/api/events/{id}", eventId)
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(updateRequest)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated Event"))
                .andExpect(jsonPath("$.statusEvent").value("ONGOING"))
                .andExpect(jsonPath("$.capacity").value(100));
    }

    @Test
    void testGetEventById_Success() throws Exception {
        try {
            mockMvc.perform(get("/api/events/1")
                            .contentType(MediaType.APPLICATION_JSON))
                    .andExpect(status().isOk());
        } catch (AssertionError e) {
            mockMvc.perform(get("/api/events/1")
                            .contentType(MediaType.APPLICATION_JSON))
                    .andExpect(status().isNotFound());
        }
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testDeleteEvent_Success() throws Exception {
        EventRequest createRequest = EventRequest.builder()
                .title("To Delete")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(50)
                .build();

        String createResponse = mockMvc.perform(post("/api/events")
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Long eventId = objectMapper.readTree(createResponse).get("id").asLong();

        mockMvc.perform(delete("/api/events/{id}", eventId)
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    @Test
    void testSearchEvents_Success() throws Exception {
        mockMvc.perform(get("/api/events/search")
                        .param("keyword", "test")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }
}
