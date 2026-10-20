#!/usr/bin/env bash
# Generate self-signed TLS certificates for development
# Usage: ./scripts/generate-tls-certs.sh [output_dir]
set -euo pipefail

OUTPUT_DIR="${1:-./nginx/certs}"
DAYS=365
SUBJECT="/C=US/ST=Local/L=Dev/O=OpsIQ/CN=localhost"

mkdir -p "$OUTPUT_DIR"

if [ -f "$OUTPUT_DIR/server.crt" ] && [ -f "$OUTPUT_DIR/server.key" ]; then
  echo "[SKIP] TLS certs already exist in $OUTPUT_DIR"
  echo "  Delete them to regenerate."
  exit 0
fi

echo "[1/3] Generating CA key and certificate..."
openssl genrsa -out "$OUTPUT_DIR/ca.key" 2048 2>/dev/null
openssl req -new -x509 -days "$DAYS" -key "$OUTPUT_DIR/ca.key" \
  -out "$OUTPUT_DIR/ca.crt" -subj "$SUBJECT/CA" 2>/dev/null

echo "[2/3] Generating server key and CSR..."
openssl genrsa -out "$OUTPUT_DIR/server.key" 2048 2>/dev/null
openssl req -new -key "$OUTPUT_DIR/server.key" \
  -out "$OUTPUT_DIR/server.csr" -subj "$SUBJECT" 2>/dev/null

echo "[3/3] Signing server certificate with CA..."
cat > "$OUTPUT_DIR/san.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=@alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

openssl x509 -req -days "$DAYS" \
  -in "$OUTPUT_DIR/server.csr" \
  -CA "$OUTPUT_DIR/ca.crt" \
  -CAkey "$OUTPUT_DIR/ca.key" \
  -CAcreateserial \
  -out "$OUTPUT_DIR/server.crt" \
  -extfile "$OUTPUT_DIR/san.ext" 2>/dev/null

# Cleanup
rm -f "$OUTPUT_DIR/server.csr" "$OUTPUT_DIR/san.ext" "$OUTPUT_DIR/ca.srl"

chmod 600 "$OUTPUT_DIR/server.key" "$OUTPUT_DIR/ca.key"
chmod 644 "$OUTPUT_DIR/server.crt" "$OUTPUT_DIR/ca.crt"

echo ""
echo "[OK] TLS certificates generated:"
echo "  Certificate: $OUTPUT_DIR/server.crt"
echo "  Private Key: $OUTPUT_DIR/server.key"
echo "  CA Certificate: $OUTPUT_DIR/ca.crt"
echo ""
echo "  Valid for: localhost, 127.0.0.1, *.localhost"
echo "  Expires in: $DAYS days"
echo ""
echo "  To use in production, replace with real certificates from:"
echo "  - Let's Encrypt (free): certbot certonly --standalone -d yourdomain.com"
echo "  - AWS ACM, Cloudflare, or your CA provider"
