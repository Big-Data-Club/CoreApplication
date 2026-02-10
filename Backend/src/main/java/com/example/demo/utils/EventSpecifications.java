package com.example.demo.utils;

import com.example.demo.enums.StatusEvent;
//
import com.example.demo.model.Event;
import org.springframework.data.jpa.domain.Specification;
import jakarta.persistence.criteria.*;

import java.time.LocalDateTime;

public class EventSpecifications {

    public static Specification<Event> containsKeyword(String keyword, String... fields) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isEmpty()) return cb.conjunction();
            Predicate[] predicates = new Predicate[fields.length];
            for (int i = 0; i < fields.length; i++) {
                predicates[i] = cb.like(cb.lower(root.get(fields[i])), "%" + keyword.toLowerCase() + "%");
            }
            return cb.or(predicates);
        };
    }

    public static Specification<Event> hasStatus(StatusEvent status) {
        return (root, query, cb) -> status == null ? cb.conjunction() : cb.equal(root.get("statusEvent"), status);
    }

    public static Specification<Event> startAfter(LocalDateTime start) {
        return (root, query, cb) -> start == null ? cb.conjunction() : cb.greaterThanOrEqualTo(root.get("startTime"), start);
    }

    public static Specification<Event> endBefore(LocalDateTime end) {
        return (root, query, cb) -> end == null ? cb.conjunction() : cb.lessThanOrEqualTo(root.get("endTime"), end);
    }
}
