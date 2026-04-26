#!/usr/bin/env bash
set -euo pipefail

# Resolve repo root regardless of invocation directory
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

echo "=== Hackathon Skill Loop — One-Command Start ==="

# Load env before checking required vars so hackathon/.env can supply them
if [ -f "hackathon/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "hackathon/.env"
    set +a
fi

# Fail fast with a clear message if required keys are missing
: "${ANTHROPIC_API_KEY?Required: set ANTHROPIC_API_KEY in hackathon/.env or environment}"
: "${DAYTONA_API_KEY?Required: set DAYTONA_API_KEY in hackathon/.env or environment}"

echo "==> Step 1/3: Installing dependencies"
if python -c "import streamlit, cognee, daytona, anthropic, pydantic, dotenv" 2>/dev/null; then
    echo "    Dependencies already installed — skipping pip install"
else
    pip install -r hackathon/requirements.txt --quiet
fi

echo "==> Step 2/3: Pre-warming Daytona image cache (up to 60s)"
# Blocks until image is cached; exits non-zero if Daytona is unreachable
if ! timeout 60 python hackathon/demo.py --warm; then
    echo "ERROR: --warm step failed. Check DAYTONA_API_KEY and DAYTONA_API_URL in hackathon/.env" >&2
    exit 1
fi

echo "==> Step 3/3: Starting Streamlit dashboard at http://localhost:8501"
streamlit run hackathon/dashboard.py --server.headless false
