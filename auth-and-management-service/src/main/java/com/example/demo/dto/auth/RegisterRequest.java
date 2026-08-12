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
    /** Multiple auth roles. The legacy role field remains the primary role. */
    private java.util.List<String> roles;
    private String team;
    private String code;
    private String type;
    private String organization;
    /** Exact organization memberships, preferably addressed by stable slug. */
    private java.util.List<OrganizationAssignmentRequest> organizations;
}
