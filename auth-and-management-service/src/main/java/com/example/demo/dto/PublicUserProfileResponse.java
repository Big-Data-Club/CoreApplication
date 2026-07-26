package com.example.demo.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PublicUserProfileResponse {
    private Long userId;
    private String alias;
    private Boolean published;
    private String message;

    // Basic User Info
    private String fullName;
    private String email;
    private String avatarUrl;
    private String userType;
    private String organization;

    // Customizable Profile Fields
    private String title;
    private String bio;
    private Object sections;
    private Object layoutConfig;
    private Object stats;
    private Boolean allowDirectChat;
}
