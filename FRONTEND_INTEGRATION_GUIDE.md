# 🎯 Personalized Learning Engine - Frontend Integration Guide

## Mục tiêu: Tạo trải nghiệm học tập hấp dẫn và động lực cho học viên

---

## 📱 UI Components Cần Tạo

### 1. **Dashboard Homepage - "Học hôm nay"**

```typescript
// components/DailyLearningDashboard.tsx
import { useEffect, useState } from 'react';

interface DailyRecommendation {
  content_id: number;
  content_title: string;
  skill_name: string;
  difficulty: number;
  current_mastery: number;
  target_mastery: number;
  reason: string;
  reason_type: string;
  estimated_minutes: number;
  priority: number;
  badge: string;
  icon: string;
  action_button: string;
  impact_description: string;
}

export function DailyLearningDashboard() {
  const [recommendations, setRecommendations] = useState(null);

  useEffect(() => {
    fetch('/api/v1/students/me/daily-recommendations?time_budget=30')
      .then(res => res.json())
      .then(data => setRecommendations(data.data));
  }, []);

  if (!recommendations) return <Loading />;

  return (
    <div className="daily-learning-container">
      {/* Hero Section với Greeting */}
      <div className="greeting-section">
        <h1 className="text-3xl font-bold">{recommendations.greeting}</h1>
        <p className="text-lg text-gray-600 mt-2">
          {recommendations.motivational_message}
        </p>
        {recommendations.learning_streak > 0 && (
          <div className="streak-badge">
            🔥 Streak {recommendations.learning_streak} ngày
          </div>
        )}
      </div>

      {/* Today's Goal */}
      <div className="goal-card bg-blue-50 p-4 rounded-lg my-4">
        <h3 className="font-semibold">🎯 Mục tiêu hôm nay</h3>
        <p>{recommendations.today_goal}</p>
      </div>

      {/* Priority Recommendations */}
      <section className="priority-recommendations mb-8">
        <h2 className="text-2xl font-bold mb-4">
          ⭐ Nên học ngay
        </h2>
        
        <div className="grid gap-4">
          {recommendations.priority_recommendations.map((rec, idx) => (
            <RecommendationCard
              key={rec.content_id}
              recommendation={rec}
              priority={true}
            />
          ))}
        </div>
      </section>

      {/* Optional Recommendations */}
      {recommendations.optional_recommendations.length > 0 && (
        <section className="optional-recommendations mb-8">
          <h2 className="text-xl font-semibold mb-4">
            💡 Nếu còn thời gian
          </h2>
          
          <div className="grid gap-4">
            {recommendations.optional_recommendations.map((rec) => (
              <RecommendationCard
                key={rec.content_id}
                recommendation={rec}
                priority={false}
              />
            ))}
          </div>
        </section>
      )}

      {/* Skills Needing Review (Spaced Repetition) */}
      {recommendations.skills_needing_review.length > 0 && (
        <section className="review-section">
          <h2 className="text-xl font-semibold mb-4">
            🔄 Kỹ năng cần ôn tập
          </h2>
          <p className="text-gray-600 mb-4">
            Các kỹ năng bạn đã thành thạo nhưng chưa luyện tập gần đây
          </p>
          
          <div className="flex gap-2 flex-wrap">
            {recommendations.skills_needing_review.map((skill) => (
              <ReviewSkillChip key={skill.skill_id} skill={skill} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function RecommendationCard({ recommendation, priority }) {
  const getBorderColor = () => {
    switch (recommendation.reason_type) {
      case 'struggling': return 'border-red-400';
      case 'practice': return 'border-yellow-400';
      case 'advance': return 'border-green-400';
      default: return 'border-blue-400';
    }
  };

  const getBackgroundColor = () => {
    switch (recommendation.reason_type) {
      case 'struggling': return 'bg-red-50';
      case 'practice': return 'bg-yellow-50';
      case 'advance': return 'bg-green-50';
      default: return 'bg-blue-50';
    }
  };

  return (
    <div
      className={`recommendation-card border-l-4 ${getBorderColor()} ${getBackgroundColor()} p-6 rounded-lg hover:shadow-lg transition-shadow cursor-pointer`}
      onClick={() => window.location.href = `/learn/content/${recommendation.content_id}`}
    >
      {priority && (
        <div className="priority-badge bg-orange-500 text-white px-2 py-1 rounded text-xs inline-block mb-2">
          Ưu tiên cao
        </div>
      )}
      
      {recommendation.badge && (
        <span className="badge bg-gray-100 text-gray-700 px-2 py-1 rounded text-sm">
          {recommendation.badge}
        </span>
      )}

      <div className="flex items-start gap-4 mt-2">
        <div className="text-4xl">{recommendation.icon}</div>
        
        <div className="flex-1">
          <h3 className="text-xl font-bold mb-2">
            {recommendation.content_title}
          </h3>
          
          <div className="skill-info text-sm text-gray-600 mb-2">
            Kỹ năng: <span className="font-semibold">{recommendation.skill_name}</span>
          </div>

          <p className="reason text-gray-700 mb-3">
            {recommendation.reason}
          </p>

          {/* Mastery Progress Bar */}
          <div className="mastery-progress mb-3">
            <div className="flex justify-between text-sm mb-1">
              <span>Thành thạo hiện tại</span>
              <span className="font-semibold">
                {Math.round(recommendation.current_mastery * 100)}%
              </span>
            </div>
            <div className="progress-bar bg-gray-200 h-2 rounded-full">
              <div
                className="progress-fill bg-blue-500 h-full rounded-full transition-all"
                style={{ width: `${recommendation.current_mastery * 100}%` }}
              />
            </div>
            
            {recommendation.target_mastery > recommendation.current_mastery && (
              <div className="text-sm text-gray-600 mt-1">
                Mục tiêu: {Math.round(recommendation.target_mastery * 100)}%
              </div>
            )}
          </div>

          <div className="impact-description bg-white p-3 rounded border border-gray-200 mb-3">
            <div className="text-sm font-semibold text-gray-700 mb-1">
              💪 Sau khi hoàn thành:
            </div>
            <div className="text-sm text-gray-600">
              {recommendation.impact_description}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4 text-sm text-gray-600">
              <span>⏱️ {recommendation.estimated_minutes} phút</span>
              <span>📊 Độ khó: {Math.round(recommendation.difficulty * 100)}%</span>
            </div>

            <button className="btn-primary bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 font-semibold">
              {recommendation.action_button}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ReviewSkillChip({ skill }) {
  return (
    <div className="review-chip bg-purple-100 text-purple-700 px-4 py-2 rounded-full text-sm hover:bg-purple-200 cursor-pointer">
      {skill.skill_name} - {Math.round(skill.mastery_score * 100)}% ⭐
    </div>
  );
}
```

