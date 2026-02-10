package com.example.demo.repository;

import com.example.demo.model.Event;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import com.example.demo.enums.StatusEvent;

@Repository
public interface EventRepository extends JpaRepository<Event, Long>, JpaSpecificationExecutor<Event> {
    List<Event> findByStatusEvent(StatusEvent statusEvent);
    List<Event> findByStartTimeBetween(LocalDateTime start, LocalDateTime end);
    @EntityGraph(attributePaths = {"tasks"})
    @Query("SELECT DISTINCT e FROM Event e")
    List<Event> findAllWithTasks();
    
    @EntityGraph(attributePaths = {"tasks"})
    Optional<Event> findWithTasksById(Long id);
}
