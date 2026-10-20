#!/bin/sh
# Prometheus entrypoint — substitutes the bearer token into the scrape config.
# Used because the prom/prometheus image is busybox-based (no envsubst).
#
# Writes PROMETHEUS_SCRAPE_TOKEN (falls back to API_KEY) to the credentials
# file referenced by prometheus.yml, then launches Prometheus.

set -e

TOKEN="${PROMETHEUS_SCRAPE_TOKEN:-${API_KEY:-}}"
if [ -z "$TOKEN" ]; then
    echo "[WARN] PROMETHEUS_SCRAPE_TOKEN/API_KEY not set — scrapes of gated /metrics will fail." >&2
fi
printf '%s' "$TOKEN" > /etc/prometheus/scrape_token

exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.path=/prometheus \
    --web.enable-lifecycle \
    "$@"