#!/usr/bin/env python3
"""Verify URLs and admin IPs in the LLM-authored report commentary.

Usage: python3 verify_urls.py <report_path> <probe_baseline.json> <probe_targeted.json> [site_context.md]

Checks:
1. Every URL in LLM-authored commentary exists in at least one source file.
2. No known admin IP (from site-context.md) appears in error/performance/burst/security findings.

Exit 0 if all checks pass.
Exit 1 with a diff report if any violation is found.
"""

import json
import re
import sys
from pathlib import Path


def extract_urls_from_text(text: str) -> set[str]:
    """Extract all https?:// URLs from arbitrary text."""
    return set(re.findall(r'https?://[^\s<>")\]\`]+', text))


def extract_urls_from_markdown_table(text: str) -> set[str]:
    """Extract URLs from markdown table cells (backtick-wrapped paths)."""
    urls = set()
    # Match `/path` or `/path/` inside backticks in table rows
    for match in re.finditer(r'`(/[^`]+)`', text):
        urls.add(match.group(1))
    return urls


def extract_urls_from_json_probe(data: list[dict]) -> set[str]:
    """Extract full URLs from probe JSON output."""
    urls = set()
    for entry in data:
        url = entry.get("url", "")
        if url:
            urls.add(url)
            # Also add the path portion
            path = url.replace("https://", "").split("/", 1)
            if len(path) > 1:
                urls.add("/" + path[1])
    return urls


def extract_urls_from_site_context(text: str) -> set[str]:
    """Extract probe URLs from site-context.md (https://domain/... lines)."""
    return set(re.findall(r'https?://[^\s\n]+', text))


def normalize_url(url: str) -> str:
    """Strip trailing punctuation that got caught in regex."""
    return url.rstrip(".,;:")


def extract_admin_ips(site_context_text: str) -> set[str]:
    """Extract known admin IPs from site-context.md table."""
    ips = set()
    # Match IPs in the "Known admin IPs" column — format: `1.2.3.4` or `1.2.3.4 (description)`
    for match in re.finditer(r'`(\d+\.\d+\.\d+\.\d+)`', site_context_text):
        ips.add(match.group(1))
    return ips


def check_admin_ip_in_findings(report_text: str, admin_ips: set[str]) -> list[str]:
    """Check if any known admin IP appears in LLM-authored error/performance/burst/security findings.

    Only checks Part 1 (LLM-authored commentary), not Part 2 (script-generated tables).
    Returns list of violation descriptions.
    """
    if not admin_ips:
        return []

    violations = []

    # Extract Part 1 only (LLM-authored)
    part1_match = re.search(r'# PART 1:.*?(?=# PART 2:)', report_text, re.DOTALL)
    if not part1_match:
        return []

    part1 = part1_match.group(0)

    # Find sections that are LLM-authored findings (not script-generated)
    # These are the sections between markers
    finding_sections = [
        ('Overall Assessment', r'### Overall Assessment.*?(?=### |\Z)'),
        ('Attack/Security Findings', r'### Attack/Security Findings.*?(?=### |\Z)'),
        ('Cache Root Cause Analysis', r'### Cache Root Cause Analysis.*?(?=### |\Z)'),
        ('Bot Traffic Strategy', r'### Bot Traffic Strategy.*?(?=### |\Z)'),
        ('Concentrated Bursts', r'### Concentrated Traffic Spikes & Bursts.*?(?=### |\Z)'),
        ('Traffic Anomalies', r'### Traffic Anomalies.*?(?=### |\Z)'),
        ('404/Error Fix Recommendations', r'### 404 Errors Recommendations.*?(?=### |\Z)'),
        ('At a Glance', r'## 📌 At a Glance.*?(?=## |# PART 2)',),
        ('Probe Cross-Match', r'## 🔬 Live Probe Cross-Match.*?(?=## |\Z)'),
    ]

    for section_name, pattern in finding_sections:
        section_match = re.search(pattern, part1 if section_name != 'Probe Cross-Match' else report_text, re.DOTALL)
        if section_match:
            section_text = section_match.group(0)
            for ip in admin_ips:
                if ip in section_text:
                    violations.append(f"Admin IP `{ip}` found in **{section_name}** — admin IPs must not appear in error/performance/burst/security findings. Replace with 'admin use' or remove the IP reference.")

    return violations


