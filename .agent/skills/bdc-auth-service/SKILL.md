---
name: bdc-auth-service
description: >
  Use when working in auth-and-management-service/ — Java 21 + Spring Boot 3.x.
  Covers: JWT, user sync, layered architecture, JPA, email, password reset,
  events, tasks, announcements, CORS, security config.
triggers:
  - auth-and-management-service/
  - spring
  - java
  - jwt
  - spring boot
version: "1.1"
authors:
  - BDC Team
requires:
  - bdc-core-orchestrator
---

# BDC Auth & Management Service — Developer Skill

## Role & Scope

You are working on `auth-and-management-service/` — the authentication and
club management backend. Built with Java 21 + Spring Boot 3.x + PostgreSQL.

**Root package:** `com.example.demo`
**Entry point:** `ClubApplication.java` (+ `@EnableScheduling`)
**Base URL:** `http://localhost:8080` | Docker: `http://backend:8080`

---

## Project Structure

```
auth-and-management-service/
├── src/main/java/com/example/demo/
│   ├── ClubApplication.java              @SpringBootApplication + @EnableScheduling
│   ├── config/
│   │   ├── CorsConfig.java               CORS whitelist (update together with SecurityConfig)
│   │   ├── DataInitializer.java          Seeds default admin from ${ADMIN_EMAIL} / ${ADMIN_PASSWORD}
│   │   ├── GlobalExceptionHandler.java   @RestControllerAdvice — ALL error responses here
│   │   ├── JwtAuthFilter.java            Reads JWT from Authorization header OR authToken cookie
│   │   ├── RestTemplateConfig.java       RestTemplate bean + @EnableAsync
│   │   ├── SecurityConfig.java           Spring Security filter chain + CORS source
│   │   ├── SwaggerConfig.java            OpenAPI with BearerAuth scheme
│   │   └── WebConfig.java                Static resource handler for /uploads/**
│   ├── controller/                       @RestController — HTTP only, no business logic
│   ├── service/                          Business logic, transactions, external calls
│   │   └── impl/                         UserServiceImpl implements UserService
│   ├── repository/                       Spring Data JPA + custom @Query
│   ├── model/                            @Entity classes
│   ├── dto/                              Request/Response DTOs (no JPA annotations)
│   ├── enums/                            Priority, StatusEvent, UserRole, etc.
│   ├── exception/                        ResourceNotFoundException, etc.
│   ├── mapper/                           Manual Entity ↔ DTO mappers (no MapStruct)
│   └── utils/                            JPA Specifications, SortUtils, PasswordGenerator
├── src/main/resources/
│   ├── application.yaml                  Local dev config
│   ├── application-docker.yaml           Docker profile (SPRING_PROFILES_ACTIVE=docker)
│   └── application-prod.yaml            Production overrides
└── src/test/
    ├── java/.../controller/              MockMvc integration tests
    ├── java/.../repository/              @DataJpaTest with H2
    └── java/.../service/                 @DataJpaTest service tests
```

---

## Layered Architecture

```
HTTP Request
    ↓
Controller   validates HTTP shape, calls Service, never touches Repository
    ↓
Service      business logic, @Transactional, calls Repository / EmailService / UserSyncService
    ↓
Repository   Spring Data JPA + custom @Query, returns Entity (not DTO)
    ↓
Mapper       Entity -> DTO conversion (lives in mapper/ package)
    ↓
Database
```

**Hard rules:**
- Controllers never call Repository directly.
- Services never return raw Entity to Controller — always go through Mapper.
- `@Transactional` belongs on Service methods, not Controllers.
- Use `@Slf4j` + `log.info()` / `log.error()` — never `System.out.println`.

---

## Adding a New Feature — Standard Workflow

### Step 1 — Domain Model

```java
@Entity
@Table(name = "my_entities")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class MyEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @ManyToOne
    @JoinColumn(name = "user_id")
    private User createdBy;

    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    @PrePersist  protected void onCreate() { createdAt = LocalDateTime.now(); }
    @PreUpdate   protected void onUpdate() { updatedAt = LocalDateTime.now(); }
}
```

### Step 2 — DTOs

