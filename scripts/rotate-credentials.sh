#!/usr/bin/env bash
# ── OpsIQ — Interactive Credential Rotation ─────────────────
# Run this script to rotate all credentials interactively
set -euo pipefail

echo "╔══════════════════════════════════════════════════╗"
echo "║       OpsIQ Credential Rotation Script          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Generate new OpsIQ API Key ─────────────────────────
echo "━━━ [1/5] OpsIQ API Key ━━━━━━━━━━━━━━━━━━━━━━━━━━"
NEW_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
echo "New API Key: $NEW_API_KEY"
echo ""
echo "Update these files manually:"
echo "  - .env (API_KEY=$NEW_API_KEY)"
echo "  - .env.docker (API_KEY=$NEW_API_KEY)"
echo "  - GitHub repo secrets (API_KEY)"
echo ""

# ── 2. Generate new Grafana password ──────────────────────
echo "━━━ [2/5] Grafana Admin Password ━━━━━━━━━━━━━━━━━━"
NEW_GRAFANA_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))" 2>/dev/null || openssl rand -base64 24)
echo "New Grafana Password: $NEW_GRAFANA_PASS"
echo "Update: docker-compose.yml (GRAFANA_ADMIN_PASSWORD)"
echo ""

# ── 3. Generate new PostgreSQL password ────────────────────
echo "━━━ [3/5] PostgreSQL Password ━━━━━━━━━━━━━━━━━━━━━"
NEW_PG_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
echo "New PostgreSQL Password: $NEW_PG_PASS"
echo "Update: .env.docker (POSTGRES_PASSWORD, DATABASE_URL)"
echo ""

# ── 4. Instructions for external services ──────────────────
echo "━━━ [4/5] External Service Keys ━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Google API Key:"
echo "  1. Go to: https://console.cloud.google.com/apis/credentials"
echo "  2. Find your key → Edit → Regenerate"
echo "  3. Update: .env (GOOGLE_API_KEY)"
echo ""
echo "Shopify Keys:"
echo "  1. Go to: https://admin.shopify.com/store/ecom-ops-automation-system/settings/apps"
echo "  2. Develop apps → Your app → Regenerate all credentials"
echo "  3. Update: .env (SHOPIFY_API_KEY, SHOPIFY_PASSWORD, SHOPIFY_ACCESS_TOKEN, SHOPIFY_CLIENT_SECRET)"
echo ""
echo "Resend API Key:"
echo "  1. Go to: https://resend.com/api-keys"
echo "  2. Revoke old key → Create new key named 'OpsIQ Production'"
echo "  3. Update: .env (RESEND_API_KEY)"
echo ""

# ── 5. Verification ───────────────────────────────────────
echo "━━━ [5/5] Post-Rotation Verification ━━━━━━━━━━━━━━"
echo "After updating all keys, run:"
echo "  docker compose restart api"
echo "  curl http://localhost:8000/health"
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  DONE! Update the files above, then restart.    ║"
echo "╚══════════════════════════════════════════════════╝"
