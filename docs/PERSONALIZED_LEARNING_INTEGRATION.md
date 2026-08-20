# Personalized Learning Engine - Integration Guide

## Overview

The Personalized Learning Engine provides skill-centric mastery tracking, intelligent recommendations, and adaptive learning paths for students in the LMS platform.

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   LMS Service   │─────▶│  Kafka Topics    │─────▶│ Personalize     │
│   (Go)          │      │  learning-events │      │ Service (Python)│
└─────────────────┘      └──────────────────┘      └─────────────────┘
        │                                                    │
        │                                                    │
        ▼                                                    ▼
┌─────────────────┐                              ┌─────────────────┐
│   PostgreSQL    │                              │   DuckDB        │
│   (OLTP)        │                              │   (Analytics)   │
└─────────────────┘                              └─────────────────┘
        │                                                    │
        │                                                    │
        └────────────────────┬───────────────────────────────┘
                             │
                             ▼
                   ┌─────────────────┐
                   │  Recommender    │
                   │  Service (Python)│
                   └─────────────────┘
```

## Database Schema

### Skills Table
Stores all available skills in the system.

```sql
CREATE TABLE skills (
    skill_id SERIAL PRIMARY KEY,
    skill_name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Learning Events Table
Immutable log of all learning interactions.

```sql
CREATE TABLE learning_events (
    event_id SERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    lesson_id BIGINT,
    question_id BIGINT,
    answer_id BIGINT,
    is_correct BOOLEAN,
    hints_used INTEGER DEFAULT 0,
    time_spent_seconds INTEGER,
    difficulty_level VARCHAR(20),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Event types: lesson_opened, lesson_completed, answer_submitted, hint_requested, skill_reviewed
```

### Learner Skill States Table
Materialized view of current mastery levels.

```sql
CREATE TABLE learner_skill_states (
    state_id SERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,
    skill_id INTEGER NOT NULL REFERENCES skills(skill_id),
    mastery_score DECIMAL(5,2) DEFAULT 0.00,
    mastery_level VARCHAR(20) DEFAULT 'developing',
    total_attempts INTEGER DEFAULT 0,
    correct_attempts INTEGER DEFAULT 0,
    last_practiced_at TIMESTAMP,
    next_review_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, skill_id)
);

-- Mastery levels: struggling (0-40), developing (40-70), advancing (70-85), mastered (85+)
```

## API Endpoints

### 1. Track Learning Event
```http
POST /api/v1/personalized-learning/events
Authorization: Bearer <token>
Content-Type: application/json

{
  "event_type": "answer_submitted",
  "question_id": 123,
  "answer_id": 456,
  "is_correct": true,
  "hints_used": 0,
  "time_spent_seconds": 45,
  "difficulty_level": "medium"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Event tracked successfully",
  "data": {
    "event_id": 789,
    "student_id": 1,
    "event_type": "answer_submitted",
    "timestamp": "2026-08-20T10:30:00Z"
  }
}
```

### 2. Get Student Skills Overview
```http
GET /api/v1/personalized-learning/students/{studentId}/skills/overview
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "student_id": 1,
    "total_skills": 12,
    "struggling_count": 2,
    "developing_count": 5,
    "advancing_count": 3,
    "mastered_count": 2,
    "overall_progress_percentage": 58.5,
    "skills": [
      {
        "skill_id": 1,
        "skill_name": "Loops",
        "mastery_level": "advancing",
        "mastery_percentage": 78,
        "progress_indicator": "78% - Tiến bộ tốt, sắp thành thạo!",
        "next_action": "Luyện tập thêm 2-3 bài để nắm vững",
        "last_practiced": "2026-08-19T14:30:00Z"
      }
    ]
  }
}
```

### 3. Get Daily Recommendations
```http
GET /api/v1/personalized-learning/students/{studentId}/recommendations/daily
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "today": "2026-08-20",
    "message": "Bạn có 3 bài học được gợi ý hôm nay",
    "recommendations": [
      {
        "lesson_id": 45,
        "lesson_name": "Advanced Loop Patterns",
        "course_title": "Python Programming",
        "reason": "Củng cố kỹ năng Loops - bạn đang ở mức advancing",
        "priority": 1,
        "estimated_minutes": 30,
        "skills": ["Loops", "Algorithms"]
      }
    ],
    "total_estimated_minutes": 90
  }
}
```

### 4. Get Discover Courses Recommendations
```http
GET /api/v1/personalized-learning/students/{studentId}/recommendations/discover-courses
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Dựa trên kỹ năng hiện tại, chúng tôi gợi ý 4 khóa học phù hợp",
    "recommendations": [
      {
        "course_id": 12,
        "course_name": "Data Structures & Algorithms",
        "reason": "Phù hợp với kỹ năng Loops và Programming Logic đã thành thạo",
        "match_percentage": 85,
        "difficulty_level": "intermediate",
        "estimated_hours": 40,
        "enrollment_count": 1250,
        "skills": ["Arrays", "Linked Lists", "Trees"],
        "badges": [
          {"text": "Phù hợp với bạn", "color": "blue"},
          {"text": "Phổ biến", "color": "green"}
        ]
      }
    ]
  }
}
```

### 5. Get Learning Trajectory
```http
GET /api/v1/personalized-learning/students/{studentId}/trajectory?days=30
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "student_id": 1,
    "total_events": 156,
    "date_range": {
      "from": "2026-07-21",
      "to": "2026-08-20"
    },
    "events": [
      {
        "event_id": 789,
        "event_type": "answer_submitted",
        "question_text": "What is the output of...",
        "is_correct": true,
        "hints_used": 0,
        "time_spent_seconds": 45,
        "skills": ["Loops", "Logic"],
        "timestamp": "2026-08-20T10:30:00Z"
      }
    ]
  }
}
```

## Frontend Integration

### 1. Import Components

```typescript
// In your student dashboard page
import { PersonalizedLearningDashboard } from "@/components/lms/student/PersonalizedLearningDashboard";
import { SkillMasteryOverview } from "@/components/lms/student/SkillMasteryOverview";
import { PersonalizedCourseDiscovery } from "@/components/lms/student/PersonalizedCourseDiscovery";
```

### 2. Use in Student Dashboard

```tsx
export default function StudentDashboardPage() {
  const { user } = useAuth();
  const router = useRouter();

  const handleNavigateToLesson = (lessonId: number) => {
    router.push(`/lms/lessons/${lessonId}`);
  };

  const handleNavigateToCourse = (courseId: number) => {
    router.push(`/lms/courses/${courseId}`);
  };

  const handleEnrollCourse = async (courseId: number) => {
    // Your enrollment logic
    await enrollmentService.enrollCourse(courseId);
  };

  return (
    <div className="space-y-6">
      {/* Daily Learning Recommendations */}
      <PersonalizedLearningDashboard
        studentId={user.id}
        onNavigateToLesson={handleNavigateToLesson}
      />

      {/* Skills Overview */}
      <SkillMasteryOverview studentId={user.id} />

      {/* Course Discovery */}
      <PersonalizedCourseDiscovery
        studentId={user.id}
        onNavigateToCourse={handleNavigateToCourse}
        onEnrollCourse={handleEnrollCourse}
      />
    </div>
  );
}
```

### 3. Track Learning Events Automatically

```typescript
// In your lesson component
import personalizedLearningTracker from "@/lib/personalized-learning-tracker";

export default function LessonPlayer({ lessonId, studentId }: Props) {
  useEffect(() => {
    // Track lesson opened
    personalizedLearningTracker.trackLessonOpened(studentId, lessonId);

    const startTime = Date.now();
    return () => {
      // Track lesson completed on unmount
      const timeSpent = Math.floor((Date.now() - startTime) / 1000);
      personalizedLearningTracker.trackLessonCompleted(
        studentId,
        lessonId,
        timeSpent
      );
    };
  }, [studentId, lessonId]);

  return <div>...</div>;
}
```

```typescript
// In your quiz component
const handleSubmitAnswer = async (questionId: number, answerId: number) => {
  const result = await quizService.submitAnswer(attemptId, questionId, answerId);

  // Track answer submission
  await personalizedLearningTracker.trackAnswerSubmitted(
    studentId,
    questionId,
    answerId,
    result.is_correct,
    hintsUsed,
    timeSpent,
    question.difficulty_level
  );
};
```

## Backend Services Integration

### LMS Service (Go)

The LMS service handles:
- CRUD operations for skills
- Tracking learning events
- Mapping content/questions to skills
- Serving UI-friendly APIs

**Key files:**
- `lms-service/internal/handler/personalized_learning_handler.go`
- `lms-service/internal/service/learning_event_service.go`
- `lms-service/internal/repository/learning_event_repository.go`
- `lms-service/migrations/V015__personalized_learning_schema.sql`

### Personalize Service (Python)

The personalize service handles:
- Consuming Kafka learning events
- Calculating mastery scores
- Maintaining skill states
- Analytics via DuckDB lakehouse

**Key files:**
- `personalize-service/app/worker/learning_event_worker.py`
- `personalize-service/app/services/mastery_engine.py`
- `personalize-service/app/services/lakehouse.py`

**Mastery Calculation Formula:**
```python
mastery = (accuracy × difficulty_adjustment) 
          - hint_penalty 
          - repeated_failure_penalty 
          + recency_boost
```

### Recommender Service (Python)

The recommender service handles:
- Next-best lesson recommendations
- Personalized course discovery
- Skill-based content matching

**Key files:**
- `recommender-service/app/skill_recommender.py`
- `recommender-service/app/main.py`

## Initial Setup

### 1. Run Database Migrations

```bash
cd lms-service
# Migration will be applied automatically on startup
# or use Flyway/manual migration tool
```

### 2. Seed Initial Skills

```sql
INSERT INTO skills (skill_name, description, category) VALUES
('Loops', 'Understanding for, while, and nested loops', 'Programming Basics'),
('Conditionals', 'If-else statements and logical operators', 'Programming Basics'),
('Functions', 'Defining and calling functions', 'Programming Basics'),
('Arrays', 'Working with arrays and lists', 'Data Structures'),
('Object-Oriented Programming', 'Classes, objects, and inheritance', 'OOP'),
('Recursion', 'Recursive problem solving', 'Algorithms'),
('Sorting', 'Bubble sort, merge sort, quick sort', 'Algorithms'),
('Searching', 'Linear and binary search', 'Algorithms');
```

### 3. Map Content to Skills

```sql
-- Map lessons to skills
INSERT INTO content_skills (content_id, skill_id) VALUES
(1, 1),  -- Lesson 1 teaches Loops
(1, 2),  -- Lesson 1 also teaches Conditionals
(2, 3);  -- Lesson 2 teaches Functions

-- Map questions to skills
INSERT INTO question_skills (question_id, skill_id) VALUES
(101, 1),  -- Question 101 tests Loops
(102, 1),  -- Question 102 also tests Loops
(103, 2);  -- Question 103 tests Conditionals
```

### 4. Start Services

```bash
# Start LMS service
cd lms-service
go run cmd/api/main.go

# Start Personalize service
cd personalize-service
python main.py

# Start Recommender service
cd recommender-service
uvicorn app.main:app --reload
```

## Mastery Level System

| Level       | Score Range | Description                                      | UI Color   |
|-------------|-------------|--------------------------------------------------|------------|
| struggling  | 0-40        | Needs significant practice                       | Red        |
| developing  | 40-70       | Making progress, needs more practice             | Amber      |
| advancing   | 70-85       | Good understanding, near mastery                 | Blue       |
| mastered    | 85-100      | Proficient, ready for spaced repetition          | Green      |

## Recommendation Logic

### Daily Recommendations

1. **Struggling skills** → Foundational lessons (priority 1)
2. **Developing skills** → Practice lessons (priority 2)
3. **Skills needing review** → Spaced repetition (priority 2)
4. **Next logical skill** → Based on prerequisites (priority 3)

### Course Discovery

1. Match student's mastered skills with course prerequisites
2. Calculate match percentage
3. Recommend courses with 60%+ match
4. Consider difficulty level relative to current skills

## Performance Considerations

1. **Caching**: Skill states are cached in Redis with 5-minute TTL
2. **Async Processing**: Events are processed asynchronously via Kafka
3. **Indexes**: Critical indexes on `student_id`, `skill_id`, `timestamp`
4. **Materialized Views**: Skill states are pre-computed for fast reads

## Monitoring

### Key Metrics

- Event ingestion rate (events/second)
- Mastery calculation latency
- Recommendation generation time
- Cache hit rate for skill states

### Logs

- LMS service: `/var/log/lms/personalized-learning.log`
- Personalize service: `/var/log/personalize/mastery-engine.log`
- Recommender service: `/var/log/recommender/recommendations.log`

## Future Enhancements

1. **ML-based mastery calculation** - Replace rule-based with ML model
2. **Collaborative filtering** - Recommend based on similar learners
3. **Learning style adaptation** - Visual, auditory, kinesthetic preferences
4. **Predictive analytics** - Predict struggling students before failure
5. **Gamification** - Badges, streaks, leaderboards based on mastery

## Troubleshooting

### Events not being processed

1. Check Kafka connectivity: `kafka-topics.sh --list`
2. Check consumer lag: `kafka-consumer-groups.sh --describe`
3. Verify personalize service is running: `systemctl status personalize-service`

### Incorrect mastery scores

1. Check mastery engine configuration in `config.py`
2. Verify skill mappings are correct: `SELECT * FROM question_skills`
3. Review recent events: `SELECT * FROM learning_events ORDER BY timestamp DESC LIMIT 100`

### Recommendations not showing

1. Check if student has any skill data: `SELECT * FROM learner_skill_states WHERE student_id = ?`
2. Verify content-skill mappings exist
3. Check recommender service logs for errors

## API Rate Limits

- Event tracking: 100 requests/minute per student
- Skill overview: 30 requests/minute per student
- Recommendations: 20 requests/minute per student

## Support

For issues or questions, contact the LMS development team or file an issue in the repository.
