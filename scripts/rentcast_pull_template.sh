#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   RENTCAST_API_KEY="your_key" ./scripts/rentcast_pull_template.sh
# Do not hardcode API keys in committed files.

: "${RENTCAST_API_KEY:?Set RENTCAST_API_KEY first}"

ZIPS=(19003 19004 19041 19083 19087 19312 19355)
OUT_DIR="$HOME/Downloads"

for ZIP in "${ZIPS[@]}"; do
  curl --request GET \
    --url "https://api.rentcast.io/v1/listings/sale?zipCode=${ZIP}&status=Active&limit=500" \
    --header "X-Api-Key: ${RENTCAST_API_KEY}" \
    --output "${OUT_DIR}/rentcast_${ZIP}.json"
done
