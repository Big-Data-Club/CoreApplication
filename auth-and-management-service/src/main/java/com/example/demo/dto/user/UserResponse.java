package com.example.demo.dto.user;

import com.example.demo.enums.AuthProvider;

import com.example.demo.enums.UserTeam;
import com.example.demo.model.User;
import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class UserResponse {

    private Long       id;
    private String     name;
    private String     email;
    private String     role;
    private java.util.List<String> roles;
    private String     team;
    private String     type;
    private String       code;
    private Integer      totalScore;
    private Boolean      active;
    private AuthProvider authProvider;
    private Boolean      pendingApproval;
    private String     profilePicture;
    private String     organization;
    private java.util.List<String> organizations;

    public static UserResponse fromEntity(User user) {
        java.util.List<String> orgList = new java.util.ArrayList<>();
        if (user.getOrganizationMembers() != null) {
            orgList = user.getOrganizationMembers().stream()
                    .map(om -> om.getOrganization().getName())
                    .toList();
        }

        return fromEntity(user, orgList);
    }

    /**
     * Maps a user without touching lazy organization relationships. List APIs
     * batch-load organization names and use this overload to avoid N+1 queries.
     */
    public static UserResponse fromEntity(User user, java.util.List<String> organizations) {
        return UserResponse.builder()
                .id(user.getId())
                .name(user.getName())
                .email(user.getEmail())
                .role(user.getRole())
                .roles(new java.util.ArrayList<>(user.effectiveRoles()))
                .team(user.getTeam())
                .type(user.getType())
                .code(user.getCode())
                .totalScore(user.getTotalScore())
                .active(user.getActive())
                .profilePicture(user.getProfilePicture())
                .authProvider(user.getAuthProvider())
                .pendingApproval(user.getPendingApproval())
                .organization(user.getOrganization())
                .organizations(organizations)
                .build();
    }
}
