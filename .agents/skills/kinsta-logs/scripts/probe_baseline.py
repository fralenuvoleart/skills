#!/usr/bin/env python3
"""
probe_baseline.py
Encapsulates the logic to extract baseline probe URLs from site-context.md
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
    site_context_file = os.path.join(skill_dir, "references", "site-context.md")
    probe_script = os.path.join(skill_dir, "scripts", "probe_urls.py")

    if not os.path.exists(state_file):
        print(f"Error: State file not found at {state_file}. Run fetch_logs.sh first.", file=sys.stderr)
        sys.exit(1)

    with open(state_file, "r") as f:
        state = json.load(f)

    # Extract site name from the dir path (e.g., ~/Downloads/kinsta-logs/{site_name}/{env_name})
    dir_parts = state["dir"].strip("/").split("/")
    if len(dir_parts) < 2:
        print(f"Error: Could not determine site name from dir path: {state['dir']}", file=sys.stderr)
        sys.exit(1)
    site_name = dir_parts[-2]

    # Extract URLs from site-context.md
    urls = []
    try:
        with open(site_context_file, "r") as f:
            content = f.read()
        
        # Find the block for the specific site
        site_block_match = re.search(rf"### {re.escape(site_name)}(.*?)(?=### |## |$)", content, re.DOTALL)
        if site_block_match:
            site_block = site_block_match.group(1)
            # Extract URLs starting with https://
            urls = re.findall(r"^(https://[^\s]+)", site_block, re.MULTILINE)
    except Exception as e:
        print(f"Error reading {site_context_file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not urls:
        print(f"Warning: No baseline probe URLs found for site '{site_name}' in site-context.md", file=sys.stderr)
        sys.exit(0)

    output_file = os.path.join(state["dir"], f"{state['timestamp']}_probe_baseline.json")
    
    print(f"Probing baseline URLs for {site_name}:")
    for url in urls:
        print(f"  - {url}")

    cmd = ["python3", probe_script, "--output", output_file] + urls
    subprocess.run(cmd, check=True)
    
    # Update state
    state["probe_baseline"] = output_file
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)
    
    print(f"Baseline probe complete. Results saved to {output_file}")

if __name__ == "__main__":
    main()
