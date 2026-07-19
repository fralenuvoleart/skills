---
name: kinsta-logs
description: Fetch Kinsta server logs (error, access, cache-perf) via the Kinsta MCP API, save them to ~/Downloads/kinsta-logs/, analyze website traffic patterns, operational health (cache HIT/MISS ratios, bot activity, response times, error rates), and present a structured severity-ranked findings report with operational recommendations. This skill is about website operations & traffic analysis — not code debugging. Use when the user asks to "analyze Kinsta logs", "check server logs", "debug Kinsta site errors", or "review cache performance".
---

# Kinsta Log Analyzer

## 🚨 ALL DIRECTIVES IN THIS SKILL MUST BE FOLLOWED LITERALLY. "LITERALLY" MEANS EXACTLY AS WRITTEN — NO INTERPRETATION, NO APPROXIMATION, NO "CLOSE ENOUGH."

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

The output is not a raw data dump — it's **an insightful, narrative report meant to be presented
to management**, structured to (a) let a non-technical reader grasp site health in under a minute
via "At a Glance," and (b) guide **specific, informed corrective action** for each finding, sourced
from Kinsta's own current documentation, not generic hosting advice. Every section below exists in
service of this: the script's raw tables are the evidence; the Analyst Commentary (Step 6) is where
that evidence becomes a narrative a business owner can act on without needing to interpret a table
themselves. **Never recommend an action by referencing this skill's own host codebase** (file
paths, function/constant names, config files of the WordPress plugin being hosted) — the report's
reader manages *infrastructure*, not this repo. Every action must be something doable from the
MyKinsta panel or sourced from an actual Kinsta KB article (cited in Step 6.6); if no such action
exists for a finding, say so plainly rather than inventing a code-level fix.

---

## How Logs Are Retrieved

The Kinsta API (`kinsta.logs.get`) is **line-based, not time-based**:

| Parameter | Required | Default | Description |
|---|---|---|---|
| `env_id` | Yes | — | Environment UUID |
| `file_name` | No | (all 3 fetched) | `error`, `access`, or `kinsta-cache-perf` |
| `lines` | No | 1000 (error), 3000 (access), 1000 (cache) | Most recent lines from each log |
| `--hours` (script) | No | **24** | Filter report to last N hours. Pass `--hours 3`, `--hours 72`, etc. |

- **No time-window filtering** — the API always returns the last N lines
- 1000 error lines ≈ 1–3 days; 1000 access lines ≈ 3–5 hours (access is much denser)
- To get better access/error log overlap, use **`"lines":3000`** for the access log (~12–15 hours coverage)
- The Kinsta API has **no offset/pagination** — just pass a higher `lines` value directly
- **The API hard-caps `lines` at 20,000** — a request above that fails with `VALIDATION_ERROR:
  Number must be less than or equal to 20000`. This is the true ceiling on how far back any single
  fetch can reach, regardless of the site's traffic volume.
- The `file_name` parameter accepts bare names (`error`) — do NOT append `.log` suffix
- **Kinsta rotates `access.log` roughly daily** (confirmed: rotated filenames follow
  `access.log-YYYY-MM-DD-<unix-timestamp>`) — but `kinsta.logs.get` transparently spans rotation
  boundaries when `lines` exceeds the current unrotated file's size, so a normal fetch does not
  need manual rotation-file handling.
- **`access.log` is origin-server traffic only — confirmed (do not re-derive this each run): it does
  not include requests Cloudflare's edge cache served without ever reaching Kinsta's origin server**
  (300+ global PoPs — see Kinsta's own [Edge Caching docs](https://kinsta.com/docs/wordpress-hosting/caching/edge-caching)).
  **This was verified against a site's actual downloaded rotated log files** — re-fetching at the
  20,000-line ceiling and manually reconstructing the same 24h window from raw files both agreed
  with the original fetch to within 6 requests, ruling out sampling/truncation as the cause of any
  gap. **Do not default to a "the dashboard's date range must be longer than 24h" explanation
  without the user confirming their dashboard's window** — a same-order-of-magnitude coincidence in
  a multi-day total is not evidence of anything; always ask/confirm the dashboard's actual reported
  window before proposing a time-window mismatch, and prefer the origin-vs-edge-cache explanation as
  the primary hypothesis when the dashboard figure is confirmed to be a genuine 24h count (one HTML
  request can carry dozens of edge-cached sub-resource requests MyKinsta's Analytics counts but
  `access.log` never sees). State this origin-vs-edge scope distinction explicitly in the report's
  Traffic Overview section whenever the user cites a higher dashboard number for the same window.
- **`kinsta-cache-perf` log data is pulled from Cloudflare logs for the site.** ~85% of all requests
  are served by Cloudflare's Edge cache and never reach Nginx. Only ~15% pass through Cloudflare to
  Nginx — broken down as dynamic (~13.5%), miss (~1%), and bypass (~0.5%). Nginx handles page
  caching for these remaining 15%, and the `kinsta-cache-perf` log's HIT/MISS/BYPASS data represents
  the cache status for this subset only — not total site traffic. When interpreting cache HIT rates
  from this log, remember: a 60% HIT rate here means 60% of 15% = ~9% of total traffic got an
  Nginx page-cache HIT, on top of the ~85% already served by Cloudflare's edge cache (combined
  ~94% of all requests served from cache).

---

## Workflow

### Step 1: Discover Sites & Environments

> ⚠️ **CRITICAL: NEVER use `mcp--kinsta--*` tool functions.** Roo Code strips dots from the tool names (e.g. `mcp--kinsta--kinstasiteslist` → `kinstasiteslist`), which causes a "Tool does not exist" error every time. **Always use `execute_command` with JSON-RPC via stdio instead** — pipe the JSON-RPC request into `npx -y kinsta-mcp@1.0.3`. This applies to EVERY Kinsta API call in this skill (Steps 1, 2, 3, and any ad-hoc lookups). The `scripts/fetch_logs.sh` script already does this internally; the only manual `execute_command` you need is the site/environment discovery call below.

