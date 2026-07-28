import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import exec from 'k6/execution';

/*
 * Production-safe performance suite.
 *
 * The script only performs login plus GET requests. It never creates, edits,
 * enrolls, submits, uploads, or deletes data. Set the account lists to
 * dedicated performance-test accounts; credentials are supplied at runtime,
 * never committed here.
 */

const BASE_URL = (__ENV.BASE_URL || 'https://bdc.hpcc.vn').replace(/\/$/, '');
const COURSE_ID = __ENV.COURSE_ID;
const TEST_ID = __ENV.TEST_ID || `manual-${Date.now()}`;
const PROFILE = __ENV.TEST_TYPE || 'smoke';

function required(name) {
  const value = __ENV[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function accounts(name) {
  try {
    const parsed = JSON.parse(required(name));
    if (!Array.isArray(parsed) || parsed.length === 0) throw new Error('must be a non-empty JSON array');
    for (const account of parsed) {
      if (!account.email || !account.password) throw new Error('every account must contain email and password');
    }
    return parsed;
  } catch (error) {
    throw new Error(`${name} must be a JSON array of {email,password}: ${error.message}`);
  }
}

const STUDENTS = accounts('STUDENT_ACCOUNTS');
const TEACHERS = accounts('TEACHER_ACCOUNTS');
const ADMINS = accounts('ADMIN_ACCOUNTS');

if (!COURSE_ID) throw new Error('COURSE_ID is required');

const profiles = {
  smoke: [{
    duration: __ENV.SMOKE_DURATION || '1m',
    target: Number(__ENV.SMOKE_VUS || 5),
  }],
  load: [
    { duration: '2m', target: Number(__ENV.LOAD_VUS || 25) },
    { duration: '5m', target: Number(__ENV.LOAD_VUS || 25) },
    { duration: '1m', target: 0 },
  ],
  stress: [
    { duration: '2m', target: Number(__ENV.STRESS_STEP_1_VUS || 50) },
    { duration: '3m', target: Number(__ENV.STRESS_STEP_2_VUS || 100) },
    { duration: '3m', target: Number(__ENV.STRESS_MAX_VUS || 200) },
    { duration: '2m', target: 0 },
  ],
  spike: [
    { duration: '30s', target: Number(__ENV.SPIKE_VUS || 150) },
    { duration: '2m', target: Number(__ENV.SPIKE_VUS || 150) },
    { duration: '30s', target: 0 },
  ],
  soak: [
    { duration: '5m', target: Number(__ENV.SOAK_VUS || 25) },
    { duration: __ENV.SOAK_DURATION || '2h', target: Number(__ENV.SOAK_VUS || 25) },
    { duration: '5m', target: 0 },
  ],
};

if (!profiles[PROFILE]) throw new Error(`unknown TEST_TYPE ${PROFILE}; use smoke, load, stress, spike, or soak`);

export const options = {
  tags: { testid: TEST_ID, profile: PROFILE },
  scenarios: {
    core_journeys: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: profiles[PROFILE],
      gracefulRampDown: '30s',
      exec: 'coreJourney',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800', 'p(99)<2000'],
    journey_failed: ['rate<0.01'],
  },
};

const journeys = new Counter('journeys');
const journeyFailed = new Rate('journey_failed');
const journeyDuration = new Trend('journey_duration', true);

function roleForVu() {
  // Stable 85/12/3 production mix without sharing a global mutable counter.
  const slot = (exec.vu.idInTest - 1) % 100;
  if (slot < 85) return 'student';
  if (slot < 97) return 'teacher';
  return 'admin';
}

function accountFor(role) {
  const pool = role === 'student' ? STUDENTS : role === 'teacher' ? TEACHERS : ADMINS;
  return pool[(exec.vu.idInTest - 1) % pool.length];
}

function request(method, path, params = {}) {
  const { body, tags: suppliedTags, ...requestParams } = params;
  const tags = { name: `${method} ${path.replace(/\/[0-9]+/g, '/:id')}`, ...suppliedTags };
  const response = http.request(method, `${BASE_URL}${path}`, body || null, {
    ...requestParams,
    tags,
  });
  const ok = check(response, {
    [`${tags.name} returns 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });
  return { response, ok };
}

function login(account) {
  const result = request('POST', '/apiv1/api/auth/login', {
    body: JSON.stringify({ email: account.email, password: account.password }),
    headers: { 'Content-Type': 'application/json' },
  });
  if (!result.ok) return null;
  const payload = result.response.json();
  return payload && payload.token ? payload.token : null;
}

function auth(token) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

function studentJourney(token) {
  let ok = true;
  group('student-read-journey', () => {
    ok = request('GET', '/lmsapiv1/courses', auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}`, auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}/my-progress`, auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}/progress-detail`, auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}/flashcards/due`, auth(token)).ok && ok;
    ok = request('GET', '/lmsapiv1/analytics/heatmap/me', auth(token)).ok && ok;
    ok = request('GET', '/chatapiv1/chat/channels', auth(token)).ok && ok;
  });
  return ok;
}

function teacherJourney(token) {
  let ok = true;
  group('teacher-read-journey', () => {
    ok = request('GET', '/lmsapiv1/courses/my', auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}`, auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}/student-progress-overview`, auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}/quiz-analytics`, auth(token)).ok && ok;
    ok = request('GET', '/lmsapiv1/analytics/teacher-dashboard', auth(token)).ok && ok;
  });
  return ok;
}

function adminJourney(token) {
  let ok = true;
  group('admin-read-journey', () => {
    ok = request('GET', '/apiv1/api/admin/roles', auth(token)).ok && ok;
    ok = request('GET', '/apiv1/api/admin/permissions', auth(token)).ok && ok;
    ok = request('GET', `/lmsapiv1/courses/${COURSE_ID}/student-progress-overview`, auth(token)).ok && ok;
  });
  return ok;
}

export function coreJourney() {
  const started = Date.now();
  const role = roleForVu();
  const token = login(accountFor(role));
  let ok = Boolean(token);

  if (token) {
    if (role === 'student') ok = studentJourney(token);
    if (role === 'teacher') ok = teacherJourney(token);
    if (role === 'admin') ok = adminJourney(token);
  }

  journeys.add(1, { journey: role });
  journeyFailed.add(!ok, { journey: role });
  journeyDuration.add(Date.now() - started, { journey: role });
  sleep(Number(__ENV.THINK_TIME_SECONDS || 1));
}
