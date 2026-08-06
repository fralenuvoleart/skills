#!/bin/bash
# Export a Kinsta Health Report (Markdown) to PDF via Chromium.
#
# Usage: export_pdf.sh <path/to/report.md>
# Output: <path/to/report>.pdf (same directory, same basename, .pdf extension)

set -euo pipefail

ENGINE="chromium"
MD_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine)
      ENGINE="$2"
      shift 2
      ;;
    *)
      MD_PATH="$1"
      shift
      ;;
  esac
done

if [ -z "$MD_PATH" ]; then
  echo "Usage: export_pdf.sh [--engine typst|chromium] <path/to/report.md>" >&2
  exit 1
fi

if [ ! -f "$MD_PATH" ]; then
  echo "⚠️  Report not found: $MD_PATH — PDF export skipped." >&2
  exit 1
fi

PDF_PATH="${MD_PATH%.md}.pdf"

case "$ENGINE" in
  chromium)
    CHROMIUM_BIN="${CHROMIUM_BIN:-/usr/bin/chromium}"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CSS_PATH="$SCRIPT_DIR/report.css"

    if [ ! -x "$CHROMIUM_BIN" ]; then
      echo "⚠️  Chromium not found at $CHROMIUM_BIN — PDF export skipped." >&2
      echo "   Set CHROMIUM_BIN to override, or install Chromium." >&2
      exit 1
    fi

    PUPPETEER_SKIP_DOWNLOAD=true PUPPETEER_EXECUTABLE_PATH="$CHROMIUM_BIN" \
      npx --yes md-to-pdf "$MD_PATH" \
        --stylesheet "$CSS_PATH" \
        --pdf-options '{"format":"a4","printBackground":true,"margin":{"top":"18mm","right":"18mm","bottom":"18mm","left":"18mm"}}' \
        --launch-options '{"args":["--no-sandbox"]}'

    if [ -f "$PDF_PATH" ]; then
      echo "📄 PDF (chromium): $PDF_PATH"
    else
      echo "⚠️  md-to-pdf ran but no PDF was found at $PDF_PATH" >&2
      exit 1
    fi
    ;;

  *)
    echo "⚠️  Unknown engine: $ENGINE — use 'chromium'" >&2
    exit 1
    ;;
esac
