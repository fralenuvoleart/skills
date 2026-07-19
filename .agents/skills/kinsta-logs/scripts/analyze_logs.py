#!/usr/bin/env python3
"""
Kinsta Log Analyzer — business-owner health report.
Usage: python3 scripts/analyze_logs.py <error.json> <access.json> [cache.json] [--hours N] [--no-geoip]

Note: ip_country() performs a live network call to ipinfo.io per unique IP and is
therefore NOT deterministic — results depend on network availability and a
third-party service, and visitor IPs are sent off-site for classification.
Pass --no-geoip to disable this (privacy/speed/determinism).
"""
import json, re, sys, os, argparse, subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

def bar_chart(value, max_val=100, width=15, fill="█", empty="░"):
    """Returns an inline-HTML-wrapped bar (blue, monospace) — raw HTML passthrough is
    supported by the Markdown renderer used for both the on-screen report and the PDF
    export, so this renders as a colored bar rather than default (black) body text."""
    pct = min(value / max(max_val, 1), 1.0)
    n = int(pct * width)
    bar_text = fill * n + empty * (width - n)
    return f'<span style="color:#2563eb; font-family: monospace;">{bar_text}</span>'

def flag_emoji(cc):
    """Derive a flag emoji from any 2-letter ISO country code (no hardcoded table)."""
    if not cc or len(cc) != 2 or not cc.isalpha(): return ""
    return "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in cc)

GEOIP_ENABLED = True  # toggled by --no-geoip in main()
_GEOIP_CACHE = {}

# Sentinel distinguishing "we never looked this up" (disabled/skipped) from "we looked it up
# and ipinfo.io genuinely returned nothing" (empty string). Conflating these two states is a
# real bug: showing "unknown"/"no PTR record" when geo-IP was simply turned off looks exactly
# like a broken lookup, and there is no way for the reader to tell the difference without this.
GEOIP_DISABLED = "\x00DISABLED\x00"

# Tracks every lookup this run so the report can show one clear banner instead of dozens of
# per-row "unknown" cells when geo-IP is off or ipinfo.io is failing/rate-limiting broadly.
_LOOKUP_STATS = {"attempted": 0, "empty": 0}

def ip_country(ip):
    """Geo-IP lookup via ipinfo.io. NETWORK CALL — not deterministic, cached per-run.
    Returns (country_code, flag). country_code is GEOIP_DISABLED when --no-geoip was passed,
    '?' when looked up but ipinfo.io returned nothing/failed, or the real 2-letter code."""
    if not GEOIP_ENABLED: return GEOIP_DISABLED, ""
    if ip in _GEOIP_CACHE: return _GEOIP_CACHE[ip]
    _LOOKUP_STATS["attempted"] += 1
    try:
        r = subprocess.run(["curl", "-s", "--connect-timeout", "2", "--max-time", "3",
                           f"https://ipinfo.io/{ip}/country"], capture_output=True, text=True)
        cc = r.stdout.strip()[:2] if r.stdout.strip() else "?"
        if cc == "?": _LOOKUP_STATS["empty"] += 1
        result = (cc, flag_emoji(cc))
    except Exception:
        _LOOKUP_STATS["empty"] += 1
        result = ("?", "")
    _GEOIP_CACHE[ip] = result
    return result

_ORG_CACHE = {}
_HOSTING_HINTS = re.compile(
    r"amazon|aws|google|microsoft|azure|digitalocean|linode|vultr|ovh|hetzner|"
    r"kinsta|cloudflare|hosting|datacenter|data center|colo|leaseweb|contabo|"
    r"m247|choopa|psychz|hivelocity|akamai|fastly|oracle cloud",
    re.IGNORECASE,
)

def ip_org(ip):
    """ASN/organization lookup via ipinfo.io. NETWORK CALL — not deterministic, cached per-run.
    Returns (org_string, is_likely_hosting). org_string is GEOIP_DISABLED when --no-geoip was
    passed, '' when looked up but ipinfo.io returned nothing, or the real org string.
    Purpose: a country flag alone cannot distinguish a real residential visitor from a
    datacenter/proxy/CDN IP that merely geolocates to that country — this tells the analyst
    which case applies so the report doesn't misrepresent infrastructure traffic as visitors."""
    if not GEOIP_ENABLED: return GEOIP_DISABLED, False
    if ip in ("::1", "127.0.0.1"): return "localhost", False
    if ip in _ORG_CACHE: return _ORG_CACHE[ip]
    _LOOKUP_STATS["attempted"] += 1
    try:
        r = subprocess.run(["curl", "-s", "--connect-timeout", "2", "--max-time", "3",
                           f"https://ipinfo.io/{ip}/org"], capture_output=True, text=True)
        org = r.stdout.strip()
        if not org: _LOOKUP_STATS["empty"] += 1
        is_hosting = bool(_HOSTING_HINTS.search(org)) if org else False
        result = (org, is_hosting)
    except Exception:
        _LOOKUP_STATS["empty"] += 1
        result = ("", False)
    _ORG_CACHE[ip] = result
    return result

_HOSTNAME_CACHE = {}
# Reverse-DNS patterns that specifically indicate "a third party's customer VM rented from
# this cloud vendor," NOT the vendor's own first-party crawler/bot infrastructure. This is a
# materially different fact than "org = Google LLC" / "org = Amazon.com, Inc." alone — an ASN
# match only tells you who owns the IP block, not whether the traffic is Google's own Googlebot
# vs. some unrelated customer's scraper running on a rented GCP/EC2 instance. Only includes
# patterns stable and well-documented for over a decade; deliberately does not attempt to
# classify every cloud provider — an unmatched hostname just gets displayed as-is for the
# analyst to judge, rather than guessing.
_CLOUD_CUSTOMER_VM_HINTS = re.compile(
    r"googleusercontent\.com$|compute\.amazonaws\.com$|\.amazonaws\.com$",
    re.IGNORECASE,
)

def ip_hostname(ip):
    """Reverse-DNS (PTR) lookup via ipinfo.io. NETWORK CALL — not deterministic, cached per-run.
    Returns (hostname, is_customer_vm). hostname is GEOIP_DISABLED when --no-geoip was passed,
    '' when looked up but there's genuinely no PTR record, or the real hostname.
    Purpose: distinguishes a cloud vendor's OWN service (e.g. Googlebot, PTR under googlebot.com)
    from an unrelated third party's customer VM merely rented from that same vendor (e.g. PTR
    under googleusercontent.com) — the ASN/org alone cannot make this distinction, and conflating
    them mislabels "some GCP customer's scraper" as "Google's own crawler."""
    if not GEOIP_ENABLED: return GEOIP_DISABLED, False
    if ip in ("::1", "127.0.0.1"): return "", False
    if ip in _HOSTNAME_CACHE: return _HOSTNAME_CACHE[ip]
    _LOOKUP_STATS["attempted"] += 1
    try:
        r = subprocess.run(["curl", "-s", "--connect-timeout", "2", "--max-time", "3",
                           f"https://ipinfo.io/{ip}/hostname"], capture_output=True, text=True)
        hostname = r.stdout.strip()
        if not hostname: _LOOKUP_STATS["empty"] += 1
        is_customer_vm = bool(_CLOUD_CUSTOMER_VM_HINTS.search(hostname)) if hostname else False
        result = (hostname, is_customer_vm)
    except Exception:
        result = ("", False)
    _HOSTNAME_CACHE[ip] = result
    return result

def ip_safety(ip, count):
    """Classify IP by observed request behavior — NOT by country of origin.
    Returns (icon, text) so the report can render them as separate table columns
    instead of an icon glued to the front of a sentence."""
    if ip in ("::1", "127.0.0.1"): return "⚪", "localhost — do not block"
    if re.match(r"^10\.|^172\.(1[6-9]|2\d|3[01])\.|^192\.168\.", ip): return "⚪", "private — do not block"
    if count >= 5: return "⚠️", "repeated scanning behavior — review and consider blocking"
    return "ℹ️", "low volume — monitor before blocking"

def geo_display(value, empty_label="unknown"):
    """Render a geo-IP lookup result consistently everywhere it's shown in the report.
    Distinguishes three real states instead of collapsing them into one confusing 'unknown':
    (1) lookup disabled (--no-geoip) → '*geo-IP disabled*', (2) looked up but genuinely empty
    → empty_label, (3) a real value → the value itself. Showing 'unknown' for state (1) looks
    exactly like a broken script to a reader who doesn't know --no-geoip was passed."""
    if value == GEOIP_DISABLED: return "*geo-IP disabled*"
    if not value: return f"*{empty_label}*"
    return value

# ASN/org substrings for residential/mobile ISPs where an IP is very likely to be dynamically
# reassigned or shared behind CGNAT — blocking it risks catching a future unrelated, legitimate
# visitor. This is the opposite end of the spectrum from _HOSTING_HINTS: a hosting/VPS/datacenter
# ASN is normally SAFE to block outright (that IP won't be reassigned to a random home user next
# week); a residential/mobile ASN is NOT safe to block permanently without a strong pattern match.
_RESIDENTIAL_ISP_HINTS = re.compile(
    r"telecom|telekom|broadband|cable|fiber|fibre|mobile|wireless|cellular|"
    r"communications|\bisp\b|internet service|dsl|ppp|dynamic",
    re.IGNORECASE,
)

