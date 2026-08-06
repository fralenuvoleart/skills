#!/usr/bin/env python3
"""Tests for analyze_logs.py + build_report.py — validates marker emission, report structure, and --validate pass."""

import json, os, subprocess, sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "analyze_logs.py")
BUILD_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "build_report.py")
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

REQUIRED_MARKERS = [
    "<!-- LLM:AT_A_GLANCE -->",
    "<!-- LLM:OVERALL_ASSESSMENT -->",
    "<!-- LLM:ATTACK_SECURITY -->",
    "<!-- LLM:CACHE_ROOT_CAUSE -->",
    "<!-- LLM:BOT_STRATEGY -->",
    "<!-- LLM:BURST_CARDS -->",
    "<!-- LLM:TRAFFIC_ANOMALIES -->",
    "<!-- LLM:ERROR_FIXES -->",
    "<!-- LLM:PROBE_CROSS_MATCH -->",
    "<!-- LLM:KB_REFERENCES -->",
]

REQUIRED_DIVIDERS = [
    "PART 1: SUMMARY & FINDINGS",
    "PART 2: TECHNICAL APPENDIX",
]

FORBIDDEN_SECTIONS = [
    "Health Summary",
    "How to Improve Cache HIT Rate",
    "Scanner IPs — Block List",
    "Directory Scanner Activity",
]

EMPTY_FINDINGS = {
    "overall_assessment": "",
    "attack_security": "",
    "cache_root_cause": "",
    "bot_strategy": "",
    "burst_cards": "",
    "traffic_anomalies": "",
    "error_fixes": "",
    "probe_cross_match": "",
    "kb_references": "",
    "at_a_glance": "",
}