1. Read `.roo/mcp.json` for `KINSTA_API_KEY` and `KINSTA_COMPANY_ID`.
2. Discover sites via JSON-RPC (`execute_command`, not `mcp--kinsta--*`):

   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"kinsta.sites.list","arguments":{"include_environments":true}}}' | KINSTA_API_KEY="..." KINSTA_COMPANY_ID="..." npx -y kinsta-mcp@1.0.3 2>/dev/null
   ```
3. **If the user specified a site name**, extract the site ID and live environment ID from the JSON output.
4. **If no site specified**:
   - Check conversation history for a previously analyzed site — reuse it.
   - **Default site: `pbservices.ge`.** If no conversation history exists and the user didn't specify a site, analyze pbservices.ge without asking. Announce it briefly: "Analyzing pbservices.ge (default site)."
   - Only ask which site if the user explicitly requests a different site or if conversation history points to a different site.
5. Default to the **live** environment. Read [`references/site-context.md`](references/site-context.md) — required context for interpreting traffic-hour patterns and geo-IP results. If the site has an `unknown — ask` entry, ask once via `ask_followup_question`, then persist the answer via `apply_diff`.
5. **Read [`references/site-context.md`](references/site-context.md)** — it records the admin's
   and business owner's timezones and each site's confirmed primary visitor market. This is
   required context for interpreting traffic-hour patterns and geo-IP results correctly in Step 6;
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

2. **At the same time** (a separate tool call, not sequentially blocking on step 1), **execute**
   [`scripts/probe_urls.py`](scripts/probe_urls.py) against the fixed sample URL list from
   [`references/site-context.md`](references/site-context.md) → "Known Probe URLs" for this site.

   > 🚫 **CRITICAL — URLs MUST be extracted mechanically from `site-context.md`, NEVER retyped.**
   > Transliterated URLs (Russian→Latin, Arabic→Latin, Chinese→Pinyin) are impossible to spell
   > correctly from memory. Retyping a URL in the probe command WILL introduce a spelling error
   > that makes the probe hit the wrong page, producing false 404 findings. Use the grep/sed
   > extraction below — it reads the URLs directly from the source file without human re-typing.
   
   **Step 2a — Extract URLs mechanically from site-context.md:**
   ```bash
   SITE_CONTEXT=".agents/skills/kinsta-logs/references/site-context.md"
   # Extract the probe URL block for this site (between "### SITENAME" and the next "###" or "##")
   PROBE_URLS=$(sed -n '/### pbservices\.ge/,/^### \|^## /p' "$SITE_CONTEXT" | grep '^https://' | tr '\n' ' ')
   echo "Probe URLs: $PROBE_URLS"  # verify before running
   ```

   **Step 2b — Execute the probe using the extracted URLs:**
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/probe_urls.py \
     --output "$DIR/${TS}_probe_baseline.json" \
     $PROBE_URLS
   ```
   
   > The `$PROBE_URLS` variable contains the exact URLs from `site-context.md`, space-separated,
   > extracted by `sed`/`grep` with zero human re-typing. The `echo` line lets you verify the
   > extracted URLs before the probe runs.

**Fetch strategy** (implemented by the script, run in parallel):

| Priority | Log | Lines | Retries | Why |
|---|---|---|---|---|
| 1 | `error` | 1000 | 1 | ~1–3 days of error coverage |
| 2 | `access` | 3000 | 1 | ~12–15 hours, overlaps with error log for cross-analysis |
| 3 | `kinsta-cache-perf` | 1000 | **3** (flaky endpoint) | Cache HIT/MISS/BYPASS data |

**Why batch the access log**: 1000 access lines ≈ 3–5 hours, but the error log spans days. Batching 3000 access lines covers 12–15 hours, giving meaningful overlap for cross-file analysis.

**Retry logic**: If cache-perf fails with `NETWORK_ERROR`, the script retries with a 3s sleep between attempts, up to 3 times, then proceeds without it — check stderr output for `[FAILED]` lines.

**Package pinning**: the script pins `kinsta-mcp@1.0.3` rather than running unpinned `npx -y kinsta-mcp`, so behavior doesn't silently change between runs when a new version publishes.

**Credential note**: passing `KINSTA_API_KEY`/`KINSTA_COMPANY_ID` inline on the command line can leak secrets via shell history or `ps aux`. Prefer exporting them in the current shell session (`export KINSTA_API_KEY=...`) rather than prefixing the command, when running interactively.

### Step 3: Analyze
Run the bundled script. **Default: last 24 hours.** Add `--hours N` for other windows. The script
prints the generated report's path on its last line (`📄 <path>`) — capture it as `$REPORT_PATH`,
since Steps 4/6/7/8 all reference the report by that path, not by `$DIR`:
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

