package com.example.demo.utils;

import com.example.demo.enums.Priority;
import com.example.demo.model.Task;
import org.springframework.data.jpa.domain.Specification;

import java.time.LocalDateTime;

public class TaskSpecifications {

    public static Specification<Task> containsKeyword(String keyword, String... fields) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isEmpty()) {
                return cb.conjunction();
            }
            
            String pattern = "%" + keyword.toLowerCase() + "%";
            var predicates = new jakarta.persistence.criteria.Predicate[fields.length];
            
            for (int i = 0; i < fields.length; i++) {
                predicates[i] = cb.like(cb.lower(root.get(fields[i])), pattern);
            }
            
            return cb.or(predicates);
        };
    }

    public static Specification<Task> hasColumnId(String columnId) {
        return (root, query, cb) -> {
            if (columnId == null || columnId.isEmpty()) {
                return cb.conjunction();
            }
            return cb.equal(root.get("columnId"), columnId);
        };
    }

    public static Specification<Task> hasPriority(Priority priority) {
        return (root, query, cb) -> {
            if (priority == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("priority"), priority);
        };
    }

    public static Specification<Task> hasEventId(Long eventId) {
        return (root, query, cb) -> {
            if (eventId == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("event").get("id"), eventId);
        };
    }

    public static Specification<Task> startAfter(LocalDateTime dateTime) {
        return (root, query, cb) -> {
            if (dateTime == null) {
                return cb.conjunction();
            }
            return cb.greaterThanOrEqualTo(root.get("startDate"), dateTime);
        };
    }

    public static Specification<Task> endBefore(LocalDateTime dateTime) {
        return (root, query, cb) -> {
            if (dateTime == null) {
                return cb.conjunction();
            }
            return cb.lessThanOrEqualTo(root.get("endDate"), dateTime);
        };
    }
}