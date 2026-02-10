package com.example.demo.repository;

import com.example.demo.enums.StatusEvent;
import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.Event;
import com.example.demo.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@ActiveProfiles("test")
class EventRepositoryTest {

    @Autowired
    private EventRepository eventRepository;

    @Autowired
    private UserRepository userRepository;

    private User creator;

    @BeforeEach
    void setUp() {
        creator = User.builder()
                .name("Event Creator")
                .email("creator@test.com")
                .password("password")
                .role(UserRole.ROLE_MANAGER)
                .team(UserTeam.RESEARCH)
                .code("CREATOR001")
                .type(UserType.DT)
                .active(true)
                .totalScore(0)
                .build();
        userRepository.save(creator);
    }

    @Test
    void testSaveEvent_Success() {
        Event event = Event.builder()
                .title("Test Event")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(100)
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Event saved = eventRepository.save(event);

        assertNotNull(saved.getId());
        assertEquals("Test Event", saved.getTitle());
    }

    @Test
    void testFindById_Success() {
        Event event = Event.builder()
                .title("Find Test")
                .description("Description")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .capacity(50)
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        eventRepository.save(event);

        Optional<Event> found = eventRepository.findById(event.getId());

        assertTrue(found.isPresent());
        assertEquals("Find Test", found.get().getTitle());
    }

    @Test
    void testFindByStatusEvent_Success() {
        Event pendingEvent = Event.builder()
                .title("Pending Event")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Event completedEvent = Event.builder()
                .title("Completed Event")
                .statusEvent(StatusEvent.COMPLETED)
                .startTime(LocalDateTime.now().minusDays(10))
                .endTime(LocalDateTime.now().minusDays(9))
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        eventRepository.save(pendingEvent);
        eventRepository.save(completedEvent);

        List<Event> pendingEvents = eventRepository.findByStatusEvent(StatusEvent.PENDING);
        List<Event> completedEvents = eventRepository.findByStatusEvent(StatusEvent.COMPLETED);

        assertTrue(pendingEvents.stream().anyMatch(e -> e.getTitle().equals("Pending Event")));
        assertTrue(completedEvents.stream().anyMatch(e -> e.getTitle().equals("Completed Event")));
    }

    @Test
    void testFindByStartTimeBetween_Success() {
        LocalDateTime startRange = LocalDateTime.now().plusDays(5);
        LocalDateTime endRange = LocalDateTime.now().plusDays(15);

        Event event1 = Event.builder()
                .title("Event in Range")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        Event event2 = Event.builder()
                .title("Event out of Range")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(20))
                .endTime(LocalDateTime.now().plusDays(21))
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();

        eventRepository.save(event1);
        eventRepository.save(event2);

        List<Event> eventsInRange = eventRepository.findByStartTimeBetween(startRange, endRange);

        assertTrue(eventsInRange.stream().anyMatch(e -> e.getTitle().equals("Event in Range")));
        assertFalse(eventsInRange.stream().anyMatch(e -> e.getTitle().equals("Event out of Range")));
    }

    @Test
    void testFindAllWithTasks_Success() {
        Event event = Event.builder()
                .title("Event with Tasks")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        eventRepository.save(event);

        List<Event> events = eventRepository.findAllWithTasks();

        assertFalse(events.isEmpty());
        assertTrue(events.stream().anyMatch(e -> e.getTitle().equals("Event with Tasks")));
    }

    @Test
    void testDelete_Success() {
        Event event = Event.builder()
                .title("To Delete")
                .statusEvent(StatusEvent.PENDING)
                .startTime(LocalDateTime.now().plusDays(10))
                .endTime(LocalDateTime.now().plusDays(11))
                .createdBy(creator)
                .createdAt(LocalDateTime.now())
                .build();
        eventRepository.save(event);

        eventRepository.delete(event);

        assertFalse(eventRepository.existsById(event.getId()));
    }
}
