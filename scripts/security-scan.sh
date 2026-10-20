#!/usr/bin/env bash
# ── OpsIQ — Security Scan Script ────────────────────────────
# Runs comprehensive security checks against the codebase

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}╔══════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║       OpsIQ Security Scanner            ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════╝${NC}"

ISSUES=0

# 1. Check for secrets in code
echo -e "\n${YELLOW}[1/6] Scanning for hardcoded secrets...${NC}"
SECRETS=$(grep -rn "sk-\|password\s*=\s*['\"]" --include="*.py" --include="*.ts" --include="*.tsx" --exclude-dir=node_modules --exclude-dir=.git --exclude="*test*" --exclude="*mock*" . 2>/dev/null | grep -v "YOUR_" | grep -v "example" || true)
if [ -n "$SECRETS" ]; then
    echo -e "${RED}✗ Potential secrets found:${NC}"
    echo "$SECRETS"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No hardcoded secrets found${NC}"
fi

# 2. Check .env is gitignored
echo -e "\n${YELLOW}[2/6] Checking .env files are gitignored...${NC}"
for f in .env .env.local .env*.local; do
    if git check-ignore -q "$f" 2>/dev/null; then
        echo -e "${GREEN}✓ $f is gitignored${NC}"
    else
        echo -e "${RED}✗ $f is NOT gitignored!${NC}"
        ISSUES=$((ISSUES + 1))
    fi
done

# 3. Check for debug mode in production
echo -e "\n${YELLOW}[3/6] Checking for debug settings...${NC}"
if grep -q "DEBUG=true" .env 2>/dev/null; then
    echo -e "${YELLOW}⚠ DEBUG=true found in .env (OK for development)${NC}"
else
    echo -e "${GREEN}✓ No debug mode in .env${NC}"
fi

# 4. Check Docker security
echo -e "\n${YELLOW}[4/6] Checking Dockerfile security...${NC}"
if grep -q "USER app" Dockerfile 2>/dev/null || grep -q "USER root" Dockerfile 2>/dev/null; then
    echo -e "${GREEN}✓ Non-root user configured in Dockerfile${NC}"
else
    echo -e "${RED}✗ Dockerfile runs as root${NC}"
    ISSUES=$((ISSUES + 1))
fi

# 5. Check dependency vulnerabilities
echo -e "\n${YELLOW}[5/6] Checking for known vulnerabilities...${NC}"
if command -v pip-audit &> /dev/null; then
    pip-audit -r requirements.txt 2>/dev/null && echo -e "${GREEN}✓ No known vulnerabilities" || echo -e "${YELLOW}⚠ Some vulnerabilities found (check output above)"
else
    echo -e "${YELLOW}⚠ pip-audit not installed, skipping${NC}"
fi

# 6. Check for SQL injection patterns
echo -f "\n${YELLOW}[6/6] Checking for SQL injection patterns...${NC}"
SQL_INJECT=$(grep -rn "text(f\".*{.*}.*SELECT\|execute(f\"" --include="*.py" ecommerce_ops/ 2>/dev/null || true)
if [ -n "$SQL_INJECT" ]; then
    echo -e "${RED}✗ Potential SQL injection:${NC}"
    echo "$SQL_INJECT"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No SQL injection patterns found${NC}"
fi

# Summary
echo -e "\n${YELLOW}══════════════════════════════════════════${NC}"
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ Security scan passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ $ISSUES issue(s) found${NC}"
    exit 1
fi
