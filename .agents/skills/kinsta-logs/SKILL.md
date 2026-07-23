---
name: kinsta-logs
description: Fetch and analyze Kinsta server logs (error, access, cache-perf) to produce a severity-ranked operational health report with cache efficiency, bot traffic, error rates, and response times. Not for code debugging. Use when user asks to "analyze Kinsta logs", "check server logs", "debug Kinsta site errors", or "review cache performance".
license: MIT
compatibility: Requires Kinsta MCP server configured in .roo/mcp.json; Python 3.8+; optional: ipinfo.io access for geo-IP, Quarto/Typst or Chromium for PDF export
---

# Kinsta Log Analyzer

## 🚨 Mechanical steps in this skill (URL extraction, validation, grep audits, marker filling) must be followed exactly as written. Analytical steps (severity judgments, tone calibration, correlation) require professional judgment within the stated guardrails.

## When to Use
- User asks to "analyze Kinsta logs", "check server logs", "debug errors on Kinsta"
- Periodic log health checks
- Debugging performance issues, errors, or traffic anomalies
- Reviewing Kinsta edge cache efficiency

## When NOT to Use
- Non-Kinsta hosting (this skill is Kinsta API-specific)
- Real-time monitoring (this is a point-in-time analysis)
- Code debugging (this skill analyzes website traffic and operational health, not source code)
- If `.roo/mcp.json` has no `kinsta` server configured

## ⚠️ Memory-Bank Isolation
This skill is a **standalone Kinsta operations tool** — it does NOT belong to the fralenuvole plugin codebase. It MUST NOT read from or write to `memory-bank/` files (activeContext.md, progress.md, systemPatterns.md, productContext.md). Those files document the plugin only. The skill's own state belongs in its `references/` directory. Any findings, reports, or changes related to this skill MUST stay within `.agents/skills/kinsta-logs/` and `~/Downloads/kinsta-logs/`.

## Scope
This skill is about **website operations & traffic analysis**. It answers questions like:
- "How healthy is my site's cache?"
- "Are bots overwhelming my traffic?"
- "Are visitors hitting errors or slow pages?"
- "What traffic patterns and anomalies exist?"

It does NOT diagnose PHP code bugs, WordPress plugin conflicts, or database queries — for those, use code-level debugging tools (WP_DEBUG, Query Monitor, Xdebug).

## Report Audience & Purpose

The report targets **management**, not developers. Every finding must include a concrete action doable from the MyKinsta panel or sourced from a Kinsta KB article (cited in Step 2). **Never recommend a code-level fix** referencing this repo's file paths, functions, or config — the reader manages infrastructure. If no documented Kinsta-side fix exists, say so plainly.

---

## Architecture Blueprint
This skill uses the **Orchestrate-Analyze-Build (OAB)** pattern. See [`references/architecture-blueprint.md`](references/architecture-blueprint.md) for a detailed explanation of this architecture and how to use it as a template for future skills.

---

## Kinsta API Constraints

**Read [`references/kinsta-api.md`](references/kinsta-api.md) before fetching or interpreting logs.** It documents API behavior (line-based, no time-window filtering, 20,000-line cap), log rotation handling, line-count coverage estimates, and the critical origin-vs-edge-cache scope distinction that must be stated in every report.

---


### Step 1: Orchestrate Data Gathering

The entire data gathering pipeline (site discovery, log fetching, baseline probing, initial analysis, and targeted probing) is now automated by a single orchestrator script.

1. **Execute the orchestrator:**
   ```bash
   KINSTA_API_KEY="..." KINSTA_COMPANY_ID="..." python3 .agents/skills/kinsta-logs/scripts/orchestrator.py [--site SITE_NAME] [--env ENV_NAME]
   ```
   *Note: If `--site` is omitted, it defaults to the site in `config/defaults.json`.*

2. **Run the initial analysis:**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py
   ```
   *Note: This script reads `.run_state.json` to find the logs and outputs a `context.json` file containing all the raw data tables and findings.*

3. **Run the targeted probe:**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/probe_targeted.py
   ```
   *Note: This script reads `.run_state.json` to find the `context.json` file, extracts the target URLs mechanically, and runs the probe.*

### Step 2: Analyze & Write Findings (JSON)

**This is LLM reasoning, not automated — every analysis is unique.** You must read the generated `context.json` and both probe JSON files (`_probe_baseline.json` and `_probe_targeted.json`), then write your findings into a structured JSON file.

