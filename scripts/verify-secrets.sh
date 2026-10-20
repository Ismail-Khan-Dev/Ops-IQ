#!/usr/bin/env bash
# ── OpsIQ — Secret Re-verification (post-rotation / push protection) ──
# Verifies that no live credentials are reachable from the repository:
#   1. Full git-history gitleaks scan (catches previously-committed secrets).
#   2. .env / .env.* must be git-ignored and NOT tracked by git.
#   3. Live secret tokens must not appear in the working tree (any depth).
#   4. The pre-push push-protection hook must be installed.
#
# Usage:
#   scripts/verify-secrets.sh            # all checks
#   scripts/verify-secrets.sh --ci       # CI mode (no gitleaks install, hard exit)

set -euo pipefail

CI=${CI:-}
GITLEAKS="${GITLEAKS:-}"

PASS=0
FAIL=0

say_pass() { echo -e "\033[0;32m✓ $1\033[0m"; PASS=$((PASS + 1)); }
say_fail() { echo -e "\033[0;31m✗ $1\033[0m"; FAIL=$((FAIL + 1)); }

echo "╔══════════════════════════════════════════════════════╗"
echo "║        OpsIQ Secret Re-verification                  ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── 1. Gitleaks over full history ────────────────────────────
echo ""
echo "[1/4] Gitleaks scan over full git history..."
if [ -n "$GITLEAKS" ]; then
  "$GITLEAKS" git --exit-code=1 --no-banner --redact
  say_pass "gitleaks full-history scan clean"
elif command -v gitleaks &> /dev/null; then
  gitleaks git --exit-code=1 --no-banner --redact
  say_pass "gitleaks full-history scan clean"
elif [ -n "$CI" ]; then
  echo "  installing gitleaks for CI scan..."
  curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz -o /tmp/gitleaks.tgz
  tar -xzf /tmp/gitleaks.tgz -C /tmp gitleaks
  chmod +x /tmp/gitleaks
  /tmp/gitleaks git --exit-code=1 --no-banner --redact
  say_pass "gitleaks full-history scan clean (installed ad hoc)"
else
  echo -e "\033[1;33m⚠ gitleaks not installed — skipping full-history scan. Install with: brew install gitleaks\033[0m"
fi

# ── 2. .env files ignored and untracked ───────────────────────
echo ""
echo "[2/4] .env files git-ignored and untracked..."
for f in .env .env.docker .env.local .env.test .env.staging .env.production; do
  if [ -f "$f" ] || [ -L "$f" ]; then
    if git check-ignore -q "$f" && ! git ls-files --error-unmatch "$f" > /dev/null 2>&1; then
      say_pass "$f is git-ignored and untracked"
    else
      say_fail "$f exists but is NOT fully git-ignored/untracked"
    fi
  fi
done
# Fail hard if any .env is actually tracked (CI pushes are blocked by this).
TRACKED_ENV=$(git ls-files | grep -E '(^|/)\.env(\.|$)' || true)
if [ -n "$TRACKED_ENV" ]; then
  say_fail "tracked .env file(s) found in git: $TRACKED_ENV"
fi

# ── 3. Live token patterns in the working tree ────────────────
echo ""
echo "[3/4] Scanning working tree for live secret tokens..."
# Matches the project's own credential formats (server API keys and
# Shopify/Slack tokens) anywhere outside .env (which is gitignored anyway).
LEAKS=$(grep -rInE "eops_[A-Za-z0-9_-]{20,}|shpat_[0-9a-fA-F]{32,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,}" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.yml" --include="*.yaml" \
  --include="*.toml" --include="*.json" --include="*.sh" --include="*.env*" \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=htmlcov \
  --exclude-dir=.venv --exclude-dir=venv . 2>/dev/null | grep -v "sk-test-key" | grep -v "sk-dummy" || true)
if [ -z "$LEAKS" ]; then
  say_pass "no live secret tokens in the working tree"
else
  say_fail "possible live secrets found:"
  echo "$LEAKS"
fi

# ── 4. Push-protection hook installed ─────────────────────────
echo ""
echo "[4/4] Pre-push push-protection hook..."
if [ -f .git/hooks/pre-push ]; then
  say_pass "pre-push hook present"
else
  if [ -n "$CI" ]; then
    say_fail "pre-push hook not installed in this clone (expected; CI gates remain active)"
  else
    echo -e "\033[1;33m⚠ pre-push hook not installed. Run:  pre-commit install --hook-type pre-push\033[0m"
  fi
fi

echo ""
echo "══════════════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
  echo -e "\033[0;32m✓ Re-verification passed ($PASS checks)\033[0m"
  exit 0
else
  echo -e "\033[0;31m✗ $FAIL check(s) failed — rotate the affected credential and re-verify\033[0m"
  exit 1
fi