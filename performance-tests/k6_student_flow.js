import http from 'k6/http';
import { sleep, check } from 'k6';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// =============================================================================
// k6 Load Testing Configuration
// =============================================================================
export const options = {
  // Scenarios define different stages of our performance test.
  // Below we define a classic Stress Test configuration.
  scenarios: {
    student_journey: {
      executor: 'ramping-arrival-rate', // controls request arrival rate independently of target response times
      startRate: 1,                    // start with 1 user iteration per second
      timeUnit: '1s',
      preAllocatedVUs: 50,             // pre-allocate virtual users pool
      maxVUs: 200,                     // allow scaling up to 200 virtual users
      stages: [
        { duration: '1m', target: 10 },  // Ramp-up: 0 to 10 active student journeys/sec
        { duration: '3m', target: 50 },  // Stress: ramp up to 50 active journeys/sec
        { duration: '2m', target: 50 },  // Sustain: hold at 50 journeys/sec
        { duration: '1m', target: 100 }, // Breakpoint: ramp up to 100 journeys/sec (find the lag breakpoint)
        { duration: '1m', target: 0 },   // Cool down: ramp down to 0
      ],
    },
  },
  thresholds: {
    // SLAs: Define target performance thresholds
    http_req_failed: ['rate<0.01'],             // Error rate must be less than 1%
    http_req_duration: ['p(95)<800', 'p(99)<2000'], // 95% of requests must complete under 800ms, 99% under 2s
  },
};

// Configurable parameters via environment variables
const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000'; // Traefik gateway or localhost
const TEST_EMAIL = __ENV.TEST_EMAIL || 'student@example.com';
const TEST_PASSWORD = __ENV.TEST_PASSWORD || 'password';
const COURSE_ID = parseInt(__ENV.COURSE_ID || '19');
const NODE_ID = parseInt(__ENV.NODE_ID || '2221');

// =============================================================================
// Virtual User (VU) Execution Flow
// =============================================================================
export default function () {
  const headers = { 'Content-Type': 'application/json' };

  // ── STEP 1: AUTHENTICATION ─────────────────────────────────────────────────
  const loginPayload = JSON.stringify({
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
  });
  
  const loginRes = http.post(`${BASE_URL}/apiv1/api/auth/login`, loginPayload, { headers });
  
  const loginOk = check(loginRes, {
    'login status is 200': (r) => r.status === 200,
    'login has token': (r) => r.json('token') !== undefined || r.json('jwt') !== undefined,
  });

  if (!loginOk) {
    sleep(1);
    return;
  }

  // Extract JWT token (handle both "token" or "jwt" depending on endpoint structure)
  const token = loginRes.json('token') || loginRes.json('jwt');
  const userId = loginRes.json('userId') || loginRes.json('id') || 137;
  const authHeaders = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  // Simulated think time (user reading/processing UI)
  sleep(randomIntBetween(1, 2));

  // ── STEP 2: BROWSE COURSE SYLLABUS ─────────────────────────────────────────
  const syllabusRes = http.get(`${BASE_URL}/lmsapiv1/api/v1/courses`, { headers: authHeaders });
  check(syllabusRes, {
    'get courses status is 200': (r) => r.status === 200,
  });

  sleep(randomIntBetween(2, 4));

  // ── STEP 3: VIEW CONTENT (Start Lesson) ────────────────────────────────────
  const viewPayload = JSON.stringify({
    course_id: COURSE_ID,
    lesson_id: null,
    node_id: NODE_ID,
    action_type: 'lesson_view',
  });
  
  const viewRes = http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, viewPayload, { headers: authHeaders });
  check(viewRes, {
    'lesson_view interaction logged': (r) => r.status === 200 || r.status === 201,
  });

  // Simulate active student learning (reading textbook/watching video)
  // Standard think time mimics real human interaction
  sleep(randomIntBetween(5, 10));

  // ── STEP 4: COMPLETE LESSON ────────────────────────────────────────────────
  const completePayload = JSON.stringify({
    course_id: COURSE_ID,
    lesson_id: null,
    node_id: NODE_ID,
    action_type: 'lesson_complete',
    payload: { reason: 'k6_load_test' },
  });
  
  const completeRes = http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, completePayload, { headers: authHeaders });
  check(completeRes, {
    'lesson_complete interaction logged': (r) => r.status === 200 || r.status === 201,
  });

  sleep(randomIntBetween(2, 5));

  // ── STEP 5: SIMULATE MICRO-ACTIONS ─────────────────────────────────────────
  // Roll a dice to decide what active learning features the student engages with
  const roll = Math.random();

  if (roll < 0.3) {
    // 30% chance: flip flashcards
    const flipPayload = JSON.stringify({
      course_id: COURSE_ID,
      lesson_id: null,
      node_id: NODE_ID,
      action_type: 'flashcard_flip',
    });
    const flipRes = http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, flipPayload, { headers: authHeaders });
    check(flipRes, { 'flashcard_flip logged': (r) => r.status === 200 });
    
  } else if (roll < 0.6) {
    // 30% chance: answer a Quick Check question
    const isCorrect = Math.random() > 0.3; // 70% success rate
    
    // Log Quick Check attempt
    const checkAttemptPayload = JSON.stringify({
      course_id: COURSE_ID,
      lesson_id: null,
      node_id: NODE_ID,
      action_type: 'quick_check_attempt',
      score: isCorrect ? 1.0 : 0.0,
      status: isCorrect ? 'correct' : 'incorrect',
    });
    http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, checkAttemptPayload, { headers: authHeaders });

    // Log Quick Check result
    const checkResultPayload = JSON.stringify({
      course_id: COURSE_ID,
      lesson_id: null,
      node_id: NODE_ID,
      action_type: isCorrect ? 'quick_check_correct' : 'quick_check_incorrect',
    });
    const checkRes = http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, checkResultPayload, { headers: authHeaders });
    check(checkRes, { 'quick_check logged': (r) => r.status === 200 });

  } else if (roll < 0.8) {
    // 20% chance: ask AI helper
    const askPayload = JSON.stringify({
      course_id: COURSE_ID,
      lesson_id: null,
      node_id: NODE_ID,
      action_type: 'ask_ai',
    });
    const askRes = http.post(`${BASE_URL}/lmsapiv1/api/v1/analytics/micro-interaction`, askPayload, { headers: authHeaders });
    check(askRes, { 'ask_ai logged': (r) => r.status === 200 });
  }

  sleep(randomIntBetween(2, 4));

  // ── STEP 6: VIEW PERSONALIZATION PROFILE ───────────────────────────────────
  // Note: This hits the personalize-service / DuckDB read queries
  const profileRes = http.get(`${BASE_URL}/personalize/student/${userId}/course/${COURSE_ID}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-AI-Secret': __ENV.AI_SERVICE_SECRET || 'ai-service-secret-change-me'
    }
  });
  check(profileRes, {
    'get personalize profile status is 200': (r) => r.status === 200,
  });

  // Final sleep before loop finishes and user closes page
  sleep(randomIntBetween(3, 5));
}
