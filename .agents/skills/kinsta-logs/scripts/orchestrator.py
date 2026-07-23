#!/usr/bin/env python3
"""
orchestrator.py
Master orchestrator for the Kinsta Log Analyzer data gathering pipeline.
Handles site discovery, log fetching, and baseline probing in a single command.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

def main():
    parser = argparse.ArgumentParser(description="Orchestrate Kinsta log gathering.")
    parser.add_argument("--site", help="Site name to analyze (defaults to config/defaults.json)")
    parser.add_argument("--env", default="live", help="Environment name (default: live)")
    args = parser.parse_args()

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Determine Site
    site_name = args.site
    if not site_name:
        defaults_file = os.path.join(skill_dir, "config", "defaults.json")
        if os.path.exists(defaults_file):
            with open(defaults_file, "r") as f:
                defaults = json.load(f)
                site_name = defaults.get("default_site")
                if not args.env and "default_environment" in defaults:
                    args.env = defaults["default_environment"]
        
        if not site_name:
            print("Error: No site specified and no default found in config/defaults.json", file=sys.stderr)
            sys.exit(1)

    print(f"Orchestrating data gathering for site: {site_name} (env: {args.env})")

    # 2. Discover Site ID and Env ID
    print("Discovering site and environment IDs...")
    list_script = os.path.join(skill_dir, "scripts", "list_sites.sh")
    try:
        result = subprocess.run(["bash", list_script], capture_output=True, text=True, check=True)
        sites_data = json.loads(result.stdout)
        
        # Handle JSON-RPC response structure
        if "result" in sites_data and "content" in sites_data["result"]:
            try:
                raw = json.loads(sites_data["result"]["content"][0]["text"])
                # API wraps sites in {"company": {"sites": [...]}}
                sites_list = raw.get("company", {}).get("sites", [])
            except (json.JSONDecodeError, KeyError, IndexError):
                sites_list = []
        else:
            sites_list = sites_data

        site_id = None
        env_id = None
        
        for site in sites_list:
            if site.get("name") == site_name or site.get("display_name") == site_name:
                site_id = site.get("id")
                for env in site.get("environments", []):
                    if env.get("name") == args.env or env.get("display_name") == args.env:
                        env_id = env.get("id")
                        break
                break
        
        if not env_id:
            print(f"Error: Could not find environment '{args.env}' for site '{site_name}'", file=sys.stderr)
            sys.exit(1)
            
        print(f"Found Env ID: {env_id}")

    except subprocess.CalledProcessError as e:
        print(f"Error running list_sites.sh: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error parsing output from list_sites.sh", file=sys.stderr)
        sys.exit(1)

    # 3. Setup Output Directory
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    base = os.environ.get("KINSTA_LOG_OUTPUT_DIR", os.path.join(os.path.expanduser("~"), "Downloads", "kinsta-logs"))
    output_dir = os.path.join(base, site_name, args.env)
    os.makedirs(output_dir, exist_ok=True)

    # 4. Fetch Logs
    print(f"Fetching logs to {output_dir}...")
    fetch_script = os.path.join(skill_dir, "scripts", "fetch_logs.sh")
    try:
        subprocess.run(["bash", fetch_script, env_id, output_dir, ts], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching logs: {e}", file=sys.stderr)
        sys.exit(1)

    # 5. Run Baseline Probe
    print("Running baseline probe...")
    probe_script = os.path.join(skill_dir, "scripts", "probe_baseline.py")
    try:
        subprocess.run(["python3", probe_script, "--dir", output_dir, "--timestamp", ts], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running baseline probe: {e}", file=sys.stderr)
        # Don't exit, probe might fail if no URLs are defined, which is okay

    print("\n✅ Orchestration complete. Data gathered successfully.")
    print(f"Next step: Run analyze_logs.py")

if __name__ == "__main__":
    main()
