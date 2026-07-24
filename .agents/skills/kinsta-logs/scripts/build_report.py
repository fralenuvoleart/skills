#!/usr/bin/env python3
"""
build_report.py
Merges the LLM's analyst_findings.json with the raw context.json to produce the final Markdown report.
"""
import argparse
import json
import os
import re
import subprocess as sp
import sys
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Build final Markdown report from JSON findings.")
    parser.add_argument("--findings", required=True, help="Path to analyst_findings.json (in run directory alongside context.json)")
    args = parser.parse_args()

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_file = os.path.join(skill_dir, ".run_state.json")

    if not os.path.exists(state_file):
        print(f"Error: State file not found at {state_file}.", file=sys.stderr)
        sys.exit(1)

    with open(state_file, "r") as f:
        state = json.load(f)

    if "context_path" not in state:
        print("Error: context_path not found in state. Run analyze_logs.py first.", file=sys.stderr)
        sys.exit(1)

    context_path = state["context_path"]
    if not os.path.exists(context_path):
        print(f"Error: Context file not found at {context_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.findings):
        print(f"Error: Findings file not found at {args.findings}", file=sys.stderr)
        sys.exit(1)

    with open(context_path, "r") as f:
        context = json.load(f)

    with open(args.findings, "r") as f:
        findings = json.load(f)

    report = context.get("report_skeleton", "")
    if not report:
        print("Error: report_skeleton not found in context.json", file=sys.stderr)
        sys.exit(1)

    # --- Inject New Data Tables into Part 2 ---
    injection_point = "## Live Probe Cross-Match"
    new_tables = []

    access_data = context.get("access_data", {})
    if access_data.get("high_value_slow"):
        new_tables.append("### Slow Responses on High-Value Paths")
        new_tables.append("")
        new_tables.append("| URL | Response Time | IP | Status |")
        new_tables.append("|---|---|---|---|")
        for e in access_data["high_value_slow"][:5]:
            new_tables.append(f"| `{e['url']}` | {e['rt']:.3f}s | `{e['ip']}` | {e['status']} |")
        new_tables.append("")

    if access_data.get("top_wasted_urls"):
        new_tables.append("### Top Server Bottlenecks (Volume x Latency)")
        new_tables.append("")
        new_tables.append("| URL | Total PHP Worker Time | Avg RT | Requests |")
        new_tables.append("|---|---|---|---|")
        for e in access_data["top_wasted_urls"]:
            new_tables.append(f"| `{e['url']}` | **{e['total_time_wasted_sec']:.1f}s** | {e['avg_rt']:.3f}s | {e['count']} |")
        new_tables.append("")

    cross_results = context.get("cross_results", {})
    if cross_results.get("miss_query_params"):
        new_tables.append("### Edge Cache Bypass (Query Parameters)")
        new_tables.append("")
        new_tables.append("| Parameter | Cache MISSes | % of Total MISSes |")
        new_tables.append("|---|---|---|")
        for p in cross_results["miss_query_params"]:
            new_tables.append(f"| `?{p['param']}=...` | {p['count']} | {p['share']:.1f}% |")
        new_tables.append("")

    if cross_results.get("top_asns"):
        new_tables.append("### Distributed Scraper Networks (ASN Aggregation)")
        new_tables.append("")
        new_tables.append("| ASN / Organization | Total Requests | Unique IPs | Avg Req/IP |")
        new_tables.append("|---|---|---|---|")
        for a in cross_results["top_asns"]:
            new_tables.append(f"| {a['org']} | **{a['total_requests']}** | {a['unique_ips']} | {a['avg_requests_per_ip']:.1f} |")
        new_tables.append("")

    if new_tables:
        report = report.replace(injection_point, "\n".join(new_tables) + "\n" + injection_point)

    # Replace markers with findings
    markers = {
        "<!-- LLM:AT_A_GLANCE -->": findings.get("at_a_glance", ""),
        "<!-- LLM:OVERALL_ASSESSMENT -->": findings.get("overall_assessment", ""),
        "<!-- LLM:ATTACK_SECURITY -->": findings.get("attack_security", ""),
        "<!-- LLM:CACHE_ROOT_CAUSE -->": findings.get("cache_root_cause", ""),
        "<!-- LLM:BOT_STRATEGY -->": findings.get("bot_strategy", ""),
        "<!-- LLM:BURST_CARDS -->": findings.get("burst_cards", ""),
        "<!-- LLM:TRAFFIC_ANOMALIES -->": findings.get("traffic_anomalies", ""),
        "<!-- LLM:ERROR_FIXES -->": findings.get("error_fixes", ""),
        "<!-- LLM:PROBE_CROSS_MATCH -->": findings.get("probe_cross_match", ""),
        "<!-- LLM:KB_REFERENCES -->": findings.get("kb_references", "")
    }

    # Strip any leading ###/## headings from finding values — the skeleton
    # already provides section headings before each marker, so including
    # headings in the finding content causes duplication.
    HEADING_RE = re.compile(r'^(?:#{2,3}\s+[^\n]+\n)+')
    for k in markers:
        if markers[k]:
            markers[k] = HEADING_RE.sub('', markers[k])

    for marker, content in markers.items():
        if content:
            report = report.replace(marker, content)

    # Apply verdicts to Part 2 tables
    report = re.sub(r"\| Bytespider \|", r"| Bytespider |", report)
    report = re.sub(r"\| Kinsta-Log-Analyzer-Probe \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| .*pending.* \|", r"| Kinsta-Log-Analyzer-Probe | \1 | \2 | \3 | \4 | ✅ Self |", report)
    report = re.sub(r"\| SevallaCacheWarmer \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| .*pending.* \|", r"| SevallaCacheWarmer | \1 | \2 | \3 | \4 | ✅ Self |", report)
    report = re.sub(r"\|[^|]*pending[^|]*\|", r"| ✅ Keep |", report)

    site_name = context.get("site_name", "unknown")
    env_name = context.get("env_name", "unknown")

    base = os.environ.get("KINSTA_LOG_OUTPUT_DIR", os.path.join(os.path.expanduser("~"), "Downloads", "kinsta-logs"))
    report_dir = os.path.join(base, "reports")
    os.makedirs(report_dir, exist_ok=True)

    ts_compact = datetime.now().strftime("%Y%m%d%H%M")
    report_path = os.path.join(report_dir, f"report_{site_name}_{env_name}_{ts_compact}.md")

    with open(report_path, "w") as f:
        f.write(report)

    print(f"Final report built successfully: {report_path}")

    state["report_path"] = report_path
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    try:
        sp.run(["code", report_path], check=False, timeout=5)
    except Exception:
        pass

if __name__ == "__main__":
    main()
