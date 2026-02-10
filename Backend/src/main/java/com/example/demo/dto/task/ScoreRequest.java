package com.example.demo.dto.task;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class ScoreRequest {
    private Long userId;
    private Integer score;
}
