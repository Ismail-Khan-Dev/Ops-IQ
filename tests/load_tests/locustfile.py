"""
Locust Load Test for OpsIQ
Realistic load scenarios for production-like testing.

Usage:
  Interactive:  locust -f tests/load_tests/locustfile.py --host=http://localhost:8000
  Headless:     locust -f tests/load_tests/locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 -t 60s
"""

import random
import uuid

from locust import HttpUser, between, tag, task

API_KEY = "opsiq-dev-key-2024"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


class DashboardUser(HttpUser):
    """Simulates a user browsing the dashboard (read-heavy)."""
    wait_time = between(2, 5)
    weight = 3

    def on_start(self):
        self.client.headers.update(HEADERS)

    @tag("health")
    @task(1)
    def health_check(self):
        self.client.get("/health")

    @tag("dashboard", "approvals")
    @task(5)
    def view_approvals(self):
        self.client.get("/api/approvals?status=pending")

    @tag("dashboard", "analytics")
    @task(3)
    def view_analytics(self):
        self.client.get("/api/analytics")

    @tag("dashboard", "agents")
    @task(3)
    def view_agents(self):
        self.client.get("/api/agents/status")

    @tag("dashboard", "audit")
    @task(2)
    def view_audit(self):
        self.client.get("/api/audit?page=1&limit=20")

    @tag("dashboard", "settings")
    @task(1)
    def view_settings(self):
        self.client.get("/api/settings")

    @tag("metrics")
    @task(1)
    def view_metrics(self):
        self.client.get("/metrics")


class OperatorUser(HttpUser):
    """Simulates an operator approving/rejecting decisions."""
    wait_time = between(3, 8)
    weight = 2

    def on_start(self):
        self.client.headers.update(HEADERS)

    @tag("operator", "approve")
    @task(3)
    def approve_action(self):
        resp = self.client.get("/api/approvals?status=pending")
        if resp.status_code == 200:
            actions = resp.json()
            if actions:
                action = random.choice(actions)
                self.client.post(
                    f"/api/approvals/{action['id']}/approve",
                    json={"notes": "Load test approval"},
                )

    @tag("operator", "reject")
    @task(1)
    def reject_action(self):
        resp = self.client.get("/api/approvals?status=pending")
        if resp.status_code == 200:
            actions = resp.json()
            if actions:
                action = random.choice(actions)
                self.client.post(
                    f"/api/approvals/{action['id']}/reject",
                    json={"reason": "Load test rejection"},
                )

    @tag("operator", "batch")
    @task(1)
    def batch_approve(self):
        resp = self.client.get("/api/approvals?status=pending")
        if resp.status_code == 200:
            actions = resp.json()
            low_risk = [a for a in actions if a.get("risk_level") == "low"]
            if len(low_risk) >= 3:
                ids = [a["id"] for a in low_risk[:5]]
                self.client.post(
                    "/api/approvals/batch",
                    json={"ids": ids, "action": "approve"},
                )

    @tag("operator", "export")
    @task(1)
    def export_audit_csv(self):
        self.client.get("/api/audit/export?format=csv")


class PipelineUser(HttpUser):
    """Simulates pipeline triggers and monitoring."""
    wait_time = between(10, 30)
    weight = 1

    def on_start(self):
        self.client.headers.update(HEADERS)

    @tag("pipeline", "run")
    @task(2)
    def trigger_pipeline(self):
        self.client.post("/api/run")

    @tag("pipeline", "task_status")
    @task(3)
    def check_task_status(self):
        task_id = str(uuid.uuid4())
        self.client.get(f"/api/tasks/{task_id}")

    @tag("pipeline", "observability")
    @task(2)
    def view_traces(self):
        self.client.get("/observability/traces")

    @tag("pipeline", "observability")
    @task(1)
    def view_metrics_summary(self):
        self.client.get("/observability/metrics/summary")

    @tag("pipeline", "observability")
    @task(1)
    def view_cost_metrics(self):
        self.client.get("/observability/metrics/costs")


class SecurityUser(HttpUser):
    """Simulates security and admin operations."""
    wait_time = between(5, 15)
    weight = 1

    def on_start(self):
        self.client.headers.update(HEADERS)

    @tag("security", "users")
    @task(2)
    def list_users(self):
        self.client.get("/security/users")

    @tag("security", "api_keys")
    @task(1)
    def list_api_keys(self):
        self.client.get("/security/api-keys")

    @tag("security", "audit")
    @task(2)
    def audit_summary(self):
        self.client.get("/security/audit/summary")

    @tag("security", "roles")
    @task(1)
    def list_roles(self):
        self.client.get("/security/roles")


class MemoryUser(HttpUser):
    """Simulates memory operations."""
    wait_time = between(3, 8)
    weight = 1

    def on_start(self):
        self.client.headers.update(HEADERS)

    @tag("memory", "search")
    @task(3)
    def search_memories(self):
        self.client.post(
            "/memory/memories/search",
            json={"query": "fraud detection patterns", "max_results": 5},
        )

    @tag("memory", "list")
    @task(2)
    def list_memories(self):
        self.client.get("/memory/memories?limit=20")

    @tag("memory", "sessions")
    @task(1)
    def list_sessions(self):
        self.client.get("/memory/sessions")

    @tag("memory", "health")
    @task(1)
    def memory_health(self):
        self.client.get("/memory/health")
