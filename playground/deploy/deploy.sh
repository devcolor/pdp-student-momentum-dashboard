#!/usr/bin/env bash
# Deploys the Playground to your own Vercel project, then checks every Sandbox page on the live site.
# Run from the repo root, with the Vercel CLI logged in:
#   playground/deploy/deploy.sh https://your-project.example.com
# The site URL can also come from SITE_URL. VERCEL_SCOPE picks the Vercel team (default: your own).
# PYTHON is the Python with requirements.txt installed (default: .venv/bin/python).
set -euo pipefail

SITE="${1:-${SITE_URL:-}}"
if [ -z "$SITE" ]; then
  echo "Usage: $0 <site-url>   (or set SITE_URL), e.g. $0 https://your-project.example.com" >&2
  exit 2
fi
export PYTHON="${PYTHON:-.venv/bin/python}"

# Runs the pinned Vercel CLI, against VERCEL_SCOPE's team when it's set.
vercel() {
  local scope=()
  if [ -n "${VERCEL_SCOPE:-}" ]; then
    scope=(--scope "$VERCEL_SCOPE")
  fi
  # A shell started by npx sets npm_config_package, which makes npx run the wrong command.
  env -u npm_config_package npx --yes vercel@65.3.1 ${scope[@]+"${scope[@]}"} "$@"
}

# Prints your GitHub no-reply email, or nothing if the gh CLI isn't logged in.
github_noreply_email() {
  gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"' 2>/dev/null || true
}

# Succeeds if you wrote the newest commit.
newest_commit_is_yours() {
  local author
  author="$(git log -1 --format=%ae)"
  # Merges made on github.com carry your GitHub no-reply email, not your git email.
  [ "$author" = "$(git config user.email)" ] || [ "$author" = "$(github_noreply_email)" ]
}

# The free plan only deploys the account owner's commits, so stop before an upload it would block.
if ! newest_commit_is_yours; then
  author="$(git log -1 --format=%ae)"
  echo "The newest commit is by $author. Vercel's free plan only deploys your own commits." >&2
  echo "Merge main into your branch, so your merge commit is on top, then run this again." >&2
  exit 1
fi
# The upload is the working tree, so uncommitted edits would go live without a commit behind them.
if ! git diff --quiet HEAD; then
  echo "You have uncommitted changes. Commit them first, so the site matches a commit." >&2
  exit 1
fi

playground/deploy/build_data.sh

# The API reads repo code outside its own folder. Copy it in for the upload, and always remove it.
trap 'playground/deploy/shared_code.sh remove' EXIT
playground/deploy/shared_code.sh add

# The client's API types are generated, not committed, so make them before the build uploads.
(cd playground/client_application && npx -y bun@1.4.3 install --frozen-lockfile && npx -y bun@1.4.3 run api-types)

vercel deploy --prod --yes
python3 playground/deploy/check_site.py "$SITE"
