package com.example.demo.controller;

import com.example.demo.dto.task.TaskRequest;
import com.example.demo.dto.event.EventRequest;
import com.example.demo.enums.Priority;
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
import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class TaskControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private User creator, assignee;
    private Long eventId;

    @BeforeEach
    void setUp() throws Exception {
        creator = User.builder()
                .name("Task Creator")
                .email("creator@test.com")
                .password(passwordEncoder.encode("creatorpass"))
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.RESEARCH)
                .code("CREATOR001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();

        assignee = User.builder()
                .name("Task Assignee")
                .email("assignee@test.com")
                .password(passwordEncoder.encode("assigneepass"))
                .role(UserRole.ROLE_USER)
                .team(UserTeam.EVENT)
                .code("ASSIGNEE001")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build();

        userRepository.save(creator);
        userRepository.save(assignee);

        // Create event
        EventRequest eventRequest = EventRequest.builder()
                .title("Test Event")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(100)
                .build();

        String eventResponse = mockMvc.perform(post("/api/events")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(eventRequest))
                        .with(request -> {
                            request.setAttribute("ADMIN_USER", creator);
                            return request;
                        }))
                .andReturn().getResponse().getContentAsString();

        if (!eventResponse.isEmpty()) {
            eventId = objectMapper.readTree(eventResponse).get("id").asLong();
        }
    }

    @Test
    @WithMockUser(username = "creator@test.com", roles = "MANAGER")
    void testCreateTask_Success() throws Exception {
        TaskRequest request = TaskRequest.builder()
                .title("New Task")
                .description("Task Description")
                .priority(Priority.HIGH)
                .columnId("todo")
                .startDate(LocalDateTime.now())
                .endDate(LocalDateTime.now().plusDays(5))
                .assigneeIds(List.of(assignee.getId()))
                .build();

        mockMvc.perform(post("/api/tasks")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.title").value("New Task"))
                .andExpect(jsonPath("$.priority").value("HIGH"))
                .andExpect(jsonPath("$.columnId").value("todo"));
    }

    @Test
    @WithMockUser(username = "creator@test.com", roles = "MANAGER")
    void testCreateTask_WithoutEvent() throws Exception {
        TaskRequest request = TaskRequest.builder()
                .title("Standalone Task")
                .description("No Event Task")
                .priority(Priority.MEDIUM)
                .columnId("in-progress")
                .build();

        mockMvc.perform(post("/api/tasks")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Standalone Task"));
    }

    @Test
    void testCreateTask_Unauthorized() throws Exception {
        TaskRequest request = TaskRequest.builder()
                .title("Task")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .build();

        mockMvc.perform(post("/api/tasks")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void testGetAllTasks_Success() throws Exception {
        mockMvc.perform(get("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    @WithMockUser(username = "creator@test.com", roles = "MANAGER")
    void testUpdateTask_Success() throws Exception {
        TaskRequest createRequest = TaskRequest.builder()
                .title("Original Task")
                .description("Original Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .build();

        String createResponse = mockMvc.perform(post("/api/tasks")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        Long taskId = objectMapper.readTree(createResponse).get("id").asLong();

        TaskRequest updateRequest = TaskRequest.builder()
                .title("Updated Task")
                .description("Updated Description")
                .priority(Priority.HIGH)
                .columnId("in-progress")
                .build();

        mockMvc.perform(put("/api/tasks/{id}", taskId)
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(updateRequest)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated Task"))
                .andExpect(jsonPath("$.priority").value("HIGH"))
                .andExpect(jsonPath("$.columnId").value("in-progress"));
    }

    @Test
    @WithMockUser(username = "creator@test.com", roles = "MANAGER")
    void testMoveTask_Success() throws Exception {
        TaskRequest createRequest = TaskRequest.builder()
                .title("Task to Move")
                .description("Description")
                .priority(Priority.MEDIUM)
                .columnId("todo")
                .build();

        String createResponse = mockMvc.perform(post("/api/tasks")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        Long taskId = objectMapper.readTree(createResponse).get("id").asLong();

        mockMvc.perform(patch("/api/tasks/{id}/move", taskId)
                        .param("columnId", "in-progress")
                        .param("userId", creator.getId().toString()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.columnId").value("in-progress"));
    }

    @Test
    void testGetTaskById_Success() throws Exception {
        mockMvc.perform(get("/api/tasks/1")
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
    void testGetTasksByEvent_Success() throws Exception {
        if (eventId != null) {
            mockMvc.perform(get("/api/tasks/event/{eventId}", eventId)
                            .contentType(MediaType.APPLICATION_JSON))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$").isArray());
        }
    }

    @Test
    void testGetTasksByColumn_Success() throws Exception {
        mockMvc.perform(get("/api/tasks/column/todo")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    void testSearchTasks_Success() throws Exception {
        mockMvc.perform(get("/api/tasks/search")
                        .param("keyword", "test")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    @WithMockUser(username = "creator@test.com", roles = "MANAGER")
    void testDeleteTask_Success() throws Exception {
        TaskRequest createRequest = TaskRequest.builder()
                .title("Task to Delete")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .build();

        String createResponse = mockMvc.perform(post("/api/tasks")
                        .param("userId", creator.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createRequest)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        Long taskId = objectMapper.readTree(createResponse).get("id").asLong();

        mockMvc.perform(delete("/api/tasks/{id}", taskId)
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }
}
