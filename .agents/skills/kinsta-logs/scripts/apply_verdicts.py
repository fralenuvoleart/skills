#!/usr/bin/env python3
"""
apply_verdicts.py
Encapsulates the logic to inject verdicts into the Markdown report tables.
Replaces the brittle sed commands in SKILL.md.
"""
import json
import os
import re
import sys

def main():
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_file = os.path.join(skill_dir, ".run_state.json")

    if not os.path.exists(state_file):
        print(f"Error: State file not found at {state_file}.", file=sys.stderr)
        sys.exit(1)

    with open(state_file, "r") as f:
        state = json.load(f)

    if "report_path" not in state:
        print("Error: report_path not found in state.", file=sys.stderr)
        sys.exit(1)

    report_path = state["report_path"]
    if not os.path.exists(report_path):
        print(f"Error: Report file not found at {report_path}", file=sys.stderr)
        sys.exit(1)

    # Read the report
    with open(report_path, "r") as f:
        content = f.read()

    # Apply specific verdicts first
    content = re.sub(r"\| Bytespider \| (.*?) \| ⏳ \*pending\* \|", r"| Bytespider | \1 | 🔧 Block |", content)
    content = re.sub(r"\| Kinsta-Log-Analyzer-Probe \| (.*?) \| ⏳ \*pending\* \|", r"| Kinsta-Log-Analyzer-Probe | \1 | ✅ Self |", content)
    
    # Apply catch-all fallback
    content = re.sub(r"\| ⏳ \*pending\* \|", r"| ✅ Keep |", content)

    # Write back
    with open(report_path, "w") as f:
        f.write(content)

    print(f"Verdicts applied to {report_path}")

if __name__ == "__main__":
    main()
