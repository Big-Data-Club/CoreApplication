package com.example.demo.model;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "user_types")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserTypeOption {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String code; // e.g. "CLC", "DT"

    @Column(nullable = false, length = 100)
    private String name; // e.g. "Chất lượng cao"

    @Column(length = 255)
    private String description;
}
