package com.example.demo.model;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "lms_role_mappings",
       uniqueConstraints = @UniqueConstraint(columnNames = {"auth_role_id", "lms_role"}))
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class LmsRoleMapping {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "auth_role_id", nullable = false)
    private Role authRole;

    @Column(name = "lms_role", nullable = false, length = 50)
    private String lmsRole;
}
