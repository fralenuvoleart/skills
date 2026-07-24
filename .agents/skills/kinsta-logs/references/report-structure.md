# Report Structure Contract

This file defines the permanent section inventory, order, format, and conditional display rules for every Kinsta Health Report. The `analyze_logs.py` script generates the skeleton with `<!-- LLM: -->` markers. The LLM fills markers with content, orders Part 1 sections by severity, and performs the Correlation & Synthesis Pass. The script validates structural compliance.

**Rule: every section heading listed below MUST appear in the final report. If a section has no data, render it with a single `✅ nothing to report` line — never remove the heading.**

---

## Part 1: Summary & Findings

LLM orders sections within Part 1 by severity: 🔴 > 🟡 > 🔧 > ✅. Within same tier, order by impact magnitude.

### `## 📌 At a Glance`

- **Marker:** `<!-- LLM:AT_A_GLANCE -->`
- **Source:** LLM (written last, after the Correlation & Synthesis Pass — it summarizes findings not yet derived until then)
- **Format:**
  - One-line overall status with severity icon
  - `### Findings for this period` — bullet list, one per finding, severity icon per line, plain language. "Findings" covers both anomalous (🟡/🔴) and informational (ℹ️) items without implying every bullet is a problem.
  - `### Priority actions this period` — numbered list, ordered by urgency, concrete and actionable
- **If empty:** "✅ No findings in this period. No actions required."

### `## 📋 Analyst Commentary & Recommendations`

Contains all analyst-written subsections below. LLM fills each via its marker.

#### `### Overall Assessment`
- **Marker:** `<!-- LLM:OVERALL_ASSESSMENT -->`
- **Format:** Severity-icon verdict line + 5-row summary table (Security / Stability / Cache / Bot traffic / Slow pages), each row with status icon and one-line detail. Never a dense prose paragraph.
- **If empty:** Not possible — always has data.

#### `### 🎯 Convergent Cross-Signals`
- **Source:** Script (deterministic, NOT an LLM marker) — a set-intersection across the report's own "notable URL" lists (top cache-MISSed pages, burst targets, top 403/404 error URLs). A URL appearing in 2+ lists is flagged as a convergent pressure point with its combined evidence cited. This is intentionally mechanical, not LLM-authored, so it's checked identically every run.
- **Excludes:** `Kinsta-Log-Analyzer-Probe` traffic — the skill's own diagnostic probe is never eligible as convergence evidence (self-generated noise, not a real finding).
- **Position:** Immediately after Overall Assessment — read before any individual finding card, since its purpose is to reprioritize what follows.
- **If empty:** "No overlap found across the cache-miss, burst, and error-URL lists this run — the findings below are independent issues, not one root cause in disguise." Always rendered — never silently omitted.

#### `### Cache Root Cause Analysis`
- **Marker:** `<!-- LLM:CACHE_ROOT_CAUSE -->`
- **Format:** Sub-headed cards (`#### 🔴 Primary Root Cause`, `#### 🟡 Secondary Contributor`). Each card: mechanism explanation → probe evidence → KB citation → fix. Evidence-cited, informed by both probe passes.
- **If empty:** "✅ Cache HIT rate is at or above target. No root cause analysis needed."

#### `### Attack/Security Findings`
- **Marker:** `<!-- LLM:ATTACK_SECURITY -->`
- **Format:** Card format. `#### 🟡|🔧|✅ [Short title]` with `- **Event:**`, `- **Analysis:**`, `- **Source:**`, `- **Actions:**` bullet items. One card per distinct pattern. Actions are presented as a bullet list; "No action required ✅" is always on its own bold line, with its description/explanation on a new indented line.
- **If empty:** "#### ✅ No security incidents in this window" with Event/Analysis/Source/Actions bullets stating zero findings.

#### `### Bot Traffic Strategy`
- **Marker:** `<!-- LLM:BOT_STRATEGY -->`
- **Format:** Table: Bot | Requests | % of bot traffic | Verdict | Evidence. Followed by a blank line, then a blockquote summary callout interpreting the table (table → blank line → blockquote order — consistent with the Top Visitor IPs section). Bot verdicts: Keep / Block / Monitor / Throttle. Evidence column cites actual numbers/behavior from auto-gen bot tables, never references `bot-taxonomy.md` directly. **Per Conciseness & Consistency Directive 2: if >70% of bots resolve to the same verdict, collapse them into one summary row** (`"✅ Keep (N bots, no action — see Part 2 for the full list)"`) **and itemize only the outliers.** This collapsing rule applies to THIS table only — the auto-generated per-category bot tables in Part 2 remain full, uncollapsed evidence appendices.
- **If empty:** "✅ No bot traffic detected in this window."

