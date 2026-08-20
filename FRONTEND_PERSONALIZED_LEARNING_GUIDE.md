# Frontend Integration Guide - Personalized Learning

## Quick Start

Personalized Learning components đã được tích hợp vào production frontend tại:
- **Student Dashboard** (`/lms/student`)
- **Course Discovery** (`/lms/student/discover`)

## Components đã tích hợp

### 1. Student Dashboard (`/lms/student/page.tsx`)

```tsx
import { PersonalizedLearningDashboard } from "@/components/lms/student/PersonalizedLearningDashboard";
import { SkillMasteryOverview } from "@/components/lms/student/SkillMasteryOverview";

// Trong component:
{user && (
  <div className="space-y-6">
    <PersonalizedLearningDashboard
      studentId={user.id}
      onNavigateToLesson={(lessonId) => {
        router.push(`/lms/student/lessons/${lessonId}`);
      }}
    />

    <SkillMasteryOverview studentId={user.id} />
  </div>
)}
```

**Features:**
- Hiển thị daily learning recommendations với priority
- Skill mastery overview với progress bars
- Tự động load data và cache

### 2. Course Discovery (`/lms/student/discover/page.tsx`)

```tsx
import { PersonalizedCourseDiscovery } from "@/components/lms/student/PersonalizedCourseDiscovery";

// Trong component:
{user && !search && selectedTag === "all" && selectedLevel === "all" && (
  <PersonalizedCourseDiscovery
    studentId={user.id}
    onNavigateToCourse={(courseId) => router.push(`/lms/student/discover/${courseId}`)}
    onEnrollCourse={async (courseId) => {
      await enrollmentService.enrollCourse(courseId);
      window.location.reload();
    }}
  />
)}
```

**Features:**
- Skill-based course recommendations
- Match percentage display
- Difficulty level và badges
- Quick enroll action

## Event Tracking

### Quiz Events (Auto-tracked)

Event tracking đã được tích hợp vào `useQuizTaking.ts`:

```typescript
import personalizedLearningTracker from "@/lib/personalized-learning-tracker";

// Tự động track khi student submit answer:
personalizedLearningTracker.trackAnswerSubmitted(
  user.id,
  questionId,
  answerId,
  isCorrect,
  hintsUsed,
  timeSpent,
  difficultyLevel
);
```

**Metrics tracked:**
- Time spent per question
- Answer correctness
- Hints used
- Question difficulty

### Lesson Events (Manual Integration Needed)

Để track lesson events, thêm vào lesson player component:

```typescript
import { useEffect } from "react";
import personalizedLearningTracker from "@/lib/personalized-learning-tracker";

export function LessonPlayer({ lessonId, studentId }: Props) {
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

  // ... rest of component
}
```

## API Service

Service layer đã được tạo tại `frontend/src/services/lms/personalizedLearningService.ts`:

```typescript
import personalizedLearningService from "@/services/lms/personalizedLearningService";

// Get student skills overview
const overview = await personalizedLearningService.getStudentSkillsOverview(studentId);

// Get daily recommendations
const daily = await personalizedLearningService.getDailyRecommendations(studentId);

// Get course discovery recommendations
const courses = await personalizedLearningService.getDiscoverCoursesRecommendations(studentId);

// Get learning trajectory (history)
const trajectory = await personalizedLearningService.getLearningTrajectory(studentId, 30);
```

## Design Compliance

Tất cả components tuân thủ design system:

✅ **Icons**: lucide-react (Target, Brain, Sparkles, TrendingUp, Award...)  
✅ **Colors**: slate, blue, emerald, amber, red với dark mode  
✅ **Borders**: rounded-xl, rounded-2xl  
✅ **Backgrounds**: bg-white dark:bg-[#0F1E35]  
✅ **Hover effects**: smooth transitions  
✅ **Typography**: font-bold, font-semibold với proper sizing  

## Component Props

### PersonalizedLearningDashboard

```typescript
interface Props {
  studentId: number;
  onNavigateToLesson?: (lessonId: number) => void;
}
```

### SkillMasteryOverview

```typescript
interface Props {
  studentId: number;
}
```

### PersonalizedCourseDiscovery

```typescript
interface Props {
  studentId: number;
  onNavigateToCourse?: (courseId: number) => void;
  onEnrollCourse?: (courseId: number) => Promise<void>;
}
```

## Loading States

Components tự động handle loading states:

```tsx
if (loading) {
  return (
    <div className="bg-white dark:bg-[#0F1E35] ... animate-pulse">
      <div className="h-6 w-1/3 bg-slate-200 dark:bg-[#0D192E] rounded ..."></div>
    </div>
  );
}
```

## Error Handling

Components handle errors gracefully và render `null` nếu có lỗi:

```tsx
if (error || !data) {
  return null; // Không làm crash trang
}
```

## Empty States

Components có empty states đẹp:

```tsx
if (data.skills.length === 0) {
  return (
    <div className="bg-white ... text-center">
      <Sparkles className="w-6 h-6" />
      <h3>Bắt đầu hành trình học tập!</h3>
      <p>Hoàn thành bài học đầu tiên...</p>
    </div>
  );
}
```

## Data Flow

```
User Action
    ↓
Event Tracking (personalizedLearningTracker)
    ↓
POST /api/v1/personalized-learning/events
    ↓
LMS Service (Go)
    ↓
Kafka (learning-events topic)
    ↓
Personalize Service (Python)
    ↓
Update Skill States
    ↓
Components fetch updated data
    ↓
UI Updates
```

## Testing

### Test Components Locally

```bash
cd frontend
npm run dev
```

Navigate to:
- `http://localhost:3000/lms/student` - Dashboard
- `http://localhost:3000/lms/student/discover` - Discovery

### Test Event Tracking

Mở browser DevTools → Network → Filter "personalized-learning" để xem events được gửi.

## Performance

- **Caching**: Data cached 5 minutes trong Redis
- **Lazy Loading**: Components only load when visible
- **Debouncing**: API calls debounced để tránh spam
- **Memoization**: useMemo/useCallback để tránh re-render

## Troubleshooting

### Components không hiển thị

1. Kiểm tra `user` object có tồn tại không
2. Kiểm tra API endpoint đã chạy chưa
3. Check console errors
4. Verify migrations đã chạy (V015, V016)

### Events không được track

1. Check personalizedLearningTracker import
2. Verify user.id có giá trị
3. Check network tab xem request có gửi không
4. Verify Kafka consumer đang chạy

### Styles bị lỗi

1. Verify Tailwind config
2. Check dark mode class
3. Clear build cache: `rm -rf .next && npm run dev`

## Next Steps

1. **Map existing content to skills**: Cần populate `content_skills` và `question_skills` tables
2. **Add lesson tracking**: Tích hợp vào lesson player component
3. **Test with real data**: Tạo test accounts và thực hiện learning activities
4. **Monitor performance**: Theo dõi API response times và event ingestion rate
5. **A/B testing**: Test recommendation quality với real users

## Support

Nếu có vấn đề, check:
- `PERSONALIZED_LEARNING_SUMMARY.md` - Full implementation details
- `docs/PERSONALIZED_LEARNING_INTEGRATION.md` - Backend integration guide
- Console logs và network tab
- Backend service logs
