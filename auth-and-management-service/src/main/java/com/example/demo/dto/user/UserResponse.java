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
    private String     team;
    private String     type;
    private String       code;
    private Integer      totalScore;
    private Boolean      active;
    private AuthProvider authProvider;
    private Boolean      pendingApproval;
    private String     profilePicture;

    public static UserResponse fromEntity(User user) {
        return UserResponse.builder()
                .id(user.getId())
                .name(user.getName())
                .email(user.getEmail())
                .role(user.getRole())
                .team(user.getTeam())
                .type(user.getType())
                .code(user.getCode())
                .totalScore(user.getTotalScore())
                .active(user.getActive())
                .profilePicture(user.getProfilePicture())
                .authProvider(user.getAuthProvider())
                .pendingApproval(user.getPendingApproval())
                .build();
    }
}