#### `### Concentrated Traffic Spikes & Bursts`
- **Marker:** `<!-- LLM:BURST_CARDS -->`
- **Format:** Card format. `#### 🔧 [Short title]` with Event/Analysis/Source/Actions bullets. Use 🔧 (not 🔴) unless pattern is an active attack. Name source IP/bot and target URL(s) explicitly. Actions are presented as a bullet list; "No action required ✅" is always on its own bold line, with its description/explanation on a new indented line.
- **If empty:** "✅ No concentrated bursts detected in this window."

#### `### Traffic Anomalies`
- **Marker:** `<!-- LLM:TRAFFIC_ANOMALIES -->`
- **Format:** Card format. `#### ✅|🟡 [Short title]` with Event/Analysis/Source/Actions bullets. Convert UTC hours to admin and business-owner local time per `site-context.md`. Actions are presented as a bullet list; "No action required ✅" is always on its own bold line, with its description/explanation on a new indented line.
- **If empty:** "✅ Traffic pattern is within normal diurnal variation for the confirmed primary market."

#### `### 404/Error Fix Recommendations`
- **Marker:** `<!-- LLM:ERROR_FIXES -->`
- **Format:** Card format for ALL items. `#### 🔧|ℹ️ [Priority] — [Short title]` with `- **Event:**`, `- **URL(s):**`, `- **Analysis:**`, `- **Source:**`, `- **Actions:**` bullets. Actions are presented as a bullet list; "No action required ✅" is always on its own bold line, with its description/explanation on a new indented line. Low-priority items may group into a single `#### ℹ️ Low Priority — Miscellaneous` card with one bullet per item. Never bare bullets without a heading.
- **If empty:** "✅ No actionable 404s or client errors detected."

### Internal Framework (Analyst Checklist)

Structure every finding around four questions internally — What / Why / Who / How — this is the analytical spine you use to REASON through each finding, but it is not what the reader sees. The **visible labels in the report are always Event / Analysis / Source / Actions** — "What/Why/Who/How" is your private checklist, never printed:

| Internal question | Visible label | Answers |
|---|---|---|
| What? | **Event** | The flagged finding, stated with its exact evidence (numbers, URLs, IPs). |
| Why? | **Analysis** | Why it's suspicious or anomalous — cross-referencing bot-taxonomy.md/site-context.md/probe results as applicable. Ordinary/expected activity gets "why this is NOT an anomaly" instead. |
| Who? | **Source** | The source (bot name, IP, or "unknown") PLUS an explicit classification tier (`Safe` / `Benign` / `Suspicious` / `Malicious`) — never just prose judgment. |
| How? | **Actions** | The concrete action, sourced from live Kinsta KB documentation, a MyKinsta-panel step, or **bold "No action required ✅"** on its own line (description on new indented line) — never a canned tip disconnected from this finding's actual evidence. |

Cross-cutting lenses to apply this framework to: attack patterns (spam injection, xmlrpc probing), traffic anomalies (hour spikes — state the multiplier, convert to local time), bot strategy (per bot-taxonomy.md), cache root cause (cite top-missed URLs/query params/probe header evidence), 404/error triage, and IP/geo sanity (hosting/proxy flags).

---

## Part 2: Technical Appendix

Auto-generated by script. Sections appear in fixed order below. LLM does NOT reorder Part 2.

### `## 📊 Cache Performance`

- **Source:** Script (auto-generated)
- **Subsections included:**
  - HIT/MISS/BYPASS table with share bars
  - `### Pages Most Frequently Missing Cache` (top-MISSed URLs table)
  - `### Response Time: Cache HIT vs MISS` (comparison table)
- **Subsections EXCLUDED (never emitted):**
  - `### How to Improve Cache HIT Rate` — Analyst Commentary's Cache Root Cause Analysis supersedes this
