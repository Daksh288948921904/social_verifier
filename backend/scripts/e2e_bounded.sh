#!/bin/bash
set -euo pipefail
DURATION="${1:-180}"
URL="${2:-https://www.youtube.com/@SkyNews/live}"

RESP=$(curl -s -X POST http://localhost:8787/api/sessions -H "Content-Type: application/json" -d "{\"url\":\"$URL\"}")
echo "created: $RESP"
SID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "SID=$SID"

cd "$(dirname "$0")/.."
source .venv/bin/activate
python scripts/ws_listen.py "$SID" "$DURATION" || true

echo "--- stopping session ---"
curl -s -X POST "http://localhost:8787/api/sessions/$SID/stop"
echo
echo "SID=$SID" > /tmp/last_e2e_sid.txt