def blocking_risk(org, is_hosting):
    """Plain-language verdict on whether blocking this IP outright is safe, based on its ASN
    type — not a guess, a direct read of the org string already fetched via ip_org(). Returns
    a short string for direct inclusion in the report; never leaves this unstated when an IP is
    being recommended for blocking."""
    if org == GEOIP_DISABLED: return "unknown — re-run without --no-geoip to check"
    if not org: return "unknown — ASN lookup returned nothing for this IP"
    if is_hosting:
        return "safe — dedicated hosting/VPS IP, not shared with other users"
    if _RESIDENTIAL_ISP_HINTS.search(org):
        return "⚠️ caution — residential/mobile ISP IP, may be dynamically reassigned to a different (legitimate) user later"
    return "uncertain — ASN doesn't clearly indicate hosting or residential; verify manually before blocking"

def parse_apache_ts(ts_str):
    try: return datetime.strptime(ts_str, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError: return None

def parse_error_ts(ts_str):
    try: return datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError: return None

def time_ago(ts):
    if ts is None: return ""
    diff = datetime.now(timezone.utc) - ts
    if diff < timedelta(minutes=1): return "just now"
    if diff < timedelta(hours=1): return f"{int(diff.total_seconds()/60)}m ago"
    if diff < timedelta(hours=24): return f"{int(diff.total_seconds()/3600)}h ago"
    return f"{diff.days}d ago"

def extract_logs(fpath):
    if not os.path.exists(fpath): return None, "file not found"
    with open(fpath) as f: data = json.load(f)
    if data.get("isError") or data.get("result", {}).get("isError"):
        return None, data["result"]["content"][0]["text"]
    try:
        inner = json.loads(data["result"]["content"][0]["text"])
        return inner["environment"]["container_info"]["logs"], None
    except (json.JSONDecodeError, KeyError) as e: return None, f"Format: {e}"

def norm(url): return url.split("?")[0].rstrip("/") or "/"

def filter_by_hours(logs, hours, log_type):
    if hours is None: return logs, None, None, len(logs.strip().split("\n"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    lines = logs.strip().split("\n")
    filtered, first_ts, last_ts = [], None, None
    for line in lines:
        if log_type == "error":
            m = re.match(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})", line)
            ts = parse_error_ts(m.group(1)) if m else None
        else:
            m = re.match(r".*?\[([^\]]+)\]", line)
            ts = parse_apache_ts(m.group(1)) if m else None
        if ts is None: filtered.append(line); continue
        if first_ts is None: first_ts = ts
        last_ts = ts
        if ts >= cutoff: filtered.append(line)
    return "\n".join(filtered), first_ts, last_ts, len(lines)

# Kinsta containers use paths like /www/{site}_{id}/public/... — strip that
# generically so nothing site-specific is hardcoded into this analyzer.
_SITE_PATH_RE = re.compile(r"^/www/[^/]+/public")
def relpath(p):
    stripped = _SITE_PATH_RE.sub("", p)
    return stripped or p

def extract_client(line):
    """Client IP from an nginx error-log line, if present on that line."""
    m = re.search(r"client: ([0-9a-fA-F:.]+)", line)
    return m.group(1) if m else None

def extract_request(line):
    """The 'METHOD /url HTTP/x.x' request string from an nginx error-log line, if present."""
    m = re.search(r'request: "([^"]+)"', line)
    return m.group(1) if m else None

# PHP error/warning/notice lines end either "... in FILE on line N" or "... in FILE:N"
_PHP_SIG_ON_LINE = re.compile(
    r"PHP message:\s*PHP (Fatal error|Parse error|Warning|Notice|Deprecated):?\s+(.*?)\s+in\s+(\S+)\s+on\s+line\s+(\d+)"
)
_PHP_SIG_COLON = re.compile(
    r"PHP message:\s*PHP (Fatal error|Parse error|Warning|Notice|Deprecated):?\s+(.*?)\s+in\s+(\S+):(\d+)"
)

def extract_php_signature(line):
    """Extract (severity, message, relative_file, line_no) from a PHP error-log line, or None."""
    m = _PHP_SIG_ON_LINE.search(line) or _PHP_SIG_COLON.search(line)
    if not m: return None
    severity, msg, file_path, lineno = m.groups()
    return severity, msg.strip(), relpath(file_path), lineno

# Heuristic bot categorization (by published User-Agent) — verify before blocking.
# Category assignment reflects each bot's actual documented nature and compliance history
# (see references/bot-taxonomy.md), not the operator's country of origin. Notably:
# - Amazonbot is grouped with AI/answer-engine bots (Alexa/product-answer indexing), NOT with
#   "aggressive/scanner" bots — it is documented to honor robots.txt Disallow.
# - The "Regional / Compliance-Unverified" bucket is reserved for bots with either documented
#   non-compliance (Bytespider) or inconsistently-reported compliance (PetalBot) — the label
#   describes the objective compliance signal, not the bot's country of origin.
BOT_CATEGORIES = {
    "GPTBot": "🤖 AI Assistant / Answer Engine",
    "ChatGPT-User": "🤖 AI Assistant / Answer Engine",
    "OAI-SearchBot": "🤖 AI Assistant / Answer Engine",
    "PerplexityBot": "🤖 AI Assistant / Answer Engine",
    "Google-Extended": "🤖 AI Assistant / Answer Engine",
    "ClaudeBot": "🤖 AI Assistant / Answer Engine",
    "Anthropic-ai": "🤖 AI Assistant / Answer Engine",
    "Amazonbot": "🤖 AI Assistant / Answer Engine",
    "Googlebot": "🔍 Search Engine Crawler",
    "Bingbot": "🔍 Search Engine Crawler",
    "YandexBot": "🔍 Search Engine Crawler",
    "Baiduspider": "🔍 Search Engine Crawler",
    "DuckDuckBot": "🔍 Search Engine Crawler",
    "AhrefsBot": "📈 SEO / Marketing Crawler",
    "SemrushBot": "📈 SEO / Marketing Crawler",
    "MJ12bot": "📈 SEO / Marketing Crawler",
    "Dataprovider": "📈 SEO / Marketing Crawler",
    "facebookexternalhit": "📱 Social Media Bot",
    "Twitterbot": "📱 Social Media Bot",
    "Discordbot": "📱 Social Media Bot",
    "LinkedInBot": "📱 Social Media Bot",
    "Applebot": "📱 Social Media Bot",
    "PetalBot": "🌍 Regional / Compliance-Unverified",
    "Bytespider": "🌍 Regional / Compliance-Unverified",
    # This skill's own live-probe traffic (scripts/probe_urls.py) — self-identified via a
    # distinctive User-Agent so a future run recognizes its own historical noise instead of
    # either silently blending into "unknown visitor" counts or, worse, getting flagged as a
    # burst anomaly (one IP hitting many pages in a short window looks exactly like the
    # Concentrated Traffic Spikes & Bursts pattern this script otherwise looks for).
    "Kinsta-Log-Analyzer-Probe": "🔧 Internal Tooling (Self)",
}

# ═══════════════════════════════════════════════════════════════════
# ANALYZE
# ═══════════════════════════════════════════════════════════════════

def analyze_error_log(logs):
    findings = {"critical": [], "medium": [], "low": []}
    lines = logs.strip().split("\n")
    all_ts = re.findall(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})", logs)
    ts_range = f"{all_ts[0]} → {all_ts[-1]}" if all_ts else "N/A"
    ips = re.findall(r"client: (\d+\.\d+\.\d+\.\d+)", logs)
    ip_counter = Counter(ips)
    error_entries = []

    scanner_paths = Counter()
    for m in re.finditer(r'directory index of "([^"]+)"', logs):
        scanner_paths[relpath(m.group(1))] += 1
    scanner_ips = Counter(re.findall(r"directory index.*?client: (\d+\.\d+\.\d+\.\d+)", logs, re.DOTALL))

    SEV_MAP = {"Fatal error": "critical", "Parse error": "critical",
               "Warning": "medium", "Deprecated": "low", "Notice": "low"}

    # Group PHP messages by (severity, file, line) — one real bug = one finding,
    # with actual client IPs / requests attached when the log line records them.
    signatures = {}
    other_stderr = Counter()
    ssl_ts, conn_ts = [], []

    for line in lines:
        ts_m = re.match(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})", line)
        ts = parse_error_ts(ts_m.group(1)) if ts_m else None

        sig = extract_php_signature(line)
        if sig:
            severity_word, msg, file_path, lineno = sig
            key = (severity_word, file_path, lineno)
            d = signatures.setdefault(key, {
                "severity_word": severity_word, "message": msg, "file": file_path, "line": lineno,
                "count": 0, "first_ts": None, "last_ts": None,
                "clients": Counter(), "requests": Counter(),
            })
            d["count"] += 1
            if ts:
                if d["first_ts"] is None or ts < d["first_ts"]: d["first_ts"] = ts
                if d["last_ts"] is None or ts > d["last_ts"]: d["last_ts"] = ts
            client = extract_client(line)
            if client: d["clients"][client] += 1
            req = extract_request(line)
            if req: d["requests"][req] += 1
            continue

        if "directory index" in line and "forbidden" in line:
            continue  # already captured via scanner_paths/scanner_ips above
        if re.search(r"SSL|ssl_certificate", line, re.IGNORECASE):
            ssl_ts.append(ts)
        elif re.search(r"connection refused|upstream timed out", line, re.IGNORECASE):
            conn_ts.append(ts)
        elif re.search(r"FastCGI sent in stderr", line, re.IGNORECASE):
            m = re.search(r'stderr:\s*"([^"]{0,160})', line)
            text = (m.group(1) if m else line.strip()[:160]).strip()
            if text: other_stderr[text] += 1

    for (severity_word, file_path, lineno), d in signatures.items():
        severity = SEV_MAP.get(severity_word, "medium")
        findings[severity].append({
            "kind": "php",
            "label": f"PHP {severity_word}",
            "message": d["message"],
            "file": file_path,
            "line": lineno,
            "count": d["count"],
            "first_ts": d["first_ts"].strftime("%Y/%m/%d %H:%M:%S") if d["first_ts"] else "unknown",
            "last_ts_str": d["last_ts"].strftime("%Y/%m/%d %H:%M:%S") if d["last_ts"] else "unknown",
            "last_ago": time_ago(d["last_ts"]),
            "clients": d["clients"].most_common(5),
            "requests": d["requests"].most_common(3),
        })

    def _bucket_generic(ts_list, severity, label, what):
        ts_list = [t for t in ts_list if t]
        if not ts_list: return
        first_ts, last_ts = min(ts_list), max(ts_list)
        findings[severity].append({
            "kind": "generic", "label": label, "count": len(ts_list),
            "first_ts": first_ts.strftime("%Y/%m/%d %H:%M:%S"),
            "last_ts_str": last_ts.strftime("%Y/%m/%d %H:%M:%S"),
            "last_ago": time_ago(last_ts), "what": what,
        })

    _bucket_generic(ssl_ts, "critical", "SSL/certificate error",
                     "SSL handshake failed — visitors saw security warnings. Check MyKinsta → Domains → certificate status.")
    _bucket_generic(conn_ts, "critical", "Connection refused / upstream timeout",
                     "nginx couldn't reach PHP-FPM — visitors saw 502/504. Check PHP worker limits in MyKinsta → Resource Usage.")

    if other_stderr:
        findings["low"].append({
            "kind": "stderr_samples", "label": "Other PHP/stderr messages",
            "count": sum(other_stderr.values()), "samples": other_stderr.most_common(5),
        })

    if scanner_paths:
        findings["low"].append({
            "kind": "generic", "label": "403 Forbidden — directory probing",
            "count": sum(scanner_paths.values()),
            "first_ts": "n/a", "last_ts_str": "", "last_ago": "",
            "what": "Bot tried to list a WordPress directory.\n\n✅ Kinsta blocked it correctly — no action needed. See the Bot section below if you want to deny these specific IPs.",
        })

    return findings, ts_range, ip_counter, error_entries, scanner_paths, scanner_ips

