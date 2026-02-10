package com.example.demo.service;

import com.example.demo.dto.event.EventRequest;
import com.example.demo.dto.event.EventResponse;
import com.example.demo.enums.StatusEvent;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.Event;
import com.example.demo.model.User;
import com.example.demo.repository.EventRepository;
import com.example.demo.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@Import(EventService.class)
@ActiveProfiles("test")
@Transactional
class EventServiceTest {

    @Autowired
    private EventService eventService;

    @Autowired
    private EventRepository eventRepository;

    @Autowired
    private UserRepository userRepository;

    private User admin, manager;

    @BeforeEach
    void setUp() {
        admin = User.builder()
                .name("Admin")
                .email("admin@test.com")
                .password("encoded_password")
                .role(UserRole.ROLE_ADMIN)
                .team(UserTeam.RESEARCH)
                .code("ADMIN001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();

        manager = User.builder()
                .name("Manager")
                .email("manager@test.com")
                .password("encoded_password")
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.ENGINEER)
                .code("MANAGER001")
                .type(UserType.TN)
                .active(true)
                .totalScore(0)
                .build();

        userRepository.save(admin);
        userRepository.save(manager);
    }

    @Test
    void testCreateEvent_Success() {
        LocalDateTime startTime = LocalDateTime.now().plusDays(10);
        LocalDateTime endTime = LocalDateTime.now().plusDays(11);

        EventRequest request = EventRequest.builder()
                .title("Test Event")
                .description("Test event description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(startTime)
                .endTime(endTime)
                .capacity(100)
                .build();

        EventResponse response = eventService.createEvent(request, admin.getId());

        assertNotNull(response);
        assertNotNull(response.getId());
        assertEquals("Test Event", response.getTitle());
        assertEquals("Test event description", response.getDescription());
        assertEquals(StatusEvent.PENDING, response.getStatusEvent());
    }

    @Test
    void testCreateEvent_CreatorNotFound() {
        EventRequest request = EventRequest.builder()
                .title("Test Event")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(100)
                .build();

        assertThrows(RuntimeException.class, () -> eventService.createEvent(request, 999L));
    }

    @Test
    void testUpdateEvent_Success() {
        Event event = Event.builder()
                .title("Original Title")
                .description("Original Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(50)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();
        eventRepository.save(event);

        EventRequest updateRequest = EventRequest.builder()
                .title("Updated Title")
                .description("Updated Description")
                .statusEvent(StatusEvent.IN_PROGRESS)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(100)
                .build();

        EventResponse response = eventService.updateEvent(event.getId(), updateRequest, manager.getId());

        assertEquals("Updated Title", response.getTitle());
        assertEquals("Updated Description", response.getDescription());
        assertEquals(StatusEvent.IN_PROGRESS, response.getStatusEvent());
        assertEquals(100, response.getCapacity());
    }

    @Test
    void testUpdateEvent_NotFound() {
        EventRequest request = EventRequest.builder()
                .title("Updated Title")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now())
                .endTime(LocalDateTime.now().plusDays(1))
                .capacity(100)
                .build();

        assertThrows(RuntimeException.class, () -> eventService.updateEvent(999L, request, admin.getId()));
    }

    @Test
    void testGetEventById_Success() {
        Event event = Event.builder()
                .title("Test Event")
                .description("Test Description")
                .statusEvent(StatusEvent.COMPLETED)
                .startTime(LocalDateTime.now().minusDays(1))
                .endTime(LocalDateTime.now())
                .capacity(50)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();
        eventRepository.save(event);

        EventResponse response = eventService.getEventById(event.getId());

        assertNotNull(response);
        assertEquals("Test Event", response.getTitle());
        assertEquals(StatusEvent.COMPLETED, response.getStatusEvent());
    }

    @Test
    void testGetEventById_NotFound() {
        assertThrows(RuntimeException.class, () -> eventService.getEventById(999L));
    }

    @Test
    void testGetAllEvents_Success() {
        Event event1 = Event.builder()
                .title("Event 1")
                .description("Description 1")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(1))
                .endTime(LocalDateTime.now().plusDays(2))
                .capacity(50)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();

        Event event2 = Event.builder()
                .title("Event 2")
                .description("Description 2")
                .statusEvent(StatusEvent.IN_PROGRESS)
                .startTime(LocalDateTime.now().plusDays(3))
                .endTime(LocalDateTime.now().plusDays(4))
                .capacity(100)
                .createdBy(manager)
                .createdAt(LocalDateTime.now())
                .build();

        eventRepository.save(event1);
        eventRepository.save(event2);

        List<EventResponse> responses = eventService.getAllEvents();

        assertEquals(2, responses.size());
    }

    @Test
    void testDeleteEvent_Success() {
        Event event = Event.builder()
                .title("Event to Delete")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(1))
                .endTime(LocalDateTime.now().plusDays(2))
                .capacity(50)
                .createdBy(admin)
                .createdAt(LocalDateTime.now())
                .build();
        eventRepository.save(event);

        eventService.deleteEvent(event.getId());

        assertFalse(eventRepository.existsById(event.getId()));
    }
}
