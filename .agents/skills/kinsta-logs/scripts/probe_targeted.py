#!/usr/bin/env python3
"""
probe_targeted.py
Encapsulates the logic to extract targeted probe URLs from context.json
and execute the probe_urls.py script.
"""
import json
import os
import subprocess
import sys

def main():
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_file = os.path.join(skill_dir, ".run_state.json")
    probe_script = os.path.join(skill_dir, "scripts", "probe_urls.py")

    if not os.path.exists(state_file):
        print(f"Error: State file not found at {state_file}. Run fetch_logs.sh and analyze_logs.py first.", file=sys.stderr)
        sys.exit(1)

    with open(state_file, "r") as f:
        state = json.load(f)

    # Read from context.json (post-refactor) instead of the old report_path
    context_path = state.get("context_path")
    if not context_path or not os.path.exists(context_path):
        print("Error: context_path not found in state or file missing. Run analyze_logs.py first.", file=sys.stderr)
        sys.exit(1)

    with open(context_path, "r") as f:
        ctx = json.load(f)

    # Extract site domain from the dir path
    dir_parts = state["dir"].strip("/").split("/")
    site_domain = dir_parts[-2]  # e.g. "pbservices.ge"

    urls_to_probe = set()

    # 1. Top cache-MISSed URL
    cross = ctx.get("cross_results", {})
    missed = cross.get("top_missed_urls", [])
    if missed:
        urls_to_probe.add(f"https://{site_domain}{missed[0]['url']}")

    # 2. Slowest page (skip wp-admin)
    access = ctx.get("access_data", {})
    slowest = access.get("slowest_pages", [])
    for entry in slowest:
        url = entry.get("url", "")
        if "wp-admin" not in url:
            urls_to_probe.add(f"https://{site_domain}{url}")
            break

    # 3. First 404 URL
    status_urls = access.get("status_urls", {})
    urls_404 = status_urls.get("404", {})
    if urls_404:
        top_404 = sorted(urls_404.items(), key=lambda x: -x[1])
        if top_404:
            urls_to_probe.add(f"https://{site_domain}{top_404[0][0]}")

    if not urls_to_probe:
        print("Warning: No targeted URLs found in context.json to probe.", file=sys.stderr)
        sys.exit(0)

    output_file = os.path.join(state["dir"], f"{state['timestamp']}_probe_targeted.json")

    print(f"Probing targeted URLs for {site_domain}:")
    for url in urls_to_probe:
        print(f"  - {url}")

    cmd = ["python3", probe_script, "--output", output_file] + list(urls_to_probe)
    subprocess.run(cmd, check=True)

    # Update state
    state["probe_targeted"] = output_file
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    print(f"Targeted probe complete. Results saved to {output_file}")

if __name__ == "__main__":
    main()
