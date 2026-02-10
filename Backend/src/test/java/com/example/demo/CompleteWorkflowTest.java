package com.example.demo;

import com.example.demo.dto.event.EventRequest;
import com.example.demo.dto.task.TaskRequest;
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
class CompleteWorkflowTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private User admin, manager, user1, user2;

    @BeforeEach
    void setUp() {
        admin = userRepository.save(User.builder()
                .name("Admin")
                .email("admin@test.com")
                .password(passwordEncoder.encode("pass"))
                .role(UserRole.ROLE_ADMIN)
                .team(UserTeam.RESEARCH)
                .code("ADMIN001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build());

        manager = userRepository.save(User.builder()
                .name("Manager")
                .email("manager@test.com")
                .password(passwordEncoder.encode("pass"))
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.ENGINEER)
                .code("MANAGER001")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build());

        user1 = userRepository.save(User.builder()
                .name("User1")
                .email("user1@test.com")
                .password(passwordEncoder.encode("pass"))
                .role(UserRole.ROLE_USER)
                .team(UserTeam.EVENT)
                .code("USER001")
                .type(UserType.CLC)
                .active(true)
                .totalScore(0)
                .build());

        user2 = userRepository.save(User.builder()
                .name("User2")
                .email("user2@test.com")
                .password(passwordEncoder.encode("pass"))
                .role(UserRole.ROLE_USER)
                .team(UserTeam.RESEARCH)
                .code("USER002")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build());
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testCompleteWorkflow_CreateEventAndTasks() throws Exception {
        // Step 1: Admin creates event
        EventRequest eventRequest = EventRequest.builder()
                .title("Hackathon 2025")
                .description("24-hour coding competition")
                .statusEvent(StatusEvent.PENDING)
                .capacity(100)
                .startTime(LocalDateTime.now().plusDays(30))
                .endTime(LocalDateTime.now().plusDays(31))
                .build();

        String eventResponse = mockMvc.perform(post("/api/events")
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(eventRequest)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Long eventId = objectMapper.readTree(eventResponse).get("id").asLong();

        // Step 2: Manager creates task in event with assignees
        TaskRequest taskRequest = TaskRequest.builder()
                .title("Build Mobile App")
                .description("Create a mobile app")
                .priority(Priority.HIGH)
                .columnId("todo")
                .eventId(eventId)
                .assigneeIds(List.of(user1.getId(), user2.getId()))
                .startDate(LocalDateTime.now().plusDays(30))
                .endDate(LocalDateTime.now().plusDays(31))
                .build();

        String taskResponse = mockMvc.perform(post("/api/tasks")
                        .param("userId", manager.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(taskRequest)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        Long taskId = objectMapper.readTree(taskResponse).get("id").asLong();

        // Step 3: Verify task was created with assignees
        mockMvc.perform(get("/api/tasks/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(taskId))
                .andExpect(jsonPath("$.title").value("Build Mobile App"))
                .andExpect(jsonPath("$.priority").value("HIGH"))
                .andExpect(jsonPath("$.columnId").value("todo"));

        // Step 4: Move task to in-progress
        mockMvc.perform(patch("/api/tasks/{id}/move", taskId)
                        .param("columnId", "in-progress")
                        .param("userId", manager.getId().toString()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.columnId").value("in-progress"));

        // Step 5: Move task to done
        mockMvc.perform(patch("/api/tasks/{id}/move", taskId)
                        .param("columnId", "done")
                        .param("userId", manager.getId().toString()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.columnId").value("done"));

        // Step 6: Get all tasks for event
        mockMvc.perform(get("/api/tasks/event/{eventId}", eventId))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "admin@test.com", roles = "ADMIN")
    void testCompleteWorkflow_MultipleTasksInEvent() throws Exception {
        // Create event
        EventRequest eventRequest = EventRequest.builder()
                .title("Workshop 2025")
                .description("Training workshop")
                .statusEvent(StatusEvent.PENDING)
                .capacity(50)
                .startTime(LocalDateTime.now().plusDays(20))
                .endTime(LocalDateTime.now().plusDays(21))
                .build();

        String eventResponse = mockMvc.perform(post("/api/events")
                        .param("userId", admin.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(eventRequest)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Long eventId = objectMapper.readTree(eventResponse).get("id").asLong();

        // Create task 1
        TaskRequest task1 = TaskRequest.builder()
                .title("Setup Environment")
                .description("Setup dev environment")
                .priority(Priority.HIGH)
                .columnId("todo")
                .eventId(eventId)
                .assigneeIds(List.of(user1.getId()))
                .build();

        mockMvc.perform(post("/api/tasks")
                        .param("userId", manager.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(task1)))
                .andExpect(status().isCreated());

        // Create task 2
        TaskRequest task2 = TaskRequest.builder()
                .title("Code Review")
                .description("Review peer code")
                .priority(Priority.MEDIUM)
                .columnId("todo")
                .eventId(eventId)
                .assigneeIds(List.of(user2.getId()))
                .build();

        mockMvc.perform(post("/api/tasks")
                        .param("userId", manager.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(task2)))
                .andExpect(status().isCreated());

        // Get all tasks for this event
        mockMvc.perform(get("/api/tasks/event/{eventId}", eventId))
                .andExpect(status().isOk());
    }
}
