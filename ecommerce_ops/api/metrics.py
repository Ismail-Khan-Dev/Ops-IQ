import os

from prometheus_client import Counter, Gauge, Histogram

# When running with multiple gunicorn/uvicorn workers, set
# PROMETHEUS_MULTIPROC_DIR to a shared tmpfs dir so that all workers'
# metrics are aggregated by the pushgateway / /metrics endpoint.
# See: https://github.com/prometheus/client_python#multiprocess-mode-eg-gunicorn
_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

if _MULTIPROC_DIR:
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
    from prometheus_client.multiprocess import MultiProcessCollector

    registry = CollectorRegistry()
    MultiProcessCollector(registry)

    def generate_metrics() -> tuple[bytes, str]:
        """Generate aggregated metrics for the /metrics endpoint (multi-worker)."""
        return generate_latest(registry), CONTENT_TYPE_LATEST
else:
    registry = None

    def generate_metrics() -> tuple[bytes, str]:
        """Generate metrics (single-process fallback)."""
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return generate_latest(), CONTENT_TYPE_LATEST


METRIC_HTTP_REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
METRIC_HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration (seconds)",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
METRIC_DECISIONS_CREATED = Counter(
    "agent_decisions_total", "Total agent decisions created", ["agent", "action_type"]
)
METRIC_DECISIONS_APPROVED = Counter(
    "agent_decisions_approved_total", "Total decisions approved", ["agent"]
)
METRIC_DECISIONS_REJECTED = Counter(
    "agent_decisions_rejected_total", "Total decisions rejected", ["agent"]
)
METRIC_DECISIONS_AUTO_APPROVED = Counter(
    "agent_decisions_auto_approved_total", "Total decisions auto-approved", ["agent"]
)
METRIC_PIPELINE_RUNS = Counter("pipeline_runs_total", "Total pipeline runs", ["status"])
METRIC_LLM_CALL_DURATION = Histogram(
    "llm_call_duration_seconds",
    "LLM call duration (seconds)",
    ["agent"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
METRIC_LLM_CALLS = Counter("llm_calls_total", "Total LLM calls", ["agent", "model"])
METRIC_ACTIVE_AGENTS = Gauge("agent_active_total", "Number of active agents", ["agent"])
METRIC_DB_CONNECTION_POOL = Gauge("db_connection_pool_size", "Database connection pool size")
METRIC_CACHE_HIT_RATIO = Gauge("cache_hit_ratio", "Cache hit ratio (0-1)")
METRIC_QUEUE_DEPTH = Gauge("task_queue_depth", "Current task queue depth")
METRIC_RATE_LIMIT_REJECTED = Counter(
    "rate_limit_rejected_total", "Total requests rejected by rate limiter"
)
METRIC_LEGACY_API_KEY_USES = Counter(
    "legacy_api_key_hash_uses_total",
    "Successful authentications via legacy unsalted SHA-256 API-key hashes",
)
METRIC_LEGACY_API_KEY_REJECTED = Counter(
    "legacy_api_key_hash_rejected_total",
    "Legacy SHA-256 API-key authentications rejected past the sunset date",
)
METRIC_SECURITY_AUDIT_DROPPED = Counter(
    "security_audit_dropped_total",
    "Audit-log rows that failed to persist and were dropped (logged only)",
)
METRIC_AGENT_CONFIDENCE_AVG = Gauge(
    "agent_decisions_confidence_avg", "Average confidence score per agent", ["agent"]
)
METRIC_HITL_QUEUE_DEPTH = Gauge("hitl_queue_depth", "Current HITL queue depth")
METRIC_FINANCIAL_IMPACT = Gauge(
    "financial_impact_total_dollars", "Total financial impact in dollars", ["agent", "action_type"]
)
METRIC_LLM_TOKENS_INPUT = Counter(
    "llm_tokens_input_total", "Total LLM input tokens consumed", ["agent", "model"]
)
METRIC_LLM_TOKENS_OUTPUT = Counter(
    "llm_tokens_output_total", "Total LLM output tokens consumed", ["agent", "model"]
)
METRIC_LLM_COST_DOLLARS = Counter(
    "llm_cost_dollars_total", "Total LLM API cost in USD", ["agent", "model"]
)
METRIC_LLM_DAILY_COST = Gauge("llm_daily_cost_dollars", "Current day LLM spend in USD")
METRIC_LLM_CACHE_HITS = Counter("llm_cache_hits_total", "Total LLM cache hits")
METRIC_LLM_CACHE_MISSES = Counter("llm_cache_misses_total", "Total LLM cache misses")

# ── Live execution (week 8) ─────────────────────────────────
METRIC_SHOP_EXECUTIONS = Counter(
    "shop_executions_total", "Total live Shopify actions attempted", ["action_type", "result"]
)
METRIC_SHOP_EXECUTION_DURATION = Histogram(
    "shop_execution_duration_seconds",
    "Live Shopify action duration (seconds)",
    ["action_type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
METRIC_OUTBOX_DEAD_LETTERS = Counter(
    "outbox_dead_letters_total",
    "Outbox messages that exhausted redelivery retries",
    ["outbox_type"],
)
METRIC_AB_EXPERIMENTS = Counter(
    "ab_experiments_total", "A/B shadow experiments executed", ["agent"]
)
METRIC_AB_DIVERGENCE = Gauge(
    "ab_divergence_score",
    "Current divergence between decision and shadow baseline (0 = identical, 1 = opposite)",
    ["agent"],
)
METRIC_AB_WINNER = Counter(
    "ab_winner_total", "Shadow A/B experiments won per variant", ["variant", "agent"]
)
METRIC_AGENT_EXECUTION_ERRORS = Counter(
    "agent_execution_errors_total", "Agent decision execution errors (auto or HITL)", ["agent"]
)

# ── Per-agent full-lifecycle instrumentation (week 12) ─────
METRIC_AGENT_RUN_DURATION = Histogram(
    "agent_run_duration_seconds",
    "Full agent run duration including LLM + fallback (seconds)",
    ["agent"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
METRIC_AGENT_RUNS_TOTAL = Counter(
    "agent_runs_total", "Total agent runs", ["agent", "status"]
)
METRIC_AGENT_FALLBACK_TOTAL = Counter(
    "agent_fallback_total", "Agent LLM→rule-based fallbacks", ["agent"]
)
METRIC_AGENT_SLO_VIOLATIONS = Counter(
    "agent_slo_violations_total", "Agent SLO violations detected", ["agent", "slo_type"]
)

# ── Outbound webhooks (week 9) ──────────────────────────────
METRIC_OUTBOUND_WEBHOOKS = Counter(
    "outbound_webhooks_total",
    "Outbound webhook deliveries to custom HTTPS endpoints",
    ["event_type", "result"],
)

# ── Secret rotation hygiene (audit remediation) ─────────────
METRIC_SECRET_OVERDUE = Gauge(
    "secret_rotation_overdue_total",
    "Number of tracked secrets whose rotation period has elapsed",
)
METRIC_SECRET_ROTATED = Counter(
    "secret_rotation_rotated_total",
    "Number of times a tracked secret was marked as rotated",
    ["secret_name"],
)
