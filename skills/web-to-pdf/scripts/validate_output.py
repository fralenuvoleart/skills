#!/usr/bin/env python3
"""
validate_output.py — Post-build validation
Checks: PDF file size, page count (when pdfinfo from poppler-utils is available).

Configuration: config/defaults.json → validation section for thresholds.
"""

import argparse
import os
import subprocess
import sys


from config_loader import load_config


def main():
    parser = argparse.ArgumentParser(
        description="Validate generated PDF output."
    )
    parser.add_argument("pdf_path", help="Path to the generated PDF file")
    args = parser.parse_args()

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_config(skill_dir)
    v = config.get("validation", {})

    if not os.path.exists(args.pdf_path):
        print(f"Error: PDF not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Validating: {args.pdf_path}")

    # File size
    file_size = os.path.getsize(args.pdf_path)
    min_bytes = v.get("min_pdf_bytes", 1024)
    max_bytes = v.get("max_pdf_bytes", 52428800)

    if file_size < min_bytes:
        print(f"FAIL: PDF too small ({file_size} bytes, min {min_bytes})", file=sys.stderr)
        sys.exit(1)
    if file_size > max_bytes:
        print(f"FAIL: PDF too large ({file_size} bytes, max {max_bytes})", file=sys.stderr)
        sys.exit(1)

    print(f"  File size: {file_size:,} bytes (OK)")

    # Page count (requires pdfinfo from poppler-utils)
    page_count = None
    try:
        result = subprocess.run(
            ["pdfinfo", args.pdf_path], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                page_count = int(line.split(":")[1].strip())
                break
    except (FileNotFoundError, ValueError):
        pass

    if page_count is not None:
        min_pages = v.get("min_pages", 1)
        max_pages = v.get("max_pages", 20)
        if page_count < min_pages:
            print(f"FAIL: Too few pages ({page_count}, min {min_pages})", file=sys.stderr)
            sys.exit(1)
        if page_count > max_pages:
            print(f"FAIL: Too many pages ({page_count}, max {max_pages})", file=sys.stderr)
            sys.exit(1)
        print(f"  Page count: {page_count} (OK)")
    else:
        print(f"  Page count: skipped (install poppler-utils for pdfinfo)")

    print("VALIDATION PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
