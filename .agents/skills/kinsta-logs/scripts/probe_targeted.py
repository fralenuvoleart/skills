#!/usr/bin/env python3
"""
probe_targeted.py
Encapsulates the logic to extract targeted probe URLs from the generated report
and execute the probe_urls.py script.
"""
import json
import os
import re
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

    if "report_path" not in state:
        print("Error: report_path not found in state. Run analyze_logs.py first.", file=sys.stderr)
        sys.exit(1)

    report_path = state["report_path"]
    if not os.path.exists(report_path):
        print(f"Error: Report file not found at {report_path}", file=sys.stderr)
        sys.exit(1)

    # Extract site name from the dir path
    dir_parts = state["dir"].strip("/").split("/")
    site_name = dir_parts[-2]
    site_domain = site_name # Assuming site_name is the domain for now, might need refinement

    urls_to_probe = set()

    try:
        with open(report_path, "r") as f:
            content = f.read()

        # Extract MISS URL
        miss_match = re.search(r"### Pages Most Frequently Missing Cache.*?\|---.*?\|\n\| `([^`]+)`", content, re.DOTALL)
        if miss_match:
            urls_to_probe.add(f"https://{site_domain}{miss_match.group(1)}")

        # Extract SLOW URL (skip wp-admin)
        slow_match = re.search(r"\*\*Slowest individual requests observed:\*\*.*?\|---.*?\|\n((?:\|.*?\n){1,10})", content, re.DOTALL)
        if slow_match:
            for line in slow_match.group(1).split("\n"):
                if line.startswith("|") and "wp-admin" not in line:
                    url_m = re.search(r"\| `([^`]+)`", line)
                    if url_m:
                        urls_to_probe.add(f"https://{site_domain}{url_m.group(1)}")
                        break # Just take the first non-admin one

        # Extract ERR URL (404)
        err_match = re.search(r"\*\*404\*\* —.*?\|---.*?\|\n\| `([^`]+)`", content, re.DOTALL)
        if err_match:
            urls_to_probe.add(f"https://{site_domain}{err_match.group(1)}")

    except Exception as e:
        print(f"Error parsing report {report_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if not urls_to_probe:
        print("Warning: No targeted URLs found in the report to probe.", file=sys.stderr)
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