def analyze_access_log(logs):
    lines = logs.strip().split("\n")
    response_times, entries = [], []
    for line in lines:
        m = re.match(r'\S+ (\S+) \[([^\]]+)\] ([A-Z]+) "([^"]*)" HTTP/[\d.]+ (\d{3})', line)
        if not m: continue
        ip, ts_str, method, url, status = m.groups()
        ts = parse_apache_ts(ts_str)
        # Kinsta appends the response time near the end, but the very last token can be a
        # placeholder "-" (upstream field). Scan the last few tokens from the right instead
        # of assuming a fixed index, so a trailing "-" or an extra field doesn't break this.
        rt = 0
        for tok in reversed(line.rstrip().split()[-3:]):
            try:
                rt = float(tok)
                break
            except ValueError:
                continue
        if rt > 0.001: response_times.append(rt)
        entries.append({"ts": ts, "ip": ip, "url": norm(url), "status": status, "rt": rt})

    stc = Counter(e["status"] for e in entries)
    fivexx = [e for e in entries if e["status"].startswith("5")]
    slow = [e for e in entries if e["rt"] > 2.0]
    # Severity needs more than a raw ">2s" count — 18 pages at 2.1s is a very different
    # situation from 18 pages at 8s. Split so the Health Summary can react to the worst
    # case, not just the count crossing the 2s line.
    severely_slow = [e for e in entries if e["rt"] > 5.0]
    avg_rt = sum(response_times)/len(response_times) if response_times else 0
    min_rt = min(response_times) if response_times else 0
    max_rt = max(response_times) if response_times else 0
    slowest_pages = sorted(
        [e for e in entries if e["rt"] > 0.001], key=lambda e: -e["rt"]
    )[:8]

    # Drill-down: which URLs/IPs are behind each 4xx/5xx status code
    status_urls = defaultdict(Counter)
    status_ips = defaultdict(set)
    for e in entries:
        if e["status"] and e["status"][0] in ("4", "5"):
            status_urls[e["status"]][e["url"]] += 1
            status_ips[e["status"]].add(e["ip"])

    # Bot detection with time windows — includes AI assistant/crawler bots so they can be
    # split from search-engine/SEO/social/scanner bots in the report (see BOT_CATEGORIES).
    bot_patterns = [
        ("Googlebot", r"Googlebot"), ("Amazonbot", r"Amazonbot"),
        ("ChatGPT-User", r"ChatGPT-User"), ("YandexBot", r"YandexBot"),
        ("PetalBot", r"PetalBot"), ("OAI-SearchBot", r"OAI-SearchBot"),
        ("Bingbot", r"bingbot"), ("Dataprovider", r"Dataprovider"),
        ("AhrefsBot", r"AhrefsBot"), ("SemrushBot", r"SemrushBot"),
        ("MJ12bot", r"MJ12bot"), ("DuckDuckBot", r"DuckDuckBot"),
        ("Baiduspider", r"Baiduspider"), ("Applebot", r"Applebot"),
        ("facebookexternalhit", r"facebookexternalhit"), ("Twitterbot", r"Twitterbot"),
        ("Discordbot", r"Discordbot"), ("LinkedInBot", r"LinkedInBot"),
        ("GPTBot", r"GPTBot"), ("ClaudeBot", r"ClaudeBot"),
        ("PerplexityBot", r"PerplexityBot"), ("Google-Extended", r"Google-Extended"),
        ("Bytespider", r"Bytespider"), ("Anthropic-ai", r"anthropic-ai"),
        ("Kinsta-Log-Analyzer-Probe", r"Kinsta-Log-Analyzer-Probe"),
    ]
    bot_data = {}
    for name, pat in bot_patterns:
        ts_list = []
        urls = Counter()
        ip_counts = Counter()
        for line in lines:
            if re.search(pat, line, re.IGNORECASE):
                m2 = re.match(r'\S+ (\S+) \[([^\]]+)\] [A-Z]+ "([^"]*)"', line)
                if m2:
                    ip_str, ts_str, url_str = m2.groups()
                    bt = parse_apache_ts(ts_str)
                    if bt: ts_list.append(bt)
                    urls[norm(url_str)] += 1
                    ip_counts[ip_str] += 1
        if ts_list:
            ts_sorted = sorted(ts_list)
            total_hits = len(ts_list)
            top_urls = urls.most_common(5)
            # Concentration: what share of this bot's traffic hit its single most-requested
            # URL? High concentration (few URLs, most hits on one) suggests targeted/repeated
            # interest in specific content; low concentration (many distinct URLs, no
            # dominant one) suggests bulk/exploratory crawling regardless of what the UA claims.
            top_share = (top_urls[0][1] / total_hits * 100) if top_urls else 0
            distinct_urls = len(urls)
            # Same concentration signal, but per-IP: one IP responsible for a disproportionate
            # share of this bot's traffic is a "burst" worth flagging separately from the
            # aggregate bot volume — see the Concentrated Traffic Spikes & Bursts section.
            top_ip, top_ip_count = ip_counts.most_common(1)[0]
            ip_top_share = (top_ip_count / total_hits * 100) if total_hits else 0
            bot_data[name] = {
                "count": total_hits, "first": ts_sorted[0], "last": ts_sorted[-1],
                "top_urls": top_urls, "distinct_urls": distinct_urls,
                "top_share": top_share, "distinct_ips": len(ip_counts),
                "top_ip": top_ip, "top_ip_count": top_ip_count, "ip_top_share": ip_top_share,
            }

    # Hourly
    hourly = Counter()
    for e in entries:
        if e["ts"]: hourly[e["ts"].strftime("%H:00")] += 1

    # Query param extraction from raw log
    query_params = Counter()
    for line in lines:
        m = re.search(r'"GET ([^?"]*)\?([^ "]+)', line)
        if m:
            for param in m.group(2).split("&"):
                name = param.split("=")[0]
                query_params[name] += 1

    access_ts = [e["ts"] for e in entries if e["ts"]]

    return {"total": len(lines), "statuses": stc, "avg_rt": avg_rt,
            "slow": slow, "severely_slow": severely_slow, "min_rt": min_rt, "max_rt": max_rt,
            "slowest_pages": slowest_pages,
            "bot_data": bot_data, "fivexx": fivexx,
            "entries": entries, "hourly": dict(sorted(hourly.items())),
            "query_params": query_params, "status_urls": status_urls,
            "status_ips": status_ips,
            "first_ts": min(access_ts) if access_ts else None,
            "last_ts": max(access_ts) if access_ts else None}

def analyze_cache_log(logs):
    hits = len(re.findall(r"\bHIT KINSTAWP", logs))
    misses = len(re.findall(r"\bMISS KINSTAWP", logs))
    bypasses = len(re.findall(r"\bBYPASS KINSTAWP", logs))
    total = hits + misses + bypasses
    if total == 0: return None
    entries = []
    for m in re.finditer(r"\[([^\]]+)\] (HIT|MISS|BYPASS) KINSTAWP(?:_MOBILE)? (\S+) ([A-Z]+) \"([^\"]+)\"", logs):
        ts = parse_apache_ts(m.group(1))
        entries.append({"ts": ts, "status": m.group(2), "ip": m.group(3), "url": norm(m.group(5))})
    cache_ts = [e["ts"] for e in entries if e["ts"]]
    return {"HIT": hits, "MISS": misses, "BYPASS": bypasses, "total": total, "entries": entries,
            "first_ts": min(cache_ts) if cache_ts else None,
            "last_ts": max(cache_ts) if cache_ts else None}

