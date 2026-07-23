# Conciseness & Consistency Directives

**Read this file in Step 6 before writing any report commentary.** These 14 rules generalize
recurring review findings into permanent, self-auditable directives. Several are grep-auditable
in the Directive Compliance Audit step.

---

## Formatting Rules

### D1 — Overall Severity Icon (Human Judgment)

The headline's overall icon is a human-judgment call, answering ONE question: is there a genuine
emergency, or just minor flags, or is everything clean? Not a formula, not a mechanical max()/sum()
over the component table — a judgment about the actual underlying facts:

- 🔴 **Overall** = at least one component represents a genuine, active emergency exactly as the
  icon vocabulary defines 🔴 (site down, active security breach, data at risk) — not merely "a
  metric missed its numeric target."
- 🟡 **Overall** = no genuine emergency exists anywhere, but one or more components have a real
  flag (🟡/🔧) worth attention.
- ✅ **Overall** = every component is clean, no flags at all.

**This means a component's own icon must itself be correctly classified first** — the root cause
of an earlier, repeated mistake here was assigning 🔴 to a cache HIT-rate miss (a performance/config
target-miss, capped at 🟡 per the icon vocabulary — never 🔴, no matter how far below target the
number is) and then mechanically propagating that wrong 🔴 upward. Fix the component's
classification first; the overall judgment call above only works when every input into it is
already correct.

### D2 — Collapse Homogeneous Tables (>70% Same Verdict)

Collapse any table where >70% of rows share the identical verdict/value into a summary line +
itemized outliers only. Applies to the Bot Traffic Strategy table and any similarly-shaped per-item
table: if 10+ items all resolve to `✅ Keep`/`no action`, write one line — `"✅ Keep (N bots, no
action needed — see Part 2 for the full list)"` — and itemize ONLY the rows with a non-default
verdict (Block/Monitor/Throttle/etc.). Never print a long column of repeated identical icons;
repetition without variation is noise, not evidence.

### D4 — Status Markers on Every Part 1 Subsection

Every Part 1 `###` subsection carries a status marker in its first line — no exceptions. A
subsection with no finding still needs a marker: a leading ✅/ℹ️. Never let one subsection break
the visual pattern the reader has learned from its siblings.

### D5 — Wide-Table Takeaways

Wide tables (5+ columns) get a plain-language one-line takeaway directly above them, before
rendering the table. Any table with 5 or more columns (e.g. the per-category bot tables with the
Verdict column) must be preceded by one sentence stating the actual conclusion (`"14 of 15 bots
need no action; only Bytespider should be blocked — see table for detail."`) so a skimming reader
gets the answer without parsing the grid.

### D6 — No Tilde (~) for Approximation

Never use `~` (tilde) for approximation in report content. Some Markdown renderers (including
Typst, used by pandoc for PDF export) interpret `~` as a strikethrough delimiter, causing text
between two tildes to render with a line through it. Use `≈` or "approximately" instead. Example:
write `≈85%` or "approximately 85%", never `~85%`. This applies to the At a Glance Scope note
and any other LLM-written content — check every occurrence of `~` before finalizing.

### D8 — At a Glance: Bold Sparingly

At a Glance: bold only key words and numbers, never entire paragraphs. Bold formatting draws the eye
— when an entire paragraph is bold, nothing stands out and the visual hierarchy collapses. Use bold
sparingly on the most critical words, numbers, and verdict terms within each sentence. The At a
Glance section's purpose is scanability; a wall of bold text defeats that purpose. Example: "Cache
HIT at **32%** in a **post-midnight cold-start window** — daytime rate not assessable. **No
security incidents.**"

**Grep check:** `grep -n '^\*\*.\{120,\}\*\*$' "$REPORT_PATH"` (must produce no output).

### D11 — Bold Key Metrics Selectively in Prose

Bold key metrics selectively within prose paragraphs. When a paragraph contains several numbers, bold
the 1–2 most significant metrics to create visual waypoints for a scanning reader. Never bold every
number in a paragraph — that produces the same uniformity problem as bolding entire paragraphs.
Choose the numbers that carry the most diagnostic weight (e.g., the HIT rate percentage, the error
count, the bot request volume) and bold only those. Example: "Cache HIT at **32%** (208 of 657
entries), BYPASS **40%** (265 entries), MISS 28% (184 entries)."

---

## Content & Citation Rules

### D3 — Explain Once, Cite Thereafter

Explain a mechanism once; every subsequent reference cites it by name, never re-explains it. When a
root cause (e.g. a specific cookie, a specific redirect chain) is described in full in one card,
every other card that's affected by the same mechanism must reference it by a short name (`"the
__cf_bm cache-block described above"`) — not restate the mechanism's how/why again. If you catch
yourself writing the same 2+ sentence explanation in a second card, delete it and cite instead.

