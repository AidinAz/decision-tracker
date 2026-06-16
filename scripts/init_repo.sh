#!/usr/bin/env bash
set -euo pipefail

mkdir -p decisions reports evaluation schemas fixtures/decisions fixtures/expected viewer scripts docs

# Optional: add a placeholder .gitignore for generated reports
cat > .gitignore <<'EOF'
# Generated outputs
reports/
decisions/index.json
decisions/graph.json
decisions/artifacts.json
EOF

echo "Initialized repo skeleton."
echo "SPEC.md and DT_DEV_CHECKLIST.md are included in this pack (v2). Copy them into your repo root."
