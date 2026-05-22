package com.example.demo.dto.auth;

import com.example.demo.enums.UserTeam;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class GoogleRegisterRequest {
    @NotBlank(message = "Google ID token is required")
    private String idToken;

    @NotBlank(message = "Name is required")
    private String name;

    @NotBlank(message = "Student/member code is required")
    private String code;

    @NotNull(message = "Team is required")
    private UserTeam team;

    @NotBlank(message = "Type is required")
    private String type;
}