- **If empty (no cache data):** "No cache-perf data available for this window."

### `## 📊 Bot & Crawler Traffic`

- **Source:** Script (auto-generated)
- **Format:** Per-category tables. Script generates a structural **Verdict** column with a placeholder `⏳ *pending*` in every row. After the LLM writes the Bot Traffic Strategy table in Part 1, it MUST overwrite every placeholder cell with the exact verdict from that table (`✅ Keep` / `🔧 Block` / `👀 Monitor` / `🔧 Throttle`) via `apply_diff`. The column's existence is script-guaranteed; its content is LLM-owned.
- **Subsections EXCLUDED (never emitted):**
  - `### Scanner IPs — Block List` — this data (`cross_results["scanner_ips"]`) has no other surface; removed because it duplicated the Directory Scanner's "no action needed" finding in practice. If a future run needs it for Burst cards, cite the `top_ips`/Bursts data instead.
- **If empty:** "No bot traffic detected in this window."

### `## 📊 Top Visitor IPs`

- **Source:** Script (auto-generated)
- **Format:** Table: IP | Requests | Country | ASN/Provider | Reverse DNS | ⚠️. Plus the infrastructure-vs-residential warning blockquote.
- **If empty:** "No visitor IP data available."

### `## Concentrated Traffic Spikes & Bursts` (raw evidence table)

- **Source:** Script (auto-generated) — **kept in Part 2, NOT suppressed.** This is the raw per-IP/per-bot concentration data (`share >= 40% and count >= 10` detection). It is the evidence the LLM cites when writing Part 1's `### Concentrated Traffic Spikes & Bursts` cards (`<!-- LLM:BURST_CARDS -->`) — removing it would leave the LLM with no source data to build cards from. The Part 1 cards are the curated narrative; this table is the evidence trail.
- **If empty:** "No single-IP burst detected."

### `## Traffic Overview`

- **Source:** Script (auto-generated)
- **Subsections included:**
  - `### Status Codes` (grouped summary + collapsible individual codes)
  - `### Errors by Status Code — Drill-Down` — **kept, NOT suppressed.** This per-URL/per-IP breakdown for every 4xx/5xx code is the evidence the LLM cites when writing Part 1's `### 404/Error Fix Recommendations` cards (`<!-- LLM:ERROR_FIXES -->`). Same rationale as Bursts above.
  - `### Requests per Hour (UTC)` (sparkline chart + busiest/quietest labels)
  - `### Performance` (avg/fastest/slowest metrics + slowest individual requests table, nested — not a separate top-level section)
- **If empty:** "No traffic data available for this window."

### `## 🔬 Live Probe Cross-Match`

- **Marker:** `<!-- LLM:PROBE_CROSS_MATCH -->`
- **Source:** LLM
- **Format:** Bullet list. Each bullet: one probe finding, what it confirmed or contradicted from the log-derived analysis. Cite specific headers (`x-kinsta-cache`, `Set-Cookie`, `cf-cache-status`).
- **If empty:** "No probe data available for cross-match."

### `## 📚 Kinsta KB References`

- **Marker:** `<!-- LLM:KB_REFERENCES -->`
- **Source:** LLM
- **Format:** Bullet list. Each bullet: linked article title, URL, one-line summary of relevant guidance. **ALWAYS append as the last entry:** `- **Kinsta Live Support Chat** — The report integrates additional insider knowledge and history of past actions, from the Kinsta Support Chat History.`
- **If empty:** "No Kinsta KB articles were cited in this report." (The Live Support Chat entry is still appended even when empty.)

---

## Sections Permanently Removed

These auto-generated sections are NEVER emitted by the script — each was verified to have
**no unique evidence** that a Part 1 card would otherwise lose access to (contrast with
Bursts/Errors-Drill-Down below, which ARE kept precisely because they ARE the evidence source):

