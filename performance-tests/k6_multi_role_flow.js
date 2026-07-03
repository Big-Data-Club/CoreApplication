import http from 'k6/http';
import { sleep, check } from 'k6';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// =============================================================================
// k6 Load Testing Configuration (Multi-Role Distribution)
// =============================================================================
export const options = {
  scenarios: {
    // 1. Student Journey (85% of active workload)
    student_scenario: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 40,
      maxVUs: 150,
      stages: [
        { duration: '1m', target: 10 },  // Ramp-up
        { duration: '3m', target: 45 },  // Peak student load
        { duration: '2m', target: 0 },   // Ramp-down
      ],
      exec: 'studentJourney',
    },
    // 2. Teacher Journey (12% of active workload)
    teacher_scenario: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '5s',                    // Lower arrival rate
      preAllocatedVUs: 5,
      maxVUs: 20,
      stages: [
        { duration: '1m', target: 2 },   // Ramp-up
        { duration: '3m', target: 5 },   // Peak teacher editing/analytics load
        { duration: '2m', target: 0 },   // Ramp-down
      ],
      exec: 'teacherJourney',
    },
    // 3. Admin Journey (3% of active workload - administrative tasks)
    admin_scenario: {
      executor: 'shared-iterations',
      vus: 2,                            // Exactly 2 admin virtual users
      iterations: 10,                    // Total iterations
      maxDuration: '6m',
      exec: 'adminJourney',
    },
  },
  thresholds: {
    // SLAs
    http_req_failed: ['rate<0.01'],              // Less than 1% errors
    http_req_duration: ['p(95)<1000', 'p(99)<2500'], // 95% under 1s, 99% under 2.5s
  },
};

// Global Configuration via Environment Variables
const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
const STUDENT_EMAIL = __ENV.STUDENT_EMAIL || 'student@example.com';
const TEACHER_EMAIL = __ENV.TEACHER_EMAIL || 'teacher@example.com';
const ADMIN_EMAIL = __ENV.ADMIN_EMAIL || 'admin@example.com';
const TEST_PASSWORD = __ENV.TEST_PASSWORD || 'password';
const COURSE_ID = parseInt(__ENV.COURSE_ID || '19');
const NODE_ID = parseInt(__ENV.NODE_ID || '2221');
const AI_SERVICE_SECRET = __ENV.AI_SERVICE_SECRET || 'ai-service-secret-change-me';

