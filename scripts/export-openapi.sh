#!/usr/bin/env bash
# ── Export OpenAPI spec from FastAPI ────────────────────────
# Usage: ./scripts/export-openapi.sh [output_path]
set -euo pipefail

OUTPUT="${1:-docs/openapi.json}"
mkdir -p "$(dirname "$OUTPUT")"

python -c "
import json, sys
sys.path.insert(0, '.')
from ecommerce_ops.api.app import app
spec = app.openapi()
with open('$OUTPUT', 'w') as f:
    json.dump(spec, f, indent=2)
print(f'OpenAPI spec written to $OUTPUT ({len(spec.get(\"paths\", {}))} paths)')
"

echo "Endpoints documented:"
python -c "
import sys; sys.path.insert(0, '.')
from ecommerce_ops.api.app import app
paths = app.openapi()['paths']
for path, methods in sorted(paths.items()):
    for method in methods:
        if method in ('get','post','put','patch','delete'):
            print(f'  {method.upper():7s} {path}')
"
