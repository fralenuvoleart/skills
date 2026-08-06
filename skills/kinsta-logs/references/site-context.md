# Site Context — Known Timezones & Markets

**Read this file in Step 1 of every run.** Traffic-hour and geo-IP interpretation is meaningless
without knowing *where the humans actually are* — both the people running the site and the people
the site is trying to reach. A "3 AM traffic spike" is not an anomaly if 3 AM local server time is
prime business hours for the site's actual target market.

This file is a **living cache**, not a one-time fixture. Update it (via `apply_diff`) whenever the
user confirms new context during an analysis — never re-ask for the same fact twice.

---

## Known Sites

| Site | Business owner location | Site admin location | Confirmed primary visitor market | Known admin IPs | Notes |
|---|---|---|---|---|---|
| **pbservices.ge** | Tbilisi, Georgia (UTC+4) | Manila, Philippines (UTC+8) | 🇬🇪 Georgia (confirmed by user) | `180.194.197.6` (Manila, PH — the site admin's IP; this is NOT a visitor or bot — exclude from ALL error/performance/burst findings) | Financial/residency/banking services for foreigners relocating to Georgia. RU and ZH-language content exists because Russian and Chinese nationals are a real target segment for Georgia residency/banking — do not assume RU/ZH traffic is automatically suspicious or bot-only. See "Known Probe URLs" below for the fixed live-verification sample set. **Sevalla cache-warmer:** `Automations (Telegram/Warmer)` app (Sevalla ID `73d65fa7`) self-identifies via User-Agent `SevallaCacheWarmer/1.0` — `analyze_logs.py` auto-classifies it as `Internal Tooling (Self)`, so its GCP IPs are never flagged as scrapers. No manual IP tracking needed. |
| **pbproperty.ge** | *unknown — ask on first analysis, then record here* | Manila, Philippines (UTC+8) | *unknown — ask* | Georgia real-estate vertical of the same portfolio; likely shares the Tbilisi/Georgia context above but **do not assume** — confirm with the user once. |
| **pbnova.com** | *unknown — ask on first analysis, then record here* | Manila, Philippines (UTC+8) | *unknown — ask* | — |

**Admin timezone (Manila, UTC+8) applies across the whole portfolio** — this is the one fact
that's safe to assume without asking, since all sites in this workspace are managed by the same
person/agency. Business-owner location and confirmed primary market are **per-site facts** — never
assume they transfer from pbservices.ge to another site without confirming.

---

## Known Probe URLs

Fixed sample URLs for the Step 4 live-verification probe — one per language x page-type
combination, so a single probe run sanity-checks routing/caching/headers across every locale the
site serves, not just the default language. Add more sites' lists here as they're confirmed;
never invent a URL you haven't verified exists.

### pbservices.ge

```
https://pbservices.ge/robots.txt
https://pbservices.ge/sitemap.xml
https://pbservices.ge/
https://pbservices.ge/about/
https://pbservices.ge/services/individual-entrepreneur-georgia/
https://pbservices.ge/ru/
https://pbservices.ge/ru/o-nas/
https://pbservices.ge/ru/uslugi/individualnyj-predprinematel/
https://pbservices.ge/ar/
https://pbservices.ge/ar/about-ar/
https://pbservices.ge/ar/offers/individual-entrepreneur-georgia-ar/
https://pbservices.ge/zh/
https://pbservices.ge/zh/guanyu/
https://pbservices.ge/zh/fuwu/individual-entrepreneur-georgia-zh/
```

## How to Use This in Analysis

1. **Convert every UTC hour bucket to both the admin's and the business owner's local time** when
   discussing traffic patterns in the Analyst Commentary — a spike at `00:00 UTC` is `08:00` in
   Manila and `04:00` in Tbilisi; state both, then judge plausibility against each.
2. **Geo-IP sanity check**: if the top visitor countries in the report do **not** match the
   confirmed primary market, do not silently accept the geo-IP tag as "a real visitor from that
   country." Cross-reference the IP's ASN/hosting-provider (see `ip_org()` in
   [`scripts/analyze_logs.py`](../scripts/analyze_logs.py)) — a `🇺🇸 US` tag on an IP whose ASN
   resolves to a hosting/proxy/CDN provider is not evidence of a US visitor; it's evidence of
   infrastructure (Kinsta's own edge nodes, a reverse proxy, a residential-proxy scraping service,
   etc.). State this distinction explicitly rather than reporting the country tag at face value.
3. **RU/ZH-language traffic and content is not inherently suspicious** for `pbservices.ge` — the
   business's actual product targets Russian- and Chinese-speaking clients relocating to or banking
   in Georgia. Only flag RU/ZH-adjacent activity as an attack pattern when the *specific URL or
   payload* is a spam/injection pattern (e.g. gambling/pharma slugs appended to a legitimate blog
   post), never merely because the language segment itself is RU/ZH.

## Learning Protocol

- If a site's business-owner location or confirmed primary market is `unknown — ask`, ask the user
  **once** (via `ask_followup_question`) during Step 1 of that analysis, then immediately persist
  the answer into the table above via `apply_diff` so future runs never ask again.
- If the user corrects a previously recorded fact, update it in place — this file describes
  current known context, not a changelog.
