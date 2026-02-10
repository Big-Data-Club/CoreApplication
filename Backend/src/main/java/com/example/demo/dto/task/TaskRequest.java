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
public class TaskRequest {
    private String title;
    private String description;
    private Priority priority;
    private String columnId;
    private LocalDateTime startDate;
    private LocalDateTime endDate;
    private Long eventId;
    private List<Long> assigneeIds;
    private List<TaskLinkRequest> links;

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class TaskLinkRequest {
        private String url;
        private String title;
    }
}