**Execute** [`scripts/probe_urls.py`](scripts/probe_urls.py) again — this second pass probes only
the URLs that Step 3's analysis actually flagged, since those can't be known before analysis runs
(unlike Step 2's fixed baseline probe). Both probe passes are real-time snapshots of right now, not
the log window, and Step 6 must state that distinction explicitly whenever it cites either one.

> 🚫 **Same mechanical-extraction rule as Step 2 applies here — URLs come from the report file,
> not from memory.** Use `grep`/`sed` on `$REPORT_PATH` to extract URLs, then pass the extracted
> values to the probe command. Never type a URL that you read from the report.

1. **Extract target URLs mechanically from `$REPORT_PATH`** — do NOT retype them:
   ```bash
   # Extract from the report's data tables (NOT from memory):
   MISS_URL=$(grep -A1 'Pages Most Frequently Missing Cache' "$REPORT_PATH" | grep '^|' | head -1 | sed 's/.*`\([^`]*\)`.*/\1/')
   # Slowest public page (skip /wp-admin/ entries — they require auth):
   SLOW_URL=$(grep 'Slowest individual requests' "$REPORT_PATH" -A10 | grep '^|' | grep -v 'wp-admin' | head -1 | sed 's/.*`\([^`]*\)`.*/\1/')
   # Top 404 URL (skip obvious spam-injection payloads):
   ERR_URL=$(grep -A10 '404.*requests from' "$REPORT_PATH" | grep '^|' | head -1 | sed 's/.*`\([^`]*\)`.*/\1/')
   echo "Target URLs: MISS=$MISS_URL  SLOW=$SLOW_URL  ERR=$ERR_URL"
   ```

2. **Build the probe command using the extracted variables** — never type URLs inline:
   ```bash
   python3 .agents/skills/kinsta-logs/scripts/probe_urls.py \
     --output "$DIR/${TS}_probe_targeted.json" \
     "https://SITE_DOMAIN${MISS_URL}" \
     "https://SITE_DOMAIN${SLOW_URL}" \
     "https://SITE_DOMAIN${ERR_URL}"
   ```
   Replace `SITE_DOMAIN` with the actual site domain (e.g. `pbservices.ge`).
3. **Read both probe JSON files** (`_probe_baseline.json` from Step 2 and `_probe_targeted.json`
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
will fill in Step 6.

### Step 6: Analyst Commentary & Report Assembly (Critical Reasoning)

**This is LLM reasoning, not automated — every analysis is unique.** This is also the step users
judge the skill's expertise on — mediocre, generic advice here (e.g. "add Crawl-Delay for AI bots,"
"block Chinese bots because they're Chinese") is a failure of this step, not an acceptable
approximation. The script has generated a two-part skeleton with `<!-- LLM: -->` markers. You MUST:

1. **Read the generated skeleton** (`read_file` on the `*_report.md`) and both probe JSON files —
   `_probe_baseline.json` from Step 2 and `_probe_targeted.json` from Step 4.

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

6b. **Consult [`references/kinsta-tribal-knowledge.md`](references/kinsta-tribal-knowledge.md) for
    platform behaviors relevant to the finding.** Not all actionable facts are in the public KB —
    support transcripts have confirmed default behaviors (xmlrpc blocked, wp-login 6 req/min),
    Nginx capability boundaries (no POST body inspection, no URL-decoding), cache-clearing side
    effects (Clear All purges Redis), and Bot Protection mechanisms (CF ML scoring 1-99) that
    directly inform accurate "Actions" recommendations. When a finding involves Nginx rule
    suggestions, rate limiting, cache operations, or bot protection configuration, check this
    reference for platform constraints and defaults before writing the recommendation.

6c. **Consult [`references/kinsta-history.md`](references/kinsta-history.md) to avoid
    re-recommending past actions.** For each finding, check whether a past action already
    addresses it. If a match is found, acknowledge it in the Actions line: cite the past action,
    its date, and whether log evidence confirms it's still effective or suggests it needs
    re-verification. If no past action matches, proceed to form a new recommendation normally.

6d. **Always append the Kinsta Live Support Chat entry at the end of KB References.**
    After filling the `<!-- LLM:KB_REFERENCES -->` marker with KB article links, ALWAYS append
    as the final bullet:

    ```
    - **Kinsta Live Support Chat** — The report integrates additional insider knowledge and history
      of past actions, from the Kinsta Support Chat History.
    ```

    This applies even when no KB articles were cited — the Live Support Chat entry is always
    present. See [`references/report-structure.md`](references/report-structure.md) §
    `## 📚 Kinsta KB References` for the contract.

7. **Structure every finding around four questions internally — What / Why / Who / How** — this is
   the analytical spine you use to REASON through each finding, but it is not what the reader sees.
   The **visible labels in the report are always Event / Analysis / Source / Actions** (Step 6.8
   spells out the exact template) — "What/Why/Who/How" is your private checklist, never printed:

   | Internal question | Visible label | Answers |
   |---|---|---|
   | What? | **Event** | The flagged finding, stated with its exact evidence (numbers, URLs, IPs). |
   | Why? | **Analysis** | Why it's suspicious or anomalous — cross-referencing bot-taxonomy.md/site-context.md/probe results as applicable. Ordinary/expected activity gets "why this is NOT an anomaly" instead. |
   | Who? | **Source** | The source (bot name, IP, or "unknown") PLUS an explicit classification tier — see Step 6.8's tier scale — never just prose judgment. |
   | How? | **Actions** | The concrete action, sourced from live Kinsta KB documentation (Step 6.6/6.6b/6.6c), a MyKinsta-panel step, or **bold "No action required ✅"** on its own line (description on new indented line) — never a canned tip disconnected from this finding's actual evidence, and never anything derived from reading the hosted app's own source code (Step 6.5 forbids opening it at all). |

   Cross-cutting lenses to apply this framework to: attack patterns (spam injection, xmlrpc
   probing), traffic anomalies (hour spikes — state the multiplier, convert to local time per Step
   6.3), bot strategy (per bot-taxonomy.md), cache root cause (cite top-missed URLs/query
   params/probe header evidence), 404/error triage, and IP/geo sanity (hosting/proxy flags).

8. **Fill the `<!-- LLM: -->` markers in the script-generated skeleton.** The `analyze_logs.py`
   script now emits a two-part report skeleton with `<!-- LLM: -->` markers where analyst-written
   content belongs. **Do NOT append commentary — fill the markers.** The script owns structure;
   you own content and narrative.

   **Workflow:**
   1. Read the ENTIRE skeleton — all auto-gen data tables, all `<!-- LLM: -->` markers, all section headings — before writing anything.
   2. Identify the dominant narrative: what ONE finding defines this run? (Cache failure? Bot surge? Security incident?)
   3. Order Part 1 sections by severity: 🔴 > 🟡 > 🔧 > ✅. Within same tier, order by impact magnitude. The script puts markers in a default order; you MUST reorder Part 1 sections so the most important finding leads.
   4. Fill each `<!-- LLM: -->` marker with content. Use `apply_diff` to replace `<!-- LLM:MARKER_NAME -->` with the actual section content.
   5. After filling all markers, inject a **Verdict** column into every auto-generated bot table in Part 2. **Use `sed` for this — do NOT use `apply_diff`.** The `apply_diff` approach for Part 2 tables is unreliable because line numbers shift significantly after Part 1 commentary is filled in. The `sed` one-liner is deterministic and always works:

      ```bash
      sed -i 's/| Bytespider | \(.*\) | ⏳ \*pending\* |/| Bytespider | \1 | 🔧 Block |/' "$REPORT_PATH"
      sed -i 's/| Kinsta-Log-Analyzer-Probe | \(.*\) | ⏳ \*pending\* |/| Kinsta-Log-Analyzer-Probe | \1 | ✅ Self |/' "$REPORT_PATH"
      sed -i 's/| ⏳ \*pending\* |/| ✅ Keep |/g' "$REPORT_PATH"
      ```

      Run these three commands in order (Bytespider and Kinsta-Log-Analyzer-Probe first, then the catch-all fallback). If the Bot Strategy table assigned any other non-`Keep` verdict, add additional targeted `sed` lines for those bots before the catch-all. Verify with `grep -c '⏳' "$REPORT_PATH"` — result must be `0`.

   **Section format rules:**

   Use a **finding-card format** for the Traffic Anomalies, Attack/Security Findings,
   and Concentrated Bursts subsections specifically — freeform prose paragraphs are not acceptable
   there. **Each of Event/Analysis/Source/Actions MUST be its own bullet list item** (not
   consecutive bold-label lines in one paragraph) — list items are the only Markdown construct
   guaranteed to render on separate lines across every renderer; runs of `**Label:** text` lines
   without blank lines between them visually collapse into one paragraph in several renderers,
   which was the primary readability complaint against earlier versions of this skill's output.

   **Tone calibration — avoid both extremes, every time.** This has been a repeated failure mode
   in both directions and must be checked explicitly before finalizing any Overall Assessment,
   At a Glance status line, or card verdict:
   - **Too alarmist:** dressing up routine housekeeping (a stale cache entry, a low-value crawler,
     a missing trailing slash) in emergency language, or a severity icon one tier higher than the
     evidence supports (see the icon table below — 🔴 is reserved, not a default).
   - **Too dismissive:** the opposite failure, and equally wrong — waving away a real, measurable,
     currently-below-target metric (e.g. a cache HIT rate sitting at 24–46% against a >50% target)
     with casual language like "minor housekeeping, nothing urgent" or "nothing to see here." A
     below-target metric with a concrete, evidence-backed fix is a genuine 🟡 finding worth an
     accurate, specific description — not a shrug.
   - **The correct register:** state the actual measured severity in plain, professional, objective
     terms, exactly as supported by the evidence — no more, no less. "Cache HIT rate is 24%, well
     below the >50% target, driven by two identified causes — fixable, but currently costing real
     performance" is calibrated. "Nothing urgent" is not, when a metric is sitting at a third of
     target.
   - **Avoid cheerleading-style status openers even when a real caveat follows** — e.g. "Overall
     status: healthy and secure, with one issue worth fixing" still reads as dismissive by leading
     with reassurance before the finding. Prefer a neutral, factual lead: **"No active security
     incidents; [metric] is below target and requires attention"** — state what was and wasn't
     found, in that order, without an adjective doing the reader's judgment for them.
   - **Never use evaluative/judgment-laden labels — state measured severity, not a verdict on
     merit.** Words like "worst"/"best"/"terrible"/"great" attach a value judgment the underlying
     data doesn't actually support (severity icons are threshold-derived facts; "worst" implies a
     ranked comparison the report never actually computed). Use objective, measured language
     instead: "highest-severity finding" not "the worst finding"; "the metric furthest below
     target" not "the worst metric." This applies everywhere a finding is singled out — At a
     Glance headlines, card titles, and the Convergent Cross-Signals summary alike.
   - Re-read every summary line against this test before finalizing: *would someone who only reads
     this one sentence come away with an accurate impression of how serious this actually is — not
     more dramatic, not more reassuring, and not a value judgment dressed up as a measurement?*

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
   - **Actions:** [concrete action per Steps 6.6/6.6b, or:
       - **No action required** ✅
         [description/explanation on new indented line]]
   ```

   **Conciseness & Consistency Directives (mandatory, self-auditable — apply before finalizing
   any report).** These generalize five recurring review findings into permanent rules, not a
   one-off fix — check every future report against all five, every run:

   1. **The headline's overall icon is a human-judgment call, answering ONE question: is there
      a genuine emergency, or just minor flags, or is everything clean?** Not a formula, not a
      mechanical max()/sum() over the component table — a judgment about the actual underlying
      facts:
      - 🔴 **Overall** = at least one component represents a genuine, active emergency exactly
        as the icon vocabulary above defines 🔴 (site down, active security breach, data at
        risk) — not merely "a metric missed its numeric target."
      - 🟡 **Overall** = no genuine emergency exists anywhere, but one or more components have
        a real flag (🟡/🔧) worth attention.
      - ✅ **Overall** = every component is clean, no flags at all.
      **This means a component's own icon must itself be correctly classified first** — the
      root cause of an earlier, repeated mistake here was assigning 🔴 to a cache HIT-rate
      miss (a performance/config target-miss, capped at 🟡 per the icon vocabulary — never 🔴,
      no matter how far below target the number is) and then mechanically propagating that
      wrong 🔴 upward. Fix the component's classification first; the overall judgment call
      above only works when every input into it is already correct.
   2. **Collapse any table where >70% of rows share the identical verdict/value into a summary
      line + itemized outliers only.** Applies to the Bot Traffic Strategy table and any
      similarly-shaped per-item table: if 10+ items all resolve to `✅ Keep`/`no action`, write
      one line — `"✅ Keep (N bots, no action needed — see Part 2 for the full list)"` — and
      itemize ONLY the rows with a non-default verdict (Block/Monitor/Throttle/etc.). Never print
      a long column of repeated identical icons; repetition without variation is noise, not
      evidence.
   3. **Explain a mechanism once; every subsequent reference cites it by name, never re-explains
      it.** When a root cause (e.g. a specific cookie, a specific redirect chain) is described in
      full in one card, every other card that's affected by the same mechanism must reference it
      by a short name (`"the `__cf_bm` cache-block described above"`) — not restate the
      mechanism's how/why again. If you catch yourself writing the same 2+ sentence explanation
      in a second card, delete it and cite instead.
   4. **Every Part 1 `###` subsection carries a status marker in its first line — no exceptions.**
      A subsection with no finding still needs a marker: a leading ✅/ℹ️. Never let one
      subsection break the visual pattern the reader has learned from its siblings.
   5. **Wide tables (5+ columns) get a plain-language one-line takeaway directly above them,
      before rendering the table.** Any table with 5 or more columns (e.g. the per-category bot
      tables with the Verdict column) must be preceded by one sentence stating the actual
      conclusion (`"14 of 15 bots need no action; only Bytespider should be blocked — see
      table for detail."`) so a skimming reader gets the answer without parsing the grid.
   6. **Never use `~` (tilde) for approximation in report content.** Some Markdown renderers
      (including Typst, used by pandoc for PDF export) interpret `~` as a strikethrough
      delimiter, causing text between two tildes to render with a line through it. Use `≈` or
      "approximately" instead. Example: write `≈85%` or "approximately 85%", never `~85%`.
      This applies to the At a Glance Scope note and any other LLM-written
      content — check every occurrence of `~` before finalizing.
   7. **NEVER retype or transliterate URLs — always copy-paste them exactly from the source.**
      URLs contain non-English characters transliterated into ASCII (e.g. Russian words written
      in Latin script like `individualnyj-predprinematel`). When you retype a URL from memory
      or sight, you WILL introduce spelling errors (missing letters, swapped vowels) that are
      invisible to spell-check because the words are transliterations, not real English words.
      This rule applies everywhere URLs appear: probe commands, report commentary, card
      findings, KB references. **Copy from the probe JSON output, the report's own data tables,
      or `site-context.md` — never retype.** Before finalizing the report, grep for any URL
      you wrote and diff it against the source it came from.
   8. **At a Glance: bold only key words and numbers, never entire paragraphs.**
      Bold formatting draws the eye — when an entire paragraph is bold, nothing stands out and
      the visual hierarchy collapses. Use bold sparingly on the most critical words, numbers,
      and verdict terms within each sentence. The At a Glance section's purpose is scanability;
      a wall of bold text defeats that purpose. Example: "Cache HIT at **32%** in a
      **post-midnight cold-start window** — daytime rate not assessable. **No security
      incidents.**"
   9. **At a Glance: never flag cache HIT rate as "below target" when the cache-perf window is
      a short post-midnight cold-start period.**
      Kinsta purges the server page cache every 24 hours at approximately midnight UTC. A
      cache-perf log covering only the post-purge window (e.g., 22:33–01:00 UTC, ≈2.5 hours)
      will always show a low HIT rate because the cache is cold — this is expected platform
      behavior, not a configuration defect. In such windows, describe the cache state factually
      (e.g., "Cache HIT at **32%** — expected for this post-midnight cold-start window; daytime
      rate not assessable from this data") rather than as a "below target" finding. Only flag
      cache HIT as a genuine 🟡 concern when the cache-perf window spans ≥6 hours of daytime
      traffic (e.g., 09:00–21:00 UTC) where a cold-start excuse no longer applies.
   10. **Cache cold-start mechanism: explain once in Cache Root Cause Analysis, cite by name
       everywhere else.**
       The midnight-UTC cache purge and its effect on HIT rates is a single root cause. Describe
       it in full ONLY in the Cache Root Cause Analysis card (Primary Root Cause). Every other
       section that references the cache HIT rate (Overall Assessment, At a Glance, Traffic
       Anomalies) must cite it by a short reference — `"(see Cache Root Cause Analysis for the
       cold-start window explanation)"` or `"as noted in Cache Root Cause"` — and NEVER
       re-explain the purge mechanism, timing, or expected behavior. This is a specific,
       high-frequency application of Directive 3 (explain once, cite thereafter) that has been
       repeatedly violated in past runs.
   11. **Bold key metrics selectively within prose paragraphs.**
       When a paragraph contains several numbers, bold the 1–2 most significant metrics to
       create visual waypoints for a scanning reader. Never bold every number in a paragraph —
       that produces the same uniformity problem as bolding entire paragraphs. Choose the
       numbers that carry the most diagnostic weight (e.g., the HIT rate percentage, the error
       count, the bot request volume) and bold only those. Example: "Cache HIT at **32%** (208
       of 657 entries), BYPASS **40%** (265 entries), MISS 28% (184 entries)."
   12. **Bytespider: never default to "Monitor" without stating the site's ZH-content relevance
       explicitly.**
       Bytespider is ByteDance's crawler for Doubao (China's #1 consumer AI search engine). Per
       `bot-taxonomy.md`, the verdict is case-by-case based on whether the site has
       Chinese-language content (`/zh/`). If the site has ZH content, Bytespider is expected
       search-engine traffic — state this explicitly and assign `✅ Keep`, not `👀 Monitor`. If
       the site has no ZH content, state that explicitly as the reason for any non-Keep verdict.
       Never write "Monitor Bytespider volume" as a vague, unexplained recommendation — always
       answer: does this site target a Chinese-speaking audience, and is the volume
       proportionate? A site without ZH content receiving moderate Bytespider volume is normal
       internet background radiation, not a finding.
   13. **403 spam-block rules: only recommend adding new rules when new spam patterns appear in
       the error log.**
       When existing Nginx keyword blocks (e.g., `yinlang388`, `388ym.com`) are confirmed
       working by log evidence (spam requests return 403 as intended), do NOT recommend "verify
       the rules are still current" or "review error log monthly for new patterns" as an action
       — the rules are already verified by the data in front of you. The only actionable
       recommendation for 403 spam-block rules is: "Add Nginx keyword block for [new spam
       domain/pattern]" when a NEW spam pattern is observed in the error log that is not already
       covered by existing rules. If no new patterns are observed, state `✅ Existing Nginx
       spam-block rules are working as intended — no new patterns detected.` and move on.


   **Full section structure — see [`references/report-structure.md`](references/report-structure.md) for the authoritative contract.** The summary below is a quick reference; the contract file defines exact formats, conditional display rules, and the marker inventory.

   The report has two parts with a hard visual divider:

   ```
   # PART 1: SUMMARY & FINDINGS
   ```
   (a real `# ` heading, not decorative dashes — a fixed-width Unicode-line divider wraps
   unpredictably across different viewport/page widths in VS Code, browser preview, and PDF;
   a heading just wraps its words like any other heading)
   
   **Part 1 sections** (LLM orders by severity: 🔴 > 🟡 > 🔧 > ✅; within same tier by impact magnitude):

   - **Overall Assessment** (`<!-- LLM:OVERALL_ASSESSMENT -->`) — severity-icon verdict line + 5-row summary table (Security / Stability / Cache / Bot traffic / Slow pages) with a slightly wider Status&nbsp;&nbsp; column. Never a dense prose paragraph. ⚠️ **D9:** If cache-perf window <6h daytime, don't call HIT rate "below target." **D10:** Reference cache cold-start by name only — full explanation lives in Cache Root Cause.
   - **🎯 Convergent Cross-Signals** — script-authored, deterministic (NOT an LLM marker). A set-intersection across the report's own notable-URL lists (top cache-MISSed pages, burst targets, top 403/404 error URLs); a URL in 2+ lists is named as the single highest-priority fix target with combined evidence cited. Excludes `Kinsta-Log-Analyzer-Probe` traffic (self-generated, not a real finding). Always present — states the overlap or states plainly that none was found. Positioned right after Overall Assessment, before every individual finding card, since its purpose is to reprioritize what follows before the reader reaches it.
   - **Attack/Security Findings** (`<!-- LLM:ATTACK_SECURITY -->`) — Event/Analysis/Source/Actions card format, one card per distinct pattern. If none: single `#### ✅ No security incidents` card. ⚠️ **D13:** 403 spam-blocks confirmed working → `✅ Existing rules working`. Only recommend new rules when new spam patterns appear. Never say "verify rules are still current."
   - **Cache Root Cause Analysis** (`<!-- LLM:CACHE_ROOT_CAUSE -->`) — sub-headed cards (`#### 🔴 Primary Root Cause`, `#### 🟡 Secondary Contributor`). Evidence-cited from both probe passes. If cache is healthy: `✅ Cache HIT rate at or above target.` ⚠️ **D10: THIS is the ONE AND ONLY place where the midnight-UTC cache purge mechanism gets a full explanation.** Every other section references it by short name only (e.g., `"post-midnight cold-start window (see Cache Root Cause)"`). If you write the purge timing/behavior explanation in any other section, you have violated this rule.
   - **Bot Traffic Strategy** (`<!-- LLM:BOT_STRATEGY -->`) — table (bot | requests | % | verdict | evidence) with Totals row. Per Conciseness Directive 2, if >70% of bots resolve to the same verdict, collapse them into one summary row (`"✅ Keep (N bots, no action — see Part 2 for the full list)"`) and itemize only the outliers (Block/Monitor/Throttle). **Note:** Directive 2 applies to THIS Part 1 table only — the auto-generated per-category bot tables in Part 2 are the full evidence appendix and must list every bot individually; do not collapse those. After writing the Part 1 table, inject a **Verdict** column into every auto-generated bot table in Part 2 using the exact verdict from this Strategy table (`✅ Keep` / `🔧 Block` / `👀 Monitor` / `🔧 Throttle`). ⚠️ **D5:** Precede table with one-line takeaway. **D12:** Bytespider verdict MUST state whether site has ZH content — if yes → `✅ Keep` (Doubao, China's #1 search engine); if no → state reason explicitly, never default to vague `👀 Monitor`.
   - **Concentrated Traffic Spikes & Bursts** (`<!-- LLM:BURST_CARDS -->`) — Event/Analysis/Source/Actions card format. Use 🔧 unless active attack. Name source IP/bot and target URL(s) explicitly. If none: `✅ No concentrated bursts.`
   - **Traffic Anomalies** (`<!-- LLM:TRAFFIC_ANOMALIES -->`) — card format, one per spike/pattern, with admin/owner local-time conversion per `site-context.md`. If none: `✅ Traffic within normal diurnal variation.` ⚠️ **D9:** Don't call cache HIT "anomalous" for cold-start window. **D10:** Cite by name, don't re-explain the purge.
   - **404/Error Fix Recommendations** (`<!-- LLM:ERROR_FIXES -->`) — card format for ALL items regardless of priority. Template:
     ```
     #### 🔧|ℹ️ [Priority] — [Short title]
     - **Event:** [brief description of the 404/error — what URL, what status code, how many hits]
     - **URL(s):** [path(s) and hit count]
     - **Analysis:** [why this 404 exists and whether it matters]
     - **Source:** [IP(s) or bot causing the errors, if identifiable; otherwise "unknown"]
     - **Actions:** [concrete fix, or:
         - **No action required** ✅
           [reason on new indented line]]
     ```
     Low-priority items MAY group into a single `#### ℹ️ Low Priority — Miscellaneous` card with one bullet per item. Never bare bullets without a heading. If none: `✅ No actionable 404s.` ⚠️ **D13:** Only recommend adding new Nginx keyword blocks when new spam patterns appear. Existing working rules → `✅ Existing rules working as intended.`

   ```
   # PART 2: TECHNICAL APPENDIX
   ```

   **Part 2 sections** (script-generated, fixed order — LLM does NOT reorder):

   - `## Performance` — metrics table (avg/min/max response time, slow pages count, 5xx count) and slowest individual requests table. **First section in Part 2.**
   - `## 📊 Cache Performance` — HIT/MISS/BYPASS table, top-MISSed URLs, HIT-vs-MISS response time. "How to Improve" is permanently suppressed.
   - `## 📊 Bot & Crawler Traffic` — per-category tables with a script-emitted **Verdict** column (placeholder `⏳ *pending*`). After writing the Bot Strategy table, overwrite every placeholder with that table's exact verdict. "Scanner IPs — Block List" is permanently suppressed.
   - `## 📊 Top Visitor IPs` — table with geo/ASN/PTR + infrastructure warning.
   - `## Concentrated Traffic Spikes & Bursts` (raw table) — **kept, not suppressed.** This is the evidence source for Part 1's Burst cards; cite it directly, don't duplicate its numbers without attribution.
   - `## Traffic Overview` — Status Codes, `### Errors by Status Code — Drill-Down` (**kept, not suppressed** — evidence source for Part 1's 404/Error Fix cards), Requests per Hour.
   - `## 🔬 Live Probe Cross-Match` (`<!-- LLM:PROBE_CROSS_MATCH -->`) — bullet list of probe findings vs. log-derived analysis.
   - `## 📚 Kinsta KB References` (`<!-- LLM:KB_REFERENCES -->`) — bullet list with URL and one-line guidance summary.

   **Permanently suppressed sections** (script never emits; if they appear, delete them): `## Health Summary`, the "low" tier of `## 🟢 Low-Priority Notes` (critical/medium tiers — real PHP errors — are NOT suppressed), `### How to Improve Cache HIT Rate`, `### Scanner IPs — Block List`, `## Directory Scanner Activity`. See [`references/report-structure.md`](references/report-structure.md) for the full rationale, including which sections were deliberately KEPT because Part 1 cards depend on them as evidence.

   **Validate before proceeding:** run `python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py --validate "$REPORT_PATH"` after filling all markers (see Step 10) — do not skip this even if the report "looks done."

8a. **Correlation & Synthesis Pass.** After all markers are filled, re-read the ENTIRE assembled
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

    After correlation is complete, apply the two-audience test before finalizing:
    - **Business Owner:** can they grasp the site's current status from At a Glance alone
      (one-line verdict + anomaly bullets + priority actions) without reading Part 2?
    - **Site Admin:** can they act immediately from the priority actions list — each action
      concrete, specific, and ordered by urgency?
    If either answer is no, revise At a Glance or the affected cards before proceeding.

9. **Write and place the `## 📌 At a Glance` section — written LAST, placed near the TOP.** This is
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

9a. **Scope note.** Append the following boilerplate block immediately after the Priority
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

10. **Script validation pass.** After all content is written, run the script's validation:
    ```bash
    python3 .agents/skills/kinsta-logs/scripts/analyze_logs.py --validate "$REPORT_PATH"
    ```
    This checks: (a) no unfilled `<!-- LLM: -->` markers remain, (b) no permanently suppressed
    section headings appear, (c) Part 1/Part 2 dividers are present, (d) card format compliance.
    If validation fails, fix the reported issues and re-run.

10b. **Conciseness Directive Compliance Audit (MANDATORY — do not skip).**
    **🚨 ALL DIRECTIVES MUST BE FOLLOWED LITERALLY. "LITERALLY" MEANS EXACTLY AS WRITTEN.**
    Before declaring the report complete, run these grep checks against `$REPORT_PATH`.
    Each check corresponds to a directive that has been repeatedly violated. If any grep
    produces output, fix the violation before proceeding — do NOT skip with "close enough."

    ```bash
    REPORT="$REPORT_PATH"

    # D8: At a Glance — no entire bold paragraphs (line starting+ending with ** >120 chars)
    echo "=== D8: Bold-paragraph check ==="
    grep -n '^\*\*.\{120,\}\*\*$' "$REPORT" || echo "PASS"

    # D9: "below target" near "cache" — only valid if window ≥6h daytime
    echo "=== D9: 'below target' near 'cache' ==="
    grep -n -i 'cache.*below.target\|below.target.*cache' "$REPORT" || echo "PASS"

    # D10: Cache purge explanation count must be ≤1 (explain once in Cache Root Cause)
    echo "=== D10: Cache-purge explanation count (must be ≤1) ==="
    COUNT=$(grep -ci 'purge.*cache\|cache.*purge\|cache.*emptied\|cache.*completely.cold\|every 24 hours.*midnight\|post-purge.cold' "$REPORT")
    if [ "$COUNT" -le 1 ]; then echo "PASS (count=$COUNT)"; else echo "FAIL: $COUNT occurrences — explain once in Cache Root Cause, cite by name elsewhere"; fi

    # D12: Bytespider "Monitor" without ZH-content justification
    echo "=== D12: Bytespider Monitor without ZH justification ==="
    if grep -qi 'bytespider.*monitor\|monitor.*bytespider' "$REPORT"; then
      echo "WARNING: Bytespider flagged as Monitor — verify ZH-content relevance is stated explicitly"
      grep -n -i 'bytespider' "$REPORT"
    else
      echo "PASS"
    fi

    # D13: "verify 403 rules are still current" or "review error log monthly for new patterns"
    echo "=== D13: 403 rule 'verify current' recommendation ==="
    grep -n -i 'verify.*403.*rules.*current\|review.*error.log.*monthly.*new patterns\|verify.*spam-block.*still current' "$REPORT" || echo "PASS"

    # D3: __cf_bm cookie explanation count must be ≤1
    echo "=== D3: __cf_bm explanation count (must be ≤1) ==="
    COUNT=$(grep -ci '__cf_bm.*cookie\|Cloudflare Bot Management.*cookie\|cf_bm.*bypass' "$REPORT")
    if [ "$COUNT" -le 1 ]; then echo "PASS (count=$COUNT)"; else echo "FAIL: $COUNT occurrences — explain once, cite by name elsewhere"; fi

    echo "=== Directive compliance audit complete ==="
    ```

    If any check prints FAIL, fix the report and re-run the audit. Do NOT proceed to
    `--validate` or PDF export until every check passes.

10c. **URL spelling verification (MANDATORY — do not skip).** Run [`scripts/verify_urls.py`](scripts/verify_urls.py)
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

11. **Be honest about uncertainty.** If the data doesn't answer a question, or a Kinsta KB search
    found nothing relevant, say so — do not fabricate explanations or citations.

### Step 7: Export PDF

**Execute** [`scripts/export_pdf.sh`](scripts/export_pdf.sh) against the FINAL report — only after
Step 6's Analyst Commentary, At a Glance, and silent final review are already written to disk,
since the PDF is a snapshot of whatever the Markdown file contains at the moment it runs:

```bash
# Default: Typst engine (Quarto's bundled pandoc + Typst, no extra deps)
bash .agents/skills/kinsta-logs/scripts/export_pdf.sh "$REPORT_PATH"

# Chromium engine (md-to-pdf + system Chromium, best visual design, A4)
bash .agents/skills/kinsta-logs/scripts/export_pdf.sh --engine chromium "$REPORT_PATH"
```

Two engines supported:

| Engine | Command | Deps | Best For |
|---|---|---|---|
| `typst` (default) | `quarto pandoc ... --pdf-engine=typst` | Quarto only | Clean typography, no extra installs |
| `chromium` | `npx md-to-pdf` + system Chromium | Chromium at `/usr/bin/chromium` | Visual design, compact layout, A4 |

Output is `{report_path minus .md}.pdf` in the same `reports/` folder. If the chosen engine's
dependencies aren't found, the script exits with a warning — the Markdown report is the primary
deliverable regardless of PDF export success.

### Step 8: Send Report by Email (User-Initiated Only)
 
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

### Step 9: Present Report

**The chat summary must never contain an insight, number, or recommendation that isn't already
written into the report file.** Chat is a condensed pointer to the report, not a second, richer
analysis that competes with it — if you find yourself writing something more useful in the chat
response than what's in the file, that's a bug: go back and add it to the report via `apply_diff`
first, then summarize it in chat. Present a concise summary confirming the report is open, quoting
(not re-deriving) the Overall Assessment verdict and the top 3-5 findings/actions directly from the
Analyst Commentary section you just wrote, and note where the PDF was saved (or that it was skipped,
per Step 7) and whether the report was emailed.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `NETWORK_ERROR` on cache-perf | Transient Kinsta API issue | Retry up to 3x with 3s sleep between |
| Tool name not found (e.g. `kinstasiteslist`) | Roo Code strips dots from tool names — confirmed upstream bug (GitHub RooCodeInc/Roo-Code #6514). The `mcp--kinsta--kinsta.sites.list` function name gets flattened to `kinstasiteslist`, which doesn't exist on the server. | **Never use `mcp--kinsta--*` functions.** Always use `execute_command` with JSON-RPC piped into `npx -y kinsta-mcp@1.0.3`. See Step 1's ⚠️ banner for the exact command template. The `scripts/fetch_logs.sh` script already does this internally for log fetching. |
| `⏳ *pending*` still in Part 2 bot tables after report assembly | `apply_diff` on Part 2 tables failed due to line number shifts after Part 1 commentary was filled in | Use the `sed` one-liner from Step 6.8 (item 5) instead — it's deterministic and doesn't depend on line numbers |
| `Validation error: Invalid enum value` | Used `error.log` instead of `error` | Use bare names: `error`, `access`, `kinsta-cache-perf` |
| Cross-file analysis empty | Error and access logs don't overlap in time | Use `"lines":8000` for the access log for full 24h coverage |
| Report file not found | Looked in `$DIR` instead of the reports folder | Reports live in `~/Downloads/kinsta-logs/reports/`, named `report_{site_name}_{env_name}_{YYYYMMDDHHMM}.md` — check `analyze_logs.py`'s printed `📄` line for the exact path |
| Analyst Commentary vanished after a later run | `analyze_logs.py` regenerates the entire report from scratch every run — a manually-appended commentary is not part of that generation and gets silently overwritten | Never re-run the script against real `$DIR` log files whose report is the one being reviewed; use scratch-copied log files (Step 3's warning). If it already happened, re-run Step 3 cleanly, then redo Steps 6.8–6.10 in the same batch of work |
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
| [`scripts/verify_urls.py`](scripts/verify_urls.py) | Post-generation mechanical URL verification — diffs every URL in LLM-authored commentary against source files (probe JSON, site-context.md, report data tables). Catches transliteration errors that are invisible to spell-check | **Execute** in Step 6.10a — mandatory, do not skip |
| [`scripts/export_pdf.sh`](scripts/export_pdf.sh) | Converts the final Markdown report to PDF via one of two engines: `typst` (default, Quarto pandoc+Typst) or `chromium` (md-to-pdf + system Chromium) | **Execute** in Step 7, after Step 6 is fully written |
| [`scripts/report.css`](scripts/report.css) | Sans-serif report stylesheet applied by the `chromium` engine — larger body text (13px), compact tables (11px), professional typography | Used automatically by `export_pdf.sh --engine chromium` |
| [`scripts/send_report_email.py`](scripts/send_report_email.py) | Sends the PDF report as email attachment via SMTP (Gmail by default). Merges non-sensitive fields from [`config/email.json`](config/email.json) (recipients, subject, signature) with SMTP credentials from `~/.config/kinsta-log-analyzer/email.json` | **Execute** in Step 8 (optional), if the user chooses to email the report |
| [`config/email.json`](config/email.json) | Non-sensitive email fields: `from_email`, `to_emails`, `subject`, `body_signature`. Lives in the skill folder; version-controlled | Edit directly to change recipients or subject |
| [`config/email.json.example`](config/email.json.example) | Template for `~/.config/kinsta-log-analyzer/email.json` — SMTP credentials only (`smtp_host`, `smtp_port`, `username`, `password`). Not version-controlled | Copy to `~/.config/kinsta-log-analyzer/email.json` and fill in credentials |
| [`references/site-context.md`](references/site-context.md) | Admin/business-owner timezones, each site's confirmed primary market, and the fixed "Known Probe URLs" list per site — a living cache, update it when the user confirms new context | **Read** in Steps 1 & 2; **update** via `apply_diff` when new context is learned |
| [`references/bot-taxonomy.md`](references/bot-taxonomy.md) | Accurate, unbiased per-bot reference: real nature (crawler vs. on-demand agent), robots.txt/Crawl-Delay compliance matrix, Kinsta/WordPress-generic mitigation tiers (no hosted-app code involved — see Step 6.5), and the ASN-vs-reverse-DNS distinction | **Read in full** in Step 6 before writing any bot-related recommendation |
| [`references/operational-playbook.md`](references/operational-playbook.md) | Expert server guidance for each anomaly type (cache, errors, response time, traffic spikes, SSL) | **Read** when the report flags an issue needing deeper action |
| [`references/kinsta-tribal-knowledge.md`](references/kinsta-tribal-knowledge.md) | Platform behaviors confirmed by Kinsta support (Nginx capabilities/limitations, cache architecture, Bot Protection mechanisms, default behaviors) — facts not in the public KB | **Read** in Step 6.6b when forming Nginx/rate-limit/cache/bot action recommendations |
| [`references/kinsta-history.md`](references/kinsta-history.md) | Chronological log of actions already taken via Kinsta support per site — prevents re-recommending past actions | **Read** in Step 6.6c before finalizing any action recommendation; **update** via `apply_diff` when new actions are taken |

## Configuration
Reads credentials from `.roo/mcp.json` → `mcpServers.kinsta.env`. Kinsta Knowledge Base lookups
(Step 6.6) use the `tavily` MCP server (`tavily-search`), also configured in `.roo/mcp.json`.
PDF export (Step 7) supports two engines: `typst` (default, Quarto pandoc+Typst, no extra deps)
and `chromium` (md-to-pdf + system Chromium at `/usr/bin/chromium`). Switch with `--engine`.

## Privacy & Retention
- Visitor IPs from the access/error logs are written to disk under `~/Downloads/kinsta-logs/` and are not automatically cleaned up — periodically prune old log/report files if this is a concern.
- Unless `--no-geoip` is passed, visitor IPs are also sent to the third-party `ipinfo.io` service up to three times per unique IP — country lookup, ASN/organization lookup (`ip_org()`), and reverse-DNS/PTR lookup (`ip_hostname()`) — during Step 3.
- Both probe passes (Step 2's baseline, Step 4's targeted) send real HTTP requests to the site being analyzed (and only that site — never a third party) from wherever this skill runs; this generates a handful of extra hits in the site's own logs at probe time, self-identified via a distinctive User-Agent (`Kinsta-Log-Analyzer-Probe`) so future analysis runs recognize this as this skill's own traffic, not an unknown visitor.
- The generated report (and its PDF) embeds raw visitor IPs and is opened in VS Code; treat it like any other file containing visitor data.
- Step 6.6's Kinsta KB lookups send search queries (not visitor data) to `tavily-search`.

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