```java
@Data @Builder
public class MyEntityRequest {
    @NotBlank private String name;
}

@Data @Builder
public class MyEntityResponse {
    private Long id;
    private String name;
    private String createdByEmail;
    private LocalDateTime createdAt;
}
```

### Step 3 — Repository

```java
@Repository
public interface MyEntityRepository
        extends JpaRepository<MyEntity, Long>, JpaSpecificationExecutor<MyEntity> {
    // Only add methods that Spring Data cannot derive automatically
    @Query("SELECT DISTINCT e FROM MyEntity e WHERE e.name LIKE %:keyword%")
    List<MyEntity> searchByKeyword(@Param("keyword") String keyword);
}
```

### Step 4 — Mapper

```java
public class MyEntityMapper {
    public static MyEntityResponse toResponse(MyEntity e) {
        return MyEntityResponse.builder()
            .id(e.getId())
            .name(e.getName())
            .createdByEmail(e.getCreatedBy() != null ? e.getCreatedBy().getEmail() : null)
            .createdAt(e.getCreatedAt())
            .build();
    }

    public static MyEntity toEntity(MyEntityRequest req, User creator) {
        return MyEntity.builder().name(req.getName()).createdBy(creator).build();
    }
}
```

### Step 5 — Service

```java
@Service
@RequiredArgsConstructor
@Slf4j
public class MyEntityService {
    private final MyEntityRepository repo;
    private final UserRepository userRepo;

    @Transactional(readOnly = true)
    public List<MyEntityResponse> getAll() {
        return repo.findAll().stream().map(MyEntityMapper::toResponse).toList();
    }

    @Transactional
    public MyEntityResponse create(MyEntityRequest req, String creatorEmail) {
        User creator = userRepo.findByEmail(creatorEmail)
            .orElseThrow(() -> new ResourceNotFoundException("User not found: " + creatorEmail));
        return MyEntityMapper.toResponse(repo.save(MyEntityMapper.toEntity(req, creator)));
    }
}
```

### Step 6 — Controller

```java
@RestController
@RequestMapping("/api/my-entities")
@RequiredArgsConstructor
public class MyEntityController {
    private final MyEntityService service;

    @GetMapping
    public ResponseEntity<List<MyEntityResponse>> getAll() {
        return ResponseEntity.ok(service.getAll());
    }

    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER')")
    public ResponseEntity<MyEntityResponse> create(@Valid @RequestBody MyEntityRequest req) {
        String email = (String) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        return ResponseEntity.ok(service.create(req, email));
    }
}
```

---

## Security & JWT

### JwtAuthFilter Behaviour

1. Reads token from `Authorization: Bearer <token>` header **or** `authToken` cookie.
2. Validates signature against `${JWT_SECRET}` (must be identical in lms-service).
3. Sets `SecurityContextHolder` with email as principal + roles as authorities.

### Role Hierarchy

```
ROLE_ADMIN    full access
ROLE_MANAGER  create events, tasks, announcements
ROLE_USER     read-only on most resources
```

### Getting Current User in a Service

```java
// Correct — read email from SecurityContext, load user from DB
private User getCurrentUser() {
    String email = (String) SecurityContextHolder.getContext()
        .getAuthentication().getPrincipal();
    return userRepo.findByEmail(email)
        .orElseThrow(() -> new EntityNotFoundException("User not found: " + email));
}

// Wrong — do not inject Authentication directly into service layer
```

---

## Exception Handling

All HTTP error responses are produced by `GlobalExceptionHandler`. Do not
return error responses from controllers or services — throw exceptions instead.

```java
// Add custom exceptions to exception/ package, then register here:
@ExceptionHandler(ResourceNotFoundException.class)
public ResponseEntity<Map<String, String>> handleResourceNotFound(ResourceNotFoundException ex) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", ex.getMessage()));
}
```

### Production Safety — hide stack trace

