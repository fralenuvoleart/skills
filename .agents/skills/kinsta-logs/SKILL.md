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

The report targets **management**, not developers. Every finding must include a concrete action doable from the MyKinsta panel or sourced from a Kinsta KB article (cited in Step 8). **Never recommend a code-level fix** referencing this repo's file paths, functions, or config — the reader manages infrastructure. If no documented Kinsta-side fix exists, say so plainly.

---

## Kinsta API Constraints

**Read [`references/kinsta-api.md`](references/kinsta-api.md) before fetching or interpreting logs.** It documents API behavior (line-based, no time-window filtering, 20,000-line cap), log rotation handling, line-count coverage estimates, and the critical origin-vs-edge-cache scope distinction that must be stated in every report.

---


### Step 1: Discover Sites & Environments

1. Read `.roo/mcp.json` for `KINSTA_API_KEY` and `KINSTA_COMPANY_ID`.
2. Discover sites via JSON-RPC using the provided script:

   ```bash
   KINSTA_API_KEY="..." KINSTA_COMPANY_ID="..." bash .agents/skills/kinsta-logs/scripts/list_sites.sh
   ```
3. **If the user specified a site name**, extract the site ID and live environment ID from the JSON output.
4. **If no site specified**:
   - Check conversation history for a previously analyzed site — reuse it.
   - **Default site:** Read `config/defaults.json` to get the default site (e.g., `pbservices.ge`). If no conversation history exists and the user didn't specify a site, analyze the default site without asking. Announce it briefly: "Analyzing [default site] (default site)."
   - Only ask which site if the user explicitly requests a different site or if conversation history points to a different site.
5. Default to the **live** environment (or the default environment from `config/defaults.json`).
6. **Read [`references/site-context.md`](references/site-context.md)** — it records the admin's
   and business owner's timezones and each site's confirmed primary visitor market. This is
   required context for interpreting traffic-hour patterns and geo-IP results correctly in the analyst steps (Steps 7–14);
   skipping it leads to misreading normal local business hours as "anomalies." If the site being
   analyzed has an `unknown — ask` entry, ask the user once via `ask_followup_question`, then
   persist the answer into that file via `apply_diff` before continuing — never ask twice for the
   same fact.

### Step 2: Fetch Logs + Baseline Probe (parallel)

**Execution order matters** — fetch the logs and probe the *fixed* sample URL set at the same
time, not sequentially, because the fixed URLs don't depend on any analysis result and probing
them close to the log-fetch time gives a more temporally-consistent snapshot than waiting until
after analysis finishes. Only the *dynamic* URLs (chosen from findings) wait for Step 4.

1. Generate a single timestamp, then **execute** [`scripts/fetch_logs.sh`](scripts/fetch_logs.sh) to fetch all three logs in parallel with retries — this encapsulates the fetch+retry logic deterministically instead of hand-writing bash each run:

   ```bash
   TS=$(date -u +%Y-%m-%d_%H%M%S)
   DIR=~/Downloads/kinsta-logs/{site_name}/{env_name}
   mkdir -p "$DIR"

   KINSTA_API_KEY="..." KINSTA_COMPANY_ID="..." \
     bash .agents/skills/kinsta-logs/scripts/fetch_logs.sh "$ENV_ID" "$DIR" "$TS"
   ```
   *Note: This script now writes a `.run_state.json` file to manage state for subsequent steps.*

2. **At the same time** (a separate tool call, not sequentially blocking on step 1), **execute**
   [`scripts/probe_baseline.py`](scripts/probe_baseline.py) to probe the fixed sample URL list from
   [`references/site-context.md`](references/site-context.md).

   ```bash
   python3 .agents/skills/kinsta-logs/scripts/probe_baseline.py
   ```
   *Note: This script reads the `.run_state.json` file to know where to save the output and automatically extracts the correct URLs from `site-context.md`.*

**Fetch strategy** (implemented by the script, run in parallel):

| Priority | Log | Lines | Retries | Why |
|---|---|---|---|---|
| 1 | `error` | 1000 | 1 | ~1–3 days of error coverage |
| 2 | `access` | 8000 | 1 | ~24 hours, full-window overlap with error log |
| 3 | `kinsta-cache-perf` | 1000 | **3** (flaky endpoint) | Cache HIT/MISS/BYPASS data |

**Why batch the access log**: 1000 access lines ≈ 3–5 hours, but the error log spans days. Batching 8000 access lines covers ~24 hours, giving full-window overlap for cross-file analysis.

**Retry logic**: If cache-perf fails with `NETWORK_ERROR`, the script retries with a 3s sleep between attempts, up to 3 times, then proceeds without it — check stderr output for `[FAILED]` lines.

**Package pinning**: the script pins `kinsta-mcp@1.0.3` rather than running unpinned `npx -y kinsta-mcp`, so behavior doesn't silently change between runs when a new version publishes.

**Credential note**: passing `KINSTA_API_KEY`/`KINSTA_COMPANY_ID` inline on the command line can leak secrets via shell history or `ps aux`. Prefer exporting them in the current shell session (`export KINSTA_API_KEY=...`) rather than prefixing the command, when running interactively.

### Step 3: Analyze
Run the bundled script. **Default: last 24 hours.** Add `--hours N` for other windows. The script
prints the generated report's path on its last line (`📄 <path>`) and updates `.run_state.json`.
```bash
# Default (24 hours):
python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py \
  "$DIR/${TS}_error.json" \
  "$DIR/${TS}_access.json" \
  "$DIR/${TS}_cache.json"

# Custom timeframe (e.g., last 3 hours, last 72 hours):
python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py \
  "$DIR/${TS}_error.json" \
  "$DIR/${TS}_access.json" \
  "$DIR/${TS}_cache.json" \
  --hours 3

# Skip geo-IP lookups (privacy/speed — no data sent to ipinfo.io, fully deterministic):
python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py \
  "$DIR/${TS}_error.json" "$DIR/${TS}_access.json" "$DIR/${TS}_cache.json" --no-geoip
```

