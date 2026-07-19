#!/usr/bin/env python3
"""
Live HTTP probe — fetches status code, timing, and response headers for a list of
URLs RIGHT NOW, so Step 5 analyst commentary can cross-match live behavior against
what the log window showed. This is a real-time snapshot, NOT historical data — the
log window covers the past N hours, this probe covers the moment it runs. State that
distinction explicitly in the report; never present a live probe result as if it
describes what visitors experienced during the log window.

Usage:
  python3 probe_urls.py --output <probe.json> <url1> <url2> ...
  cat urls.txt | python3 probe_urls.py --output <probe.json> --stdin

Each URL becomes one JSON object: {url, http_code, time_connect, time_first_byte,
time_total, size_download, headers, error}. `error` is set (and other fields are
null) when curl itself failed (DNS, TLS, timeout) rather than the server returning
an HTTP error code — a 404/500 is a normal successful entry with that http_code.

Self-identification: requests carry a distinctive User-Agent (KINSTA_ANALYZER_UA below)
so a FUTURE analysis run's access-log parsing can recognize "this hit was this skill's
own probe," not an unknown visitor or bot — without this, repeated/scheduled runs of
this skill could eventually flag their own probe traffic as a burst anomaly in a later
report. See analyze_logs.py's BOT_CATEGORIES / bot_patterns for the matching entry.
"""
import json, subprocess, sys, argparse

KINSTA_ANALYZER_UA = "Kinsta-Log-Analyzer-Probe/1.0 (+internal verification; not organic traffic)"

def probe_one(url: str, timeout_connect: float = 5, timeout_total: float = 10) -> dict:
    try:
        r = subprocess.run(
            ["curl", "-s", "-D", "-", "-o", "/dev/null",
             "-A", KINSTA_ANALYZER_UA,
             "--connect-timeout", str(timeout_connect), "--max-time", str(timeout_total),
             "-w", "\n__METRICS__ %{http_code}|%{time_connect}|%{time_starttransfer}|%{time_total}|%{size_download}",
             url],
            capture_output=True, text=True, timeout=timeout_total + 5,
        )
    except subprocess.TimeoutExpired:
        return {"url": url, "http_code": None, "time_connect": None, "time_first_byte": None,
                "time_total": None, "size_download": None, "headers": {},
                "error": "local timeout (curl did not return in time)"}
    except Exception as e:
        return {"url": url, "http_code": None, "time_connect": None, "time_first_byte": None,
                "time_total": None, "size_download": None, "headers": {},
                "error": f"curl invocation failed: {e}"}

    out = r.stdout
    metrics_line = ""
    header_lines = []
    for line in out.splitlines():
        if line.startswith("__METRICS__"):
            metrics_line = line[len("__METRICS__"):].strip()
        else:
            header_lines.append(line)

    parts = (metrics_line.split("|") + ["", "", "", "", ""])[:5]
    code, t_conn, t_fb, t_total, size = parts

    headers = {}
    for line in header_lines:
        if ":" in line:
            k, _, v = line.partition(":")
            headers[k.strip()] = v.strip()

    err = None
    if r.returncode != 0:
        err = (r.stderr or "").strip()[:200] or f"curl exited {r.returncode}"

    def _f(s):
        try: return float(s)
        except ValueError: return None
    def _i(s):
        try: return int(float(s))
        except ValueError: return None

    return {
        "url": url,
        "http_code": code or None,
        "time_connect": _f(t_conn),
        "time_first_byte": _f(t_fb),
        "time_total": _f(t_total),
        "size_download": _i(size),
        "headers": headers,
        "error": err,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("urls", nargs="*", help="URLs to probe")
    p.add_argument("--output", required=True, help="Output JSON file path")
    p.add_argument("--stdin", action="store_true", help="Also read URLs (one per line) from stdin")
    args = p.parse_args()

    urls = list(args.urls)
    if args.stdin:
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    # De-dupe while preserving order — the caller may list a dynamic URL that
    # happens to already be in the fixed sample set.
    seen = set(); deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u); deduped.append(u)

    results = [probe_one(u) for u in deduped]

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    ok = sum(1 for r in results if r["error"] is None)
    print(f"Probed {len(results)} URL(s): {ok} responded, {len(results)-ok} failed.")
    print(f"Written to {args.output}")

if __name__ == "__main__":
    main()
