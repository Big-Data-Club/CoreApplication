package com.example.demo.dto.auth;


import com.example.demo.enums.UserTeam;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class RegisterRequest {
    private String name;
    private String email;
    private String role;
    private String team;
    private String code;
    private String type;
    private String organization;
}