| Removed section | Reason |
|---|---|
| `## Health Summary` | All its numbers (HIT/BYPASS %, avg response time, slow-page count, 5xx count, error counts) are independently re-surfaced in Cache Performance, Performance, and the error-findings sections — nothing unique is lost. Duplicated by At a Glance + Overall Assessment table. |
| `## 🟢 Low-Priority Notes` (the "low" severity tier only) | The one recurring finding here (403 directory-probe noise) is fully covered by Attack/Security Findings' default "no incidents" card. `critical`/`medium` tiers (`## 🔴 Issues Found` / `## 🟡 Warnings`, real PHP errors) are UNCHANGED and still emitted. |
| `### How to Improve Cache HIT Rate` | Pure generic tips with no unique data — actively contradicted evidence-based findings in Cache Root Cause Analysis. Zero evidentiary loss. |
| `### Scanner IPs — Block List` | Narrow, low-volume list (`cross_results["scanner_ips"]`); overlaps with Directory Scanner Activity's "no action needed" verdict. Accepted as a minor, deliberate evidentiary trade-off — not reconstructable elsewhere, but low-value in practice. |
| `## Directory Scanner Activity` | Noise — one-line "nothing found" section adds no value beyond confirming Kinsta's default 403 behavior. |

**NOT removed (kept in Part 2 as evidence, despite initially being miscategorized as removable during design):**

| Section | Why it stays |
|---|---|
| `### Errors by Status Code — Drill-Down` | This is the ONLY source of per-URL/per-IP breakdown for 4xx/5xx codes. The LLM's `### 404/Error Fix Recommendations` cards (Part 1) are built FROM this data — removing it would leave the LLM unable to cite specific URLs/counts. |
| `## Concentrated Traffic Spikes & Bursts` (auto-gen table) | This is the ONLY source of the `share >= 40%` burst-detection computation. The LLM's `### Concentrated Traffic Spikes & Bursts` cards (Part 1) are built FROM this data — same rationale as above. |

---

## Marker Inventory (Script Must Emit)

| Marker | Section |
|---|---|
| `<!-- LLM:AT_A_GLANCE -->` | Part 1 → At a Glance |
| `<!-- LLM:OVERALL_ASSESSMENT -->` | Part 1 → Overall Assessment |
| `<!-- LLM:ATTACK_SECURITY -->` | Part 1 → Attack/Security Findings |
| `<!-- LLM:CACHE_ROOT_CAUSE -->` | Part 1 → Cache Root Cause Analysis |
| `<!-- LLM:BOT_STRATEGY -->` | Part 1 → Bot Traffic Strategy |
| `<!-- LLM:BURST_CARDS -->` | Part 1 → Concentrated Traffic Spikes & Bursts (cards — cites the Part 2 raw table above) |
| `<!-- LLM:TRAFFIC_ANOMALIES -->` | Part 1 → Traffic Anomalies |
| `<!-- LLM:ERROR_FIXES -->` | Part 1 → 404/Error Fix Recommendations (cards — cites the Part 2 raw table above) |
| `<!-- LLM:PROBE_CROSS_MATCH -->` | Part 2 → Live Probe Cross-Match |
| `<!-- LLM:KB_REFERENCES -->` | Part 2 → Kinsta KB References |

The script emits these markers in this fixed default order in Part 1 (Overall Assessment →
Attack/Security → Cache Root Cause → Bot Strategy → Burst Cards → Traffic
Anomalies → Error Fixes → At a Glance heading at the very top). **The LLM MAY reorder the
`###`-level Part 1 subsections by severity tier before finalizing** — the script's order is a
neutral default, not a mandate (see SKILL.md Step 6, point 3).

---

## Validation Rules (Script Enforces via `--validate`)

Run: `python3 scripts/analyze_logs.py --validate <report_path>`. Exit code 0 = pass, 1 = fail
with itemized problems printed to stdout. Checks:

1. **No unfilled markers** — no `<!-- LLM:... -->` string remains in the file
2. **No forbidden sections** — none of the "Permanently Removed" section headings appear
3. **Part 1/Part 2 dividers present** — both `PART 1: SUMMARY & FINDINGS` and `PART 2: TECHNICAL APPENDIX` lines exist
4. **Card format compliance** — every `####` card under Attack/Security Findings, Concentrated Traffic Spikes & Bursts, and Traffic Anomalies has a `- **Event:**` bullet (unless the section states "not observed")

**Not currently validated** (LLM judgment, not mechanically checkable): tone calibration, severity icon accuracy, Bot Strategy Verdict-column injection into Part 2 tables, Correlation & Synthesis Pass quality. These remain the LLM's responsibility per SKILL.md Step 6/6a.