# ═══════════════════════════════════════════════════════════════════
# CROSS-ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def cross_analyze(access_entries, cache_entries, error_entries, ip_counter, scanner_ips):
    results = {}
    if access_entries and cache_entries:
        acc_by_url = defaultdict(list)
        for e in access_entries: acc_by_url[e["url"]].append(e)

        slow_misses = []
        for ce in cache_entries:
            if ce["status"] != "MISS": continue
            for ae in acc_by_url.get(ce["url"], []):
                if ce["ts"] and ae["ts"] and abs((ce["ts"]-ae["ts"]).total_seconds()) < 5 and ae["rt"] > 1.0:
                    slow_misses.append({"url": ce["url"], "rt": ae["rt"], "ip": ae["ip"]})
                    break
        results["slow_cache_misses"] = slow_misses[:3]

        miss_by_url = defaultdict(list)
        for ce in cache_entries:
            if ce["status"] == "MISS" and ce["ts"]: miss_by_url[ce["url"]].append(ce["ts"])
        top_missed = []
        for url, timestamps in sorted(miss_by_url.items(), key=lambda x: -len(x[1]))[:7]:
            tss = sorted(timestamps)
            top_missed.append({"url": url, "count": len(timestamps),
                               "from": tss[0].strftime("%H:%M"), "to": tss[-1].strftime("%H:%M")})
        results["top_missed_urls"] = top_missed

        hit_urls = set(ce["url"] for ce in cache_entries if ce["status"] == "HIT")
        miss_urls_set = set(ce["url"] for ce in cache_entries if ce["status"] == "MISS")
        hit_rts, miss_rts = [], []
        for e in access_entries:
            if e["rt"] > 0.001:
                if e["url"] in hit_urls: hit_rts.append(e["rt"])
                elif e["url"] in miss_urls_set: miss_rts.append(e["rt"])
        if hit_rts and miss_rts:
            ah, am = sum(hit_rts)/len(hit_rts), sum(miss_rts)/len(miss_rts)
            results["hit_vs_miss_rt"] = (ah, am, len(hit_rts), len(miss_rts))

    if ip_counter and access_entries:
        acc_ip_set = set(e["ip"] for e in access_entries)
        suspicious = [(ip, cnt) for ip, cnt in ip_counter.most_common(10) if ip in acc_ip_set]
        results["suspicious_ips"] = suspicious[:5]

    results["top_ips"] = Counter(e["ip"] for e in access_entries).most_common(8)
    results["scanner_ips"] = scanner_ips.most_common(5)
    return results

# ═══════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════