**Grep check:** `grep -ci '__cf_bm.*cookie\|Cloudflare Bot Management.*cookie\|cf_bm.*bypass' "$REPORT_PATH"` (count must be ≤1).

### D10 — Cache Cold-Start: Explain Once, Cite Everywhere Else

The midnight-UTC cache purge and its effect on HIT rates is a single root cause. Describe it in full
ONLY in the Cache Root Cause Analysis card (Primary Root Cause). Every other section that references
the cache HIT rate (Overall Assessment, At a Glance, Traffic Anomalies) must cite it by a short
reference — `"(see Cache Root Cause Analysis for the cold-start window explanation)"` or `"as noted
in Cache Root Cause"` — and NEVER re-explain the purge mechanism, timing, or expected behavior.
This is a specific, high-frequency application of Directive 3 (explain once, cite thereafter).

**Grep check:** `grep -ci 'purge.*cache\|cache.*purge\|cache.*emptied\|cache.*completely.cold\|every 24 hours.*midnight\|post-purge.cold' "$REPORT_PATH"` (count must be ≤1).

### D14 — Cache-Perf HIT Rate: Always State Time Window and Scope

Cache-perf HIT rate: always state its time window and Nginx-page-cache scope. See the SKILL.md
"How Logs Are Retrieved" section for why the cache-perf number differs from the dashboard. In the
Overall Assessment cache row and Cache Root Cause Analysis: always state the cache-perf log's time
window and that it represents the Nginx page-cache subset. If the window is <6h daytime, add:
"daytime steady-state rate not assessable from this data." When the user cites a conflicting
dashboard number: cite both, explain the gap (time window + scope), and identify the dashboard as
the authoritative full-day metric.

### D15 — Tone Calibration

Avoid both extremes, every time. This has been a repeated failure mode in both directions and must be checked explicitly before finalizing any Overall Assessment, At a Glance status line, or card verdict:
- **Too alarmist:** dressing up routine housekeeping (a stale cache entry, a low-value crawler, a missing trailing slash) in emergency language, or a severity icon one tier higher than the evidence supports (see the icon table below — 🔴 is reserved, not a default).
- **Too dismissive:** the opposite failure, and equally wrong — waving away a real, measurable, currently-below-target metric (e.g. a cache HIT rate sitting at 24–46% against a >50% target) with casual language like "minor housekeeping, nothing urgent" or "nothing to see here." A below-target metric with a concrete, evidence-backed fix is a genuine 🟡 finding worth an accurate, specific description — not a shrug.
- **The correct register:** state the actual measured severity in plain, professional, objective terms, exactly as supported by the evidence — no more, no less. "Cache HIT rate is 24%, well below the >50% target, driven by two identified causes — fixable, but currently costing real performance" is calibrated. "Nothing urgent" is not, when a metric is sitting at a third of target.
- **Avoid cheerleading-style status openers even when a real caveat follows** — e.g. "Overall status: healthy and secure, with one issue worth fixing" still reads as dismissive by leading with reassurance before the finding. Prefer a neutral, factual lead: **"No active security incidents; [metric] is below target and requires attention"** — state what was and wasn't found, in that order, without an adjective doing the reader's judgment for them.
- **Never use evaluative/judgment-laden labels — state measured severity, not a verdict on merit.** Words like "worst"/"best"/"terrible"/"great" attach a value judgment the underlying data doesn't actually support (severity icons are threshold-derived facts; "worst" implies a ranked comparison the report never actually computed). Use objective, measured language instead: "highest-severity finding" not "the worst finding"; "the metric furthest below target" not "the worst metric." This applies everywhere a finding is singled out — At a Glance headlines, card titles, and the Convergent Cross-Signals summary alike.
- Re-read every summary line against this test before finalizing: *would someone who only reads this one sentence come away with an accurate impression of how serious this actually is — not more dramatic, not more reassuring, and not a value judgment dressed up as a measurement?*

---

## Domain-Specific Rules

### D9 — Cache Cold-Start Window in At a Glance