def main():
    if len(sys.argv) < 3:
        print("Usage: verify_urls.py <report_path> <probe_baseline.json> <probe_targeted.json> [site_context.md]")
        sys.exit(2)

    report_path = Path(sys.argv[1])
    baseline_probe_path = Path(sys.argv[2])
    targeted_probe_path = Path(sys.argv[3])
    site_context_path = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    # --- Build the source URL set ---
    source_urls: set[str] = set()
    site_context_text = ""

    # From probe JSON files
    for probe_path in [baseline_probe_path, targeted_probe_path]:
        if probe_path.exists():
            with open(probe_path) as f:
                source_urls |= extract_urls_from_json_probe(json.load(f))

    # From site-context.md
    if site_context_path and site_context_path.exists():
        with open(site_context_path) as f:
            site_context_text = f.read()
        source_urls |= extract_urls_from_site_context(site_context_text)

    # From report's own data tables (paths like `/ru/uslugi/...`)
    with open(report_path) as f:
        report_text = f.read()
    source_urls |= extract_urls_from_markdown_table(report_text)

    # Normalize all source URLs
    source_urls = {normalize_url(u) for u in source_urls}

    # --- Extract known admin IPs from site-context ---
    admin_ips = extract_admin_ips(site_context_text)

    # --- Extract URLs from LLM-authored commentary sections ---
    commentary_urls: set[str] = set()

    # Find the analyst commentary section (Part 1)
    part1_match = re.search(
        r'# PART 1:.*?(?=# PART 2:)', report_text, re.DOTALL
    )
    if part1_match:
        commentary_urls |= extract_urls_from_text(part1_match.group(0))

    # Find Part 2's LLM-authored sections
    for marker in [r'## 🔬 Live Probe Cross-Match', r'## 📚 Kinsta KB References']:
        section_match = re.search(
            rf'{marker}.*?(?=## |\Z)', report_text, re.DOTALL
        )
        if section_match:
            commentary_urls |= extract_urls_from_text(section_match.group(0))

    # Normalize
    commentary_urls = {normalize_url(u) for u in commentary_urls}

    # --- Check 1: Admin IP in findings ---
    admin_violations = check_admin_ip_in_findings(report_text, admin_ips)

    # --- Check 2: Diff: find commentary URLs not in any source ---
    safe_domains = {"kinsta.com", "platform.openai.com", "docs.kinsta.com"}
    orphan_urls: list[str] = []
    for url in sorted(commentary_urls):
        domain = url.split("/")[2] if "//" in url and url.count("/") >= 2 else ""
        if domain in safe_domains:
            continue
        if url not in source_urls:
            path_part = "/" + url.split("/", 3)[-1] if "//" in url and url.count("/") >= 3 else url
            if path_part not in source_urls and url not in source_urls:
                orphan_urls.append(url)

    # --- Report results ---
    exit_code = 0

    if admin_violations:
        print("❌ ADMIN IP VERIFICATION FAILED — known admin IPs found in findings sections:")
        for v in admin_violations:
            print(f"  - {v}")
        print(f"\nKnown admin IPs: {', '.join(sorted(admin_ips))}")
        print("Fix: replace the admin IP reference with 'admin use' or remove it from the finding.")
        exit_code = 1
    else:
        if admin_ips:
            print(f"✅ Admin IP check passed — no known admin IPs ({', '.join(sorted(admin_ips))}) found in findings sections.")

    if orphan_urls:
        print("\n❌ URL VERIFICATION FAILED — these URLs in the commentary are not attested in any source file:")
        for url in orphan_urls:
            path = "/" + url.split("/", 3)[-1] if "//" in url and url.count("/") >= 3 else url
            candidates = [s for s in source_urls if path.replace("/", "")[:10] in s.replace("/", "")[:20]]
            hint = ""
            if candidates:
                hint = f"  → Did you mean: {candidates[0]}"
            print(f"  - {url}{hint}")
        print(f"\nSource URLs checked: {len(source_urls)}")
        print("Fix: copy the correct URL from the source file and replace the misspelled one.")
        exit_code = 1
    else:
        print(f"✅ URL verification passed — all {len(commentary_urls)} commentary URLs attested in source files ({len(source_urls)} source URLs checked).")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