def run_pipeline(error_json, access_json, cache_json, args=None):
    """Run analyze_logs.py → build_report.py and return (returncode, stdout, stderr, report_path)."""
    cmd = ["python3", SCRIPT, "--error_file", error_json, "--access_file", access_json, "--cache_file", cache_json, "--no-geoip"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return result.returncode, result.stdout, result.stderr, None

    # Parse context.json path from analyze_logs.py output
    context_path = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("📄 Context data written to "):
            context_path = line.replace("📄 Context data written to ", "").strip()
            break

    if not context_path or not os.path.exists(context_path):
        return -1, result.stdout, "Could not find context.json", None

    # Write empty findings next to context.json
    findings_dir = os.path.dirname(context_path)
    findings_path = os.path.join(findings_dir, "test_analyst_findings.json")
    with open(findings_path, "w") as f:
        json.dump(EMPTY_FINDINGS, f)

    # Run build_report.py to generate the report
    build_result = subprocess.run(
        ["python3", BUILD_SCRIPT, "--findings", findings_path],
        capture_output=True, text=True,
    )

    report_path = None
    for line in build_result.stdout.splitlines():
        if line.startswith("Final report built successfully: "):
            report_path = line.replace("Final report built successfully: ", "").strip()
            break

    # Clean up findings file
    if os.path.exists(findings_path):
        os.remove(findings_path)

    return build_result.returncode, build_result.stdout, build_result.stderr, report_path


def cleanup(report_path):
    """Remove only the generated report file, not the entire reports/ directory."""
    if report_path and os.path.exists(report_path):
        os.remove(report_path)


def test_generates_report_with_all_markers():
    """Report must contain all 10 LLM markers."""
    rc, stdout, stderr, report_path = run_pipeline(
        os.path.join(FIXTURES, "error.json"),
        os.path.join(FIXTURES, "access.json"),
        os.path.join(FIXTURES, "cache.json"),
    )
    assert rc == 0, f"Script exited with {rc}: {stderr}"
    assert report_path and os.path.exists(report_path), f"No report: {stdout}"

    with open(report_path) as f:
        content = f.read()

    missing = [m for m in REQUIRED_MARKERS if m not in content]
    cleanup(report_path)
    assert not missing, f"Missing markers: {missing}"


def test_report_has_part_dividers():
    """Report must have Part 1 and Part 2 dividers."""
    rc, stdout, stderr, report_path = run_pipeline(
        os.path.join(FIXTURES, "error.json"),
        os.path.join(FIXTURES, "access.json"),
        os.path.join(FIXTURES, "cache.json"),
    )
    assert rc == 0

    with open(report_path) as f:
        content = f.read()

    for divider in REQUIRED_DIVIDERS:
        assert divider in content, f"Missing divider: {divider}"
    cleanup(report_path)


def test_no_forbidden_sections():
    """Report must not contain permanently suppressed sections."""
    rc, stdout, stderr, report_path = run_pipeline(
        os.path.join(FIXTURES, "error.json"),
        os.path.join(FIXTURES, "access.json"),
        os.path.join(FIXTURES, "cache.json"),
    )
    assert rc == 0

    with open(report_path) as f:
        content = f.read()

    for forbidden in FORBIDDEN_SECTIONS:
        assert forbidden not in content, f"Forbidden section found: {forbidden}"
    cleanup(report_path)


def test_validate_detects_unfilled_markers():
    """--validate should FAIL on skeleton with unfilled markers (exit code 1)."""
    # Generate context.json first (skip build_report to keep markers unfilled)
    cmd = ["python3", SCRIPT, "--error_file", os.path.join(FIXTURES, "error.json"),
           "--access_file", os.path.join(FIXTURES, "access.json"),
           "--cache_file", os.path.join(FIXTURES, "cache.json"), "--no-geoip"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0

    # Extract context.json, load report_skeleton, write it as a .md file
    context_path = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("📄 Context data written to "):
            context_path = line.replace("📄 Context data written to ", "").strip()
            break
    assert context_path and os.path.exists(context_path)

    with open(context_path) as f:
        ctx = json.load(f)

    skeleton = ctx.get("report_skeleton", "")
    assert skeleton, "report_skeleton not found in context.json"

    skeleton_path = context_path.replace("_context.json", "_skeleton.md")
    with open(skeleton_path, "w") as f:
        f.write(skeleton)

    # Validate the skeleton — should fail because markers are unfilled
    val_result = subprocess.run(
        ["python3", SCRIPT, "--validate", skeleton_path],
        capture_output=True, text=True,
    )
    os.remove(skeleton_path)
    assert val_result.returncode == 1, \
        f"--validate should fail (exit 1) on unfilled skeleton, got {val_result.returncode}"
    assert "unfilled" in val_result.stdout.lower() or "LLM" in val_result.stdout, \
        f"Validation should report unfilled markers: {val_result.stdout[:200]}"


def test_missing_cache_log_handled_gracefully():
    """Script should work without cache.json (optional argument)."""
    nonexistent = os.path.join(FIXTURES, "nonexistent_cache.json")
    cmd = ["python3", SCRIPT, "--error_file", os.path.join(FIXTURES, "error.json"),
           "--access_file", os.path.join(FIXTURES, "access.json"), "--no-geoip"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Script should handle missing cache: exit={result.returncode}, stderr={result.stderr[:200]}"

    # Extract context.json and check cache section
    context_path = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("📄 Context data written to "):
            context_path = line.replace("📄 Context data written to ", "").strip()
            break
    assert context_path and os.path.exists(context_path)

    with open(context_path) as f:
        ctx = json.load(f)
    assert "cache_data" in ctx, "Should have cache_data key (even if empty)"
    # Remove generated context.json (it's in the fixtures dir, which we want clean)
    os.remove(context_path)


def test_report_written_to_reports_folder():
    """Report must be written to kinsta-logs/reports/."""
    rc, stdout, stderr, report_path = run_pipeline(
        os.path.join(FIXTURES, "error.json"),
        os.path.join(FIXTURES, "access.json"),
        os.path.join(FIXTURES, "cache.json"),
    )
    assert rc == 0
    assert "kinsta-logs/reports/" in report_path, \
        f"Report not in reports/ folder: {report_path}"
    cleanup(report_path)


if __name__ == "__main__":
    tests = [
        ("generates report with all 10 markers", test_generates_report_with_all_markers),
        ("report has Part 1/Part 2 dividers", test_report_has_part_dividers),
        ("no forbidden sections", test_no_forbidden_sections),
        ("--validate detects unfilled markers", test_validate_detects_unfilled_markers),
        ("missing cache log handled gracefully", test_missing_cache_log_handled_gracefully),
        ("report written to reports/ folder", test_report_written_to_reports_folder),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    sys.exit(1 if failed else 0)
