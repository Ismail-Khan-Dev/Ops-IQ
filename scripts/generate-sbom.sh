#!/usr/bin/env bash
# ── Generate SBOM (Software Bill of Materials) ─────────────
# Creates a CycloneDX SBOM for the project
set -euo pipefail

OUTPUT_DIR="${1:-./sbom}"
mkdir -p "$OUTPUT_DIR"

echo "=== OpsIQ SBOM Generator ==="

# Check for syft (preferred) or fall back to pip-licenses
if command -v syft &>/dev/null; then
    echo "[1/3] Generating Python SBOM with syft..."
    syft dir:. -o cyclonedx-json="$OUTPUT_DIR/sbom-python.json" 2>/dev/null || true

    echo "[2/3] Generating Frontend SBOM..."
    if [ -d frontend/node_modules ]; then
        syft dir:frontend -o cyclonedx-json="$OUTPUT_DIR/sbom-frontend.json" 2>/dev/null || true
    fi

    echo "[3/3] Generating Docker SBOM..."
    if docker image inspect opsiq-api:latest &>/dev/null; then
        syft opsiq-api:latest -o cyclonedx-json="$OUTPUT_DIR/sbom-docker.json" 2>/dev/null || true
    fi
else
    echo "[1/3] syft not found, installing..."
    curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin 2>/dev/null || {
        echo "[WARN] Could not install syft. Using pip-licenses as fallback."
        echo "[1/3] Generating Python dependency list..."
        pip install pip-licenses -q 2>/dev/null || true
        pip-licenses --format=json --output-file="$OUTPUT_DIR/dependencies-python.json" 2>/dev/null || true
    }

    if command -v syft &>/dev/null; then
        echo "[2/3] Generating SBOM with syft..."
        syft dir:. -o cyclonedx-json="$OUTPUT_DIR/sbom.json" 2>/dev/null || true
    fi

    echo "[3/3] Frontend SBOM..."
    if [ -d frontend/node_modules ]; then
        cd frontend && npm audit --json > "$OUTPUT_DIR/npm-audit.json" 2>/dev/null || true
        cd ..
    fi
fi

echo ""
echo "=== SBOM Generation Complete ==="
echo "Output directory: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR" 2>/dev/null || true
echo ""
echo "Files can be uploaded to:"
echo "  - GitHub Dependency Graph: Settings > Code security and analysis"
echo "  - Snyk: https://app.snyk.io"
echo "  - Dependency-Track: https://dependencytrack.org"
