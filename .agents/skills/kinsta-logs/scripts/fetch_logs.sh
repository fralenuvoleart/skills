#!/usr/bin/env bash
# Fetch Kinsta error/access/cache-perf logs in parallel, with per-log retry logic.
# Encapsulates the fetch+retry strategy deterministically instead of relying on
# the agent to hand-write correct parallel/retry bash on every run.
#
# Usage: fetch_logs.sh <env_id> <output_dir> <timestamp>
# Requires KINSTA_API_KEY and KINSTA_COMPANY_ID to be set in the environment.
# Writes: <output_dir>/<timestamp>_error.json, _access.json, _cache.json
set -uo pipefail

ENV_ID="${1:?Usage: fetch_logs.sh <env_id> <output_dir> <timestamp>}"
DIR="${2:?Usage: fetch_logs.sh <env_id> <output_dir> <timestamp>}"
TS="${3:?Usage: fetch_logs.sh <env_id> <output_dir> <timestamp>}"

: "${KINSTA_API_KEY:?KINSTA_API_KEY must be set in the environment}"
: "${KINSTA_COMPANY_ID:?KINSTA_COMPANY_ID must be set in the environment}"

# Pin the MCP package version — unpinned `npx -y kinsta-mcp` would silently pull
# whatever "latest" resolves to on every run (supply-chain / reproducibility risk).
KINSTA_MCP_VERSION="1.0.3"

mkdir -p "$DIR"

fetch_one() {
  local file_name="$1" lines="$2" retries="$3" out="$4"
  local attempt=1
  while (( attempt <= retries )); do
    echo "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"kinsta.logs.get\",\"arguments\":{\"env_id\":\"${ENV_ID}\",\"file_name\":\"${file_name}\",\"lines\":${lines}}}}" \
      | KINSTA_API_KEY="$KINSTA_API_KEY" KINSTA_COMPANY_ID="$KINSTA_COMPANY_ID" \
        npx -y "kinsta-mcp@${KINSTA_MCP_VERSION}" 2>/dev/null > "$out"

    if [[ -s "$out" ]] && ! grep -q "NETWORK_ERROR" "$out"; then
      return 0
    fi
    echo "  [retry ${attempt}/${retries}] ${file_name} fetch failed, retrying in 3s..." >&2
    sleep 3
    ((attempt++))
  done
  echo "  [FAILED] ${file_name} after ${retries} attempt(s) — see ${out}" >&2
  return 1
}

# Run all three fetches in parallel; each has its own retry budget.
# access uses 8000 lines (not 3000) to cover a full 24h window (~330 lines/hour).
fetch_one "error"             1000 1 "$DIR/${TS}_error.json"  &
fetch_one "access"            8000 1 "$DIR/${TS}_access.json" &
fetch_one "kinsta-cache-perf" 1000 3 "$DIR/${TS}_cache.json"  &

wait

echo "Logs written to ${DIR}/${TS}_{error,access,cache}.json"