**Report location**: the report is NOT written into `$DIR` — it's written to a single flat
`~/Downloads/kinsta-logs/reports/` folder (created automatically), named
`report_{site_name}_{env_name}_{YYYYMMDDHHMM}.md`, so reports from every site/environment/run stay
browsable in one place without digging through per-site subfolders. The raw `_error.json`/
`_access.json`/`_cache.json`/`_probe_*.json` files remain in `$DIR` as before.

**Privacy note**: by default, `ip_country()` sends each unique visitor IP to `ipinfo.io` over the network to resolve a country code — this is the only non-deterministic, network-dependent part of the script (results are cached per-run to avoid duplicate lookups). Pass `--no-geoip` to keep the analysis fully local and deterministic; the report will show "unknown" instead of a country.

**⚠️ The script always regenerates the entire report skeleton from scratch on every run.** LLM-filled
marker content is NOT part of the script's generation — it gets silently destroyed by a re-run.
Never re-run the script against real `$DIR` log files whose report is the active one. If testing
script changes, copy log JSON files to `/tmp/` first.

The script produces a **two-part report skeleton** with `<!-- LLM: -->` markers where analyst content belongs. See [`references/report-structure.md`](references/report-structure.md) for the authoritative section contract. The skeleton includes:

- **Part 1 (Summary & Findings):** headings and `<!-- LLM: -->` markers for Overall Assessment, Cache Root Cause, Attack/Security, Bot Strategy, Burst Cards, Traffic Anomalies, 404 Fixes, and At a Glance. LLM orders Part 1 sections by severity tier.
- **Part 2 (Technical Appendix):** auto-generated data tables — Cache Performance (HIT/MISS/BYPASS, top-MISSed URLs, HIT-vs-MISS response time), Bot & Crawler Traffic (per-category tables without verdict column), Top Visitor IPs, Traffic Overview (Status Codes, Requests per Hour, Performance), and Slowest Pages. Plus `<!-- LLM: -->` markers for Probe Cross-Match and KB References.
- **Validation pass:** when run with `--validate <report_path>`, the script checks that all markers are filled, no permanently suppressed sections appear, and card formats comply.

**Permanently suppressed** (script never emits): Health Summary, Low-Priority Notes, How to Improve Cache HIT Rate, Scanner IPs — Block List, Errors by Status Code Drill-Down, Concentrated Traffic Spikes & Bursts auto-gen table, Directory Scanner Activity.

### Step 4: Targeted URL Probe (Dynamic, Post-Analysis)

