#!/usr/bin/env bash
# Build the site for the unlisted draft at https://jamiesimon.io/draft-redwood-website/ and copy it
# into Jamie's personal-site repo. Does NOT commit or push; do that by hand (only this folder).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${TARGET:-$HOME/Projects/james-simon.github.io/draft-redwood-website}"

cd "$HERE/site"
SITE=https://jamiesimon.io BASE=/draft-redwood-website PUBLIC_NOINDEX=true npx astro build
rsync -a --delete dist/ "$TARGET/"
echo "Copied build to $TARGET"
