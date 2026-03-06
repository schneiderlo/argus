#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

required_files=(
  "AGENTS.md"
  "README.md"
  "SPECS.md"
  "PROMPT.md"
  "fix_plan.md"
  "scripts/ralph-loop.sh"
  "scripts/verify.sh"
  "schemas/problem-spec.schema.json"
  "schemas/candidate.schema.json"
  "schemas/critique.schema.json"
  "schemas/final-recommendation.schema.json"
)

echo "Argus verification"
echo "repository=$ROOT_DIR"

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file" >&2
    exit 1
  fi
done

if [[ ! -f pyproject.toml ]]; then
  echo "Application scaffold missing: expected pyproject.toml" >&2
  echo "Implement the Python project described in specs/ before verification can pass." >&2
  exit 1
fi

if [[ ! -d src ]]; then
  echo "Application scaffold missing: expected src/ directory" >&2
  exit 1
fi

if [[ ! -d tests ]]; then
  echo "Application scaffold missing: expected tests/ directory" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for verification" >&2
  exit 1
fi

python3 -m compileall src tests
python3 -m pytest

if command -v ruff >/dev/null 2>&1; then
  ruff check .
fi

echo "Verification complete."

