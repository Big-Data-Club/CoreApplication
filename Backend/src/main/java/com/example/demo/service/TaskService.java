package com.example.demo.service;

import com.example.demo.dto.task.TaskRequest;
import com.example.demo.dto.task.TaskResponse;
import com.example.demo.enums.Priority;
import com.example.demo.model.*;
import com.example.demo.repository.*;
import com.example.demo.utils.SortUtils;
import com.example.demo.utils.TaskSpecifications;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class TaskService {
    private final TaskRepository taskRepo;
    private final UserRepository userRepo;
    private final EventRepository eventRepo;

    @Transactional
    public TaskResponse createTask(TaskRequest request, Long creatorId) {
        User creator = userRepo.findById(creatorId)
                .orElseThrow(() -> new RuntimeException("User not found"));

        Task task = Task.builder()
                .title(request.getTitle())
                .description(request.getDescription())
                .priority(request.getPriority())
                .columnId(request.getColumnId())
                .startDate(request.getStartDate())
                .endDate(request.getEndDate())
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        // Set event if provided
        if (request.getEventId() != null) {
            Event event = eventRepo.findById(request.getEventId())
                    .orElseThrow(() -> new RuntimeException("Event not found"));
            task.setEvent(event);
        }

        // Save task first
        task = taskRepo.save(task);

        // Add links
        if (request.getLinks() != null) {
            for (TaskRequest.TaskLinkRequest linkReq : request.getLinks()) {
                TaskLink link = TaskLink.builder()
                        .url(linkReq.getUrl())
                        .title(linkReq.getTitle())
                        .task(task)
                        .build();
                task.getLinks().add(link);
            }
        }

        // Add assignees
        if (request.getAssigneeIds() != null) {
            for (Long userId : request.getAssigneeIds()) {
                User user = userRepo.findById(userId)
                        .orElseThrow(() -> new RuntimeException("User not found: " + userId));
                UserTask userTask = UserTask.builder()
                        .user(user)
                        .task(task)
                        .build();
                task.getAssignees().add(userTask);
            }
        }

        task = taskRepo.save(task);
        return mapToResponse(task);
    }

    @Transactional
    public TaskResponse updateTask(Long taskId, TaskRequest request, Long updaterId) {
        Task task = taskRepo.findById(taskId)
                .orElseThrow(() -> new RuntimeException("Task not found"));

        User updater = userRepo.findById(updaterId)
                .orElseThrow(() -> new RuntimeException("User not found"));

        task.setTitle(request.getTitle());
        task.setDescription(request.getDescription());
        task.setPriority(request.getPriority());
        task.setColumnId(request.getColumnId());
        task.setStartDate(request.getStartDate());
        task.setEndDate(request.getEndDate());
        task.setUpdatedBy(updater);
        task.setUpdatedAt(LocalDateTime.now());

        // Update event
        if (request.getEventId() != null) {
            Event event = eventRepo.findById(request.getEventId())
                    .orElseThrow(() -> new RuntimeException("Event not found"));
            task.setEvent(event);
        } else {
            task.setEvent(null);
        }

        // Update links
        task.getLinks().clear();
        if (request.getLinks() != null) {
            for (TaskRequest.TaskLinkRequest linkReq : request.getLinks()) {
                TaskLink link = TaskLink.builder()
                        .url(linkReq.getUrl())
                        .title(linkReq.getTitle())
                        .task(task)
                        .build();
                task.getLinks().add(link);
            }
        }

        // Update assignees
        task.getAssignees().clear();
        if (request.getAssigneeIds() != null) {
            for (Long userId : request.getAssigneeIds()) {
                User user = userRepo.findById(userId)
                        .orElseThrow(() -> new RuntimeException("User not found: " + userId));
                UserTask userTask = UserTask.builder()
                        .user(user)
                        .task(task)
                        .build();
                task.getAssignees().add(userTask);
            }
        }

        task = taskRepo.save(task);
        return mapToResponse(task);
    }

    @Transactional(readOnly = true)
    public List<TaskResponse> searchTasks(String keyword,
                                          String columnId,
                                          Priority priority,
                                          Long eventId,
                                          LocalDateTime startAfter,
                                          LocalDateTime endBefore,
                                          String[] sortParams) {

        Specification<Task> spec = Specification
                .where(TaskSpecifications.containsKeyword(keyword, "title", "description"))
                .and(TaskSpecifications.hasColumnId(columnId))
                .and(TaskSpecifications.hasPriority(priority))
                .and(TaskSpecifications.hasEventId(eventId))
                .and(TaskSpecifications.startAfter(startAfter))
                .and(TaskSpecifications.endBefore(endBefore));

        Sort sort = SortUtils.parseSort(sortParams);

        return taskRepo.findAll(spec, sort).stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public TaskResponse getTaskById(Long id) {
        // Fetch với assignees
        Task task = taskRepo.findByIdWithAssignees(id)
                .orElseThrow(() -> new RuntimeException("Task not found"));
        
        // Fetch links
        taskRepo.findByIdWithLinks(id);
        
        return mapToResponse(task);
    }

    @Transactional(readOnly = true)
    public List<TaskResponse> getTasksByEventId(Long eventId) {
        List<Task> tasks = taskRepo.findByEventIdWithAssignees(eventId);
        
        if (!tasks.isEmpty()) {
                taskRepo.findLinksForTasks(tasks);
        }
        
        return tasks.stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<TaskResponse> getTasksByColumnId(String columnId) {
        List<Task> tasks = taskRepo.findByColumnIdWithAssignees(columnId);
        
        if (!tasks.isEmpty()) {
                taskRepo.findLinksForTasks(tasks);
        }
        
        return tasks.stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<TaskResponse> getAllTasks() {
        // Step 1: Fetch với assignees
        List<Task> tasks = taskRepo.findAllWithAssignees();
        
        // Step 2: Fetch links cho các tasks đó
        if (!tasks.isEmpty()) {
                taskRepo.findLinksForTasks(tasks);
        }
        
        return tasks.stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional
    public void deleteTask(Long id) {
        taskRepo.deleteById(id);
    }

    @Transactional
    public TaskResponse moveTask(Long taskId, String newColumnId, Long userId) {
        Task task = taskRepo.findById(taskId)
                .orElseThrow(() -> new RuntimeException("Task not found"));

        User updater = userRepo.findById(userId)
                .orElseThrow(() -> new RuntimeException("User not found"));

        task.setColumnId(newColumnId);
        task.setUpdatedBy(updater);
        task.setUpdatedAt(LocalDateTime.now());

        task = taskRepo.save(task);
        return mapToResponse(task);
    }

    private TaskResponse mapToResponse(Task task) {
        TaskResponse.TaskResponseBuilder builder = TaskResponse.builder()
                .id(task.getId())
                .title(task.getTitle())
                .description(task.getDescription())
                .priority(task.getPriority())
                .columnId(task.getColumnId())
                .startDate(task.getStartDate())
                .endDate(task.getEndDate())
                .createdAt(task.getCreatedAt());

        if (task.getEvent() != null) {
            builder.event(TaskResponse.EventInfo.builder()
                    .id(task.getEvent().getId())
                    .title(task.getEvent().getTitle())
                    .build());
        }

        if (task.getCreatedBy() != null) {
            builder.createdBy(TaskResponse.UserInfo.builder()
                    .id(task.getCreatedBy().getId())
                    .name(task.getCreatedBy().getName())
                    .email(task.getCreatedBy().getEmail())
                    .build());
        }

        if (task.getUpdatedBy() != null) {
            builder.updatedBy(TaskResponse.UserInfo.builder()
                    .id(task.getUpdatedBy().getId())
                    .name(task.getUpdatedBy().getName())
                    .email(task.getUpdatedBy().getEmail())
                    .build())
                    .updatedAt(task.getUpdatedAt());
        }

        builder.assignees(task.getAssignees().stream()
                .map(ut -> TaskResponse.AssigneeInfo.builder()
                        .id(ut.getUser().getId())
                        .name(ut.getUser().getName())
                        .email(ut.getUser().getEmail())
                        .code(ut.getUser().getCode())
                        .team(ut.getUser().getTeam().name())
                        .type(ut.getUser().getType().name())
                        .build())
                .collect(Collectors.toList()));

        builder.links(task.getLinks().stream()
                .map(link -> TaskResponse.TaskLinkInfo.builder()
                        .id(link.getId())
                        .url(link.getUrl())
                        .title(link.getTitle())
                        .build())
                .collect(Collectors.toList()));

        return builder.build();
    }
}