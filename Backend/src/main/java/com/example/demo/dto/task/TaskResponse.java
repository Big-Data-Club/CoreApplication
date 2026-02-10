package com.example.demo.dto.task;

import com.example.demo.enums.Priority;
import lombok.*;

import java.time.LocalDateTime;
import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TaskResponse {
    private Long id;
    private String title;
    private String description;
    private Priority priority;
    private String columnId;
    private LocalDateTime startDate;
    private LocalDateTime endDate;
    private EventInfo event;
    private List<AssigneeInfo> assignees;
    private List<TaskLinkInfo> links;
    private LocalDateTime createdAt;
    private UserInfo createdBy;
    private LocalDateTime updatedAt;
    private UserInfo updatedBy;

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class EventInfo {
        private Long id;
        private String title;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class AssigneeInfo {
        private Long id;
        private String name;
        private String email;
        private String code;
        private String team;
        private String type;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class TaskLinkInfo {
        private Long id;
        private String url;
        private String title;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class UserInfo {
        private Long id;
        private String name;
        private String email;
    }
}