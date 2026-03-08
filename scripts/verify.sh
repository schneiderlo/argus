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

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for verification" >&2
  exit 1
fi

UI_DIR="src/argus/render/ui"

if [[ ! -f "$UI_DIR/package.json" ]]; then
  echo "Observer UI scaffold missing: expected $UI_DIR/package.json" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required for frontend verification" >&2
  exit 1
fi

if [[ ! -f "$UI_DIR/package-lock.json" ]]; then
  echo "Frontend lockfile missing: expected $UI_DIR/package-lock.json" >&2
  exit 1
fi

if [[ ! -d "$UI_DIR/node_modules" ]]; then
  echo "Frontend dependencies missing under $UI_DIR/node_modules. Run 'npm --prefix $UI_DIR ci' and retry verification." >&2
  exit 1
fi

if [[ ! -f uv.lock ]]; then
  echo "uv.lock is required for verification. Run 'uv lock' or 'uv sync --group dev' and commit the lockfile." >&2
  exit 1
fi

uv sync --locked --group dev --python 3.12
uv run --locked --no-sync --python 3.12 python -V
uv run --locked --no-sync --python 3.12 python -m compileall src tests
uv run --locked --no-sync --python 3.12 python -m unittest discover -s tests -t .
uv run --locked --no-sync --python 3.12 ruff check .
npm --prefix "$UI_DIR" run check

echo "Verification complete."