def generate_report(site_name, error_findings, error_meta, access_data,
                    cache_data, cross_results, scanner_paths, hours, data_errors=None,
                    env_name="live"):
    data_errors = data_errors or {}
    now = datetime.now(timezone.utc)
    L = []

    period = f"Last {hours} hours" if hours else "All available data"
    # Escape the dot so Markdown "linkify" renderers (VS Code preview, some GFM configs)
    # don't autolink the bare domain and render the title in link-blue.
    title_site_name = site_name.replace(".", "\\.")
    L.append(f"# Kinsta Health Report - {title_site_name} ({env_name})")
    L.append("")
    # Both metadata lines merged into ONE paragraph using an explicit <br> tag — NOT the
    # trailing-double-space Markdown "hard break" convention, which this renderer does not
    # honor (confirmed: it collapsed both lines onto one with just a space between them).
    # <br> is raw HTML passthrough, the same mechanism already confirmed working for the
    # bar_chart() colored spans, so it reliably forces a line break within one paragraph —
    # avoiding the blank-line paragraph-break gap (each <p> carries its own bottom margin)
    # while still visually separating the date/period line from the counts line.
    subtitle = f"**{now.strftime('%d %B %Y, %H:%M UTC')}** · Approx. {period}"
    if error_meta:
        subtitle += (f"<br>**{access_data['total'] if access_data else 0}** requests · "
                     f"**{cache_data['total'] if cache_data else 0}** cache entries · "
                     f"**{error_meta['total_lines']}** error lines")
    L.append(subtitle)
    L.append("")

    # Surface actual fetch/parse failures instead of silently showing "unavailable"
    if data_errors:
        L.append("> ⚠️ **Data source issues**")
        for source, reason in data_errors.items():
            L.append(f"> - `{source}` log: {reason}")
        L.append("")

    # Lean 3-line time-period disclosure — the three source logs are fetched
    # independently (line-based Kinsta API, no shared time filter), so their actual
    # coverage rarely lines up exactly. Every row uses the identical format
    # "log name: start → end UTC (duration)" so the three are visually comparable at a
    # glance, and each is flagged if its actual span falls short of the requested
    # --hours window — the Kinsta API is line-based, not time-based, so "24 hours
    # requested" frequently doesn't mean "24 hours actually returned."
    acc_first = access_data.get("first_ts") if access_data else None
    acc_last = access_data.get("last_ts") if access_data else None
    cache_first = cache_data.get("first_ts") if cache_data else None
    cache_last = cache_data.get("last_ts") if cache_data else None
    err_first_dt = err_last_dt = None
    if error_meta and error_meta.get("timerange") and " → " in error_meta["timerange"]:
        try:
            a, b = error_meta["timerange"].split(" → ")
            err_first_dt = parse_error_ts(a.strip())
            err_last_dt = parse_error_ts(b.strip())
        except Exception:
            pass

    def _period_row(n, label, first, last):
        # Kept concise on purpose: every log window is nearly always shorter than the
        # requested --hours (the Kinsta API is line-based, not time-based, so this is the
        # normal case, not an anomaly) — flagging it on every single row added noise without
        # signal. The actual duration is bolded so it's still easy to compare across the 3 rows.
        # Duration is rendered as "H:MM hours" (total hours:minutes, seconds dropped) rather
        # than timedelta's default "H:MM:SS" — seconds add no value for a report read at a
        # glance and only invite false precision.
        if not (first and last):
            return f"{n}. **{label}:** not available this run"
        span = last - first
        total_min = int(span.total_seconds() // 60)
        hh, mm = divmod(total_min, 60)
        span_str = f"{hh}:{mm:02d} hours"
        return (f"{n}. **{label}:** `{first.strftime('%Y-%m-%d %H:%M')} → "
                f"{last.strftime('%Y-%m-%d %H:%M')} UTC` **({span_str})**")

    if error_meta or acc_first:
        L.append("## Time Period")
        L.append("")
        L.append(_period_row(1, "Access log", acc_first, acc_last))
        L.append(_period_row(2, "Error log", err_first_dt, err_last_dt))
        L.append(_period_row(3, "Cache-perf log", cache_first, cache_last))
        L.append("")

    # Remember where to insert the geo-IP status banner — computed only after every
    # ip_country()/ip_org()/ip_hostname() call below has run, but displayed here at the
    # top so the reader sees it before any IP-attribution table, not buried after dozens
    # of confusing "unknown" cells.
    geoip_banner_index = len(L)

    # ══════════════════════════════════════════════════════════════
    # HEALTH METRICS (computed here, rendered in Part 1's Overall Assessment
    # marker by the LLM — see references/report-structure.md). No heading/table
    # is emitted directly; "## Health Summary" is a permanently suppressed
    # section per the report structure contract.
    # ══════════════════════════════════════════════════════════════
    critical_count = len(error_findings.get("critical", []))
    medium_count = len(error_findings.get("medium", []))
    fivexx_count = len(access_data["fivexx"]) if access_data else 0
    hit_pct = cache_data["HIT"]/cache_data["total"]*100 if cache_data else None
    bypass_pct = cache_data["BYPASS"]/cache_data["total"]*100 if cache_data else None
    avg_rt = access_data["avg_rt"] if access_data else 0
    slow_count = len(access_data["slow"]) if access_data else 0
    severely_slow_count = len(access_data.get("severely_slow", [])) if access_data else 0

    # ══════════════════════════════════════════════════════════════
    # BURST DETECTION — computed here (early) rather than at its Part-2 rendering
    # location, because the Convergent Cross-Signals check below (Part 1, right
    # after Overall Assessment) needs burst_rows/burst_target_urls before Part 1 is
    # written. Rendering into "## Concentrated Traffic Spikes & Bursts" still happens
    # later, in its original Part 2 position, reusing this same computed burst_rows.
    # ══════════════════════════════════════════════════════════════
    def _host_suffix(ip):
        """Short reverse-DNS annotation for a Bursts-table source — flags the specific
        'cloud vendor's ASN but NOT their own crawler' case that a bare IP/UA doesn't reveal."""
        hostname, is_customer_vm = ip_hostname(ip)
        if not hostname: return ""
        return f" — PTR: `{hostname}`" + (" ⚠️ cloud customer VM" if is_customer_vm else "")

    # One-line plain-language identity for bot names that aren't self-explanatory — "Offender"
    # is the wrong word for a low-value-but-legitimate crawler like Dataprovider; stating
    # plainly who/what it is (not "our" traffic, not necessarily malicious) belongs right in
    # this table, not requiring a cross-reference to bot-taxonomy.md to understand.
    _BOT_IDENTITY = {
        "Dataprovider": "Dataprovider.com — third-party commercial web-data crawler, not malicious, zero SEO value to this site",
        "MJ12bot": "Majestic SEO's backlink-index crawler — third-party SEO tool, not malicious",
        "SemrushBot": "Semrush's SEO-audit crawler — third-party SEO tool, not malicious",
        "AhrefsBot": "Ahrefs' SEO-audit crawler — third-party SEO tool, not malicious",
        "Bytespider": "ByteDance's (TikTok's parent) crawler — see bot-taxonomy.md for compliance history",
        "PetalBot": "Huawei's Petal Search crawler — see bot-taxonomy.md for relevance assessment",
    }
    def _bot_label(name):
        return _BOT_IDENTITY.get(name, name)

    burst_rows = []
    # Clean, single-URL burst targets only (bot-IP-concentration bursts) — tracked
    # separately from burst_rows because scanner-IP and slow-IP bursts describe
    # MULTIPLE paths in prose ("multiple `/wp-admin/`..."), not one clean URL, and
    # mixing those into the URL-equality check below would compare text, not URLs.
    burst_target_urls = []
    if access_data and access_data.get("bot_data"):
        for name, b in access_data["bot_data"].items():
            share = b.get("ip_top_share", 0)
            # A single IP responsible for >=40% of a bot's total traffic (and that
            # bot has enough volume to matter) is a burst worth calling out — most
            # legitimate bot traffic is spread across many source IPs (see
            # bot-taxonomy.md), so a concentrated single-IP share is the anomaly.
            if share >= 40 and b.get("count", 0) >= 10:
                top_url = b["top_urls"][0][0] if b.get("top_urls") else "(multiple URLs)"
                burst_rows.append({
                    "source": f"`{b['top_ip']}` — {_bot_label(name)}{_host_suffix(b['top_ip'])}",
                    "target": top_url,
                    "detail": f"{b['top_ip_count']} of {b['count']} requests ({share:.0f}%)",
                })
                # Exclude this skill's own diagnostic probe traffic from the convergence
                # check's evidence — it's self-generated noise (probe_urls.py hitting a
                # fixed baseline URL list), not a real site-traffic finding. Citing "100%
                # of our own probe's requests hit X" as a prioritization reason would be
                # nonsensical in the finished report.
                if b.get("top_urls") and name != "Kinsta-Log-Analyzer-Probe":
                    burst_target_urls.append((top_url, share, f"{share:.0f}% of {name}'s traffic via one IP"))
    for ip, cnt in cross_results.get("scanner_ips", []):
        burst_rows.append({
            "source": f"`{ip}` — directory scanner{_host_suffix(ip)}",
            "target": "multiple `/wp-admin/`, `/wp-includes/` paths",
            "detail": f"{cnt} probe attempts",
        })
    # Non-bot-classified burst check: a single IP dominating the SLOW-requests list, even
    # when its User-Agent didn't match any known bot pattern above. This is exactly the
    # case that would otherwise stay invisible — an unclassified IP hitting many pages with
    # no other signal except "everything it touches is slow."
    if access_data and access_data.get("slow"):
        slow_ip_counts = Counter(e["ip"] for e in access_data["slow"])
        if slow_ip_counts:
            top_slow_ip, top_slow_count = slow_ip_counts.most_common(1)[0]
            total_slow = len(access_data["slow"])
            slow_share = top_slow_count / total_slow * 100 if total_slow else 0
            if slow_share >= 50 and top_slow_count >= 3:
                slow_urls = [e["url"] for e in access_data["slow"] if e["ip"] == top_slow_ip]
                burst_rows.append({
                    "source": f"`{top_slow_ip}` — unclassified, no matching bot UA pattern{_host_suffix(top_slow_ip)}",
                    "target": f"{len(set(slow_urls))} distinct pages, e.g. `{slow_urls[0]}`",
                    "detail": f"{top_slow_count} of {total_slow} slow (>2s) requests ({slow_share:.0f}%)",
                })

    # ══════════════════════════════════════════════════════════════
    # CONVERGENT PRESSURE POINTS — a deterministic set-intersection across the
    # report's own "notable URL" lists (top cache-MISSed pages, burst targets, top
    # 403/404 error URLs). A URL appearing in 2+ lists is a genuine convergence of
    # independent problems on one page — a stronger, more specific fix target than
    # any single list states alone. Intentionally mechanical (not left to the LLM
    # to notice by eye) so it's checked every run, not only when the analyst happens
    # to manually cross-reference three separate tables.
    # ══════════════════════════════════════════════════════════════
    missed_urls = {m["url"]: m["count"] for m in cross_results.get("top_missed_urls", [])}
    # Multiple bots can target the same URL — keep the highest-share entry per URL
    # rather than a plain dict() built from the tuple list, which would silently
    # keep whichever entry happens to iterate last (an ordering artifact, not a
    # meaningful choice).
    burst_urls = {}
    _burst_share_seen = {}
    for url, share_val, reason in burst_target_urls:
        if url not in _burst_share_seen or share_val > _burst_share_seen[url]:
            _burst_share_seen[url] = share_val
            burst_urls[url] = reason
    error_urls = {}
    status_urls_map = access_data.get("status_urls") if access_data else None
    if status_urls_map:
        for code in (403, 404):
            for url, cnt in status_urls_map.get(code, Counter()).most_common(5):
                error_urls[url] = f"{cnt}x {code}"

    url_hits = defaultdict(list)
    for list_name, url_map in (("cache-miss", missed_urls), ("burst", burst_urls), ("error", error_urls)):
        for url in url_map:
            url_hits[url].append(list_name)

    convergent = {u: lists for u, lists in url_hits.items() if len(lists) >= 2}
    convergent_lines = []
    if convergent:
        # Only the strongest convergence is named explicitly — concise, not a dump
        # of every overlapping URL — with a one-line note if more exist.
        top_conv_url = max(convergent, key=lambda u: len(convergent[u]))
        lists_hit = convergent[top_conv_url]
        evidence_parts = []
        if "cache-miss" in lists_hit:
            evidence_parts.append(f"{missed_urls[top_conv_url]} cache MISSes")
        if "burst" in lists_hit:
            evidence_parts.append(burst_urls[top_conv_url])
        if "error" in lists_hit:
            evidence_parts.append(error_urls[top_conv_url])
        convergent_lines.append(
            f"`{top_conv_url}` appears in {len(lists_hit)} of the report's notable-URL lists — "
            f"{', '.join(evidence_parts)}. The relevant sections below (Cache Root Cause, "
            f"Bursts, or Error Recommendations) address whether this overlap is actionable."
        )
        remaining = len(convergent) - 1
        if remaining:
            convergent_lines.append(
                f"({remaining} other URL{'s' if remaining > 1 else ''} also show minor overlap — "
                f"see Part 2 tables for detail.)"
            )
    else:
        convergent_lines.append(
            "No overlap found across the cache-miss, burst, and error-URL lists this run — the "
            "findings below are independent issues, not one root cause in disguise."
        )

    # ══════════════════════════════════════════════════════════════
    # PART 1: SUMMARY & FINDINGS — script emits headings + <!-- LLM: --> markers only.
    # LLM fills every marker per Step 6 of SKILL.md and references/report-structure.md.
    # LLM re-orders these sections by severity before finalizing (script order is a
    # neutral default, not a mandate).
    # ══════════════════════════════════════════════════════════════
    # A real "# " heading (not a fixed-width Unicode-line divider) — a run of decorative
    # ━ characters wraps unpredictably across VS Code/browser/PDF viewport widths; a heading
    # just wraps its words, and h1:not(:first-of-type) in report.css gives it distinct styling.
    L.append("# PART 1: SUMMARY & FINDINGS")
    L.append("")
    L.append("## 📌 At a Glance")
    L.append("")
    L.append("<!-- LLM:AT_A_GLANCE -->")
    L.append("")
    L.append("## 📋 Analyst Commentary & Recommendations")
    L.append("")
    L.append("### Overall Assessment")
    L.append("")
    L.append("<!-- LLM:OVERALL_ASSESSMENT -->")
    L.append("")
    # Script-authored (not an LLM marker) — this finding is a deterministic set
    # intersection computed above, not analyst judgment, so it doesn't need LLM
    # authorship. Always present, either naming a convergence or stating there
    # is none — never silently omitted.
    L.append("### 🎯 Convergent Cross-Signals")
    L.append("")
    for _line in convergent_lines:
        L.append(_line)
        L.append("")
    L.append("### Attack/Security Findings")
    L.append("")
    L.append("<!-- LLM:ATTACK_SECURITY -->")
    L.append("")
    L.append("### Cache Root Cause Analysis")
    L.append("")
    L.append("<!-- LLM:CACHE_ROOT_CAUSE -->")
    L.append("")
    L.append("### Bot Traffic Strategy")
    L.append("")
    L.append("<!-- LLM:BOT_STRATEGY -->")
    L.append("")
    L.append("### Concentrated Traffic Spikes & Bursts")
    L.append("")
    L.append("<!-- LLM:BURST_CARDS -->")
    L.append("")
    L.append("### Traffic Anomalies")
    L.append("")
    L.append("<!-- LLM:TRAFFIC_ANOMALIES -->")
    L.append("")
    L.append("### 404 Errors Recommendations")
    L.append("")
    L.append("<!-- LLM:ERROR_FIXES -->")
    L.append("")
    L.append("# PART 2: TECHNICAL APPENDIX")
    L.append("")

    # ══════════════════════════════════════════════════════════════
    # PERFORMANCE — top-level section, first in Part 2
    # ══════════════════════════════════════════════════════════════
    if access_data:
        L.append("## Performance")
        L.append("")
        L.append(f"| Metric | Value |")
        L.append(f"|---|---|")
        L.append(f"| Average response time | **{access_data['avg_rt']:.3f}s** |")
        L.append(f"| Fastest response | **{access_data.get('min_rt', 0):.3f}s** |")
        L.append(f"| Slowest response | **{access_data.get('max_rt', 0):.3f}s** |")
        L.append(f"| Slow pages (>2s) | **{len(access_data['slow'])}** |")
        L.append(f"| Server errors (5xx) | **{len(access_data['fivexx'])}** |")
        L.append("")
        if access_data.get("slowest_pages"):
            L.append("**Slowest individual requests observed:**")
            L.append("")
            L.append("| URL | Response Time | IP | Country | Status | Reverse DNS |")
            L.append("|---|---|---|---|---|---|")
            slow_ip_set = set()
            for e in access_data["slowest_pages"][:8]:
                # Reverse-DNS here specifically, not just ASN/org — "org = Google LLC" does not
                # tell you whether this is Google's own crawler or an unrelated third party's
                # customer VM merely rented from Google Cloud. A hostname ending in
                # googleusercontent.com/compute.amazonaws.com is the actual tell; ASN alone is not.
                hostname, is_customer_vm = ip_hostname(e["ip"])
                if hostname:
                    host_display = f"`{hostname}`" + (" ⚠️ cloud customer VM, not the vendor's own service" if is_customer_vm else "")
                else:
                    host_display = "*no PTR record*"
                cc, flag = ip_country(e["ip"])
                if cc == GEOIP_DISABLED:
                    country_display = "*geo-IP disabled*"
                elif cc and cc != "?":
                    country_display = f"{flag} {cc}" if flag else cc
                else:
                    country_display = "*unknown*"
                slow_ip_set.add(e["ip"])
                L.append(f"| `{e['url']}` | {e['rt']:.3f}s | `{e['ip']}` | {country_display} | {e['status']} | {host_display} |")
            L.append("")
            if len(slow_ip_set) == 1 and len(access_data["slowest_pages"][:8]) >= 3:
                only_ip = next(iter(slow_ip_set))
                L.append(f"> ⚠️ **All of the above come from a single IP (`{only_ip}`)** — this is one "
                         f"source systematically hitting multiple pages, not several unrelated slow "
                         f"visitor experiences. Check its reverse-DNS/org above before assuming it's "
                         f"a real visitor or the site's own performance problem.")
                L.append("")
    else:
        reason = data_errors.get("access")
        L.append(f"Performance data unavailable{f': {reason}' if reason else ''}.")
        L.append("")

    # ══════════════════════════════════════════════════════════════
    # ISSUES — each finding now carries real extracted data (message, file:line,
    # client IPs, requests) instead of only a canned generic "fix" tip.
    # "low" tier (🟢 Low-Priority Notes) is permanently suppressed — Attack/Security
    # Findings in Part 1 covers this ground with a default "no incidents" card.
    # ══════════════════════════════════════════════════════════════
    for sev_key, title in [("critical", "## 🔴 Issues Found"), ("medium", "## 🟡 Warnings")]:
        findings = error_findings.get(sev_key, [])
        if not findings: continue
        L.append(title)
        L.append("")
        for f in findings:
            kind = f.get("kind", "generic")
            if kind == "php":
                L.append(f"### {f['label']}: {f['message']}")
                L.append("")
                L.append(f"`{f['file']}:{f['line']}`")
                L.append("")
                L.append("| | |")
                L.append("|---|---|")
                L.append(f"| Occurrences | **{f['count']}** |")
                L.append(f"| First seen | {f['first_ts']} |")
                L.append(f"| Last seen | {f['last_ts_str']} ({f['last_ago']}) |")
                if f["clients"]:
                    parts = []
                    for ip, cnt in f["clients"]:
                        cc, flag = ip_country(ip)
                        cdisp = f"{flag} {cc}" if flag else (cc if cc != "?" else "unknown")
                        parts.append(f"`{ip}` ({cdisp}, {cnt}×)")
                    L.append(f"| Client IP(s) | {', '.join(parts)} |")
                else:
                    L.append("| Client IP(s) | *not recorded on this log line* |")
                if f["requests"]:
                    reqs = [f"`{r}` ({c}×)" for r, c in f["requests"]]
                    L.append(f"| Request(s) | {', '.join(reqs)} |")
                else:
                    L.append("| Request(s) | *not recorded on this log line* |")
                L.append("")
                L.append(f"**Fix**: Open `{f['file']}` at line **{f['line']}** — {f['message']}")
                L.append("")
                L.append("---")
                L.append("")
            elif kind == "stderr_samples":
                L.append(f"### {f['label']}")
                L.append("")
                L.append(f"**{f['count']}** occurrences that didn't match a known PHP severity pattern. "
                         f"Actual sample messages (not a generic tip):")
                L.append("")
                for text, cnt in f["samples"]:
                    L.append(f"- `{text}` ({cnt}×)")
                L.append("")
                L.append("---")
                L.append("")
            else:
                L.append(f"### {f['label']}")
                L.append("")
                L.append("| | |")
                L.append("|---|---|")
                L.append(f"| Occurrences | **{f['count']}** |")
                L.append(f"| First seen | {f['first_ts']} |")
                if f.get("last_ts_str"):
                    L.append(f"| Last seen | {f['last_ts_str']} ({f['last_ago']}) |")
                L.append("")
                # CommonMark doesn't allow ** to span a blank line — if 'what' contains a
                # paragraph break (e.g. a finding statement followed by a ✅ resolution note),
                # only bold the first paragraph; render any subsequent ones as plain text.
                what_parts = f['what'].split("\n\n")
                L.append(f"**{what_parts[0]}**")
                for extra in what_parts[1:]:
                    L.append("")
                    L.append(extra)
                L.append("")
                L.append("---")
                L.append("")

    # ══════════════════════════════════════════════════════════════
    # CACHE
    # ══════════════════════════════════════════════════════════════
    L.append("## Cache Performance")
    L.append("")
    if cache_data:
        total = cache_data["total"]
        L.append("| Status | Requests | Share |")
        L.append("|---|---|---|")
        for s in ["HIT", "MISS", "BYPASS"]:
            cnt = cache_data[s]
            pct = cnt/total*100
            bar = bar_chart(pct, 100, 15)
            L.append(f"| {s} | {cnt} | {bar} **{pct:.0f}%** |")
        L.append("")

        # Capped at 🟡, never 🔴 — a cache HIT-rate shortfall is a performance/config
        # target-miss, not the active-emergency (site down/breach/data-at-risk) that 🔴
        # is reserved for per SKILL.md's severity icon vocabulary.
        if hit_pct >= 50: v = "✅ Most visitors get instant cached pages."
        else: v = "🟡 More than half of requests miss cache."
        L.append(f"**Assessment**: {v} Target is >50% HIT.")
        L.append("")

        if cross_results.get("top_missed_urls"):
            L.append("### Pages Most Frequently Missing Cache")
            L.append("")
            L.append("| Page | MISSes | Active between |")
            L.append("|---|---|---|")
            for m in cross_results["top_missed_urls"][:5]:
                L.append(f"| `{m['url']}` | {m['count']} | {m['from']}–{m['to']} UTC |")
            L.append("")

        if cross_results.get("hit_vs_miss_rt"):
            ah, am, nh, nm = cross_results["hit_vs_miss_rt"]
            ratio = am/ah if ah > 0 else 0
            L.append("### Response Time: Cache HIT vs MISS")
            L.append("")
            L.append("| | Avg | Samples |")
            L.append("|---|---|---|")
            L.append(f"| Cache HIT | **{ah:.3f}s** | {nh} |")
            L.append(f"| Cache MISS | **{am:.3f}s** | {nm} |")
            if ratio > 1.01:
                L.append(f"| **Difference** | MISS is **{ratio:.1f}x slower** — cache provides clear benefit | |")
            elif ratio < 0.99:
                L.append(f"| **Difference** | MISS is **{ratio:.1f}x faster** (cached pages are heavier content) | |")
            else:
                L.append(f"| **Difference** | Similar speed — cache has neutral impact | |")
            L.append("")

    else:
        reason = data_errors.get("cache")
        L.append(f"Cache data unavailable{f': {reason}' if reason else ' (no cache_file provided or empty response)'}.")
        L.append("")

    # ══════════════════════════════════════════════════════════════
    # BOTS — grouped by heuristic category so AI assistants/answer engines are
    # visible separately from search engines, SEO crawlers, social bots, and scanners.
    # ══════════════════════════════════════════════════════════════
    L.append("## Bot & Crawler Traffic")
    L.append("")
    if access_data and access_data["bot_data"]:
        bots = access_data["bot_data"]
        total_bot = sum(b["count"] for b in bots.values())
        total_req = access_data["total"]
        L.append("*Categorization is a heuristic based on published User-Agent strings — verify before blocking.*")
        L.append("")

        by_cat = defaultdict(list)
        for name, b in bots.items():
            by_cat[BOT_CATEGORIES.get(name, "❓ Other / Unclassified Bot")].append((name, b))

        for cat in sorted(by_cat, key=lambda c: -sum(b["count"] for _, b in by_cat[c])):
            items = sorted(by_cat[cat], key=lambda x: -x[1]["count"])
            cat_total = sum(b["count"] for _, b in items)
            cat_pct = cat_total / total_req * 100 if total_req else 0
            # Total + % of ALL traffic now lives in the header itself (first line the reader
            # sees for this category), replacing both the old top-of-section summary sentence
            # and the old bottom-of-table "Total" row — one number, stated once, up front.
            L.append(f"### {cat} — {cat_total} requests ({cat_pct:.0f}% of all traffic)")
            L.append("")
            # "Verdict" column is a structural placeholder — LLM MUST overwrite each
            # "⏳ pending" cell with the exact verdict from the Bot Traffic Strategy
            # table (Part 1) once that table is written. This guarantees the column
            # always exists (script-owned structure) even though its content is
            # LLM-owned (see references/report-structure.md).
            L.append("| Bot | Requests | Active window | Distinct IPs | URL pattern | Verdict |")
            L.append("|---|---|---|---|---|---|")
            for name, b in items:
                window = f"{b['first'].strftime('%H:%M')}–{b['last'].strftime('%H:%M')} UTC"
                # Concentration signal: high top_share + low distinct_urls = repeated hits on
                # specific content (targeted interest); low top_share + high distinct_urls =
                # distributed/exploratory crawling. See references/bot-taxonomy.md before
                # interpreting this for ChatGPT-User specifically — it changes the verdict.
                top_share = b.get("top_share", 0)
                distinct = b.get("distinct_urls", 0)
                if distinct <= 1:
                    pattern = "single URL only"
                elif top_share >= 50:
                    # >=50% on one URL out of several is an anomaly worth flagging visually,
                    # not just a neutral data point — pair the label with a warning icon.
                    pattern = f"⚠️ concentrated: {top_share:.0f}% on 1 URL ({distinct} distinct)"
                elif distinct <= 5:
                    pattern = f"narrow: {distinct} distinct URLs"
                else:
                    pattern = f"distributed: {distinct} distinct URLs"
                bot_pct = b['count'] / total_req * 100 if total_req else 0
                L.append(f"| {name} | **{b['count']}** ({bot_pct:.0f}%) | {window} | {b.get('distinct_ips', '?')} | {pattern} | ⏳ *pending* |")
            L.append("")
            # Show the actual top URLs for the single highest-volume bot in this category so
            # the analyst can cite real evidence instead of guessing at "pattern or scattered".
            top_bot_name, top_bot = max(items, key=lambda x: x[1]["count"])
            if top_bot.get("top_urls"):
                L.append(f"<details><summary>Top URLs requested by <code>{top_bot_name}</code> (highest-volume bot in this category)</summary>")
                L.append("")
                L.append("| URL | Hits |")
                L.append("|---|---|")
                for u, c in top_bot["top_urls"]:
                    L.append(f"| `{u}` | {c} |")
                L.append("")
                L.append("</details>")
                L.append("")

    else:
        L.append("No bot data.")
        L.append("")
    # "### Scanner IPs — Block List" is permanently suppressed — Part 1's Burst Cards
    # (<!-- LLM:BURST_CARDS -->) supersede this with evidence-cited, per-actor cards.

    # ══════════════════════════════════════════════════════════════
    # CONCENTRATED TRAFFIC SPIKES & BURSTS — rendering only. burst_rows was
    # computed earlier (before Part 1) so the Convergent Cross-Signals check
    # could use it; this section just renders that already-computed list.
    # ══════════════════════════════════════════════════════════════
    if burst_rows:
        L.append("## Concentrated Traffic Spikes & Bursts")
        L.append("")
        L.append("| Source | Country | Target | Detail |")
        L.append("|---|---|---|---|")
        for r in burst_rows:
            # Extract IP from source string for geo lookup — source format: "`IP` — description"
            ip_match = re.match(r"`([^`]+)`", r['source'])
            if ip_match:
                burst_ip = ip_match.group(1)
                cc, flag = ip_country(burst_ip)
                if cc == GEOIP_DISABLED:
                    country_display = "*—*"
                elif cc and cc != "?":
                    country_display = f"{flag} {cc}" if flag else cc
                else:
                    country_display = "*—*"
            else:
                country_display = "*—*"
            L.append(f"| {r['source']} | {country_display} | {r['target']} | {r['detail']} |")
        L.append("")
    else:
        L.append("## Concentrated Traffic Spikes & Bursts")
        L.append("")
        L.append("No single-IP burst detected — traffic within each bot/category is "
                 "spread across multiple source IPs, not dominated by one.")
        L.append("")

    # ══════════════════════════════════════════════════════════════
    # IP INTELLIGENCE
    # ══════════════════════════════════════════════════════════════
    if cross_results.get("top_ips"):
        L.append("## Top Visitor IPs")
        L.append("")
        L.append("| IP | Requests | Country | ASN / Provider | Reverse DNS | ⚠️ |")
        L.append("|---|---|---|---|---|---|")
        any_hosting = False
        any_customer_vm = False
        for ip, cnt in cross_results["top_ips"]:
            if ip in ("::1", "127.0.0.1"):
                # This is the server talking to itself — WP-Cron, health checks, internal
                # loopback API calls — not an external visitor of any kind. Spelled out
                # explicitly so it's never mistaken for a real visitor with a generic label.
                country_display = "—"
                org_display = "🖥️ this server itself (internal/cron, not a visitor)"
                host_display = ""
                flag_cell = ""
            else:
                cc, flag = ip_country(ip)
                if cc == GEOIP_DISABLED:
                    country_display = "*geo-IP disabled*"
                elif cc and cc != "?":
                    country_display = f"{flag} {cc}" if flag else cc
                else:
                    country_display = "*unknown*"
                org, is_hosting = ip_org(ip)
                org_display = geo_display(org, "unknown")
                hostname, is_customer_vm = ip_hostname(ip)
                raw_hostname = geo_display(hostname, "no PTR record")
                host_display = raw_hostname if raw_hostname.startswith("*") else f"`{raw_hostname}`"
                # Icon lives in its own column now — the ASN/Provider column stays plain
                # text, so it's not competing for attention with the warning glyph. A
                # cloud-customer-VM hostname (e.g. googleusercontent.com) is flagged the
                # same way as a generic hosting ASN match — both mean "not a residential
                # visitor," and the Reverse DNS column shows which specific case applies.
                flag_cell = "⚠️" if (is_hosting or is_customer_vm) else ""
                if is_hosting: any_hosting = True
                if is_customer_vm: any_customer_vm = True
            # IP plain text, request count bold — the count is the number worth scanning down
            # this column for, not the IP string itself.
            L.append(f"| `{ip}` | **{cnt}** | {country_display} | {org_display} | {host_display} | {flag_cell} |")
        L.append("")
        if any_hosting or any_customer_vm:
            # Broken into short bullets (not one dense paragraph) so the reader can scan the
            # three distinct points instead of parsing a single run-on sentence.
            L.append("> ⚠️ **At least one top IP is infrastructure, not a residential visitor**")
            L.append(">")
            L.append("> - The country tag shows where that server/proxy is located — not where a "
                      "human visitor actually is.")
            L.append("> - An ASN like *\"Google LLC\"* alone does **not** confirm it's Google's own "
                      "crawler.")
            L.append("> - Check the **Reverse DNS** column: a vendor's own bot domain (e.g. "
                      "`bot.semrush.com`) confirms genuine bot traffic; a "
                      "`*usercontent.com`/`*.amazonaws.com`-style hostname means it's a "
                      "**customer's rented VM**, not the vendor itself.")
            L.append("")
        L.append("")

    # ══════════════════════════════════════════════════════════════
    # TRAFFIC
    # ══════════════════════════════════════════════════════════════
    L.append("## Traffic Overview")
    L.append("")
    if access_data:
        total = access_data["total"]
        stc = access_data["statuses"]

        L.append("### Status Codes")
        L.append("")
        # Group totals first (2xx/3xx/4xx/5xx) so the reader sees the shape of traffic
        # health at a glance, then the individual codes as an indented sub-dimension —
        # rather than 8+ ungrouped rows with no sense of which bucket dominates.
        groups = {"2xx": [], "3xx": [], "4xx": [], "5xx": []}
        for code, cnt in sorted(stc.items()):
            if cnt and code and code[0] in "2345":
                groups[f"{code[0]}xx"].append((code, cnt))
        L.append("| Group | Total | Share |")
        L.append("|---|---|---|")
        for g in ["2xx", "3xx", "4xx", "5xx"]:
            g_total = sum(c for _, c in groups[g])
            if g_total == 0: continue
            pct = g_total/total*100
            bar = bar_chart(pct, 100, 15)
            L.append(f"| **{g}** | **{g_total}** | {bar} **{pct:.0f}%** |")
        L.append("")
        L.append("<details><summary>Individual status codes</summary>")
        L.append("")
        L.append("| Code | Count | Share |")
        L.append("|---|---|---|")
        for g in ["2xx", "3xx", "4xx", "5xx"]:
            for code, cnt in groups[g]:
                pct = cnt/total*100
                bar = bar_chart(pct, 100, 15)
                L.append(f"| {code} | {cnt} | {bar} **{pct:.0f}%** |")
        L.append("")
        L.append("</details>")
        L.append("")

        # Drill-down: exactly which URLs/IPs are behind each 4xx/5xx code, instead
        # of leaving the reader with only an aggregate count.
        status_urls = access_data.get("status_urls") or {}
        status_ips = access_data.get("status_ips") or {}
        error_codes = sorted(c for c in status_urls if status_urls[c])
        if error_codes:
            L.append("### Errors by Status Code — Drill-Down")
            L.append("")
            for code in error_codes:
                urls = status_urls[code]
                ips = status_ips.get(code, set())
                total_code = sum(urls.values())
                L.append(f"**{code}** — {total_code} requests from {len(ips)} distinct IP(s)")
                L.append("")
                L.append("| URL | Count |")
                L.append("|---|---|")
                for url, cnt in urls.most_common(5):
                    L.append(f"| `{url}` | {cnt} |")
                L.append("")

        L.append("### Requests per Hour (UTC)")
        L.append("")
        if access_data.get("hourly"):
            hourly = access_data["hourly"]
            max_h = max(hourly.values()) if hourly else 1
            # Real proportional bars (bar_chart(), the same █/░ helper used for Cache
            # Performance/Status Codes elsewhere in this report) REPLACE the previous
            # Unicode block-height sparkline (▁▂▃▄▅▆▇█). That approach was unreadable in
            # practice: at normal table font sizes, the height differences between adjacent
            # glyphs (e.g. ▄ vs ▅) are only 1-2 pixels and visually indistinguishable, so a
            # 127-request hour and a 460-request hour could render as near-identical bars.
            # A vertical table with an actual length-proportional bar AND the exact count
            # alongside it removes any ambiguity — the reader never has to eyeball a glyph.
            hour_keys = [f"{h:02d}:00" for h in range(24)]
            L.append("| Hour (UTC) | Requests | |")
            L.append("|---|---|---|")
            for key in hour_keys:
                cnt = hourly.get(key, 0)
                bar = bar_chart(cnt, max_h, 20)
                L.append(f"| `{key}` | {cnt} | {bar} |")
            L.append("")
            peak_hour, peak_cnt = max(hourly.items(), key=lambda x: x[1])
            low_hour, low_cnt = min(hourly.items(), key=lambda x: x[1])
            L.append(f"**Busiest:** `{peak_hour}` UTC ({peak_cnt} requests) · "
                     f"**Quietest:** `{low_hour}` UTC ({low_cnt} requests)")
        L.append("")

    else:
        reason = data_errors.get("access")
        L.append(f"Access log unavailable{f': {reason}' if reason else ''}.")
        L.append("")

    # "## Directory Scanner Activity" is permanently suppressed (pure noise — a single
    # "no action needed" line per report-structure.md). scanner_paths remains available
    # in-memory if a future section needs it, but nothing is rendered here.

    # Insert the geo-IP status banner now that every lookup this run has actually happened —
    # one clear notice instead of the reader having to infer "why does everything say unknown"
    # from dozens of individual table cells scattered across the report.
    banner = []
    if not GEOIP_ENABLED:
        banner = ["> ℹ️ **Geo-IP/ASN/reverse-DNS lookups were disabled** (`--no-geoip` was passed) "
                  "— every Country/ASN/Reverse DNS cell below reads *geo-IP disabled*, not "
                  "\"unknown\" or a broken lookup. Re-run without `--no-geoip` for that data.", ""]
    elif _LOOKUP_STATS["attempted"] >= 5 and _LOOKUP_STATS["empty"] / _LOOKUP_STATS["attempted"] > 0.5:
        pct = _LOOKUP_STATS["empty"] / _LOOKUP_STATS["attempted"] * 100
        banner = [f"> ⚠️ **Geo-IP lookups returned nothing for {pct:.0f}% of the "
                  f"{_LOOKUP_STATS['attempted']} IPs checked this run** — this looks like an "
                  f"`ipinfo.io` outage, rate limit, or network issue, not that these IPs "
                  f"genuinely have no data. Re-run later before trusting a high \"unknown\" "
                  f"count as a real finding.", ""]
    if banner:
        L[geoip_banner_index:geoip_banner_index] = banner

    # ══════════════════════════════════════════════════════════════
    # PART 2 (continued): LLM-filled reference sections
    # ══════════════════════════════════════════════════════════════
    L.append("## 🔬 Live Probe Cross-Match")
    L.append("")
    L.append("<!-- LLM:PROBE_CROSS_MATCH -->")
    L.append("")
    L.append("## 📚 Kinsta KB References")
    L.append("")
    L.append("<!-- LLM:KB_REFERENCES -->")
    L.append("")

    return "\n".join(L)

# ═══════════════════════════════════════════════════════════════════
# VALIDATION — checks a finished report against the structure contract in
# references/report-structure.md. Run via: analyze_logs.py --validate <report.md>
# ═══════════════════════════════════════════════════════════════════

REQUIRED_MARKERS = [
    "<!-- LLM:AT_A_GLANCE -->", "<!-- LLM:OVERALL_ASSESSMENT -->",
    "<!-- LLM:ATTACK_SECURITY -->",
    "<!-- LLM:CACHE_ROOT_CAUSE -->", "<!-- LLM:BOT_STRATEGY -->",
    "<!-- LLM:BURST_CARDS -->", "<!-- LLM:TRAFFIC_ANOMALIES -->",
    "<!-- LLM:ERROR_FIXES -->", "<!-- LLM:PROBE_CROSS_MATCH -->",
    "<!-- LLM:KB_REFERENCES -->",
]

FORBIDDEN_SECTIONS = [
    "## Health Summary", "## 🟢 Low-Priority Notes", "### How to Improve Cache HIT Rate",
    "### Scanner IPs — Block List", "## Directory Scanner Activity",
]

CARD_SECTIONS_REQUIRING_INCIDENT_BULLET = [
    "### Attack/Security Findings", "### Concentrated Traffic Spikes & Bursts",
    "### Traffic Anomalies",
]

def validate_report(path):
    """Returns (ok: bool, problems: list[str])."""
    with open(path) as f:
        text = f.read()
    problems = []

    unfilled = [m for m in REQUIRED_MARKERS if m in text]
    if unfilled:
        problems.append(f"Unfilled markers remain: {', '.join(unfilled)}")

    for section in FORBIDDEN_SECTIONS:
        if section in text:
            problems.append(f"Forbidden section present: '{section}'")

    if "PART 1: SUMMARY & FINDINGS" not in text:
        problems.append("Missing 'PART 1: SUMMARY & FINDINGS' divider")
    if "PART 2: TECHNICAL APPENDIX" not in text:
        problems.append("Missing 'PART 2: TECHNICAL APPENDIX' divider")

    # Card format check: for each card-bearing subsection, if it has any "####" card,
    # at least one "- **Event:**" bullet must
    # follow before the next "####"/"###"/"##" heading.
    for section_heading in CARD_SECTIONS_REQUIRING_INCIDENT_BULLET:
        idx = text.find(section_heading)
        if idx == -1:
            continue
        next_h2_or_h3 = len(text)
        for marker in ("\n## ", "\n### "):
            pos = text.find(marker, idx + len(section_heading))
            if pos != -1:
                next_h2_or_h3 = min(next_h2_or_h3, pos)
        block = text[idx:next_h2_or_h3]
        if "#### " in block and "- **Event:**" not in block and "- **URL(s):**" not in block and "not observed" not in block.lower():
            problems.append(f"'{section_heading}' has a card (####) with no '- **Event:**' or '- **URL(s):**' bullet")

    return (len(problems) == 0, problems)

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    # --validate is a separate mode (report_path only) checked before the normal
    # argparse setup below, which requires error_file/access_file as positionals.
    if len(sys.argv) >= 3 and sys.argv[1] == "--validate":
        ok, problems = validate_report(sys.argv[2])
        if ok:
            print("✅ Validation passed — no unfilled markers, no forbidden sections, card format OK.")
            sys.exit(0)
        else:
            print("❌ Validation failed:")
            for p in problems:
                print(f"  - {p}")
            sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("error_file")
    parser.add_argument("access_file")
    parser.add_argument("cache_file", nargs="?")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--no-geoip", action="store_true",
                         help="Disable network geo-IP lookups to ipinfo.io (privacy/speed/determinism)")
    args = parser.parse_args()

    global GEOIP_ENABLED
    GEOIP_ENABLED = not args.no_geoip

    site_name = os.path.basename(os.path.dirname(os.path.dirname(args.error_file)))
    # Environment (e.g. "live", "staging") is the immediate parent dir of the raw log files —
    # {site_name}/{env_name}/{ts}_error.json — used for the title and the flat reports/ filename.
    env_name = os.path.basename(os.path.dirname(args.error_file))

    data_errors = {}
    err_logs, err_err = extract_logs(args.error_file)
    if err_err: data_errors["error"] = err_err
    acc_logs, acc_err = extract_logs(args.access_file)
    if acc_err: data_errors["access"] = acc_err
    cache_data = None; cache_entries = []
    if args.cache_file:
        cl, cache_err = extract_logs(args.cache_file)
        if cache_err: data_errors["cache"] = cache_err
        if cl:
            cache_data = analyze_cache_log(cl)
            if cache_data: cache_entries = cache_data.get("entries", [])

    err_filtered = err_logs; acc_filtered = acc_logs
    if err_logs: err_filtered, _, _, _ = filter_by_hours(err_logs, args.hours, "error")
    if acc_logs: acc_filtered, _, _, _ = filter_by_hours(acc_logs, args.hours, "access")

    error_findings = {"critical": [], "medium": [], "low": []}
    error_meta = None; error_entries = []; access_data = None; access_entries = []
    scanner_paths = Counter(); scanner_ips = Counter()

    if err_filtered:
        error_findings, ts_range, ip_counter, error_entries, scanner_paths, scanner_ips = \
            analyze_error_log(err_filtered)
        error_meta = {"timerange": ts_range, "total_lines": len(err_filtered.split("\n"))}
    if acc_filtered:
        access_data = analyze_access_log(acc_filtered)
        access_entries = access_data.get("entries", [])

    cross_results = cross_analyze(access_entries, cache_entries, error_entries,
                                  ip_counter if err_filtered else Counter(), scanner_ips)

    report = generate_report(site_name, error_findings, error_meta, access_data,
                             cache_data, cross_results, scanner_paths, args.hours, data_errors,
                             env_name=env_name)

    # Reports live in a single flat ~/Downloads/kinsta-logs/reports/ folder (not nested per
    # site/env like the raw logs) — the filename itself encodes site/env/timestamp so reports
    # stay unique and easy to browse chronologically without digging into subfolders.
    report_dir = os.path.expanduser("~/Downloads/kinsta-logs/reports")
    os.makedirs(report_dir, exist_ok=True)
    ts_raw = "_".join(os.path.basename(args.error_file).split("_")[:2])
    try:
        ts_compact = datetime.strptime(ts_raw, "%Y-%m-%d_%H%M%S").strftime("%Y%m%d%H%M")
    except ValueError:
        ts_compact = ts_raw.replace("-", "").replace("_", "")[:12]
    report_path = os.path.join(report_dir, f"report_{site_name}_{env_name}_{ts_compact}.md")
    with open(report_path, "w") as f: f.write(report)

    print(report)
    print(f"\n📄 {report_path}")

    import subprocess as sp
    try: sp.run(["code", report_path], check=False, timeout=5)
    except Exception: pass

if __name__ == "__main__": main()
