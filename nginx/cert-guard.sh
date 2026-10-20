#!/bin/sh
# ── OpsIQ — TLS cert boot guard (nginx container entrypoint) ──
# Fail-fast if TLS certificates are missing. nginx is never
# started without TLS (no silent HTTP-only fallback).
#
# Provide certs in ./nginx/certs/ (server.crt + server.key) or
# run: bash scripts/generate-tls-certs.sh

set -e

CRT="${TLS_CERT_PATH:-/etc/nginx/certs/server.crt}"
KEY="${TLS_KEY_PATH:-/etc/nginx/certs/server.key}"

if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
    echo "ERROR: TLS certificates not found." >&2
    echo "  Missing: $CRT and/or $KEY" >&2
    echo "  Generate self-signed certs: bash scripts/generate-tls-certs.sh" >&2
    echo "  Or mount real certificates under ./nginx/certs/." >&2
    echo "  Refusing to start nginx without TLS." >&2
    exit 1
fi

# Hand off to the stock nginx entrypoint (keeps its docker-entrypoint.d scripts).
exec /docker-entrypoint.sh "$@"