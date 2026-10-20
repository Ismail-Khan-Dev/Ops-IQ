#!/usr/bin/env bash
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ISSUES=0
WARNINGS=0

echo -e "${YELLOW}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║    OpsIQ Deep Security Scan (MANGO-Level)          ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════════════════╝${NC}"

# ── 1. eval/exec usage ──
echo -e "\n${YELLOW}[1/10] Checking for eval()/exec() usage...${NC}"
EVAL=$(grep -rn '\beval\s*(' --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null || true)
EVAL2=$(grep -rn '\bexec\s*(' --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null || true)
if [ -n "$EVAL" ] || [ -n "$EVAL2" ]; then
    echo -e "${RED}✗ eval()/exec() found:${NC}"
    [ -n "$EVAL" ] && echo "$EVAL"
    [ -n "$EVAL2" ] && echo "$EVAL2"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No eval()/exec() found${NC}"
fi

# ── 2. subprocess shell=True ──
echo -e "\n${YELLOW}[2/10] Checking for subprocess shell=True...${NC}"
SHELL_TRUE=$(grep -rn "shell=True" --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null || true)
if [ -n "$SHELL_TRUE" ]; then
    echo -e "${RED}✗ shell=True found:${NC}"
    echo "$SHELL_TRUE"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No shell=True found${NC}"
fi

# ── 3. CORS configuration ──
echo -e "\n${YELLOW}[3/10] Checking CORS configuration...${NC}"
CORS=$(grep -rn 'allow_origins.*\*' --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null || true)
if [ -n "$CORS" ]; then
    echo -e "${RED}✗ Wildcard CORS (allow_origins=*) found:${NC}"
    echo "$CORS"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No wildcard CORS found${NC}"
fi

# ── 4. SSL verification disabled ──
echo -e "\n${YELLOW}[4/10] Checking for disabled SSL verification...${NC}"
SSL_OFF=$(grep -rn "verify=False\|VERIFY.*False\|ssl.*False" --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null || true)
if [ -n "$SSL_OFF" ]; then
    echo -e "${YELLOW}⚠ SSL verification disabled:${NC}"
    echo "$SSL_OFF"
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}✓ SSL verification not disabled${NC}"
fi

# ── 5. Debug mode in production ──
echo -e "\n${YELLOW}[5/10] Checking debug settings...${NC}"
DEBUG=$(grep -rn "DEBUG.*True\|debug.*=.*True" --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null | grep -v "logger\|logging\|LOG_" || true)
if [ -n "$DEBUG" ]; then
    echo -e "${YELLOW}⚠ Debug mode enabled:${NC}"
    echo "$DEBUG"
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}✓ No debug mode in production code${NC}"
fi

# ── 6. SQL injection patterns ──
echo -e "\n${YELLOW}[6/10] Checking for SQL injection patterns...${NC}"
SQL=$(grep -rn 'text(f".*{.*}.*SELECT\|execute(f"\|\.raw(' --include="*.py" --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" . 2>/dev/null || true)
if [ -n "$SQL" ]; then
    echo -e "${RED}✗ Potential SQL injection:${NC}"
    echo "$SQL"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No SQL injection patterns found${NC}"
fi

# ── 7. Hardcoded API keys / tokens ──
echo -e "\n${YELLOW}[7/10] Scanning for hardcoded API keys/tokens...${NC}"
KEYS=$(grep -rn 'sk-live-\|sk-test-\|akia\|AIza\|ghp_\|glpat-\|xoxb-\|xoxp-' --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=ecommerce_ops --exclude="*test*" --exclude="*mock*" . 2>/dev/null || true)
if [ -n "$KEYS" ]; then
    echo -e "${RED}✗ Hardcoded API keys found:${NC}"
    echo "$KEYS"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No hardcoded API keys found${NC}"
fi

# ── 8. Dependency vulnerabilities (pip-audit fallback) ──
echo -e "\n${YELLOW}[8/10] Checking Python dependency vulnerabilities...${NC}"
if command -v pip-audit &> /dev/null; then
    pip-audit -r /tmp/scan/requirements.txt 2>/dev/null && echo -e "${GREEN}✓ No known vulnerabilities" || { echo -e "${YELLOW}⚠ Vulnerabilities found"; WARNINGS=$((WARNINGS + 1)); }
else
    echo -e "${YELLOW}⚠ pip-audit not installed, checking manually...${NC}"
    pip install pip-audit -q 2>/dev/null && pip-audit -r /tmp/scan/requirements.txt 2>/dev/null || echo -e "${YELLOW}⚠ Could not run pip-audit${NC}"
fi

# ── 9. Docker secrets exposure ──
echo -e "\n${YELLOW}[9/10] Checking Docker secrets exposure...${NC}"
DOCKER_SECRETS=$(grep -rn 'SECRET_KEY\|API_KEY\|PASSWORD' docker-compose.yml docker-compose.override.yml 2>/dev/null | grep -v '\$\{' | grep -v '#' || true)
if [ -n "$DOCKER_SECRETS" ]; then
    echo -e "${RED}✗ Hardcoded secrets in Docker Compose:${NC}"
    echo "$DOCKER_SECRETS"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No hardcoded secrets in Docker Compose${NC}"
fi

# ── 10. .gitignore coverage ──
echo -e "\n${YELLOW}[10/10] Checking .gitignore coverage...${NC}"
MISSING=""
for pattern in ".env" ".env.local" "*.pem" "*.key" "*.p12" "__pycache__" "node_modules" ".pytest_cache"; do
    if ! grep -q "$pattern" .gitignore 2>/dev/null; then
        MISSING="$MISSING $pattern"
    fi
done
if [ -n "$MISSING" ]; then
    echo -e "${YELLOW}⚠ Missing from .gitignore:${NC}$MISSING"
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}✓ .gitignore covers critical patterns${NC}"
fi

# ── Summary ──
echo -e "\n${YELLOW}══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}RESULTS:${NC}"
echo -e "  ${RED}Critical Issues: $ISSUES${NC}"
echo -e "  ${YELLOW}Warnings:         $WARNINGS${NC}"
echo -e "${YELLOW}══════════════════════════════════════════════════════${NC}"
if [ $ISSUES -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ Security scan PASSED — No issues found!${NC}"
    exit 0
elif [ $ISSUES -eq 0 ]; then
    echo -e "${YELLOW}⚠ Security scan PASSED with warnings${NC}"
    exit 0
else
    echo -e "${RED}✗ Security scan FAILED — $ISSUES critical issue(s) found${NC}"
    exit 1
fi
