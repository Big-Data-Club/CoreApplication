---
name: bdc-test-writer
description: >
  Use when writing, reviewing, or expanding test cases for any BDC service.
  Covers: unit tests, integration tests, repository tests, service tests,
  controller tests, and Kafka worker tests for Java (JUnit 5), Go (testing),
  and Python (pytest). Enforces AAA structure, descriptive naming, and
  coverage requirements.
triggers:
  - test
  - testing
  - unit test
  - integration test
  - test case
  - junit
  - pytest
  - go test
  - coverage
  - mock
version: "1.1"
authors:
  - BDC Team
requires:
  - bdc-core-orchestrator
---

# BDC Test Writer - Skill

## Universal Rules

```
1.  Every test follows AAA: Arrange, Act, Assert. Label sections with
    comments when the block exceeds 5 lines.

2.  Test names follow: [method]_[scenario]_[expectedOutcome]
    Example: createCourse_withDuplicateTitle_throwsConflictException

3.  One logical assertion per test. Multiple assert statements are permitted
    only when verifying a single logical outcome (e.g., all fields of a DTO).

4.  No shared mutable state between tests. No ordering dependencies.

5.  No real external services in unit tests. DB, HTTP, Redis, MinIO must be
    mocked or replaced with in-memory substitutes.

6.  Tests must be deterministic. Seed or fix any random values, timestamps,
    or UUIDs in the Arrange phase.

7.  Test code follows the same standards as application code.

8.  Every bug fix must include a regression test that reproduces the bug
    before the fix is applied.

9.  Do not test framework behaviour. Only test code you own.
```

---

## Coverage Targets (Minimum, Enforced in CI)

| Layer | Target |
|-------|--------|
| Service | 80% line coverage |
| Repository | 70% line coverage |
| Controller / Handler | 70% line coverage |
| Overall per service | 70% line coverage |

---

## Java / Spring Boot

### Test Stack

```
JUnit 5, Mockito, MockMvc, @DataJpaTest (H2), @SpringBootTest, AssertJ
```

### Naming

```java
// Class: [ClassUnderTest]Test
class AuthServiceTest { }

// Method: [method]_[scenario]_[expectedOutcome]
@Test void login_withValidCredentials_returnsJwtToken() { }
@Test void bulkRegister_withDuplicateEmail_skipsExistingUser() { }
```

### Service Unit Test

```java
@ExtendWith(MockitoExtension.class)
class AuthServiceTest {
    @Mock  private UserRepository userRepository;
    @Mock  private JwtService jwtService;
    @Mock  private PasswordEncoder passwordEncoder;
    @InjectMocks private AuthService authService;

    @Test
    void login_withValidCredentials_returnsAuthResponseWithToken() {
        // Arrange
        LoginRequest request = LoginRequest.builder()
            .email("student@bdc.com").password("correct-password").build();
        User user = User.builder()
            .id(1L).email("student@bdc.com")
            .password("$2a$encoded").role(UserRole.ROLE_USER).build();

        when(userRepository.findByEmail("student@bdc.com")).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("correct-password", "$2a$encoded")).thenReturn(true);
        when(jwtService.generateToken(user)).thenReturn("mock.jwt.token");

        // Act
        AuthResponse response = authService.login(request);

        // Assert
        assertThat(response.getToken()).isEqualTo("mock.jwt.token");
        verify(jwtService, times(1)).generateToken(user);
    }

    @Test
    void login_withNonExistentEmail_throwsResourceNotFoundException() {
        // Arrange
        when(userRepository.findByEmail("ghost@bdc.com")).thenReturn(Optional.empty());

        // Act & Assert
        assertThatThrownBy(() -> authService.login(
            LoginRequest.builder().email("ghost@bdc.com").password("any").build()
        ))
            .isInstanceOf(ResourceNotFoundException.class)
            .hasMessageContaining("ghost@bdc.com");

        verify(jwtService, never()).generateToken(any());
    }
}
```

### Repository Test

```java
@DataJpaTest
@ActiveProfiles("test")
class UserRepositoryTest {
    @Autowired UserRepository userRepository;
    @Autowired TestEntityManager entityManager;

    @Test
    void findByEmail_withExistingEmail_returnsUser() {
        // Arrange
        entityManager.persistAndFlush(User.builder()
            .email("test@bdc.com").fullName("Test User")
            .password("encoded").role(UserRole.ROLE_USER).build());

        // Act
        Optional<User> result = userRepository.findByEmail("test@bdc.com");

        // Assert
        assertThat(result).isPresent();
        assertThat(result.get().getFullName()).isEqualTo("Test User");
    }
}
```