1. **Read the data:**
   - Read `context.json` (contains all auto-generated data tables and metrics).
   - Read the baseline and targeted probe JSON files (paths are in `.run_state.json`).
   - Read `references/site-context.md` for timezone and market context.
   - Read `references/bot-taxonomy.md` before writing any bot-related recommendation.

2. **Gather External Evidence:**
   - Look up the current Kinsta Knowledge Base for any 🔴/🟡 finding using `tavily-search` scoped to `kinsta.com`.
   - Consult `references/kinsta-tribal-knowledge.md` and `references/kinsta-history.md`.

3. **Apply Internal Framework:**
   - See `references/report-structure.md` for the Internal Framework (Analyst Checklist). Use this framework to REASON through each finding (What / Why / Who / How).

4. **Write Findings to JSON:**
   Create a file named `analyst_findings.json` in the workspace root. It MUST contain the following keys, corresponding to the report sections. Use the **finding-card format** (Markdown) for the values, adhering strictly to the Tone Calibration and Severity Icon vocabulary in `references/conciseness-directives.md`.

   ```json
   {
     "overall_assessment": "...",
     "attack_security": "...",
     "cache_root_cause": "...",
     "bot_strategy": "...",
     "burst_cards": "...",
     "traffic_anomalies": "...",
     "error_fixes": "...",
     "probe_cross_match": "...",
     "kb_references": "...",
     "at_a_glance": "..."
   }
   ```
   *Note: Write `at_a_glance` LAST, after performing a Correlation & Synthesis Pass across all your other findings.*

### Step 3: Build & Validate Report

1. **Build the final Markdown report:**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/build_report.py --findings analyst_findings.json
   ```
   *Note: This script merges your JSON findings with the raw data tables in `context.json` to produce the final, perfectly formatted Markdown report in `.output/kinsta-logs/reports/`.*

2. **Validate the report:**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py --validate "$REPORT_PATH"
   ```
   *(Get `$REPORT_PATH` from the output of `build_report.py` or `.run_state.json`)*

3. **URL spelling verification (MANDATORY):**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/verify_urls.py \
     "$REPORT_PATH" \
     "$(jq -r .probe_baseline .agents/skills/kinsta-logs/.run_state.json)" \
     "$(jq -r .probe_targeted .agents/skills/kinsta-logs/.run_state.json)" \
     ".agents/skills/kinsta-logs/references/site-context.md"
   ```

### Step 4: Export PDF & Email (Optional)

1. **Export PDF:**
   ```bash
   bash .agents/skills/kinsta-logs/scripts/export_pdf.sh "$REPORT_PATH"
   ```

2. **Send Email (User-Initiated Only):**
   Ask the user if they want to email the report. If yes:
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/send_report_email.py "${REPORT_PATH%.md}.pdf"
   ```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `NETWORK_ERROR` on cache-perf | Transient Kinsta API issue | Retry up to 3x with 3s sleep between |
