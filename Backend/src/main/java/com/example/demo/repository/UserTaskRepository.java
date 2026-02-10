package com.example.demo.repository;

import com.example.demo.model.UserTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface UserTaskRepository extends JpaRepository<UserTask, Long> {
    Optional<UserTask> findByUserIdAndTaskId(Long userId, Long taskId);
    boolean existsByUserIdAndTaskId(Long userId, Long taskId);
    long countByTaskId(Long taskId); // NEW: Count assignments for a task
}