At a Glance: never flag cache HIT rate as "below target" when the cache-perf window is a short
post-midnight cold-start period. Kinsta purges the server page cache every 24 hours at approximately
midnight UTC. A cache-perf log covering only the post-purge window (e.g., 22:33–01:00 UTC, ≈2.5
hours) will always show a low HIT rate because the cache is cold — this is expected platform
behavior, not a configuration defect. In such windows, describe the cache state factually (e.g.,
"Cache HIT at **32%** — expected for this post-midnight cold-start window; daytime rate not
assessable from this data") rather than as a "below target" finding. Only flag cache HIT as a
genuine 🟡 concern when the cache-perf window spans ≥6 hours of daytime traffic (e.g., 09:00–21:00
UTC) where a cold-start excuse no longer applies.

**Grep check:** `grep -n -i 'cache.*below.target\|below.target.*cache' "$REPORT_PATH"` (must produce no output).

### D12 — Bytespider: Never Default to "Monitor"

Bytespider: never default to "Monitor" without stating the site's ZH-content relevance explicitly.
Bytespider is ByteDance's crawler for Doubao (China's #1 consumer AI search engine). Per
`bot-taxonomy.md`, the verdict is case-by-case based on whether the site has Chinese-language
content (`/zh/`). If the site has ZH content, Bytespider is expected search-engine traffic — state
this explicitly and assign `✅ Keep`, not `👀 Monitor`. If the site has no ZH content, state that
explicitly as the reason for any non-Keep verdict. Never write "Monitor Bytespider volume" as a
vague, unexplained recommendation — always answer: does this site target a Chinese-speaking
audience, and is the volume proportionate? A site without ZH content receiving moderate Bytespider
volume is normal internet background radiation, not a finding.

**Grep check:** If `grep -qi 'bytespider.*monitor\|monitor.*bytespider' "$REPORT_PATH"` matches,
verify ZH-content relevance is stated explicitly.

### D13 — 403 Spam-Block Rules: Only Add for New Patterns

403 spam-block rules: only recommend adding new rules when new spam patterns appear in the error
log. When existing Nginx keyword blocks (e.g., `yinlang388`, `388ym.com`) are confirmed working by
log evidence (spam requests return 403 as intended), do NOT recommend "verify the rules are still
current" or "review error log monthly for new patterns" as an action — the rules are already
verified by the data in front of you. The only actionable recommendation for 403 spam-block rules
is: "Add Nginx keyword block for [new spam domain/pattern]" when a NEW spam pattern is observed in
the error log that is not already covered by existing rules. If no new patterns are observed, state
`✅ Existing Nginx spam-block rules are working as intended — no new patterns detected.` and move
on.

**Grep check:** `grep -n -i 'verify.*403.*rules.*current\|review.*error.log.*monthly.*new patterns\|verify.*spam-block.*still current' "$REPORT_PATH"` (must produce no output).

---

## Operational Rules

### D7 — Never Retype or Transliterate URLs

NEVER retype or transliterate URLs — always copy-paste them exactly from the source. URLs contain
non-English characters transliterated into ASCII (e.g. Russian words written in Latin script like
`individualnyj-predprinematel`). When you retype a URL from memory or sight, you WILL introduce
spelling errors (missing letters, swapped vowels) that are invisible to spell-check because the
words are transliterations, not real English words. This rule applies everywhere URLs appear: probe
commands, report commentary, card findings, KB references. **Copy from the probe JSON output, the
report's own data tables, or `site-context.md` — never retype.** Before finalizing the report, grep
for any URL you wrote and diff it against the source it came from.

---

## Directive Compliance Audit (Grep Checks)

After filling all report markers, run these checks against `$REPORT_PATH`:

```bash
REPORT="$REPORT_PATH"

# D8: At a Glance — no entire bold paragraphs
echo "=== D8: Bold-paragraph check ==="
grep -n '^\*\*.\{120,\}\*\*$' "$REPORT" || echo "PASS"

# D9: "below target" near "cache"
echo "=== D9: 'below target' near 'cache' ==="
grep -n -i 'cache.*below.target\|below.target.*cache' "$REPORT" || echo "PASS"

# D10: Cache-purge explanation count must be ≤1
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

# D13: "verify 403 rules are still current" or similar
echo "=== D13: 403 rule 'verify current' recommendation ==="
grep -n -i 'verify.*403.*rules.*current\|review.*error.log.*monthly.*new patterns\|verify.*spam-block.*still current' "$REPORT" || echo "PASS"

# D3: __cf_bm cookie explanation count must be ≤1
echo "=== D3: __cf_bm explanation count (must be ≤1) ==="
COUNT=$(grep -ci '__cf_bm.*cookie\|Cloudflare Bot Management.*cookie\|cf_bm.*bypass' "$REPORT")
if [ "$COUNT" -le 1 ]; then echo "PASS (count=$COUNT)"; else echo "FAIL: $COUNT occurrences — explain once, cite by name elsewhere"; fi

echo "=== Directive compliance audit complete ==="
```

If any check prints FAIL, fix the report and re-run the audit. Do NOT proceed to `--validate` or
PDF export until every check passes.
