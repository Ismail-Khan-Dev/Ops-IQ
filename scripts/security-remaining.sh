#!/usr/bin/env bash
set -uo pipefail
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
ISSUES=0
WARNINGS=0

echo -e "${YELLOW}[1/5] Checking Docker secrets in compose files...${NC}"
SECR=$(grep -n 'SECRET_KEY\|API_KEY\|PASSWORD' /tmp/scan/docker-compose.yml /tmp/scan/docker-compose.override.yml 2>/dev/null | grep -v 'ENV\|env\|#' | grep -v '${' || true)
if [ -n "$SECR" ]; then echo -e "${RED}FOUND:${NC} $SECR"; ISSUES=$((ISSUES+1)); else echo -e "${GREEN}Clean${NC}"; fi

echo -e "\n${YELLOW}[2/5] Checking .gitignore coverage...${NC}"
MISSING=""
for p in ".env" ".env.local" "*.pem" "*.key" "*.p12" "__pycache__" "node_modules"; do
  if ! grep -q "$p" /tmp/scan/.gitignore 2>/dev/null; then MISSING="$MISSING $p"; fi
done
if [ -n "$MISSING" ]; then echo -e "${YELLOW}Missing:${NC}$MISSING"; WARNINGS=$((WARNINGS+1)); else echo -e "${GREEN}Complete${NC}"; fi

echo -e "\n${YELLOW}[3/5] Checking for hardcoded API keys/tokens...${NC}"
KEYS=$(grep -rn 'sk-live-\|sk-test-\|akia\|AIza\|ghp_\|glpat-' --include="*.py" --include="*.ts" --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" /tmp/scan/ 2>/dev/null || true)
if [ -n "$KEYS" ]; then echo -e "${RED}FOUND:${NC} $KEYS"; ISSUES=$((ISSUES+1)); else echo -e "${GREEN}Clean${NC}"; fi

echo -e "\n${YELLOW}[4/5] Checking SSL verify=False...${NC}"
SSL=$(grep -rn 'verify=False' --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" /tmp/scan/ 2>/dev/null || true)
if [ -n "$SSL" ]; then echo -e "${YELLOW}Warning:${NC} $SSL"; WARNINGS=$((WARNINGS+1)); else echo -e "${GREEN}Clean${NC}"; fi

echo -e "\n${YELLOW}[5/5] Checking DEBUG=True in code...${NC}"
DBG=$(grep -rn 'DEBUG.*True' --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" /tmp/scan/ 2>/dev/null | grep -v 'logger\|logging' || true)
if [ -n "$DBG" ]; then echo -e "${YELLOW}Warning:${NC} $DBG"; WARNINGS=$((WARNINGS+1)); else echo -e "${GREEN}Clean${NC}"; fi

echo -e "\n${YELLOW}========================================${NC}"
echo -e "  ${RED}Critical: $ISSUES${NC}  ${YELLOW}Warnings: $WARNINGS${NC}"
if [ $ISSUES -eq 0 ]; then echo -e "${GREEN}PASSED${NC}"; else echo -e "${RED}FAILED${NC}"; fi
exit $ISSUES
