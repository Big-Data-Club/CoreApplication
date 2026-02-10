package com.example.demo.dto.event;

import com.example.demo.enums.StatusEvent;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class EventRequest {
    private String title;
    private String description;
    private StatusEvent statusEvent;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private Integer capacity;
}
