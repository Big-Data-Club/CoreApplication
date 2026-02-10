package com.example.demo.model;

import com.example.demo.enums.StatusPermission;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "announcements")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Announcement {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @Column(length = 2000)
    private String content;

    @ElementCollection
    @Builder.Default
    private List<String> images = new ArrayList<>();

    private StatusPermission status;

    private LocalDateTime createdAt;
    @ManyToOne
    @JoinColumn(name = "created_by")
    private User createdBy;

    private LocalDateTime updatedAt;
    @ManyToOne
    @JoinColumn(name = "updated_by")
    private User updatedBy;
}
