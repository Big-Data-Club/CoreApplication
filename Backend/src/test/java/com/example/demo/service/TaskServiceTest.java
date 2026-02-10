package com.example.demo.service;

import com.example.demo.dto.task.TaskRequest;
import com.example.demo.dto.task.TaskResponse;
import com.example.demo.enums.Priority;
import com.example.demo.enums.StatusEvent;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.Event;
import com.example.demo.model.Task;
import com.example.demo.model.User;
import com.example.demo.repository.EventRepository;
import com.example.demo.repository.TaskRepository;
import com.example.demo.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@Import(TaskService.class)
@ActiveProfiles("test")
@Transactional
class TaskServiceTest {

    @Autowired
    private TaskService taskService;

    @Autowired
    private TaskRepository taskRepository;

    @Autowired
    private EventRepository eventRepository;

    @Autowired
    private UserRepository userRepository;

    private User creator, assignee;
    private Event event;

    @BeforeEach
    void setUp() {
        creator = User.builder()
                .name("Creator")
                .email("creator@test.com")
                .password("password")
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.RESEARCH)
                .code("CREATOR001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();

        assignee = User.builder()
                .name("Assignee")
                .email("assignee@test.com")
                .password("password")
                .role(UserRole.ROLE_USER)
                .team(UserTeam.EVENT)
                .code("ASSIGNEE001")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build();

        userRepository.save(creator);
        userRepository.save(assignee);

        event = Event.builder()
                .title("Test Event")
                .description("Test Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(100)
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        eventRepository.save(event);
    }

    @Test
    void testCreateTask_Success() {
        TaskRequest request = TaskRequest.builder()
                .title("New Task")
                .description("Task Description")
                .priority(Priority.HIGH)
                .columnId("todo")
                .startDate(LocalDateTime.now())
                .endDate(LocalDateTime.now().plusDays(5))
                .eventId(event.getId())
                .assigneeIds(List.of(assignee.getId()))
                .build();

        TaskResponse response = taskService.createTask(request, creator.getId());

        assertNotNull(response);
        assertNotNull(response.getId());
        assertEquals("New Task", response.getTitle());
        assertEquals(Priority.HIGH, response.getPriority());
        assertEquals("todo", response.getColumnId());
    }

    @Test
    void testCreateTask_WithoutEvent() {
        TaskRequest request = TaskRequest.builder()
                .title("Standalone Task")
                .description("No Event Task")
                .priority(Priority.MEDIUM)
                .columnId("in-progress")
                .startDate(LocalDateTime.now())
                .endDate(LocalDateTime.now().plusDays(3))
                .build();

        TaskResponse response = taskService.createTask(request, creator.getId());

        assertNotNull(response);
        assertEquals("Standalone Task", response.getTitle());
    }

    @Test
    void testCreateTask_CreatorNotFound() {
        TaskRequest request = TaskRequest.builder()
                .title("Task")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .build();

        assertThrows(RuntimeException.class, () -> taskService.createTask(request, 999L));
    }

    @Test
    void testCreateTask_EventNotFound() {
        TaskRequest request = TaskRequest.builder()
                .title("Task")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .eventId(999L)
                .build();

        assertThrows(RuntimeException.class, () -> taskService.createTask(request, creator.getId()));
    }

    @Test
    void testCreateTask_AssigneeNotFound() {
        TaskRequest request = TaskRequest.builder()
                .title("Task")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .assigneeIds(List.of(999L))
                .build();

        assertThrows(RuntimeException.class, () -> taskService.createTask(request, creator.getId()));
    }

    @Test
    void testUpdateTask_Success() {
        Task task = Task.builder()
                .title("Original Task")
                .description("Original Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .event(event)
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        TaskRequest updateRequest = TaskRequest.builder()
                .title("Updated Task")
                .description("Updated Description")
                .priority(Priority.HIGH)
                .columnId("in-progress")
                .eventId(event.getId())
                .build();

        TaskResponse response = taskService.updateTask(task.getId(), updateRequest, creator.getId());

        assertEquals("Updated Task", response.getTitle());
        assertEquals("Updated Description", response.getDescription());
        assertEquals(Priority.HIGH, response.getPriority());
        assertEquals("in-progress", response.getColumnId());
    }

    @Test
    void testUpdateTask_NotFound() {
        TaskRequest request = TaskRequest.builder()
                .title("Task")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .build();

        assertThrows(RuntimeException.class, () -> taskService.updateTask(999L, request, creator.getId()));
    }

    @Test
    void testMoveTask_Success() {
        Task task = Task.builder()
                .title("Task to Move")
                .description("Description")
                .priority(Priority.MEDIUM)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        TaskResponse response = taskService.moveTask(task.getId(), "in-progress", creator.getId());

        assertEquals("in-progress", response.getColumnId());
    }

    @Test
    void testGetTaskById_Success() {
        Task task = Task.builder()
                .title("Get Task")
                .description("Description")
                .priority(Priority.HIGH)
                .columnId("done")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        TaskResponse response = taskService.getTaskById(task.getId());

        assertNotNull(response);
        assertEquals("Get Task", response.getTitle());
    }

    @Test
    void testGetTaskById_NotFound() {
        assertThrows(RuntimeException.class, () -> taskService.getTaskById(999L));
    }

    @Test
    void testGetAllTasks_ByEvent() {
        Task task1 = Task.builder()
                .title("Event Task 1")
                .description("Description 1")
                .priority(Priority.HIGH)
                .columnId("todo")
                .event(event)
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Task task2 = Task.builder()
                .title("Event Task 2")
                .description("Description 2")
                .priority(Priority.MEDIUM)
                .columnId("in-progress")
                .event(event)
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        taskRepository.save(task1);
        taskRepository.save(task2);

        List<TaskResponse> responses = taskService.getAllTasks();

        assertFalse(responses.isEmpty());
        assertTrue(responses.stream().anyMatch(t -> t.getTitle().equals("Event Task 1")));
    }

    @Test
    void testGetAllTasks_Success() {
        Task task = Task.builder()
                .title("Standalone Task")
                .description("No Event")
                .priority(Priority.LOW)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        List<TaskResponse> responses = taskService.getAllTasks();

        assertFalse(responses.isEmpty());
    }

    @Test
    void testDeleteTask_Success() {
        Task task = Task.builder()
                .title("Task to Delete")
                .description("Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        taskService.deleteTask(task.getId());

        assertFalse(taskRepository.existsById(task.getId()));
    }
}
