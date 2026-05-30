package com.example.demo.model;

import com.example.demo.enums.AuthProvider;

import com.example.demo.enums.UserTeam;
import jakarta.persistence.*;
import lombok.*;
import java.util.ArrayList;
import java.util.List;
import com.fasterxml.jackson.annotation.JsonIgnore;

@Entity
@Table(name = "users")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder(toBuilder = true)
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false, unique = true, length = 100)
    private String email;

    @Column(nullable = false)
    @JsonIgnore
    private String password;

    @Column(nullable = false, length = 50)
    private String role;

    @Column(nullable = false, length = 50)
    private String team;

    @Column(nullable = false, unique = true, length = 100)
    private String code;

    @Column(nullable = false, length = 20)
    private String type;

    @Column(nullable = true, length = 255)
    private String organization;

    @Column(nullable = false)
    @Builder.Default
    private Boolean active = true;

    // Path to profile picture
    @Column(nullable = true)
    private String profilePicture;

    @Column(nullable = false)
    @Builder.Default
    private Integer totalScore = 0;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    @Builder.Default
    private AuthProvider authProvider = AuthProvider.LOCAL;

    @Column(unique = true)
    private String googleId;

    @Column(nullable = false)
    @Builder.Default
    private Boolean pendingApproval = false;

    @OneToMany(mappedBy = "user", cascade = CascadeType.ALL)
    @JsonIgnore
    @Builder.Default
    private List<UserTask> userTasks = new ArrayList<>();
}