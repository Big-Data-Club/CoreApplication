package com.example.demo.service;

import com.example.demo.dto.event.*;
import com.example.demo.enums.StatusEvent;
import com.example.demo.model.Event;
import com.example.demo.model.User;
import com.example.demo.repository.EventRepository;
import com.example.demo.repository.UserRepository;
import com.example.demo.utils.*;

import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class EventService {
    private final EventRepository eventRepo;
    private final UserRepository userRepo;

    @Transactional
    public EventResponse createEvent(EventRequest request, Long creatorId) {
        User creator = userRepo.findById(creatorId).orElseThrow(() -> new RuntimeException("User not found"));
        Event event = Event.builder()
                .title(request.getTitle())
                .description(request.getDescription())
                .statusEvent(request.getStatusEvent())
                .startTime(request.getStartTime())
                .endTime(request.getEndTime())
                .capacity(request.getCapacity())
                .createdAt(LocalDateTime.now())
                .createdBy(creator)
                .build();
        event = eventRepo.save(event);
        return mapToResponse(event);
    }

    @Transactional
    public EventResponse updateEvent(Long id, EventRequest request, Long updaterId) {
        Event event = eventRepo.findById(id)
                .orElseThrow(() -> new RuntimeException("Event not found"));
        
        User updater = userRepo.findById(updaterId)
                .orElseThrow(() -> new RuntimeException("User not found"));

        event.setTitle(request.getTitle());
        event.setDescription(request.getDescription());
        event.setStatusEvent(request.getStatusEvent());
        event.setStartTime(request.getStartTime());
        event.setEndTime(request.getEndTime());
        event.setCapacity(request.getCapacity());
        event.setUpdatedAt(LocalDateTime.now());
        event.setUpdatedBy(updater);
        event = eventRepo.save(event);
        return mapToResponse(event);
    }

    @Transactional(readOnly = true)
    public List<EventResponse> searchEvents(String keyword,
                                            StatusEvent status,
                                            LocalDateTime start,
                                            LocalDateTime end,
                                            String[] sortParams) {

        Specification<Event> spec = Specification
                .where(EventSpecifications.containsKeyword(keyword, "title", "description"))
                .and(EventSpecifications.hasStatus(status))
                .and(EventSpecifications.startAfter(start))
                .and(EventSpecifications.endBefore(end));

        Sort sort = SortUtils.parseSort(sortParams);

        return eventRepo.findAll(spec, sort).stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<EventResponse> getAllEvents() {
        // Sử dụng EntityGraph để fetch tasks cùng lúc, tránh N+1 query
        return eventRepo.findAllWithTasks().stream()
                .map(this::mapToResponseWithTasks)
                .toList();
    }

    @Transactional(readOnly = true)
    public EventResponse getEventById(Long id) {
        // Fetch event cùng với tasks
        return eventRepo.findWithTasksById(id)
                .map(this::mapToResponseWithTasks)
                .orElseThrow(() -> new RuntimeException("Event not found"));
    }

    @Transactional
    public void deleteEvent(Long id) {
        eventRepo.deleteById(id);
    }

    private EventResponse mapToResponse(Event event) {
        return EventResponse.builder()
                .id(event.getId())
                .title(event.getTitle())
                .description(event.getDescription())
                .statusEvent(event.getStatusEvent())
                .startTime(event.getStartTime())
                .endTime(event.getEndTime())
                .capacity(event.getCapacity())
                .build();
    }

    private EventResponse mapToResponseWithTasks(Event event) {
        EventResponse.EventResponseBuilder builder = EventResponse.builder()
                .id(event.getId())
                .title(event.getTitle())
                .description(event.getDescription())
                .statusEvent(event.getStatusEvent())
                .startTime(event.getStartTime())
                .endTime(event.getEndTime())
                .capacity(event.getCapacity());

        if (event.getTasks() != null && !event.getTasks().isEmpty()) {
            List<EventResponse.TaskInfo> taskInfos = event.getTasks().stream()
                    .map(task -> EventResponse.TaskInfo.builder()
                            .id(task.getId())
                            .title(task.getTitle())
                            .description(task.getDescription())
                            .priority(task.getPriority() != null ? task.getPriority().name() : null)
                            .columnId(task.getColumnId())
                            .startDate(task.getStartDate())
                            .endDate(task.getEndDate())
                            .build())
                    .collect(Collectors.toList());
            builder.tasks(taskInfos);
        }

        return builder.build();
    }
}