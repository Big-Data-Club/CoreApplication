package com.example.demo.mapper;

import com.example.demo.dto.task.TaskResponse;
import com.example.demo.model.Task;
import com.example.demo.model.TaskScore;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.Optional;

@Component
public class TaskMapper implements EntityMapper<Task, TaskResponse> {

    @Override
    public TaskResponse toResponse(Task task) {
        return toResponse(task, Map.of());
    }

    public TaskResponse toResponse(Task task, Map<Long, TaskScore> scoresByUserId) {
        return TaskResponse.builder()
                .id(task.getId())
                .title(task.getTitle())
                .description(task.getDescription())
                .priority(task.getPriority())
                .columnId(task.getColumnId())
                .startDate(task.getStartDate())
                .endDate(task.getEndDate())
                .createdAt(task.getCreatedAt())
                .updatedAt(task.getUpdatedAt())
                .event(mapEvent(task))
                .createdBy(mapUser(task.getCreatedBy()))
                .updatedBy(mapUser(task.getUpdatedBy()))
                .assignees(mapAssignees(task, scoresByUserId))
                .links(mapLinks(task))
                .build();
    }

    public List<TaskResponse> toResponseList(List<Task> tasks,
                                             Map<Long, Map<Long, TaskScore>> scoresByTask) {
        return tasks.stream()
                .map(t -> toResponse(t, scoresByTask.getOrDefault(t.getId(), Map.of())))
                .toList();
    }

    private TaskResponse.EventInfo mapEvent(Task task) {
        return Optional.ofNullable(task.getEvent())
                .map(e -> TaskResponse.EventInfo.builder()
                        .id(e.getId())
                        .title(e.getTitle())
                        .build())
                .orElse(null);
    }

    private TaskResponse.UserInfo mapUser(com.example.demo.model.User user) {
        return Optional.ofNullable(user)
                .map(u -> TaskResponse.UserInfo.builder()
                        .id(u.getId())
                        .name(u.getName())
                        .email(u.getEmail())
                        .build())
                .orElse(null);
    }

    private List<TaskResponse.AssigneeInfo> mapAssignees(Task task,
                                                          Map<Long, TaskScore> scores) {
        return task.getAssignees().stream()
                .map(ut -> {
                    var u = ut.getUser();
                    var score = scores.get(u.getId());
                    return TaskResponse.AssigneeInfo.builder()
                            .id(u.getId())
                            .name(u.getName())
                            .email(u.getEmail())
                            .code(u.getCode())
                            .team(u.getTeam().name())
                            .type(u.getType())
                            .score(score != null ? score.getScore() : null)
                            .applied(score != null ? score.getApplied() : null)
                            .appliedAt(score != null ? score.getAppliedAt() : null)
                            .build();
                })
                .toList();
    }

    private List<TaskResponse.TaskLinkInfo> mapLinks(Task task) {
        return task.getLinks().stream()
                .map(l -> TaskResponse.TaskLinkInfo.builder()
                        .id(l.getId())
                        .url(l.getUrl())
                        .title(l.getTitle())
                        .build())
                .toList();
    }
}
