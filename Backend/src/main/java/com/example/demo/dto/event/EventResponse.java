package com.example.demo.dto.event;

import com.example.demo.enums.StatusEvent;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Data
@Builder
public class EventResponse {
    private Long id;
    private String title;
    private String description;
    private StatusEvent statusEvent;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private Integer capacity;
    private List<TaskInfo> tasks;

    @Data
    @Builder
    public static class TaskInfo {
        private Long id;
        private String title;
        private String description;
        private String priority;
        private String columnId;
        private LocalDateTime startDate;
        private LocalDateTime endDate;
    }
}