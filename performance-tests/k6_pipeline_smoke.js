import http from 'k6/http';
import { check, sleep } from 'k6';

// This verifies only the k6 → Prometheus remote-write → Grafana pipeline.
// It is deliberately public, read-only, and independent of test accounts.
const BASE_URL = (__ENV.BASE_URL || 'https://bdc.hpcc.vn').replace(/\/$/, '');

export const options = {
  vus: Number(__ENV.SMOKE_VUS || 5),
  duration: __ENV.SMOKE_DURATION || '1m',
  tags: { testid: __ENV.TEST_ID || 'pipeline-smoke', profile: 'smoke' },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
};

export default function () {
  const homepage = http.get(`${BASE_URL}/`, { tags: { name: 'GET /' } });
  check(homepage, { 'homepage is 200': (response) => response.status === 200 });

  const authHealth = http.get(`${BASE_URL}/apiv1/actuator/health`, {
    tags: { name: 'GET auth health' },
  });
  check(authHealth, { 'auth health is 200': (response) => response.status === 200 });
  sleep(1);
}
