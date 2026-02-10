package com.example.demo.dto.usertask;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class UserTaskResponse {
    private Long userId;
    private String userName;
    private Integer score;
}
