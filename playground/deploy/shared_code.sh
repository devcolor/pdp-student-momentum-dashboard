#!/usr/bin/env bash
# Copies the repo code the API reads at runtime into the API's folder, or removes the copies.
# Vercel packs only the API's folder, but the API reaches outside it for these. Run from the repo root:
#   playground/deploy/shared_code.sh add      before the upload
#   playground/deploy/shared_code.sh remove   after it, so local runs use the real folders again
set -euo pipefail

API=playground/server_application

# Each copy and why the API needs it there.
#   normalized-data-model/config  The API finds the repo by this folder, and reads the model's YAML.
#   _vendor/config                Vercel installs the data model's code in _vendor/, without its
#                                 config/ folder, and the code looks for config/ beside itself.
#   mcp, gap_finder, measures     The shared code the API imports from the repo.
#   .agents/skills/metadata-advisor  The chat's instructions; without them every question fails.
#   data/dictionaries, normalized-data-model/README.md  What the chat's definitions tools read.
COPIES="normalized-data-model _vendor mcp gap_finder measures .agents data"

remove() {
  for copy in $COPIES; do
    rm -rf "${API:?}/$copy"
  done
}

add() {
  remove
  mkdir -p "$API/normalized-data-model" "$API/_vendor" "$API/mcp" "$API/.agents/skills" "$API/data"
  cp -R normalized-data-model/config "$API/normalized-data-model/config"
  cp normalized-data-model/README.md "$API/normalized-data-model/"
  cp -R normalized-data-model/config "$API/_vendor/config"
  cp -R mcp/pdp_mcp mcp/schemas "$API/mcp/"
  cp -R .agents/skills/metadata-advisor "$API/.agents/skills/"
  cp -R data/dictionaries "$API/data/"
  # Code only: their tests and saved outputs stay behind.
  rsync -a --exclude tests --exclude output --exclude __pycache__ gap_finder measures "$API/"
}

case "${1:-}" in
  add) add ;;
  remove) remove ;;
  *) echo "Usage: $0 add|remove" >&2; exit 2 ;;
esac