### Controller Test

```java
@WebMvcTest(AuthController.class)
@ActiveProfiles("test")
class AuthControllerTest {
    @Autowired MockMvc mockMvc;
    @MockBean  AuthService authService;
    @Autowired ObjectMapper objectMapper;

    @Test
    void login_withValidBody_returns200WithToken() throws Exception {
        // Arrange
        when(authService.login(any()))
            .thenReturn(AuthResponse.builder().token("mock.jwt.token").build());

        // Act & Assert
        mockMvc.perform(post("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(
                LoginRequest.builder().email("u@b.com").password("pw").build())))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token").value("mock.jwt.token"));
    }

    @Test
    void login_withMissingEmail_returns400() throws Exception {
        mockMvc.perform(post("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"password\":\"pw\"}"))
            .andExpect(status().isBadRequest());
        verify(authService, never()).login(any());
    }
}
```

### test application-test.yaml

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1;MODE=PostgreSQL
    driver-class-name: org.h2.Driver
  jpa:
    hibernate.ddl-auto: create-drop
    database-platform: org.hibernate.dialect.H2Dialect
jwt:
  secret: test-secret-key-must-be-at-least-32-chars-long
  expiration: 3600000
```

---

## Go (lms-service)

### Test Stack

```
testing, testify/assert, testify/mock, go-sqlmock, net/http/httptest
```

### Naming

```go
func TestCourseService_CreateCourse_WithValidInput_ReturnsCourse(t *testing.T) {}
func TestCourseHandler_Create_WithMissingTitle_Returns400(t *testing.T) {}
```

### Service Test (sqlmock)

```go
func TestCourseService_CreateCourse_WithValidInput_ReturnsCourse(t *testing.T) {
    // Arrange
    db, mock, err := sqlmock.New()
    require.NoError(t, err)
    defer db.Close()

    mock.ExpectQuery(`INSERT INTO courses`).
        WithArgs("Go Fundamentals", "Introduction to Go", int64(1)).
        WillReturnRows(sqlmock.NewRows([]string{"id", "created_at"}).
            AddRow(int64(42), time.Now()))

    svc := service.NewCourseService(repository.NewCourseRepository(db))

    // Act
    result, err := svc.CreateCourse(context.Background(),
        &dto.CreateCourseRequest{Title: "Go Fundamentals", Description: "Introduction to Go"},
        int64(1), "TEACHER")

    // Assert
    require.NoError(t, err)
    assert.Equal(t, int64(42), result.ID)
    assert.NoError(t, mock.ExpectationsWereMet())
}
```

### Handler Test (httptest)

```go
func TestCourseHandler_Create_WithValidBody_Returns201(t *testing.T) {
    // Arrange
    mockSvc := new(MockCourseService)
    mockSvc.On("CreateCourse", mock.Anything, mock.Anything, int64(1), "TEACHER").
        Return(&dto.CourseResponse{ID: 42, Title: "Go Fundamentals"}, nil)

    gin.SetMode(gin.TestMode)
    r := gin.New()
    r.Use(func(c *gin.Context) {
        c.Set("user_id", int64(1))
        c.Set("user_role", "TEACHER")
        c.Next()
    })
    r.POST("/api/v1/courses", handler.NewCourseHandler(mockSvc).Create)

    body, _ := json.Marshal(dto.CreateCourseRequest{Title: "Go Fundamentals"})
    req := httptest.NewRequest(http.MethodPost, "/api/v1/courses", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    w := httptest.NewRecorder()

    // Act
    r.ServeHTTP(w, req)

    // Assert
    assert.Equal(t, http.StatusCreated, w.Code)
    mockSvc.AssertExpectations(t)
}
```

### Run Commands

```bash
go test ./...                  # All tests
go test -race ./...            # Race condition check (required in CI)
go test -coverprofile=c.out ./...
go tool cover -html=c.out      # Visual report
go vet ./...                   # Must pass before commit
```

---

## Python / FastAPI (ai-service)

### Test Stack

```
pytest, pytest-asyncio, httpx (AsyncClient), unittest.mock (AsyncMock)
```

### conftest.py

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from app.main import app
from app.core.config import settings

@pytest.fixture
def ai_secret_header():
    return {"X-AI-Secret": settings.AI_SERVICE_SECRET}

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture(autouse=True)
def patch_llm():
    with patch("app.core.llm.get_llm") as mock_llm, \
         patch("app.core.llm.get_embedding_model") as mock_embed:
        mock_llm.return_value  = AsyncMock()
        mock_embed.return_value = AsyncMock()
        yield

@pytest.fixture(autouse=True)
def kafka_mock():
    with patch("app.worker.kafka_producer.producer", new_callable=AsyncMock):
        yield
```

### Endpoint Test

```python
pytestmark = pytest.mark.asyncio

async def test_diagnose_with_valid_request_returns_explanation(client, ai_secret_header):
    # Arrange
    expected = {"explanation": "...", "confidence": 0.87}
    with patch("app.api.endpoints.diagnose.diagnose_error", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = expected

        # Act
        response = await client.post("/ai/diagnose", headers=ai_secret_header,
            json={"student_id":1,"attempt_id":10,"question_id":3,
                  "wrong_answer":"B","course_id":1})

    # Assert
    assert response.status_code == 200
    assert response.json()["explanation"] == "..."
    mock_svc.assert_called_once()

async def test_diagnose_without_auth_returns_403(client):
    response = await client.post("/ai/diagnose",
        json={"student_id":1,"attempt_id":1,"question_id":1,"wrong_answer":"A","course_id":1})
    assert response.status_code == 403
```

### Kafka Worker Test

```python
async def test_process_ai_command_success_publishes_completed_status():
    payload = {"command_type": "GENERATE_QUIZ", "job_id": "test-job-1"}

    with patch("app.worker.kafka_worker.quiz_service.generate_for_node",
               new_callable=AsyncMock) as mock_gen, \
         patch("app.worker.kafka_worker.publish_ai_job_status",
               new_callable=AsyncMock) as mock_pub:
        mock_gen.return_value = [1, 2, 3]

        from app.worker.kafka_worker import process_ai_command
        await process_ai_command(payload)

    assert mock_pub.call_count == 2  # processing + completed
    mock_pub.assert_called_with("test-job-1", "completed", result=[1, 2, 3])

async def test_process_ai_command_failure_publishes_failed_status():
    payload = {"command_type": "GENERATE_QUIZ", "job_id": "test-job-fail"}

    with patch("app.worker.kafka_worker.quiz_service.generate_for_node",
               new_callable=AsyncMock) as mock_gen, \
         patch("app.worker.kafka_worker.publish_ai_job_status",
               new_callable=AsyncMock) as mock_pub:
        mock_gen.side_effect = ValueError("LLM overload")

        from app.worker.kafka_worker import process_ai_command
        await process_ai_command(payload)

    mock_pub.assert_called_with("test-job-fail", "failed", error="LLM overload")
```

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
markers =
    integration: requires external services
    slow: takes > 5 seconds
```

### Run Commands

```bash
pytest                                        # All tests
pytest -v                                    # Verbose
pytest --cov=app --cov-report=term-missing   # With coverage
pytest -k "diagnose" -v                      # By name pattern
pytest -m "not integration" -v               # Exclude integration
```

---

## What Must Be Tested

| Layer | Required Cases |
|-------|---------------|
| Service method | Happy path, each error path, authorization boundary |
| Repository | Returns correct result, empty on not found, handles DB errors |
| Controller / Endpoint | 2xx valid input, 400/422 invalid input, 401/403 auth, 404/500 service error |
| Kafka Worker | Successful path, failure publishes error status |
| Pure utility function | All branches, edge cases (empty input, max bounds) |

## What Must NOT Be Tested

- Framework internals (Spring Security filters, Gin routing, FastAPI validation)
- Generated code (Lombok getters/setters, Swagger stubs)
- Third-party library behaviour (JWT encoding, bcrypt)
- Trivial getters and setters with no logic

---

## CI Test Commands

```bash
# Auth service
./mvnw test -Dspring.profiles.active=test

# LMS service
go test -race ./...

# AI service
pytest --cov=app --cov-fail-under=70
```

---

## Test Checklist

```
[ ] Name follows [method]_[scenario]_[expectedOutcome]
[ ] AAA structure clear - sections labeled if body > 5 lines
[ ] No real DB, network, or filesystem calls in unit tests
[ ] All mocks verified (verify(), AssertExpectations(), assert_called_once())
[ ] At least one negative/error path per happy path
[ ] No shared mutable state between tests
[ ] Deterministic - no unseeded random or time.Now()
[ ] Table-driven / parametrized for multiple input variants
[ ] conftest fixtures used instead of copy-pasted Arrange blocks
[ ] Bug fix includes regression test
[ ] Coverage does not drop below threshold
```