---

### 2. **Skills Overview Page - "Kỹ năng của tôi"**

```typescript
// components/SkillsOverview.tsx
export function SkillsOverview() {
  const [overview, setOverview] = useState(null);

  useEffect(() => {
    fetch('/api/v1/students/me/skills-overview')
      .then(res => res.json())
      .then(data => setOverview(data.data));
  }, []);

  if (!overview) return <Loading />;

  return (
    <div className="skills-overview-container">
      {/* Overall Progress Header */}
      <div className="progress-header bg-gradient-to-r from-blue-500 to-purple-600 text-white p-8 rounded-lg mb-8">
        <h1 className="text-3xl font-bold mb-4">Kỹ năng của bạn</h1>
        
        <div className="grid grid-cols-4 gap-4">
          <StatCard
            label="Tổng kỹ năng"
            value={overview.total_skills}
            icon="📚"
          />
          <StatCard
            label="Đã thành thạo"
            value={overview.mastered_skills}
            icon="⭐"
            highlight
          />
          <StatCard
            label="Đang gặp khó khăn"
            value={overview.struggling_skills}
            icon="🔴"
          />
          <StatCard
            label="Tiến độ tổng thể"
            value={`${overview.overall_progress}%`}
            icon="📈"
          />
        </div>

        {/* Overall Progress Bar */}
        <div className="mt-6">
          <div className="flex justify-between text-sm mb-2">
            <span>Tiến độ tổng thể</span>
            <span className="font-bold">{overview.overall_progress}%</span>
          </div>
          <div className="progress-bar bg-white/30 h-4 rounded-full">
            <div
              className="progress-fill bg-white h-full rounded-full transition-all"
              style={{ width: `${overview.overall_progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* Recommended Actions */}
      {overview.recommended_actions.length > 0 && (
        <section className="recommended-actions mb-8">
          <h2 className="text-2xl font-bold mb-4">🎯 Nên làm gì tiếp theo?</h2>
          
          <div className="grid gap-4">
            {overview.recommended_actions.map((action, idx) => (
              <ActionCard key={idx} action={action} />
            ))}
          </div>
        </section>
      )}

      {/* Skills Grid */}
      <section className="skills-grid">
        <h2 className="text-2xl font-bold mb-4">📊 Chi tiết kỹ năng</h2>
        
        <div className="grid gap-4">
          {overview.skills.map((skill) => (
            <SkillDetailCard key={skill.skill_id} skill={skill} />
          ))}
        </div>
      </section>
    </div>
  );
}

