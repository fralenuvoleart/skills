#!/bin/bash
# Export a Kinsta Health Report (Markdown) to PDF.
#
# Supports two engines:
#   chromium — md-to-pdf via npx + system Chromium (default, CSS-friendly, best for visual design)
#   typst    — Quarto's bundled pandoc + Typst (fallback, no extra deps)
#
# Usage: export_pdf.sh [--engine chromium|typst] <path/to/report.md>
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
  typst)
    TYPST_BIN="${TYPST_BIN:-/opt/quarto/bin/tools/x86_64/typst}"

    if ! command -v quarto &>/dev/null; then
      echo "⚠️  Quarto not found — PDF export skipped." >&2
      echo "   Install Quarto from https://quarto.org/docs/get-started/" >&2
      exit 1
    fi

    if [ ! -x "$TYPST_BIN" ]; then
      echo "⚠️  Typst not found at $TYPST_BIN — PDF export skipped." >&2
      echo "   Set TYPST_BIN to the typst binary bundled with Quarto." >&2
      exit 1
    fi

    quarto pandoc "$MD_PATH" \
      -o "$PDF_PATH" \
      --pdf-engine="$TYPST_BIN"

    if [ -f "$PDF_PATH" ]; then
      echo "📄 PDF (typst): $PDF_PATH"
    else
      echo "⚠️  pandoc+typst ran but no PDF was found at $PDF_PATH" >&2
      exit 1
    fi
    ;;

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
    echo "⚠️  Unknown engine: $ENGINE — use 'typst' or 'chromium'" >&2
    exit 1
    ;;
esac
