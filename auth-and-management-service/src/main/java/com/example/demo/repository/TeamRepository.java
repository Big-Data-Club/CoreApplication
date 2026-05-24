package com.example.demo.repository;

import com.example.demo.model.Team;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface TeamRepository extends JpaRepository<Team, Long> {
    Optional<Team> findByCode(String code);
    boolean existsByCode(String code);
}