function SkillDetailCard({ skill }) {
  const getMasteryColor = () => {
    if (skill.mastery_level === 'mastered') return 'text-green-600';
    if (skill.mastery_level === 'advancing') return 'text-blue-600';
    if (skill.mastery_level === 'developing') return 'text-yellow-600';
    return 'text-red-600';
  };

  const getMasteryBgColor = () => {
    if (skill.mastery_level === 'mastered') return 'bg-green-50';
    if (skill.mastery_level === 'advancing') return 'bg-blue-50';
    if (skill.mastery_level === 'developing') return 'bg-yellow-50';
    return 'bg-red-50';
  };

  const getMasteryLabel = () => {
    switch (skill.mastery_level) {
      case 'mastered': return 'Đã thành thạo';
      case 'advancing': return 'Đang tiến bộ';
      case 'developing': return 'Đang phát triển';
      case 'struggling': return 'Cần ôn tập';
      default: return skill.mastery_level;
    }
  };

  return (
    <div className={`skill-card ${getMasteryBgColor()} border border-gray-200 rounded-lg p-6`}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="text-3xl">{skill.progress_indicator}</div>
          <div>
            <h3 className="text-xl font-bold">{skill.skill_name}</h3>
            {skill.skill_description && (
              <p className="text-sm text-gray-600">{skill.skill_description}</p>
            )}
          </div>
        </div>
        
        <div className={`mastery-badge ${getMasteryColor()} font-semibold px-3 py-1 rounded-full text-sm`}>
          {getMasteryLabel()}
        </div>
      </div>

      {/* Mastery Progress */}
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-600">Mức độ thành thạo</span>
          <span className={`font-bold ${getMasteryColor()}`}>
            {skill.mastery_percentage}%
          </span>
        </div>
        <div className="progress-bar bg-gray-300 h-3 rounded-full overflow-hidden">
          <div
            className={`progress-fill h-full transition-all ${
              skill.mastery_level === 'mastered' ? 'bg-green-500' :
              skill.mastery_level === 'advancing' ? 'bg-blue-500' :
              skill.mastery_level === 'developing' ? 'bg-yellow-500' :
              'bg-red-500'
            }`}
            style={{ width: `${skill.mastery_percentage}%` }}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid grid grid-cols-3 gap-4 mb-4">
        <StatItem
          label="Lần thử"
          value={skill.attempt_count}
          icon="🎯"
        />
        <StatItem
          label="Độ chính xác"
          value={`${Math.round(skill.accuracy * 100)}%`}
          icon="✓"
        />
        <StatItem
          label="Tin cậy"
          value={`${Math.round(skill.confidence_score * 100)}%`}
          icon="📊"
        />
      </div>

      {/* Alerts and Actions */}
      {skill.is_struggling && (
        <div className="alert bg-red-100 border border-red-300 text-red-700 p-3 rounded mb-3">
          ⚠️ Kỹ năng này cần được ôn tập thêm
        </div>
      )}

      {skill.needs_review && (
        <div className="alert bg-purple-100 border border-purple-300 text-purple-700 p-3 rounded mb-3">
          🔄 Đã lâu chưa luyện tập (Spaced Repetition)
        </div>
      )}

      {/* Action Button */}
      <button
        className={`action-btn w-full py-2 rounded font-semibold ${
          skill.is_struggling
            ? 'bg-red-500 hover:bg-red-600 text-white'
            : skill.mastery_level === 'advancing'
            ? 'bg-blue-500 hover:bg-blue-600 text-white'
            : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
        }`}
      >
        {skill.next_action === 'review' && '🔴 Ôn tập ngay'}
        {skill.next_action === 'practice' && '🟡 Luyện tập thêm'}
        {skill.next_action === 'advance' && '🟢 Thử thách mới'}
        {skill.next_action === 'maintain' && '⭐ Duy trì thành thạo'}
      </button>

      {/* Last Practiced */}
      {skill.last_practiced_at && (
        <div className="text-xs text-gray-500 mt-2 text-center">
          Lần cuối luyện: {new Date(skill.last_practiced_at).toLocaleDateString('vi-VN')}
        </div>
      )}
    </div>
  );
}

