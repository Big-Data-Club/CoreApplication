package com.example.demo.repository;

import com.example.demo.model.Task;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface TaskRepository extends JpaRepository<Task, Long>, JpaSpecificationExecutor<Task> {
    
    // Step 1: Fetch tasks với assignees
    @Query("SELECT DISTINCT t FROM Task t " +
           "LEFT JOIN FETCH t.event " +
           "LEFT JOIN FETCH t.assignees a " +
           "LEFT JOIN FETCH a.user " +
           "LEFT JOIN FETCH t.createdBy " +
           "LEFT JOIN FETCH t.updatedBy")
    List<Task> findAllWithAssignees();
    
    // Step 2: Fetch links riêng
    @Query("SELECT DISTINCT t FROM Task t " +
           "LEFT JOIN FETCH t.links " +
           "WHERE t IN :tasks")
    List<Task> findLinksForTasks(@Param("tasks") List<Task> tasks);
    
    // Similar for single task
    @Query("SELECT DISTINCT t FROM Task t " +
           "LEFT JOIN FETCH t.event " +
           "LEFT JOIN FETCH t.assignees a " +
           "LEFT JOIN FETCH a.user " +
           "LEFT JOIN FETCH t.createdBy " +
           "LEFT JOIN FETCH t.updatedBy " +
           "WHERE t.id = :id")
    Optional<Task> findByIdWithAssignees(@Param("id") Long id);
    
    @Query("SELECT DISTINCT t FROM Task t " +
           "LEFT JOIN FETCH t.links " +
           "WHERE t.id = :id")
    Optional<Task> findByIdWithLinks(@Param("id") Long id);
    
    // By event
    @Query("SELECT DISTINCT t FROM Task t " +
           "LEFT JOIN FETCH t.event " +
           "LEFT JOIN FETCH t.assignees a " +
           "LEFT JOIN FETCH a.user " +
           "LEFT JOIN FETCH t.createdBy " +
           "LEFT JOIN FETCH t.updatedBy " +
           "WHERE t.event.id = :eventId")
    List<Task> findByEventIdWithAssignees(@Param("eventId") Long eventId);
    
    // By column
    @Query("SELECT DISTINCT t FROM Task t " +
           "LEFT JOIN FETCH t.event " +
           "LEFT JOIN FETCH t.assignees a " +
           "LEFT JOIN FETCH a.user " +
           "LEFT JOIN FETCH t.createdBy " +
           "LEFT JOIN FETCH t.updatedBy " +
           "WHERE t.columnId = :columnId")
    List<Task> findByColumnIdWithAssignees(@Param("columnId") String columnId);
    
    // Keep original methods
    List<Task> findByEventId(Long eventId);
    List<Task> findByColumnId(String columnId);
}