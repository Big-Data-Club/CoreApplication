/**
 * Autocannon Benchmark Script for BDC LMS
 * Run this directly via: node tests/performance/autocannon_test.js
 * (Requires autocannon to be installed or run via npx)
 */

const axios = require("axios");
const autocannon = require("autocannon");

const AUTH_URL = process.env.AUTH_URL || "http://localhost:8080";
const LMS_URL = process.env.LMS_URL || "http://localhost:8081";
const USER_EMAIL = process.env.USER_EMAIL || "phucnhan289@gmail.com";
const USER_PASSWORD = process.env.USER_PASSWORD || "Phucnhan289@";

async function run() {
  console.log("🔑 Authenticating with Auth Service...");
  let token = "";

  try {
    const res = await axios.post(`${AUTH_URL}/api/auth/login`, {
      email: USER_EMAIL,
      password: USER_PASSWORD,
    });
    token = res.data.token;
  } catch (err) {
    console.error("❌ Authentication failed. Make sure Backend is running!");
    console.error(err.message);
    process.exit(1);
  }

  if (!token) {
    console.error("❌ Token not found in login response!");
    process.exit(1);
  }

  console.log("✅ Authenticated successfully.");
  console.log(`🚀 Starting Stress Test on: ${LMS_URL}/api/v1/courses ...`);

  const instance = autocannon({
    url: `${LMS_URL}/api/v1/courses?page=1&page_size=10`,
    connections: 100,          // 100 concurrent connections
    pipelining: 1,             // No pipelining (1 request per connection at a time)
    duration: 30,              // Test duration in seconds
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    }
  }, (err, result) => {
    if (err) {
      console.error("❌ Stress test error:", err);
      return;
    }
    console.log("📈 Stress Test completed successfully!");
  });

  // Track progress and print it to terminal
  autocannon.track(instance, { renderProgressBar: true });
}

run();
