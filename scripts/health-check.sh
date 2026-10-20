#!/usr/bin/env bash
# ── OpsIQ — Health Check Script ─────────────────────────────
# Quick health verification for all services

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}╔══════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║       OpsIQ Health Check                 ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════╝${NC}"

HEALTHY=0
TOTAL=0

check_service() {
    local name=$1
    local url=$2
    local expected=$3
    TOTAL=$((TOTAL + 1))

    if curl -sf "$url" > /dev/null 2>&1; then
        STATUS=$(curl -sf "$url" 2>/dev/null | head -c 100)
        echo -e "${GREEN}✓ $name${NC} — ${STATUS}"
        HEALTHY=$((HEALTHY + 1))
    else
        echo -e "${RED}✗ $name${NC} — Not responding"
    fi
}

echo ""

# API Health
check_service "FastAPI" "http://localhost:8000/live" "OK"
check_service "API Health" "http://localhost:8000/health" ""

# Database
TOTAL=$((TOTAL + 1))
if docker compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL${NC} — Accepting connections"
    HEALTHY=$((HEALTHY + 1))
else
    echo -e "${RED}✗ PostgreSQL${NC} — Not responding"
fi

# Redis
TOTAL=$((TOTAL + 1))
if docker compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Redis${NC} — PONG"
    HEALTHY=$((HEALTHY + 1))
else
    echo -e "${RED}✗ Redis${NC} — Not responding"
fi

# Monitoring
check_service "Prometheus" "http://localhost:9090/-/healthy" ""
check_service "Grafana" "http://localhost:3000/api/health" ""

# Frontend
check_service "Frontend" "http://localhost:3001" ""

# Summary
echo -e "\n${YELLOW}══════════════════════════════════════════${NC}"
echo -e "Result: ${GREEN}$HEALTHY${NC}/$TOTAL services healthy"

if [ $HEALTHY -eq $TOTAL ]; then
    echo -e "${GREEN}✓ All systems operational!${NC}"
    exit 0
elif [ $HEALTHY -gt 0 ]; then
    echo -e "${YELLOW}⚠ Some services are down${NC}"
    exit 1
else
    echo -e "${RED}✗ All services are down${NC}"
    exit 2
fi