function ActionCard({ action }) {
  const getActionColor = () => {
    switch (action.action) {
      case 'review': return 'border-red-400 bg-red-50';
      case 'practice': return 'border-yellow-400 bg-yellow-50';
      case 'advance': return 'border-green-400 bg-green-50';
      default: return 'border-blue-400 bg-blue-50';
    }
  };

  return (
    <div className={`action-card border-l-4 ${getActionColor()} p-4 rounded-lg flex items-center justify-between`}>
      <div className="flex items-center gap-3">
        <div className="text-2xl">{action.icon}</div>
        <div>
          <div className="font-semibold">{action.skill_name}</div>
          <div className="text-sm text-gray-600">{action.reason}</div>
        </div>
      </div>
      
      <button className="btn-action bg-white border-2 border-gray-300 px-4 py-2 rounded font-semibold hover:bg-gray-50">
        {action.action_text}
      </button>
    </div>
  );
}

function StatItem({ label, value, icon }) {
  return (
    <div className="stat-item text-center">
      <div className="text-lg mb-1">{icon}</div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-gray-600">{label}</div>
    </div>
  );
}

function StatCard({ label, value, icon, highlight }) {
  return (
    <div className={`stat-card ${highlight ? 'bg-white/20' : 'bg-white/10'} p-4 rounded-lg`}>
      <div className="text-2xl mb-2">{icon}</div>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-sm opacity-90">{label}</div>
    </div>
  );
}
```

---

### 3. **Course Discovery Page - "Khám phá khóa học"**

```typescript
// components/CourseDiscovery.tsx
export function CourseDiscovery() {
  const [recommendations, setRecommendations] = useState(null);

  useEffect(() => {
    fetch('/api/v1/students/me/discover-courses?limit=12')
      .then(res => res.json())
      .then(data => setRecommendations(data.data));
  }, []);

  if (!recommendations) return <Loading />;

  return (
    <div className="course-discovery-container">
      <header className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Khám phá khóa học</h1>
        <p className="text-gray-600">{recommendations.recommendation_reason}</p>
        
        <div className="personalization-badge mt-4 inline-block">
          {recommendations.personalization_level === 'high' && (
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded-full text-sm font-semibold">
              ⭐ Cá nhân hóa cao - Dựa trên hồ sơ học tập của bạn
            </span>
          )}
          {recommendations.personalization_level === 'medium' && (
            <span className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-sm font-semibold">
              💡 Được gợi ý dựa trên kỹ năng bạn đã học
            </span>
          )}
        </div>
      </header>

      <div className="courses-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {recommendations.courses.map((course) => (
          <CourseRecommendationCard key={course.course_id} course={course} />
        ))}
      </div>
    </div>
  );
}

