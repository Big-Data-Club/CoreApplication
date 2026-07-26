package com.example.demo.model;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "user_profiles", indexes = {
    @Index(name = "idx_user_profiles_alias", columnList = "alias", unique = true),
    @Index(name = "idx_user_profiles_user_id", columnList = "user_id", unique = true)
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder(toBuilder = true)
public class UserProfile {

    @Id
    @Column(name = "user_id")
    private Long userId;

    @OneToOne(fetch = FetchType.LAZY)
    @MapsId
    @JoinColumn(name = "user_id")
    private User user;

    @Column(unique = true, length = 50)
    private String alias;

    @Column(nullable = false)
    @Builder.Default
    private Boolean published = false;

    @Column(length = 255)
    private String title;

    @Column(columnDefinition = "TEXT")
    private String bio;

    @Column(columnDefinition = "TEXT")
    private String sectionsJson;

    @Column(columnDefinition = "TEXT")
    private String layoutConfigJson;

    @Column(columnDefinition = "TEXT")
    private String statsCacheJson;

    @Column(nullable = false)
    @Builder.Default
    private Boolean allowDirectChat = true;

    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