**Execute** [`scripts/probe_targeted.py`](scripts/probe_targeted.py) — this second pass probes only
the URLs that Step 3's analysis actually flagged, since those can't be known before analysis runs
(unlike Step 2's fixed baseline probe). Both probe passes are real-time snapshots of right now, not
the log window, and the Analyst Commentary (Steps 10–12) must state that distinction explicitly whenever it cites either one.

1. **Execute the targeted probe script:**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/probe_targeted.py
   ```
   *Note: This script reads `.run_state.json` to find the report, extracts the target URLs mechanically, and runs the probe.*

2. **Read both probe JSON files** (`_probe_baseline.json` from Step 2 and `_probe_targeted.json`
   from this step) and cross-match against the log-derived report:
   - Does the live `http_code` match what the log window showed for that URL? A mismatch (e.g.
     log shows `200`, live probe shows `404`) means content changed between the log window and
     now — state this explicitly, don't treat it as a report error.
   - Does a `Set-Cookie` header appear on a public page? This directly confirms/refutes any BYPASS
     hypothesis from the Cache Root Cause Analysis — cite the actual cookie name (e.g. `__cf_bm` is
     Cloudflare Bot Management, not a WordPress/Polylang cookie — don't misattribute it).
   - Does `x-kinsta-cache` or an equivalent cache-status header confirm the log's HIT/MISS/BYPASS
     pattern for that specific URL right now?
   - Is `time_total` for the live probe consistent with the log's `avg_rt`/slowest-pages data, or
     does it suggest the site has gotten faster/slower since the log window closed?

### Step 5: Open Report
The script auto-opens the report skeleton in VS Code. It contains `<!-- LLM: -->` markers that you
will fill in Steps 7–14.

### Step 6: Read Skeleton & Probe Files

**This is LLM reasoning, not automated — every analysis is unique.** This is also the step users
judge the skill's expertise on — mediocre, generic advice here (e.g. "add Crawl-Delay for AI bots,"
"block Chinese bots because they're Chinese") is a failure of this step, not an acceptable
approximation. The script has generated a two-part skeleton with `<!-- LLM: -->` markers. You MUST:

1. **Read the generated skeleton** (`read_file` on the `*_report.md`) and both probe JSON files —
   `_probe_baseline.json` from Step 2 and `_probe_targeted.json` from Step 4.

### Step 7: Read Reference Files

2. **Read [`references/bot-taxonomy.md`](references/bot-taxonomy.md) in full before writing any
   bot-related recommendation.** It contains the accurate nature of each bot (crawler vs.
   real-time user-triggered agent), the actual robots.txt/Crawl-Delay compliance matrix, and the
   unbiased three-question assessment framework. Two hard rules from that file apply to every
   report, no exceptions:
   - **Never recommend `Crawl-Delay:` for a bot without documented support for it** (only Bingbot,
     YandexBot, AhrefsBot, SemrushBot, MJ12bot have it — see the compliance matrix). For every
     other bot, the only real levers are `Disallow` (best-effort) or a hard block/throttle.
   - **Never justify a keep/block verdict by the bot operator's country of origin.** Apply the same
     three questions (nature, compliance, audience relevance) to every bot and show your work —
     see the "Regional / High-Volume Crawlers" table for the reference example of doing this
     correctly (Amazonbot: US-operated but low relevance ≠ automatic keep; Bytespider:
     China-operated but the *actual* disqualifying facts are documented non-compliance + low
     audience relevance, not its origin).

3. **Check [`references/site-context.md`](references/site-context.md) against the report's
   traffic-hour and top-IP data**:
   - Convert flagged hour-of-day anomalies to **both** the admin's and the business owner's local
     time before calling anything a spike — a "spike" during the target market's normal business
     hours is not an anomaly.
   - For every top IP or scanner IP flagged as `hosting/proxy` in the ASN/Provider column, do not
     describe it as a visitor from that country — describe it as infrastructure, and say so
     explicitly with the actual org string as evidence.
   - **Check the Reverse DNS column too, not just ASN/Provider — ASN alone is not enough.** An ASN
     of "Google LLC" does NOT mean Google's own crawler; it only means the IP is on Google Cloud's
     network. A confirmed real miss from an earlier run: an IP reported as "Google LLC" was
     initially left unattributed, when its actual PTR record (`*.googleusercontent.com`) shows it's
     an unrelated third party's customer VM. Conversely, a PTR under the bot's own domain (e.g.
     `bot.semrush.com`, `dataproviderbot.com`) is positive confirmation the traffic is genuinely who
     it claims to be. See [`bot-taxonomy.md`] (references/bot-taxonomy.md#asn-is-not-enough)
     for the known-pattern table before writing any "who is this IP" conclusion.
   - If the confirmed primary market is known (e.g. Georgia for pbservices.ge) and RU/ZH-language
     traffic appears, do not flag it as suspicious by default — that language segment may be the
     actual target market. Only flag it when the specific URL/payload is itself a spam/injection
     pattern.
   - **Business-owner Easter egg (evidence-gated, do not force it):** if a top IP's geo/ASN
     plausibly resolves to the business owner's location (Tbilisi, per `site-context.md`) AND that
     IP's behavior shows obsessive-checking (unusually high request count on its own, or repeated
     hits on the same page/admin path), you may add ONE concise, tasteful, sarcastic one-liner
     about checking one's own site obsessively — in the finding's Interpretation, not as a
     separate section. If no such evidence exists, do not add a joke; fabricating one to be funny
     violates the no-fabrication rule and is worse than no joke at all.
   - **🚫 NEVER include known admin IPs in any error, performance, burst, or security finding.**
     Check `site-context.md` → "Known admin IPs" column before writing ANY card or commentary
     that names a specific IP. If an IP matches a known admin IP, it is the site administrator
     doing their job — exclude it from slow-page findings, burst cards, scanner lists, and error
     drill-down commentary. The script-generated tables (Slowest Requests, Top Visitor IPs,
     Bursts) are auto-generated evidence and may still show the IP — that's acceptable as raw
     data, but the LLM-authored commentary MUST NOT treat it as a finding. In the Overall
     Assessment and At a Glance, attribute admin-IP activity as "admin use" without naming the IP.
  - **🚫 NEVER disclose internal operational directives in the report.** The reader must never see
    references to internal filenames (`site-context.md`, `bot-taxonomy.md`, `kinsta-tribal-knowledge.md`,
    `kinsta-history.md`, `SKILL.md`), internal policy language ("explicitly excluded from all findings,"
    "per standing policy," "per our internal reference"), or any phrase that reveals HOW the analysis
    was conducted rather than WHAT was found. The report is a deliverable to management — cite
    evidence (log data, probe results, Kinsta support records, KB articles), never internal
    workflow files or policies. When an admin IP is identified, state only the factual conclusion
    ("site administrator working from Manila" / "admin activity") without explaining the exclusion
    mechanism. When converting timezones, state the converted times and market context without
    naming the internal reference file used to look them up.

### Step 8: Gather External Evidence

4. **Consult the per-bot URL-concentration data and the Concentrated Traffic Spikes & Bursts
   section already in the report** — do not guess whether a bot's traffic is "targeted" or
   "distributed." The report states the actual distinct-URL count, top-URL share, per-bot top-IP
   share, and lists the real top-5 URLs for the highest-volume bot per category. Cite these numbers
   directly (e.g. "ChatGPT-User's 641 requests spread across 160 distinct URLs, with its top 5
   being cost-of-living/neighborhood blog posts — consistent with real users asking ChatGPT about
   relocating to Georgia, not bulk scraping" vs. "ClaudeBot: 164 of 183 requests (90%) from a
   single IP, all to `/robots.txt` — this is a burst, not normal crawling behavior").

5. **Do not read, search, or open ANY file in the hosted plugin/theme codebase for this step, or
   at any other point in this skill.** This skill's own Scope (top of this file) already says it
   "does NOT diagnose PHP code bugs, WordPress plugin conflicts, or database queries" — that
   includes not reading the code "just to check," even privately. Bot-mitigation recommendations
   are decided **exclusively** from: (a) a MyKinsta-panel action (Denied IPs, Edge Caching
   exclusions, etc.), (b) a Kinsta support ticket for a WAF/`limit_req` rule, or (c) an honest,
   generic "no Kinsta-panel or documented fix exists for this pattern — flag it for whoever
   maintains the site's code" when neither (a) nor (b) applies. Never open `config/`, `includes/`,
   or any other plugin source path to check for an existing mitigation — the report's severity
   judgment is based only on the log data itself (e.g. request/IP concentration), never on
   anything read from the site's own code.

6. **Look up the current Kinsta Knowledge Base for any 🔴/🟡 finding** using `tavily-search` scoped
   to `kinsta.com` (e.g. `site:kinsta.com/knowledgebase edge caching bypass query strings`). Cite
   the specific article/URL found and summarize its guidance — this is what elevates
   recommendations from "generic hosting advice" to "what Kinsta support would actually tell you,"
   sourced from Kinsta's own current documentation rather than assumed from memory. If no relevant
   article is found, say so rather than fabricating a citation. **This is the "How" — never a
   boilerplate tip.** A live Kinsta KB citation, a MyKinsta-panel action, or an honest "no
   documented Kinsta-side fix — flag for your developer" (phrased generically, never naming this
   codebase) are the only three acceptable answers to "how do I fix this."

**kinsta-tribal-knowledge:** [`references/kinsta-tribal-knowledge.md`](references/kinsta-tribal-knowledge.md) records
    platform behaviors relevant to the finding.** Not all actionable facts are in the public KB —
    support transcripts have confirmed default behaviors (xmlrpc blocked, wp-login 6 req/min),
    Nginx capability boundaries (no POST body inspection, no URL-decoding), cache-clearing side
    effects (Clear All purges Redis), and Bot Protection mechanisms (CF ML scoring 1-99) that
    directly inform accurate "Actions" recommendations. When a finding involves Nginx rule
    suggestions, rate limiting, cache operations, or bot protection configuration, check this
    reference for platform constraints and defaults before writing the recommendation.

**kinsta-history:** [`references/kinsta-history.md`](references/kinsta-history.md) to avoid
    re-recommending past actions.** For each finding, check whether a past action already
    addresses it. If a match is found, acknowledge it in the Actions line: cite the past action,
    its date, and whether log evidence confirms it's still effective or suggests it needs
    re-verification. If no past action matches, proceed to form a new recommendation normally.

**Live Support Chat entry:** Always append the Kinsta Live Support Chat entry at the end of KB References.**
    After filling the `<!-- LLM:KB_REFERENCES -->` marker with KB article links, ALWAYS append
    as the final bullet:

    ```
    - **Kinsta Live Support Chat** — The report integrates additional insider knowledge and history
      of past actions, from the Kinsta Support Chat History.
    ```

    This applies even when no KB articles were cited — the Live Support Chat entry is always
    present. See [`references/report-structure.md`](references/report-structure.md) §
    `## 📚 Kinsta KB References` for the contract.

### Step 9: Apply Internal Framework

7. **See [`references/report-structure.md`](references/report-structure.md) for the Internal Framework (Analyst Checklist).** Use this framework to REASON through each finding (What / Why / Who / How).

### Step 10: Fill Report Markers

8. **Fill the `<!-- LLM: -->` markers in the script-generated skeleton.** The `analyze_logs.py`
   script now emits a two-part report skeleton with `<!-- LLM: -->` markers where analyst-written
   content belongs. **Do NOT append commentary — fill the markers.** The script owns structure;
   you own content and narrative.

   **Workflow:**
   1. Read the ENTIRE skeleton — all auto-gen data tables, all `<!-- LLM: -->` markers, all section headings — before writing anything.
   2. Identify the dominant narrative: what ONE finding defines this run? (Cache failure? Bot surge? Security incident?)
   3. Order Part 1 sections by severity: 🔴 > 🟡 > 🔧 > ✅. Within same tier, order by impact magnitude. The script puts markers in a default order; you MUST reorder Part 1 sections so the most important finding leads.
   4. Fill each `<!-- LLM: -->` marker with content. Use `apply_diff` to replace `<!-- LLM:MARKER_NAME -->` with the actual section content.
   5. After filling all markers, inject a **Verdict** column into every auto-generated bot table in Part 2 using the provided script:

      ```bash
      python3 .agents/skills/kinsta-logs/scripts/apply_verdicts.py
      ```
      *Note: This script reads `.run_state.json` to find the report and applies the verdicts robustly.*

   **Section format rules:**

   Use a **finding-card format** for the Traffic Anomalies, Attack/Security Findings,
   and Concentrated Bursts subsections specifically — freeform prose paragraphs are not acceptable
   there. **Each of Event/Analysis/Source/Actions MUST be its own bullet list item** (not
   consecutive bold-label lines in one paragraph) — list items are the only Markdown construct
   guaranteed to render on separate lines across every renderer; runs of `**Label:** text` lines
   without blank lines between them visually collapse into one paragraph in several renderers,
   which was the primary readability complaint against earlier versions of this skill's output.

   **Tone calibration — see [`references/conciseness-directives.md`](references/conciseness-directives.md) (D15).** Avoid both extremes (too alarmist, too dismissive).

   **Severity icon vocabulary — do not mix these two axes up:**
   | Icon | Reserved for |
   |---|---|
   | 🔴 | A genuine, active emergency — site down, active security breach, data at risk. Reserve this; do not use it for routine housekeeping (a stale cache file, a misbehaving bot, a low-value crawler) even if the fix is "high priority." |
   | 🟡 | A real concern worth attention soon, but not actively harming anyone right now. |
   | ✅ / 🟢 | Healthy, or handled correctly already — no action needed. |
   | 🔧 | A worthwhile housekeeping/maintenance action — NOT a health/security severity. Use this (never 🔴/🟡) for "add this bot to the throttle list," "flush this stale cache directory," "block this low-value crawler." |

   **Source classification tier** (required in every card's Source line): `Safe` / `Benign` /
   `Suspicious` / `Malicious` — a single word from this exact scale, stated plainly, not implied by
   the card's icon alone (the icon is about urgency, the tier is about intent — they are different
   axes and both must be stated).

   Template:

   ```markdown
   #### 🔴|🟡|🔧|✅ [Short title]
   - **Event:** [exact evidence — numbers/URLs/IPs from the report, or "not observed in this window"]
   - **Analysis:** [interpretation — is this suspicious, and why/why not]
   - **Source:** [who/what + classification tier: Safe/Benign/Suspicious/Malicious + targeted URL(s)]
   - **Actions:** [concrete action per Steps 7–8, or:
       - **No action required** ✅
         [description/explanation on new indented line]]
   ```

    **Conciseness & Consistency Directives — see [`references/conciseness-directives.md`](references/conciseness-directives.md).** Read this file in full before writing any report commentary. It defines 15 mandatory rules governing formatting, tone, citation, and domain-specific judgment. Several are grep-auditable in the Directive Compliance Audit (Step 13, below).

  **Full section structure — see [`references/report-structure.md`](references/report-structure.md).** That file is the sole authoritative contract: it defines every section heading, format, conditional display rule, marker inventory, and permanently suppressed sections. Read it now before filling any markers.

    **Validate before proceeding:** run `python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py --validate "$REPORT_PATH"` after filling all markers (see validation step below) — do not skip this even if the report "looks done."

### Step 11: Correlation & Synthesis Pass

**Correlation & Synthesis Pass.** After all markers are filled, re-read the ENTIRE assembled
    report — every Part 1 card, every Part 2 data table — and perform a holistic correlation pass.
    This is NOT a mechanical consistency check (matching numbers). This is where you find the
    connections between seemingly separate findings and weave them into one coherent narrative.

    For each section, ask: *"Does another section's data or analysis change how this one should
    read?"* Examples of correlations to surface:

    - A cache root cause (`__cf_bm` cookie) cascades into multiple metrics: the BYPASS rate, the
      elevated MISS count, the slow pages from a known crawler (who also hits cache MISS every
      time), the Polylang redirects (which also always MISS). State the cascade explicitly.
    - A heavy crawler IP flagged in Burst cards is the same IP dominating the Slowest Pages table
      in Part 2 — connect them with a cross-reference.
    - Bot traffic that looked suspicious in raw numbers becomes clearly legitimate when you
      cross-reference the top URLs (cost-of-living blog posts = real users, not scrapers).

    After this pass, update any section that needs revision based on correlations discovered.
    Common updates:

    - **Overall Assessment table:** refine the Cache/Bot traffic/Slow pages rows if correlation
      revealed connections the initial verdict missed.
    - **Cache Root Cause:** add a "Cascade effects" bullet listing which other metrics this root
      cause explains.
    - **Burst cards:** add cross-reference footnotes like "⚠️ This IP also appears in Slowest
      Pages (Part 2) — 75% of slow requests are from this one actor."
    - **At a Glance:** update anomaly descriptions and action priority if correlation changed the
      severity picture.

    After correlation is complete, for any 🟡 or 🔴 finding, consult [`references/operational-playbook.md`](references/operational-playbook.md) for the corresponding anomaly type (cache health, bot traffic, error patterns, response time, traffic spikes) before finalizing the Actions bullets. Then apply the two-audience test before finalizing:
    - **Business Owner:** can they grasp the site's current status from At a Glance alone
      (one-line verdict + anomaly bullets + priority actions) without reading Part 2?
    - **Site Admin:** can they act immediately from the priority actions list — each action
      concrete, specific, and ordered by urgency?
    If either answer is no, revise At a Glance or the affected cards before proceeding.

### Step 12: Write At a Glance

Write and place the `## 📌 At a Glance` section — written LAST, placed near the TOP.** This is
   the management-facing summary. Write it AFTER the Correlation & Synthesis Pass (it summarizes
   the fully correlated findings). The script-generated skeleton already has the `📌 At a Glance`
   heading in Part 1 with a `<!-- LLM:AT_A_GLANCE -->` marker. Fill that marker. Structure:
   - One-line overall status with severity icon
   - **Anomalies found in this period** — bullet list, one line per distinct finding, severity icon per line, plain-language (no jargon a manager wouldn't know)
   - **Priority actions this period** — numbered list, ordered by urgency, each action concrete enough to hand to whoever's fixing it

   **Formatting rules for At a Glance** (see Conciseness Directives 8–10 for full text):
   - Bold only key words and numbers within each bullet, never entire paragraphs (Directive 8).
   - Never flag cache HIT as "below target" when the window is a short post-midnight cold-start
     period; state it factually as expected behavior (Directive 9).
   - Reference the cache cold-start mechanism by name only — the full explanation lives in Cache
     Root Cause Analysis, not here (Directive 10).

**Scope note:** Append the following boilerplate block immediately after the Priority
    Actions numbered list (before the `>` blockquote that starts with "Scope:"). The origin-vs-
    edge-cache distinction belongs here.
    
    ```
    > **Scope:** This report analyzes origin-server traffic from `access.log`, `error.log`, and
    > `kinsta-cache-perf.log`. It does NOT include requests served entirely from Cloudflare's
    > edge cache (≈85% of total traffic) — MyKinsta Analytics will report higher totals that
    > include all edge-cached sub-resource requests invisible to these logs.
    ```
    
    Use `≈` (not `~`) for the percentage to avoid strikethrough rendering (see Directive 6).
    Verify this block is present; if missing, insert it.

### Step 13: Validate Report

**Script validation pass:** After all content is written, run the script's validation:
    ```bash
    python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py --validate "$REPORT_PATH"
    ```
    This checks: (a) no unfilled `<!-- LLM: -->` markers remain, (b) no permanently suppressed
    section headings appear, (c) Part 1/Part 2 dividers are present, (d) card format compliance.
    If validation fails, fix the reported issues and re-run.

**Conciseness Directive Compliance Audit (MANDATORY — do not skip).**
    🚨 Execute the grep audit script in [`references/conciseness-directives.md`](references/conciseness-directives.md)
    (see "Directive Compliance Audit" section at the bottom of that file). Copy the entire
    bash block, run it against `$REPORT_PATH`, and confirm every check prints PASS.
    If any check prints FAIL, fix the report and re-run the audit. Do NOT proceed to
    `--validate` or PDF export until every check passes. This is not optional —
    the `--validate` step below depends on these checks being clean.

**URL spelling verification (MANDATORY — do not skip).** Run [`scripts/verify_urls.py`](scripts/verify_urls.py)
    to mechanically diff every URL in the LLM-authored commentary against the source files:
    ```bash
    python3 .agents/skills/kinsta-logs/scripts/verify_urls.py \
      "$REPORT_PATH" \
      "$DIR/${TS}_probe_baseline.json" \
      "$DIR/${TS}_probe_targeted.json" \
      ".agents/skills/kinsta-logs/references/site-context.md"
    ```
    This catches transliteration errors (e.g. `prinimatel` vs `prinematel`) that are invisible to
    spell-check because the words are Russian written in Latin script. If any URL in the commentary
    doesn't exist in the source files, the script reports the mismatch with a "Did you mean?" hint.
    **Fix all reported mismatches before proceeding.** Do NOT proceed to PDF export until both
    `--validate` AND `verify_urls.py` pass with exit code 0.

### Step 14: Final Review

**Be honest about uncertainty:** If the data doesn't answer a question, or a Kinsta KB search
    found nothing relevant, say so — do not fabricate explanations or citations.

### Step 15: Export PDF

**Execute** [`scripts/export_pdf.sh`](scripts/export_pdf.sh) against the FINAL report — only after
the analyst commentary (Steps 7–14), At a Glance (Step 12), and final review are already written to disk,
since the PDF is a snapshot of whatever the Markdown file contains at the moment it runs:

```bash
# Default: Chromium engine (md-to-pdf + system Chromium, best visual design, A4)
bash .agents/skills/kinsta-logs/scripts/export_pdf.sh "$REPORT_PATH"

# Typst engine (Quarto's bundled pandoc + Typst, no extra deps)
bash .agents/skills/kinsta-logs/scripts/export_pdf.sh --engine typst "$REPORT_PATH"
```

Two engines supported:

| Engine | Command | Deps | Best For |
|---|---|---|---|
| `chromium` **(default)** | `npx md-to-pdf` + system Chromium | Chromium at `/usr/bin/chromium` | Visual design, compact layout, A4 |
| `typst` | `quarto pandoc ... --pdf-engine=typst` | Quarto only | Clean typography, no extra installs |

Output is `{report_path minus .md}.pdf` in the same `reports/` folder. If the chosen engine's
dependencies aren't found, the script exits with a warning — the Markdown report is the primary
deliverable regardless of PDF export success.

### Step 16: Send Report by Email (User-Initiated Only)
 
After PDF export, **ask the user** whether to email the report. Do not send email automatically.
Only send the PDF if the user explicitly chooses to send it in their chat response.
 
When the user confirms, send the PDF using
[`scripts/send_report_email.py`](scripts/send_report_email.py).
 
**Configuration — two files, split by sensitivity:**
 
| File | Contents | Version-controlled? |
|---|---|---|
| [`config/email.json`](config/email.json) | Non-sensitive: `from_email`, `to_emails`, `subject`, `body_signature` | ✅ Yes — lives inside the skill folder |
| `~/.config/kinsta-log-analyzer/email.json` | Sensitive: `smtp_host`, `smtp_port`, `username`, `password` | ❌ No — outside the project tree (see [`config/email.json.example`](config/email.json.example)) |
 
The script merges both at runtime. Recipients, subject, and signature are portable with the skill;
SMTP credentials stay on the local machine only.
 
**Prerequisites:**
- For Gmail: an **App Password** is required because regular account passwords do not work when
  2-Step Verification is enabled. Generate it at
  https://myaccount.google.com/apppasswords after enabling 2-Step Verification.

**Command:**
```bash
# Send the newest PDF in ~/Downloads/kinsta-logs/reports/
python3 .agents/skills/kinsta-logs/scripts/send_report_email.py

# Or send a specific PDF.
# IMPORTANT: pass the .pdf path, not the .md path. `$REPORT_PATH` from earlier
# steps points to the Markdown report — substituting the extension is the
# safest way to avoid attaching the wrong file:
python3 .agents/skills/kinsta-logs/scripts/send_report_email.py "${REPORT_PATH%.md}.pdf"
```

**Hard rule:** the script does NOT validate that the path you pass is a `.pdf`
— it attaches whatever file you give it as `application/octet-stream` and the
filename of the attachment matches the input. If you pass the `.md` path, the
email will contain the Markdown source, not the PDF. Always derive the path
from the Markdown report (e.g. `${REPORT_PATH%.md}.pdf`) or look it up via
`ls -t ~/Downloads/kinsta-logs/reports/*.pdf | head -1` before sending.

The script sends only the PDF attachment to all addresses in `to_emails`. If `to_emails` is not
provided, it falls back to a single `to_email`. The default subject is
`Kinsta Report from your AI Buddy` (configurable via the `subject` key). If the config file
is missing or invalid, the script exits with a clear error and does not send anything.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `NETWORK_ERROR` on cache-perf | Transient Kinsta API issue | Retry up to 3x with 3s sleep between |
| Tool name not found (e.g. `kinstasiteslist`) | Roo Code strips dots from tool names — confirmed upstream bug (GitHub RooCodeInc/Roo-Code #6514). The `mcp--kinsta--kinsta.sites.list` function name gets flattened to `kinstasiteslist`, which doesn't exist on the server. | **Never use `mcp--kinsta--*` functions.** Always use `execute_command` with JSON-RPC piped into `npx -y kinsta-mcp@1.0.3`. See Step 1's ⚠️ banner for the exact command template. The `scripts/fetch_logs.sh` script already does this internally for log fetching. |
| `⏳ *pending*` still in Part 2 bot tables after report assembly | `apply_diff` on Part 2 tables failed due to line number shifts after Part 1 commentary was filled in | Use the `sed` one-liner from Step 10 (item 5) instead — it's deterministic and doesn't depend on line numbers |
| `Validation error: Invalid enum value` | Used `error.log` instead of `error` | Use bare names: `error`, `access`, `kinsta-cache-perf` |
| Cross-file analysis empty | Error and access logs don't overlap in time | Use `"lines":8000` for the access log for full 24h coverage |
| Report file not found | Looked in `$DIR` instead of the reports folder | Reports live in `~/Downloads/kinsta-logs/reports/`, named `report_{site_name}_{env_name}_{YYYYMMDDHHMM}.md` — check `analyze_logs.py`'s printed `📄` line for the exact path |
| Analyst Commentary vanished after a later run | `analyze_logs.py` regenerates the entire report from scratch every run — a manually-appended commentary is not part of that generation and gets silently overwritten | Never re-run the script against real `$DIR` log files whose report is the one being reviewed; use scratch-copied log files (Step 3's warning). If it already happened, re-run Step 3 cleanly, then redo Steps 10–13 in the same batch of work |
| Report shows "unknown"/"no PTR record" everywhere | `--no-geoip` was passed, or `ipinfo.io` is failing/rate-limiting broadly | Check the top-of-report banner — it states which case applies. Re-run without `--no-geoip`, or wait and retry if ipinfo.io is down |
| PDF export fails/skipped | Quarto not found (typst engine), or Chromium missing (chromium engine), or npx/network unavailable | For typst: install Quarto or set `TYPST_BIN`. For chromium: set `CHROMIUM_BIN` to the correct path. The Markdown report is still valid on its own regardless |
| `verify_urls.py` reports URL mismatch | A URL in the LLM-authored commentary was retyped from memory instead of copy-pasted from a source file — transliterated non-English words (e.g. Russian in Latin script) have no semantic meaning to the LLM, so a retyped URL will almost always have a spelling error | Copy the correct URL from the "Did you mean?" hint in the error output, replace the misspelled one in the report via `sed`, then re-run `verify_urls.py`. Also re-run `--validate` and re-export PDF |

---

## Files

| File | Purpose | Action |
|---|---|---|
| [`scripts/fetch_logs.sh`](scripts/fetch_logs.sh) | Parallel log fetch with per-log retry, pinned `kinsta-mcp` version | **Execute** in Step 2 |
| [`scripts/analyze_logs.py`](scripts/analyze_logs.py) | Log analysis + cross-file correlation, including per-bot URL/IP-concentration ("bursts"), ASN/hosting-provider/reverse-DNS detection, and grouped status codes (local parsing is deterministic; geo-IP/ASN/PTR lookups are not — see `--no-geoip`). **Always regenerates the full report from scratch**, and writes it to `~/Downloads/kinsta-logs/reports/` (not `$DIR`) — see Step 3's scratch-testing warning and the Troubleshooting entry above | **Execute** in Step 3 |
| [`scripts/probe_urls.py`](scripts/probe_urls.py) | Live HTTP probe (status/timing/headers) — a real-time snapshot, not historical. Run twice: baseline (fixed URLs, Step 2) and targeted (dynamic URLs from findings, Step 4) | **Execute** in Steps 2 & 4 |
| [`scripts/verify_urls.py`](scripts/verify_urls.py) | Post-generation mechanical URL verification — diffs every URL in LLM-authored commentary against source files (probe JSON, site-context.md, report data tables). Catches transliteration errors that are invisible to spell-check | **Execute** in Step 13 — mandatory, do not skip |
| [`scripts/tests/test_analyze_logs.py`](scripts/tests/test_analyze_logs.py) | Automated tests for marker emission, report structure, forbidden sections, and --validate pass. Uses fixture data in `tests/fixtures/` | **Execute** after making script changes — `python3 scripts/tests/test_analyze_logs.py` |
| [`scripts/export_pdf.sh`](scripts/export_pdf.sh) | Converts the final Markdown report to PDF via one of two engines: `chromium` (default, md-to-pdf + system Chromium) or `typst` (Quarto pandoc+Typst) | **Execute** in Step 15, after Steps 7–14 are complete |
| [`scripts/report.css`](scripts/report.css) | Sans-serif report stylesheet applied by the `chromium` engine (default) — larger body text (13px), compact tables (11px), professional typography | Used automatically by `export_pdf.sh` |
| [`scripts/send_report_email.py`](scripts/send_report_email.py) | Sends the PDF report as email attachment via SMTP (Gmail by default). Merges non-sensitive fields from [`config/email.json`](config/email.json) (recipients, subject, signature) with SMTP credentials from `~/.config/kinsta-log-analyzer/email.json` | **Execute** in Step 16 (optional), if the user chooses to email the report |
| [`config/email.json`](config/email.json) | Non-sensitive email fields: `from_email`, `to_emails`, `subject`, `body_signature`. Lives in the skill folder; version-controlled | Edit directly to change recipients or subject |
| [`config/email.json.example`](config/email.json.example) | Template for `~/.config/kinsta-log-analyzer/email.json` — SMTP credentials only (`smtp_host`, `smtp_port`, `username`, `password`). Not version-controlled | Copy to `~/.config/kinsta-log-analyzer/email.json` and fill in credentials |
| [`references/site-context.md`](references/site-context.md) | Admin/business-owner timezones, each site's confirmed primary market, and the fixed "Known Probe URLs" list per site — a living cache, update it when the user confirms new context | **Read** in Steps 1 & 2; **update** via `apply_diff` when new context is learned |
| [`references/bot-taxonomy.md`](references/bot-taxonomy.md) | Accurate, unbiased per-bot reference: real nature (crawler vs. on-demand agent), robots.txt/Crawl-Delay compliance matrix, Kinsta/WordPress-generic mitigation tiers (no hosted-app code involved — see Step 8), and the ASN-vs-reverse-DNS distinction | **Read in full** in Step 7 before writing any bot-related recommendation |
| [`references/report-structure.md`](references/report-structure.md) | Authoritative contract: defines every section heading, format, conditional display rule, marker inventory, and permanently suppressed sections for the generated report | **Read** in Step 10 before filling any markers |
| [`references/conciseness-directives.md`](references/conciseness-directives.md) | 14 mandatory conciseness & consistency rules governing report formatting, tone, citation, and domain-specific judgment. Several are grep-auditable | **Read in full** in Step 6 before writing any report commentary |
| [`references/kinsta-api.md`](references/kinsta-api.md) | Kinsta API constraints: line-based retrieval, log rotation, line-count estimates, and the origin-vs-edge-cache scope distinction | **Read** before Step 2 (log fetching) and when interpreting cache HIT rates |
| [`references/operational-playbook.md`](references/operational-playbook.md) | Expert server guidance for each anomaly type (cache, errors, response time, traffic spikes, SSL) | **Read** when the report flags an issue needing deeper action |
| [`references/kinsta-tribal-knowledge.md`](references/kinsta-tribal-knowledge.md) | Platform behaviors confirmed by Kinsta support (Nginx capabilities/limitations, cache architecture, Bot Protection mechanisms, default behaviors) — facts not in the public KB | **Read** in Step 7 when forming Nginx/rate-limit/cache/bot action recommendations |
| [`references/kinsta-history.md`](references/kinsta-history.md) | Chronological log of actions already taken via Kinsta support per site — prevents re-recommending past actions | **Read** in Step 7 before finalizing any action recommendation; **update** via `apply_diff` when new actions are taken |

## Configuration
Reads credentials from `.roo/mcp.json` → `mcpServers.kinsta.env`. Kinsta Knowledge Base lookups
(Step 8) use the `tavily` MCP server (`tavily-search`), also configured in `.roo/mcp.json`.
PDF export (Step 15) supports two engines: `chromium` (default, md-to-pdf + system Chromium at `/usr/bin/chromium`, best visual design, A4)
and `typst` (Quarto pandoc+Typst, no extra deps). Switch with `--engine`.

## Privacy & Retention
- Visitor IPs from the access/error logs are written to disk under `~/Downloads/kinsta-logs/` and are not automatically cleaned up — periodically prune old log/report files if this is a concern.
- Unless `--no-geoip` is passed, visitor IPs are also sent to the third-party `ipinfo.io` service up to three times per unique IP — country lookup, ASN/organization lookup (`ip_org()`), and reverse-DNS/PTR lookup (`ip_hostname()`) — during Step 3.
- Both probe passes (Step 2's baseline, Step 4's targeted) send real HTTP requests to the site being analyzed (and only that site — never a third party) from wherever this skill runs; this generates a handful of extra hits in the site's own logs at probe time, self-identified via a distinctive User-Agent (`Kinsta-Log-Analyzer-Probe`) so future analysis runs recognize this as this skill's own traffic, not an unknown visitor.
- The generated report (and its PDF) embeds raw visitor IPs and is opened in VS Code; treat it like any other file containing visitor data.
- Step 8's Kinsta KB lookups send search queries (not visitor data) to `tavily-search`.

## Output Structure
```
~/Downloads/kinsta-logs/
├── {site_name}/
│   └── {env_name}/
│       ├── {YYYY-MM-DD_HHMMSS}_error.json
│       ├── {YYYY-MM-DD_HHMMSS}_access.json
│       ├── {YYYY-MM-DD_HHMMSS}_cache.json
│       ├── {YYYY-MM-DD_HHMMSS}_probe_baseline.json
│       └── {YYYY-MM-DD_HHMMSS}_probe_targeted.json
└── reports/
    ├── report_{site_name}_{env_name}_{YYYYMMDDHHMM}.md
    └── report_{site_name}_{env_name}_{YYYYMMDDHHMM}.pdf
```
Raw per-run logs/probes stay nested under `{site_name}/{env_name}/`; every generated report (and
its PDF) lands in a single flat `reports/` folder, since the filename itself already encodes
site, environment, and timestamp.
