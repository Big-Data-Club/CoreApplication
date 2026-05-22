package com.example.demo.repository;

import com.example.demo.model.UserTypeOption;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface UserTypeOptionRepository extends JpaRepository<UserTypeOption, Long> {
    Optional<UserTypeOption> findByCode(String code);
    boolean existsByCode(String code);
}