| Tool name not found (e.g. `kinstasiteslist`) | Roo Code strips dots from tool names — confirmed upstream bug (GitHub RooCodeInc/Roo-Code #6514). The `mcp--kinsta--kinsta.sites.list` function name gets flattened to `kinstasiteslist`, which doesn't exist on the server. | **Never use `mcp--kinsta--*` functions.** Always use `execute_command` with JSON-RPC piped into `npx -y kinsta-mcp@1.0.3`. See Step 1's ⚠️ banner for the exact command template. The `scripts/fetch_logs.sh` script already does this internally for log fetching. |
| `⏳ *pending*` still in Part 2 bot tables after report assembly | `apply_diff` on Part 2 tables failed due to line number shifts after Part 1 commentary was filled in | Use the `sed` one-liner from the `sed` instructions in Step 2 instead — it's deterministic and doesn't depend on line numbers |
| `Validation error: Invalid enum value` | Used `error.log` instead of `error` | Use bare names: `error`, `access`, `kinsta-cache-perf` |
| Cross-file analysis empty | Error and access logs don't overlap in time | Use `"lines":8000` for the access log for full 24h coverage |
| Report file not found | Looked in `$DIR` instead of the reports folder | Reports live in `~/Downloads/kinsta-logs/reports/`, named `report_{site_name}_{env_name}_{YYYYMMDDHHMM}.md` — check `analyze_logs.py`'s printed `📄` line for the exact path |
| Analyst Commentary vanished after a later run | `analyze_logs.py` regenerates the entire report from scratch every run — a manually-appended commentary is not part of that generation and gets silently overwritten | Never re-run the script against real `$DIR` log files whose report is the one being reviewed; use scratch-copied log files (Step 3's warning). If it already happened, re-run Step 3 cleanly, then redo Step 2 analysis (analyst_findings.json) in the same batch of work |
| Report shows "unknown"/"no PTR record" everywhere | `--no-geoip` was passed, or `ipinfo.io` is failing/rate-limiting broadly | Check the top-of-report banner — it states which case applies. Re-run without `--no-geoip`, or wait and retry if ipinfo.io is down |
| PDF export fails/skipped | Quarto not found (typst engine), or Chromium missing (chromium engine), or npx/network unavailable | For typst: install Quarto or set `TYPST_BIN`. For chromium: set `CHROMIUM_BIN` to the correct path. The Markdown report is still valid on its own regardless |
| `verify_urls.py` reports URL mismatch | A URL in the LLM-authored commentary was retyped from memory instead of copy-pasted from a source file — transliterated non-English words (e.g. Russian in Latin script) have no semantic meaning to the LLM, so a retyped URL will almost always have a spelling error | Copy the correct URL from the "Did you mean?" hint in the error output, replace the misspelled one in the report via `sed`, then re-run `verify_urls.py`. Also re-run `--validate` and re-export PDF |

---

## Files

| File | Purpose | Action |
|---|---|---|
| [`scripts/fetch_logs.sh`](scripts/fetch_logs.sh) | Parallel log fetch with per-log retry, pinned `kinsta-mcp` version | **Execute** in Step 1 |
| [`scripts/analyze_logs.py`](scripts/analyze_logs.py) | Log analysis + cross-file correlation, including per-bot URL/IP-concentration ("bursts"), ASN/hosting-provider/reverse-DNS detection, and grouped status codes (local parsing is deterministic; geo-IP/ASN/PTR lookups are not — see `--no-geoip`). **Always regenerates the full report from scratch**, and writes it to `~/Downloads/kinsta-logs/reports/` (not `$DIR`) — see Step 3's scratch-testing warning and the Troubleshooting entry above | **Execute** in Step 1 |
| [`scripts/probe_urls.py`](scripts/probe_urls.py) | Live HTTP probe (status/timing/headers) — a real-time snapshot, not historical. Run twice: baseline (fixed URLs, Step 2) and targeted (dynamic URLs from findings, Step 4) | **Execute** in Step 1 |
| [`scripts/verify_urls.py`](scripts/verify_urls.py) | Post-generation mechanical URL verification — diffs every URL in LLM-authored commentary against source files (probe JSON, site-context.md, report data tables). Catches transliteration errors that are invisible to spell-check | **Execute** in Step 3 — mandatory, do not skip |
| [`scripts/tests/test_analyze_logs.py`](scripts/tests/test_analyze_logs.py) | Automated tests for marker emission, report structure, forbidden sections, and --validate pass. Uses fixture data in `tests/fixtures/` | **Execute** after making script changes — `python3 scripts/tests/test_analyze_logs.py` |
| [`scripts/export_pdf.sh`](scripts/export_pdf.sh) | Converts the final Markdown report to PDF via one of two engines: `chromium` (default, md-to-pdf + system Chromium) or `typst` (Quarto pandoc+Typst) | **Execute** in Step 4 |
| [`scripts/report.css`](scripts/report.css) | Sans-serif report stylesheet applied by the `chromium` engine (default) — larger body text (13px), compact tables (11px), professional typography | Used automatically by `export_pdf.sh` |
| [`scripts/send_report_email.py`](scripts/send_report_email.py) | Sends the PDF report as email attachment via SMTP (Gmail by default). Merges non-sensitive fields from [`config/email.json`](config/email.json) (recipients, subject, signature) with SMTP credentials from `~/.config/kinsta-log-analyzer/email.json` | **Execute** in Step 4 (optional), if the user chooses to email the report |
| [`config/email.json`](config/email.json) | Non-sensitive email fields: `from_email`, `to_emails`, `subject`, `body_signature`. Lives in the skill folder; version-controlled | Edit directly to change recipients or subject |
| [`config/email.json.example`](config/email.json.example) | Template for `~/.config/kinsta-log-analyzer/email.json` — SMTP credentials only (`smtp_host`, `smtp_port`, `username`, `password`). Not version-controlled | Copy to `~/.config/kinsta-log-analyzer/email.json` and fill in credentials |
| [`references/site-context.md`](references/site-context.md) | Admin/business-owner timezones, each site's confirmed primary market, and the fixed "Known Probe URLs" list per site — a living cache, update it when the user confirms new context | **Read** in Step 1; **update** via `apply_diff` when new context is learned |
| [`references/bot-taxonomy.md`](references/bot-taxonomy.md) | Accurate, unbiased per-bot reference: real nature (crawler vs. on-demand agent), robots.txt/Crawl-Delay compliance matrix, Kinsta/WordPress-generic mitigation tiers (no hosted-app code involved — see Step 2), and the ASN-vs-reverse-DNS distinction | **Read in full** in Step 2 before writing any bot-related recommendation |
| [`references/report-structure.md`](references/report-structure.md) | Authoritative contract: defines every section heading, format, conditional display rule, marker inventory, and permanently suppressed sections for the generated report | **Read** in Step 2 before writing findings |
| [`references/conciseness-directives.md`](references/conciseness-directives.md) | 14 mandatory conciseness & consistency rules governing report formatting, tone, citation, and domain-specific judgment. Several are grep-auditable | **Read in full** in Step 2 before writing any report commentary |
| [`references/kinsta-api.md`](references/kinsta-api.md) | Kinsta API constraints: line-based retrieval, log rotation, line-count estimates, and the origin-vs-edge-cache scope distinction | **Read** before Step 1 (log fetching) and when interpreting cache HIT rates |
| [`references/operational-playbook.md`](references/operational-playbook.md) | Expert server guidance for each anomaly type (cache, errors, response time, traffic spikes, SSL) | **Read** when the report flags an issue needing deeper action |
| [`references/kinsta-tribal-knowledge.md`](references/kinsta-tribal-knowledge.md) | Platform behaviors confirmed by Kinsta support (Nginx capabilities/limitations, cache architecture, Bot Protection mechanisms, default behaviors) — facts not in the public KB | **Read** in Step 2 when forming Nginx/rate-limit/cache/bot action recommendations |
| [`references/kinsta-history.md`](references/kinsta-history.md) | Chronological log of actions already taken via Kinsta support per site — prevents re-recommending past actions | **Read** in Step 2 before finalizing any action recommendation; **update** via `apply_diff` when new actions are taken |

## Configuration
Reads credentials from `.roo/mcp.json` → `mcpServers.kinsta.env`. Kinsta Knowledge Base lookups
(Step 2) use the `tavily` MCP server (`tavily-search`), also configured in `.roo/mcp.json`.
PDF export (Step 4) supports two engines: `chromium` (default, md-to-pdf + system Chromium at `/usr/bin/chromium`, best visual design, A4)
and `typst` (Quarto pandoc+Typst, no extra deps). Switch with `--engine`.

## Privacy & Retention
- Visitor IPs from the access/error logs are written to disk under `~/Downloads/kinsta-logs/` and are not automatically cleaned up — periodically prune old log/report files if this is a concern.
- Unless `--no-geoip` is passed, visitor IPs are also sent to the third-party `ipinfo.io` service up to three times per unique IP — country lookup, ASN/organization lookup (`ip_org()`), and reverse-DNS/PTR lookup (`ip_hostname()`) — during Step 3.
- Both probe passes (Step 2's baseline, Step 4's targeted) send real HTTP requests to the site being analyzed (and only that site — never a third party) from wherever this skill runs; this generates a handful of extra hits in the site's own logs at probe time, self-identified via a distinctive User-Agent (`Kinsta-Log-Analyzer-Probe`) so future analysis runs recognize this as this skill's own traffic, not an unknown visitor.
- The generated report (and its PDF) embeds raw visitor IPs and is opened in VS Code; treat it like any other file containing visitor data.
- Step 2's Kinsta KB lookups send search queries (not visitor data) to `tavily-search`.

## Output Structure
```
.output/kinsta-logs/
├── {site_name}/
│   └── {env_name}/
│       ├── {YYYY-MM-DD_HHMMSS}_error.json
│       ├── {YYYY-MM-DD_HHMMSS}_access.json
│       ├── {YYYY-MM-DD_HHMMSS}_cache.json
│       ├── {YYYY-MM-DD_HHMMSS}_probe_baseline.json
│       ├── {YYYY-MM-DD_HHMMSS}_probe_targeted.json
│       └── context.json
└── reports/
    ├── report_{site_name}_{env_name}_{YYYYMMDDHHMM}.md
    └── report_{site_name}_{env_name}_{YYYYMMDDHHMM}.pdf
```
Raw per-run logs/probes stay nested under `{site_name}/{env_name}/`; every generated report (and
its PDF) lands in a single flat `reports/` folder, since the filename itself already encodes
site, environment, and timestamp.
