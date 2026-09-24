#!/usr/bin/env bash
# Builds from src/v2-head.html + src/v2-script.html:
#   src/v2.html      - the artifact page (no <html>/<head> wrapper; the claude.ai artifact service adds it)
#   site/index.html  - a complete HTML document for ordinary hosting (GitHub Pages, Cloudflare Pages, any web server)
# Product photos live in site/img/ (700x700 WebP plus 220px thumbnails, img/<id>-N.webp and img/<id>-N-s.webp).
set -euo pipefail
cd "$(dirname "$0")/.."
cat src/v2-head.html src/v2-script.html > src/v2.html
mkdir -p site
{
  printf '%s\n' '<!doctype html>' '<html lang="en">' '<head>' '<meta charset="utf-8">' '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' '<meta name="description" content="Nestia: home, kitchen, pet and wellness gadgets, delivered across the EU with tracking.">'
  head -n 4 src/v2.html        # <title> and the font <link>s belong in <head> on a normal page
  printf '%s\n' '<style>:root{color-scheme:light}body{margin:0}img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style>'
  printf '%s\n' '</head>' '<body>'
  tail -n +5 src/v2.html
  printf '%s\n' '</body>' '</html>'
} > site/index.html
echo "artifact page: $(wc -c < src/v2.html) bytes; hosted page: $(wc -c < site/index.html) bytes; images: $(ls site/img | wc -l)"
