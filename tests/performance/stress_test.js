import http from "k6/http";
import { check, sleep } from "k6";

// ─── STRESS TEST CONFIGURATION ───────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "30s", target: 20 },  // Ramp-up to 20 virtual users (VUs)
    { duration: "1m", target: 50 },   // Normal load: 50 VUs
    { duration: "1m", target: 200 },  // Stress: ramp up to 200 VUs
    { duration: "30s", target: 500 }, // Spike: ramp up to 500 VUs
    { duration: "1m", target: 0 },    // Ramp-down to 0 VUs
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],   // Request error rate must be less than 1%
    http_req_duration: ["p(95)<300"], // 95% of requests must complete under 300ms
  },
};

// ─── ENVIRONMENT VARIABLES ───────────────────────────────────────────────────
const AUTH_URL = __ENV.AUTH_URL || "http://localhost:8080"; // Auth Service
const LMS_URL = __ENV.LMS_URL || "http://localhost:8081";   // LMS Service
const USER_EMAIL = __ENV.USER_EMAIL || "phucnhan289@gmail.com";
const USER_PASSWORD = __ENV.USER_PASSWORD || "Phucnhan289@";

// Setup function runs ONCE before the test to authenticate and get JWT
export function setup() {
  const loginUrl = `${AUTH_URL}/api/auth/login`;
  const payload = JSON.stringify({
    email: USER_EMAIL,
    password: USER_PASSWORD,
  });
  const params = {
    headers: { "Content-Type": "application/json" },
  };

  const response = http.post(loginUrl, payload, params);
  
  const ok = check(response, {
    "auth success": (r) => r.status === 200,
  });

  if (!ok) {
    console.log(`Auth failed with status ${response.status}: ${response.body}`);
    throw new Error("Authentication failed, cannot run load test!");
  }

  // Extract auth token from response body or set-cookie header
  let token = "";
  try {
    const data = JSON.parse(response.body);
    token = data.token;
  } catch (e) {
    // Fallback: extract from set-cookie header
    const setCookie = response.headers["Set-Cookie"] || response.headers["set-cookie"];
    const match = setCookie ? setCookie.match(/authToken=([^;]+)/) : null;
    token = match ? match[1] : "";
  }

  if (!token) {
    throw new Error("Token not found in response!");
  }

  return { token };
}

// Default function runs repeatedly for each Virtual User (VU)
export default function (data) {
  const url = `${LMS_URL}/api/v1/courses?page=1&page_size=10`;
  const params = {
    headers: {
      "Authorization": `Bearer ${data.token}`,
      "Content-Type": "application/json",
    },
  };

  // Perform request to Course listing endpoint (tests database filters + Redis cache)
  const res = http.get(url, params);

  // Validate response status is 200 OK
  check(res, {
    "status is 200": (r) => r.status === 200,
    "has data": (r) => r.body && r.body.includes("data"),
  });

  // Wait 1 second between requests per VU to simulate realistic user browsing
  sleep(1);
}