function CourseRecommendationCard({ course }) {
  const getMatchBadge = () => {
    if (course.match_score >= 0.8) return { text: 'Rất phù hợp', color: 'bg-green-500' };
    if (course.match_score >= 0.6) return { text: 'Phù hợp', color: 'bg-blue-500' };
    return { text: 'Khám phá', color: 'bg-gray-500' };
  };

  const matchBadge = getMatchBadge();

  return (
    <div className="course-card bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-xl transition-shadow cursor-pointer">
      {/* Thumbnail */}
      <div className="relative">
        <img
          src={course.thumbnail_url || '/default-course.jpg'}
          alt={course.title}
          className="w-full h-48 object-cover"
        />
        
        {/* Match Score Badge */}
        <div className={`absolute top-4 right-4 ${matchBadge.color} text-white px-3 py-1 rounded-full text-sm font-semibold`}>
          {matchBadge.text}
        </div>

        {/* Course Badge */}
        {course.badge && (
          <div className="absolute top-4 left-4 bg-white/90 px-3 py-1 rounded-full text-sm font-semibold">
            {course.badge}
          </div>
        )}
      </div>

      <div className="p-6">
        {/* Title and Category */}
        <div className="mb-3">
          <span className="text-xs text-gray-500 uppercase">{course.category}</span>
          <h3 className="text-xl font-bold mt-1">{course.title}</h3>
        </div>

        {/* Description */}
        <p className="text-gray-600 text-sm mb-4 line-clamp-2">
          {course.description}
        </p>

        {/* Match Reason */}
        <div className="match-reason bg-blue-50 border border-blue-200 p-3 rounded mb-4">
          <div className="text-xs font-semibold text-blue-700 mb-1">
            Tại sao phù hợp với bạn:
          </div>
          <div className="text-sm text-gray-700">{course.match_reason}</div>
        </div>

        {/* Skills You'll Learn */}
        <div className="mb-4">
          <div className="text-xs font-semibold text-gray-700 mb-2">
            Kỹ năng bạn sẽ học:
          </div>
          <div className="flex flex-wrap gap-2">
            {course.skills_you_will_learn.slice(0, 3).map((skill, idx) => (
              <span key={idx} className="skill-tag bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs">
                {skill}
              </span>
            ))}
          </div>
        </div>

        {/* Relevant Skills (What you already know) */}
        {course.relevant_skills && course.relevant_skills.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-semibold text-green-700 mb-2">
              ✓ Kỹ năng bạn đã có:
            </div>
            <div className="flex flex-wrap gap-2">
              {course.relevant_skills.slice(0, 2).map((skill, idx) => (
                <span key={idx} className="skill-tag bg-green-100 text-green-700 px-2 py-1 rounded text-xs">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Meta Info */}
        <div className="flex items-center justify-between text-sm text-gray-600 mb-4">
          <span>{course.level}</span>
          <span>⏱️ {course.estimated_duration}</span>
          <span>👥 {course.enrollment_count}</span>
        </div>

        {/* Difficulty Match */}
        <div className="difficulty-match mb-4">
          {course.difficulty_match === 'perfect' && (
            <div className="text-sm text-green-600 font-semibold">
              ✓ Độ khó hoàn hảo cho bạn
            </div>
          )}
          {course.difficulty_match === 'challenging' && (
            <div className="text-sm text-orange-600 font-semibold">
              🔥 Thử thách phù hợp
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2">
          <button className="btn-primary flex-1 bg-blue-600 text-white py-2 rounded font-semibold hover:bg-blue-700">
            Đăng ký học
          </button>
          <button className="btn-secondary px-4 border border-gray-300 rounded hover:bg-gray-50">
            Xem chi tiết
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## 🔧 API Integration trong Frontend

### Tracking Learning Events (Quan trọng!)

```typescript
// utils/learningTracker.ts
export class LearningTracker {
  private sessionId: string;

  constructor() {
    this.sessionId = this.generateSessionId();
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  // Track when student opens a lesson
  async trackLessonOpened(lessonId: number, courseId: number) {
    await this.trackEvent({
      event_type: 'lesson_opened',
      course_id: courseId,
      lesson_id: lessonId,
    });
  }

  // Track when student completes a lesson
  async trackLessonCompleted(lessonId: number, courseId: number, timeSpentMs: number) {
    await this.trackEvent({
      event_type: 'lesson_completed',
      course_id: courseId,
      lesson_id: lessonId,
      response_time_ms: timeSpentMs,
    });
  }

  // Track when student answers a question
  async trackAnswerSubmitted(
    questionId: number,
    courseId: number,
    isCorrect: boolean,
    attemptNo: number,
    responseTimeMs: number,
    hintCount: number = 0
  ) {
    await this.trackEvent({
      event_type: 'answer_submitted',
      course_id: courseId,
      question_id: questionId,
      correct: isCorrect,
      attempt_no: attemptNo,
      response_time_ms: responseTimeMs,
      hint_count: hintCount,
    });
  }

  // Track when student requests a hint
  async trackHintRequested(questionId: number, courseId: number) {
    await this.trackEvent({
      event_type: 'hint_requested',
      course_id: courseId,
      question_id: questionId,
    });
  }

  private async trackEvent(event: any) {
    try {
      const response = await fetch('/api/v1/learning-events', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getAccessToken()}`,
        },
        body: JSON.stringify({
          ...event,
          session_id: this.sessionId,
        }),
      });

      if (!response.ok) {
        console.error('Failed to track learning event', await response.text());
      }
    } catch (error) {
      console.error('Error tracking learning event', error);
    }
  }
}

// Singleton instance
export const learningTracker = new LearningTracker();
```

### Usage trong components:

```typescript
// In LessonViewer component
import { learningTracker } from '@/utils/learningTracker';

export function LessonViewer({ lessonId, courseId }) {
  useEffect(() => {
    // Track when lesson is opened
    learningTracker.trackLessonOpened(lessonId, courseId);
    
    const startTime = Date.now();
    
    return () => {
      // Track completion when leaving
      const timeSpent = Date.now() - startTime;
      if (timeSpent > 60000) { // More than 1 minute = serious attempt
        learningTracker.trackLessonCompleted(lessonId, courseId, timeSpent);
      }
    };
  }, [lessonId, courseId]);

  return <div>...</div>;
}

// In QuizQuestion component
export function QuizQuestion({ question, courseId }) {
  const [attemptNo, setAttemptNo] = useState(1);
  const [hintCount, setHintCount] = useState(0);
  const startTime = useRef(Date.now());

  const handleSubmitAnswer = async (answer: string) => {
    const responseTime = Date.now() - startTime.current;
    const isCorrect = checkAnswer(answer);
    
    // Track the answer
    await learningTracker.trackAnswerSubmitted(
      question.id,
      courseId,
      isCorrect,
      attemptNo,
      responseTime,
      hintCount
    );
    
    if (!isCorrect) {
      setAttemptNo(prev => prev + 1);
    }
  };

  const handleRequestHint = () => {
    setHintCount(prev => prev + 1);
    learningTracker.trackHintRequested(question.id, courseId);
  };

  return <div>...</div>;
}
```

---

## 📊 Summary

Tôi đã tạo:

1. ✅ **DTO chuẩn** theo pattern của project
2. ✅ **Handler với API đầy đủ** - không có mock, gọi đúng service
3. ✅ **Frontend components hấp dẫn** với:
   - Dashboard học hàng ngày với greeting & motivation
   - Skills overview với visual progress bars
   - Course discovery với personalized recommendations
   - Learning tracking tự động
4. ✅ **Visual elements** để học viên thấy rõ tiến trình:
   - Progress bars màu sắc
   - Emojis và badges
   - Priority indicators
   - Gamification (streak, achievements)

**Điều quan trọng:** Học viên giờ sẽ thấy được:
- Họ đang ở đâu trong hành trình học tập
- Nên học gì tiếp theo và tại sao
- Tiến bộ của họ qua từng kỹ năng
- Động lực qua streak, badges, achievements

Bạn có muốn tôi tiếp tục implement phần nào khác không?
