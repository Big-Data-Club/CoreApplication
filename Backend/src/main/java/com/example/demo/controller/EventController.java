package com.example.demo.controller;

import com.example.demo.dto.event.EventRequest;
import com.example.demo.dto.event.EventResponse;
import com.example.demo.enums.StatusEvent;
import com.example.demo.service.EventService;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/events")
@RequiredArgsConstructor
public class EventController {
    private final EventService eventService;

    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN','MANAGER')")
    public EventResponse create(@RequestBody EventRequest request, @RequestParam Long userId) {
        return eventService.createEvent(request, userId);
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAnyRole('ADMIN','MANAGER')")
    public EventResponse update(
            @PathVariable Long id,
            @RequestBody EventRequest request,
            @RequestParam Long userId) {
        return eventService.updateEvent(id, request, userId);
    }

    @GetMapping
    public List<EventResponse> getAll() {
        return eventService.getAllEvents();
    }

    @GetMapping("/{id}")
    public EventResponse getById(@PathVariable Long id) {
        return eventService.getEventById(id);
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAnyRole('ADMIN','MANAGER')")
    public void delete(@PathVariable Long id) {
        eventService.deleteEvent(id);
    }

    @GetMapping("/search")
    public List<EventResponse> searchEvents(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) StatusEvent status,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime end,
            @RequestParam(required = false) String[] sort
    ) {
        return eventService.searchEvents(keyword, status, start, end, sort);
    }
}