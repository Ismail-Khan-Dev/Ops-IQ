// OpsIQ API Load Test Suite
// Run: k6 run scripts/load-test.js
// Or via Docker: docker run --rm -i grafana/k6 run - < scripts/load-test.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ── Custom Metrics ──────────────────────────────────────────
const apiErrors = new Counter('api_errors');
const successRate = new Rate('success_rate');
const latencyP95 = new Trend('api_latency_p95', true);

// ── Configuration ───────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'opsiq-dev-key-2024';

export const options = {
  scenarios: {
    // Scenario 1: Steady-state traffic (10 VUs for 1 minute)
    steady: {
      executor: 'constant-vus',
      vus: 10,
      duration: '1m',
      exec: 'steadyTraffic',
    },
    // Scenario 2: Spike test (0 → 50 VUs in 10s, hold 30s, ramp down)
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 50 },
        { duration: '30s', target: 50 },
        { duration: '10s', target: 0 },
      ],
      exec: 'spikeTraffic',
    },
    // Scenario 3: Soak test (gradual ramp to 20 VUs over 2 min)
    soak: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '30s', target: 10 },
        { duration: '30s', target: 15 },
        { duration: '30s', target: 20 },
      ],
      exec: 'soakTraffic',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<2000'],
    http_req_failed: ['rate<0.1'],
    success_rate: ['rate>0.9'],
  },
};

// ── Helpers ─────────────────────────────────────────────────
const headers = {
  'Content-Type': 'application/json',
  'X-API-Key': API_KEY,
};

function authHeaders() {
  return {
    ...headers,
    'Authorization': `Bearer ${API_KEY}`,
  };
}

function randomSleep(min = 0.5, max = 2) {
  sleep(min + Math.random() * (max - min));
}

// ── Scenario: Steady Traffic ────────────────────────────────
export function steadyTraffic() {
  const res = http.get(`${BASE_URL}/health`, { headers, tags: { endpoint: 'health' } });
  check(res, {
    'health: status 200': (r) => r.status === 200,
  });
  successRate.add(res.status === 200);
  apiErrors.add(res.status >= 400);
  latencyP95.add(res.timings.duration);

  randomSleep(0.5, 1.5);

  // Get approvals (authenticated)
  const approvals = http.get(`${BASE_URL}/api/approvals?status=pending`, {
    headers: authHeaders(),
    tags: { endpoint: 'approvals' },
  });
  check(approvals, {
    'approvals: status 200': (r) => r.status === 200,
  });
  successRate.add(approvals.status === 200);
  apiErrors.add(approvals.status >= 400);

  randomSleep(0.5, 1);

  // Get analytics
  const analytics = http.get(`${BASE_URL}/api/analytics`, {
    headers: authHeaders(),
    tags: { endpoint: 'analytics' },
  });
  check(analytics, {
    'analytics: status 200': (r) => r.status === 200,
  });
  successRate.add(analytics.status === 200);
  apiErrors.add(analytics.status >= 400);

  randomSleep(1, 2);
}

// ── Scenario: Spike Traffic ─────────────────────────────────
export function spikeTraffic() {
  const res = http.get(`${BASE_URL}/health`, { headers, tags: { endpoint: 'health' } });
  check(res, { 'spike health: status 200': (r) => r.status === 200 });
  successRate.add(res.status === 200);
  apiErrors.add(res.status >= 400);

  randomSleep(0.1, 0.5);

  const agents = http.get(`${BASE_URL}/api/agents/status`, {
    headers: authHeaders(),
    tags: { endpoint: 'agents' },
  });
  check(agents, { 'spike agents: status 200': (r) => r.status === 200 });
  successRate.add(agents.status === 200);
  apiErrors.add(agents.status >= 400);
}

// ── Scenario: Soak Traffic ──────────────────────────────────
export function soakTraffic() {
  const endpoints = [
    { url: '/health', auth: false },
    { url: '/api/approvals?status=pending', auth: true },
    { url: '/api/analytics', auth: true },
    { url: '/api/agents/status', auth: true },
    { url: '/api/audit?limit=10', auth: true },
    { url: '/api/settings', auth: true },
  ];

  const ep = endpoints[Math.floor(Math.random() * endpoints.length)];
  const h = ep.auth ? authHeaders() : headers;

  const res = http.get(`${BASE_URL}${ep.url}`, {
    headers: h,
    tags: { endpoint: ep.url },
  });

  check(res, {
    [`soak ${ep.url}: status 200`]: (r) => r.status === 200,
  });
  successRate.add(res.status === 200);
  apiErrors.add(res.status >= 400);
  latencyP95.add(res.timings.duration);

  randomSleep(0.5, 2);
}

// ── Summary ─────────────────────────────────────────────────
export function handleSummary(data) {
  const results = data.root_group.checks || [];
  const passed = results.filter((r) => r.passes > 0).length;
  const failed = results.filter((r) => r.fails > 0).length;

  const summary = {
    timestamp: new Date().toISOString(),
    total_requests: data.metrics.http_reqs?.values?.count || 0,
    failed_requests: data.metrics.http_req_failed?.values?.count || 0,
    avg_duration_ms: data.metrics.http_req_duration?.values?.avg?.toFixed(2),
    p95_duration_ms: data.metrics.http_req_duration?.values?.['p(95)']?.toFixed(2),
    p99_duration_ms: data.metrics.http_req_duration?.values?.['p(99)']?.toFixed(2),
    success_rate: data.metrics.success_rate?.values?.rate?.toFixed(4),
    checks_passed: passed,
    checks_failed: failed,
  };

  return {
    stdout: '\n' + JSON.stringify(summary, null, 2) + '\n',
    [`scripts/load-test-report-${Date.now()}.json`]: JSON.stringify(summary, null, 2),
  };
}