// Helper function to log in and get token
function authenticate(email, password) {
  const payload = JSON.stringify({ email, password });
  const res = http.post(`${BASE_URL}/apiv1/api/auth/login`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (res.status === 200) {
    return {
      token: res.json('token') || res.json('jwt'),
      userId: res.json('userId') || res.json('id') || 1,
    };
  }
  return null;
}

// =============================================================================
// STUDENT JOURNEY SCENARIO
// =============================================================================
export function studentJourney() {
  const auth = authenticate(STUDENT_EMAIL, TEST_PASSWORD);
  if (!auth) { sleep(2); return; }

  const authHeaders = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${auth.token}`,
  };

  // Browse Courses
  const syllabusRes = http.get(`${BASE_URL}/lmsapiv1/api/v1/courses`, { headers: authHeaders });
  check(syllabusRes, { 'student: get courses ok': (r) => r.status === 200 });
  sleep(randomIntBetween(2, 4));

  // View Lesson
  const viewPayload = JSON.stringify({
    course_id: COURSE_ID,
    lesson_id: null,
    node_id: NODE_ID,
    action_type: 'lesson_view',
  });
  http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, viewPayload, { headers: authHeaders });
  sleep(randomIntBetween(5, 10)); // simulated read time

  // Complete Lesson
  const completePayload = JSON.stringify({
    course_id: COURSE_ID,
    lesson_id: null,
    node_id: NODE_ID,
    action_type: 'lesson_complete',
    payload: { reason: 'k6_multi_role_test' },
  });
  http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, completePayload, { headers: authHeaders });
  sleep(randomIntBetween(2, 5));

  // Flip Flashcard
  if (Math.random() < 0.5) {
    const flipPayload = JSON.stringify({
      course_id: COURSE_ID,
      lesson_id: null,
      node_id: NODE_ID,
      action_type: 'flashcard_flip',
    });
    http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, flipPayload, { headers: authHeaders });
  }

  // Load personalization profile
  const profileRes = http.get(`${BASE_URL}/personalize/student/${auth.userId}/course/${COURSE_ID}`, {
    headers: { 'Content-Type': 'application/json', 'X-AI-Secret': AI_SERVICE_SECRET }
  });
  check(profileRes, { 'student: get personalize profile ok': (r) => r.status === 200 });

  sleep(randomIntBetween(3, 5));
}

// =============================================================================
// TEACHER JOURNEY SCENARIO
// =============================================================================
export function teacherJourney() {
  const auth = authenticate(TEACHER_EMAIL, TEST_PASSWORD);
  if (!auth) { sleep(2); return; }

  const authHeaders = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${auth.token}`,
  };

  // 1. Browse course list
  const coursesRes = http.get(`${BASE_URL}/lmsapiv1/api/v1/courses`, { headers: authHeaders });
  check(coursesRes, { 'teacher: list courses ok': (r) => r.status === 200 });
  sleep(randomIntBetween(2, 4));

  // 2. View Teacher Dashboard metrics
  const dashboardRes = http.get(`${BASE_URL}/lmsapiv1/api/v1/analytics/teacher-dashboard`, { headers: authHeaders });
  check(dashboardRes, { 'teacher: load teacher dashboard ok': (r) => r.status === 200 || r.status === 404 });
  sleep(randomIntBetween(3, 5));

  // 3. View Student Progress Overview for a course
  const progressRes = http.get(`${BASE_URL}/lmsapiv1/api/v1/courses/${COURSE_ID}/student-progress-overview`, { headers: authHeaders });
  check(progressRes, { 'teacher: get progress overview ok': (r) => r.status === 200 || r.status === 404 });
  sleep(randomIntBetween(3, 5));

  // 4. View Quiz Analytics
  const quizAnalyticsRes = http.get(`${BASE_URL}/lmsapiv1/api/v1/courses/${COURSE_ID}/quiz-analytics`, { headers: authHeaders });
  check(quizAnalyticsRes, { 'teacher: get quiz analytics ok': (r) => r.status === 200 || r.status === 404 });

  // 5. Create a draft content (simulated course building)
  const createContentPayload = JSON.stringify({
    title: `Load Test Lesson - ${Date.now()}`,
    type: 'TEXT',
    is_mandatory: false,
    metadata: { content: 'Load testing content body' }
  });
  
  // Note: Standard course editing endpoint would be hit here
  // We check response code, allowing 403 in case role setup varies on current environment
  const editRes = http.post(`${BASE_URL}/lmsapiv1/api/v1/courses`, createContentPayload, { headers: authHeaders });
  check(editRes, { 'teacher: modify course status resolved': (r) => r.status === 200 || r.status === 201 || r.status === 403 || r.status === 404 });

  sleep(randomIntBetween(5, 10));
}

// =============================================================================
// ADMIN JOURNEY SCENARIO (Lakehouse sync operations)
// =============================================================================
export function adminJourney() {
  const auth = authenticate(ADMIN_EMAIL, TEST_PASSWORD);
  if (!auth) { sleep(5); return; }

  const authHeaders = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${auth.token}`,
  };

  // 1. List users (Management)
  const usersRes = http.get(`${BASE_URL}/apiv1/api/users`, { headers: authHeaders });
  check(usersRes, { 'admin: list users ok': (r) => r.status === 200 || r.status === 403 });
  sleep(randomIntBetween(3, 6));

  // 2. Fetch Lakehouse Student Metrics View (Personalize)
  const metricsRes = http.get(`${BASE_URL}/personalize/analytics/gold/student-metrics`, {
    headers: { 'Content-Type': 'application/json', 'X-AI-Secret': AI_SERVICE_SECRET }
  });
  check(metricsRes, { 'admin: get lakehouse metrics ok': (r) => r.status === 200 });
  sleep(randomIntBetween(2, 4));

  // 3. Fetch Lakehouse Struggles View
  const strugglesRes = http.get(`${BASE_URL}/personalize/analytics/gold/concept-struggles`, {
    headers: { 'Content-Type': 'application/json', 'X-AI-Secret': AI_SERVICE_SECRET }
  });
  check(strugglesRes, { 'admin: get lakehouse struggles ok': (r) => r.status === 200 });
  sleep(randomIntBetween(2, 4));

  // 4. Fetch Struggle Alerts
  const alertsRes = http.get(`${BASE_URL}/personalize/analytics/gold/struggle-alerts`, {
    headers: { 'Content-Type': 'application/json', 'X-AI-Secret': AI_SERVICE_SECRET }
  });
  check(alertsRes, { 'admin: get lakehouse alerts ok': (r) => r.status === 200 });
  sleep(randomIntBetween(3, 5));

  // 5. Trigger Parquet Export (heavy DuckDB operation)
  const exportRes = http.post(`${BASE_URL}/personalize/analytics/gold/export`, {}, {
    headers: { 'Content-Type': 'application/json', 'X-AI-Secret': AI_SERVICE_SECRET }
  });
  check(exportRes, { 'admin: trigger parquet export ok': (r) => r.status === 200 });

  sleep(randomIntBetween(5, 10));
}
