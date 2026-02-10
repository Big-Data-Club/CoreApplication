package com.example.demo.repository;

import com.example.demo.enums.Priority;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.Task;
import com.example.demo.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@ActiveProfiles("test")
class TaskRepositoryTest {

    @Autowired
    private TaskRepository taskRepository;

    @Autowired
    private UserRepository userRepository;

    private User creator;

    @BeforeEach
    void setUp() {
        creator = User.builder()
                .name("Task Creator")
                .email("creator@test.com")
                .password("password")
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.RESEARCH)
                .code("CREATOR001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();
        userRepository.save(creator);
    }

    @Test
    void testSaveTask_Success() {
        Task task = Task.builder()
                .title("Test Task")
                .description("Description")
                .priority(Priority.HIGH)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Task saved = taskRepository.save(task);

        assertNotNull(saved.getId());
        assertEquals("Test Task", saved.getTitle());
        assertEquals(Priority.HIGH, saved.getPriority());
    }

    @Test
    void testFindById_Success() {
        Task task = Task.builder()
                .title("Find Task")
                .description("Description")
                .priority(Priority.MEDIUM)
                .columnId("in-progress")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        Optional<Task> found = taskRepository.findById(task.getId());

        assertTrue(found.isPresent());
        assertEquals("Find Task", found.get().getTitle());
    }

    @Test
    void testFindByColumnId_WithPriority_Success() {
        Task highTask = Task.builder()
                .title("High Priority Task")
                .priority(Priority.HIGH)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Task lowTask = Task.builder()
                .title("Low Priority Task")
                .priority(Priority.LOW)
                .columnId("in-progress")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        taskRepository.save(highTask);
        taskRepository.save(lowTask);

        List<Task> todoTasks = taskRepository.findByColumnId("todo");

        assertTrue(todoTasks.stream().anyMatch(t -> t.getTitle().equals("High Priority Task") && t.getPriority() == Priority.HIGH));
    }

    @Test
    void testFindByColumnId_Success() {
        Task todoTask = Task.builder()
                .title("Todo Task")
                .priority(Priority.HIGH)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Task progressTask = Task.builder()
                .title("Progress Task")
                .priority(Priority.MEDIUM)
                .columnId("in-progress")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        taskRepository.save(todoTask);
        taskRepository.save(progressTask);

        List<Task> todoTasks = taskRepository.findByColumnId("todo");

        assertTrue(todoTasks.stream().anyMatch(t -> t.getTitle().equals("Todo Task")));
        assertFalse(todoTasks.stream().anyMatch(t -> t.getTitle().equals("Progress Task")));
    }

    @Test
    void testDelete_Success() {
        Task task = Task.builder()
                .title("To Delete")
                .priority(Priority.LOW)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        taskRepository.delete(task);

        assertFalse(taskRepository.existsById(task.getId()));
    }

    @Test
    void testUpdate_Success() {
        Task task = Task.builder()
                .title("Original Title")
                .description("Original Description")
                .priority(Priority.LOW)
                .columnId("todo")
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        taskRepository.save(task);

        task.setTitle("Updated Title");
        task.setDescription("Updated Description");
        task.setPriority(Priority.HIGH);
        task.setColumnId("done");
        task.setUpdatedAt(LocalDateTime.now());

        Task updated = taskRepository.save(task);

        assertEquals("Updated Title", updated.getTitle());
        assertEquals("Updated Description", updated.getDescription());
        assertEquals(Priority.HIGH, updated.getPriority());
        assertEquals("done", updated.getColumnId());
    }
}
