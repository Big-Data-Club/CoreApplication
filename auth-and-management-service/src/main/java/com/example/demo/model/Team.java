package com.example.demo.model;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "teams")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Team {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String code; // e.g. "RESEARCH", "ENGINEER"

    @Column(nullable = false, length = 100)
    private String name; // e.g. "Research", "Engineer"

    @Column(length = 255)
    private String description;
}
