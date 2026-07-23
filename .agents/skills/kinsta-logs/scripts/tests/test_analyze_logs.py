#!/usr/bin/env python3
"""Tests for analyze_logs.py — validates marker emission, report structure, and --validate pass."""

import os, subprocess, sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "analyze_logs.py")
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

def run_analyze(error_json, access_json, cache_json, args=None):
    """Run analyze_logs.py and return (returncode, stdout, stderr, report_path)."""
    cmd = ["python3", SCRIPT, error_json, access_json, cache_json, "--no-geoip"]
    if args:
        cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    report_path = None
    for line in result.stdout.splitlines():
        if line.startswith("📄 "):
            report_path = line[2:].strip()
    return result.returncode, result.stdout, result.stderr, report_path

def cleanup(report_path):
    """Remove only the generated report file, not the entire reports/ directory."""
    if report_path and os.path.exists(report_path):
        os.remove(report_path)

def test_generates_report_with_all_markers():
    """Report must contain all 10 LLM markers."""
    rc, stdout, stderr, report_path = run_analyze(
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
    rc, stdout, stderr, report_path = run_analyze(
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
    rc, stdout, stderr, report_path = run_analyze(
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
    rc, stdout, stderr, report_path = run_analyze(
        os.path.join(FIXTURES, "error.json"),
        os.path.join(FIXTURES, "access.json"),
        os.path.join(FIXTURES, "cache.json"),
    )
    assert rc == 0

    result = subprocess.run(
        ["python3", SCRIPT, "--validate", report_path],
        capture_output=True, text=True,
    )
    # Validation should fail because markers are unfilled — expected for a skeleton
    assert result.returncode == 1, \
        f"--validate should fail (exit 1) on unfilled skeleton, got {result.returncode}"
    assert "unfilled" in result.stdout.lower() or "LLM" in result.stdout, \
        f"Validation should report unfilled markers: {result.stdout[:200]}"
    cleanup(report_path)

def test_missing_cache_log_handled_gracefully():
    """Script should work without cache.json (optional argument)."""
    nonexistent = os.path.join(FIXTURES, "nonexistent_cache.json")
    rc, stdout, stderr, report_path = run_analyze(
        os.path.join(FIXTURES, "error.json"),
        os.path.join(FIXTURES, "access.json"),
        nonexistent,
    )
    assert rc == 0, f"Script should handle missing cache: exit={rc}, stderr={stderr[:200]}"
    assert report_path and os.path.exists(report_path)

    with open(report_path) as f:
        content = f.read()
    assert "No cache-perf data" in content or "cache" in content.lower(), \
        f"Should mention missing cache data"
    cleanup(report_path)

def test_report_written_to_reports_folder():
    """Report must be written to ~/Downloads/kinsta-logs/reports/."""
    rc, stdout, stderr, report_path = run_analyze(
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
