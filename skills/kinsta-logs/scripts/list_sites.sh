#!/bin/bash
# list_sites.sh
# Abstract the JSON-RPC call to list Kinsta sites and environments.

if [ -z "$KINSTA_API_KEY" ] || [ -z "$KINSTA_COMPANY_ID" ]; then
  echo "Error: KINSTA_API_KEY and KINSTA_COMPANY_ID environment variables must be set." >&2
  exit 1
fi

echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"kinsta.sites.list","arguments":{"include_environments":true}}}' | npx -y kinsta-mcp@1.0.3 2>/dev/null