```java
// Current code exposes stack trace — fix before production deploy
// ❌
return ResponseEntity.status(500).body(Map.of(
    "error", ex.getMessage(),
    "trace", ex.getStackTrace()[0].toString()  // REMOVE
));

// ✅
@Value("${spring.profiles.active:default}")
private String activeProfile;

@ExceptionHandler(Exception.class)
public ResponseEntity<?> handleGenericException(Exception ex) {
    log.error("Unhandled exception: {}", ex.getMessage(), ex);
    if ("docker".equals(activeProfile) || "prod".equals(activeProfile)) {
        return ResponseEntity.status(500).body(Map.of("error", "Internal server error"));
    }
    return ResponseEntity.status(500).body(Map.of("error", ex.getMessage()));
}
```

---

## JPA Patterns

### Avoiding N+1 Queries

```java
// ❌ N+1
events.forEach(e -> e.getTasks().size());

// ✅ EntityGraph
@EntityGraph(attributePaths = {"tasks"})
@Query("SELECT DISTINCT e FROM Event e")
List<Event> findAllWithTasks();

// ✅ Two-step fetch for multiple collections (avoids MultipleBagFetchException)
List<Task> tasks = taskRepo.findAllWithAssignees();   // Step 1
if (!tasks.isEmpty()) {
    taskRepo.findLinksForTasks(tasks);                // Step 2
}
```

### Transaction Guidelines

```java
@Transactional(readOnly = true)  // SELECT queries — better performance
@Transactional                   // INSERT / UPDATE / DELETE
// Never put @Transactional on Controller methods
// Never swallow exceptions inside @Transactional (prevents rollback)
```

---

## Email Service

Gmail SMTP requires a 16-character App Password (not the regular account password).

```yaml
spring.mail:
  host: smtp.gmail.com
  port: 587
  username: ${EMAIL}
  password: ${EMAIL_PASSWORD}
  properties.mail.smtp.starttls.enable: true
```

`bulkRegister()` catches email exceptions and **does not fail the HTTP request**.
Users can be created without receiving their password email. Always verify:
```bash
docker compose logs backend | grep -i "email\|mail"
```

---

## User Sync to LMS

`UserSyncService.syncUsersToLms()` is `@Async`. If LMS is down at creation
time, sync silently fails. Manual re-sync:

```bash
curl -X POST http://localhost:8081/api/v1/sync/users/bulk \
  -H "X-Sync-Secret: $LMS_SYNC_SECRET" \
  -H "Content-Type: application/json" \
  -d '[{"user_id":1,"email":"a@b.com","full_name":"Name","roles":["TEACHER","STUDENT"]}]'
```

**Role mapping** — applied in `UserSyncService` and `AuthService` (keep in sync):
```java
private List<String> determineRoles(UserRole userRole) {
    List<String> roles = new ArrayList<>(List.of("TEACHER", "STUDENT")); // default for all
    if (userRole == UserRole.ROLE_ADMIN) roles.add("ADMIN");
    return roles;
}
```

---

## Known Issues (Fix Before Production)

| Priority | File | Issue |
|----------|------|-------|
| HIGH | `JwtAuthFilter.java` | Remove `System.out.println` debug statements |
| HIGH | `GlobalExceptionHandler.java` | Hide stack trace in production response |
| HIGH | `CorsConfig.java` + `SecurityConfig.java` | Read `allowedOrigins` from env var, not hardcoded `bdc.hpcc.vn` |
| HIGH | `DataInitializer.java` | Read admin email/password from env var — already done, verify it works |
| MED | `AuthServiceTest.java` | `testBulkRegister_AssignsDefaultPassword` asserts wrong expected password |
| MED | `EventControllerTest.java` | `testUpdateEvent_Success` asserts `"ONGOING"` but enum is `"IN_PROGRESS"` |

---

## Code Quality Checklist

```
[ ] New endpoint has @PreAuthorize or is explicitly public
[ ] All business logic in Service layer, not Controller
[ ] @Transactional(readOnly = true) on read-only Service methods
[ ] No System.out.println — use @Slf4j
[ ] New env var added to .env.example + application.yaml + docker-compose.yml
[ ] ResourceNotFoundException used for 404 cases (registered in GlobalExceptionHandler)
[ ] N+1 queries avoided (EntityGraph or two-step fetch)
[ ] Tests: at least Repository test + Controller integration test
[ ] CORS updated if adding new allowed origin (CorsConfig + SecurityConfig together)
```