# Kinsta Action History

Chronological log of actions already taken via Kinsta support for each site. Consulted during report generation (Step 6.6c) to avoid re-recommending actions already implemented.

**Maintenance:** When new actions are taken via Kinsta support, add a dated entry under the relevant site. Keep entries factual: what was done, when, by whom, what scope.

---

## pbservices.ge (Live)

### 2026-07-17 — Server Cache TTL Test: 24h → 7 Days (Francesco, self)

**Action category: Cache configuration**
- Testing change of Kinsta server cache TTL from the default **24 hours** to **7 days** (604,800 seconds)
- Purpose: observe whether extended cache retention improves HIT rate and reduces origin load
- Cache-perf log analysis on subsequent runs should be evaluated against this new TTL, noting that a higher TTL means MISSes and BYPASSes are more significant (stale cache persists longer), while HITs are "cheaper" (fewer regenerations)
- ⚠️ This is a test — effectiveness and any adverse effects (stale content, disk usage) should be reassessed after a full week of traffic under the new TTL

### 2026-07-16 — Full Denied IPs Audit (Francesco, self)

Complete Denied IPs list retrieved via Kinsta API (`kinsta.tools.denied-ips`). 18 IPs total. IPs with known addition dates are annotated; the remainder predate kinsta-history tracking.

| # | IP | Date Added | Reason |
|---|---|---|---|
| 1 | `188.166.185.173` | *unknown* | — |
| 2 | `45.173.30.48` | *unknown* | — |
| 3 | `90.93.17.145` | *unknown* | — |
| 4 | `157.100.188.78` | *unknown* | — |
| 5 | `47.55.188.190` | *unknown* | — |
| 6 | `157.173.106.113` | *unknown* | — |
| 7 | `149.22.91.71` | *unknown* | — |
| 8 | `20.195.184.45` | *unknown* | — |
| 9 | `92.5.53.199` | *unknown* | — |
| 10 | `167.86.117.252` | *unknown* | — |
| 11 | `193.32.162.60` | *unknown* | — |
| 12 | `143.198.202.164` | *unknown* | — |
| 13 | `1.92.223.0` | *unknown* | — |
| 14 | `157.173.109.225` | *unknown* | — |
| 15 | `34.169.72.237` | *unknown* | — |
| 16 | `34.185.133.109` | 2026-07-15 | GCP-based crawler causing slow pages |
| 17 | `34.179.198.189` | 2026-07-15 | GCP-based crawler, same pattern as #16 |
| 18 | `40.83.78.94` | 2026-07-16 | Microsoft Azure VM (HK) — directory scanner probing `/wp-admin/` paths (23 attempts/24h) |

**Redirects snapshot** — 121 rules exported from MyKinsta. Full CSV: [`redirects-pbservices.ge.csv`](references/redirects-pbservices.ge.csv).

No redirect loops detected. Categories:

| Category | Count | Examples |
|---|---|---|
| Blog slug migrations (old → new) | 41 | `/cost-of-living-in-georgia-prices/` → `/blog/cost-of-living-in-georgia-prices/` |
| Service page renames | 9 | `/personal-bank-account/` → `/services/personal-bank-account-georgia/` |
| Cyrillic URL → Latin transliteration (RU) | 20 | `/ru/о-нас/` → `/ru/o-nas/` |
| RU blog slug migrations | 15 | `/ru/oczenka-nedvizhimosti-v-gruzii/` → `/ru/blog/oczenka-nedvizhimosti-v-gruzii/` |
| Typo corrections | 5 | `individualnyj-predprinimatel` → `individualnyj-predprinematel` |
| Category restructures (capture groups) | 9 | `/university/(.+)` → `/info/university/$1` |
| Former staff pages → about/team | 5 | `/about/giorgi-nabiev/` → `/about/yana-chugianova/` |
| Static asset fixes | 3 | `/apple-touch-icon-120x120-precomposed.png` → `/apple-touch-icon.png` |
| Trailing slash normalization | 2 | `/services/hr-outsourcing-georgia` → `/services/hr-outsourcing-georgia/` |
| Removed content → homepage | 3 | `/jobs/` → `/` |
| AR blog slug migrations | 2 | `/ar/hr-outsourcing-ar/` → `/ar/blog/hr-outsourcing-ar/` |
| Subpage squashes (discard subpath) | 7 | `/ru/resursy-po-gruzii/svobodnye-zony-gruzii/(.+)` → parent |

**Flagged for review:**
- **Redirect #4** (`/ru/uslugi/lichnyj-schet-v-gruzinskombanke/?$`) — missing `^` anchor (all other 120 rules have it). Matches any path ending with this pattern, not just those starting with it. Low practical risk but inconsistent.
- **Redirects #58 and #60** appear near-duplicate — both point `/blog/solo-bank-everything-you-need-to-know-about-bogs-premium-branch/` → slightly different targets. The first one (#59, different path) has a different source. Verify intent: #58 → `/blog/solo-bank-everything-you-need-to-know-bogs-premium-branch/` and #60 → `/blog/solo-bank-bogs-premium-branch/`. The second target seems to be the canonical short slug — rule #58 may be a stale duplicate.

**Also this date:**
- **301 redirect added:** `/ru/uslugi/lichnyj-schet-v-gruzinskom-banke` → `/ru/uslugi/lichnyj-schet-v-gruzinskom-banke/` (trailing slash). Polylang was issuing 301 for missing trailing slash with `x-kinsta-cache: MISS` — redirect now handled upstream.
- **301 redirect added:** `/services/hr-outsourcing-georgia` → `/services/hr-outsourcing-georgia/` (trailing slash). Same Polylang trailing-slash pattern as above; also the URL of the slowest request in the 2026-07-16 log window (21.9s via Sogou spider).

### 2026-07-15 — IPs Blocked via Denied IPs (Francesco, self)

- **IP blocked:** `34.185.133.109` — added to Kinsta Denied IPs list (MyKinsta → Tools → Denied IPs)
- **IP blocked:** `34.179.198.189` — added to Kinsta Denied IPs list (MyKinsta → Tools → Denied IPs). Same GCP-based crawler pattern as `34.185.133.109`; identified as the largest remaining source of slow-page generation in the 2026-07-15 log analysis.

### 2026-07-13 — DNS Moved to Kinsta DNS (Adrian, Kinsta Support)

- Domain pbservices.ge DNS management moved from personal Cloudflare to Kinsta DNS
- Kinsta nameservers set at registrar level; personal Cloudflare bypassed entirely
- Existing DNS records scanned and imported from Cloudflare to Kinsta

### 2026-07-10 — Nginx Security Rules (Uros, Kinsta Support)

**File blocks:**
- `/wp-admin/install.php` — blocked at Nginx level
- `/xmlrpc.php` — already blocked by Kinsta platform default (confirmed by support)

**URI keyword blocks:**
- `yinlang388` — blocked in request URI
- `388ym.com` — blocked in request URI
- Note: POST body inspection not possible at Nginx level — body-level spam not covered

**SQL injection query-string matching:**
- Keywords: `UPDATEXML`, `EXTRACTVALUE`, `GTID_SUBSET`, `UNION SELECT`, `ANALYSE(`, `/**/`
- ⚠️ Nginx does not URL-decode query strings — encoded variants (e.g., `%55PDATEXML`) bypass these rules. Full SQLi coverage requires a WAF.

**Rate limits:**
- `admin-ajax.php` (logged-out users): 60 req/min — logged-in users exempt (checked via `wordpress_logged_in` cookie)
- Search queries (`?s=`): per-IP, 20 req/min
- `wp-login.php`: kept default 6 req/min with burst (declined user's proposed 20 req/min)
- `ChatGPT-User` user-agent: 30 req/min, `burst=20 nodelay` — per-IP (keyed on `$binary_remote_addr`), applies only when UA matches "ChatGPT-User"

### 2026-07-08 — TLS Minimum Version Adjusted (Vladimir, Kinsta Support)

- TLS minimum changed from 1.3 to 1.2 to test ERR_HTTP2_PROTOCOL_ERROR fix
- Later reverted to 1.3 when change didn't resolve the issue
- Root cause identified as RAV Endpoint Protection on user's computer, not server-side

### 2026-07-05 — WP REST Cache Plugin Deactivated (Francesco, self)

- WP REST Cache plugin deactivated to eliminate potential interference with form submissions and REST API endpoints

### 2026-07-03 — Schema & Structured Data for WP Plugin Flagged (Chris/Ljiljana, Kinsta Support)

- Plugin generating PHP deprecation warnings on every page load due to PHP 8.5 incompatibility
- Recommended to update to latest version or contact developer for PHP 8.5 compatibility

### 2026-07-01 — Cron Interval (Ghassen, Kinsta Support)

- Server cron interval changed from default 15 minutes to **5 minutes** for all environments (live + staging)

### 2026-06-30 — Easy Optimizer Replaced with Autoptimize (Francesco, self)

- Easy Optimizer plugin uninstalled after Kinsta support identified its aggressive cache preload as a contributing factor to lead drops after cache clearing (preloader hitting 100+ pages/min across all language versions, saturating PHP workers)
- Easy Optimizer also generating errors accessing restricted system files on Kinsta's platform
- Replaced with Autoptimize (CSS/JS minification only, no caching features)

### 2026-06-27 — 404 Caching Disabled (Franchesco, Kinsta Support)

- Server configured to NOT cache 404 responses (was: cached for 15 minutes by default)
- Reduces amplification of intermittent Polylang 404s on translated pages

### 2026-06-27 — O2O Disabled, Switched to A Records (Kristiyan, Kinsta Support)

- O2O (Orange-to-Orange) Cloudflare proxy disabled
- DNS switched from CNAME records (proxied to Kinsta) to A records (DNS-only) pointing to `162.159.135.42`
- Both @ and www records set as A records with DNS-only status
- Purpose: eliminate double-caching from personal Cloudflare account

### 2026-06-27 — Force-Cache Rules Added (Fredrick, Kinsta Support)

- `?eopreload` query parameter: force-cache rule added (was causing 20,934 BYPASSes in 4 days)
- UTM tracking parameters: force-cache rule added (was causing ~1,200 MISSes in 4 days)
- Existing `?yclid` rule (added Jun 19) confirmed working

### 2026-06-21 — Redundant HTTPS Redirect Rules Removed (Franchesco/Ljiljana, Kinsta Support)

- Removed redundant "Force HTTPS" redirect rule from MyKinsta (duplicate of Cloudflare's own force HTTPS)
- Removed www redirect rule that was conflicting with O2O setup

### 2026-06-19 — DNS Fixed to Proxied (Edgar/Wilfredo, Kinsta Support)

- DNS CNAME records changed from "DNS only" (grey cloud) to "Proxied" (orange cloud) — Kinsta internal documentation requires proxied
- Added explicit WWW CNAME record (wildcard * alone insufficient for www)
- Kinsta-side Cloudflare misconfiguration resolved (previous host's CF zone clash fixed by sysadmins)
- Universal SSL disabled on user's Cloudflare account (conflicts with Kinsta SSL)
- Bot Protection reset to default (block malicious only) after testing

### 2026-06-19 — yclid Force-Cache Rule Added (Alessandro, Kinsta Support)

- `?yclid=` (Yandex Metrica) query parameter: custom force-cache rule added
- Yandex Metrica bot was generating many BYPASS requests with this parameter

### 2026-06-17 — DNS Pointing Confirmed (Ghassen, Kinsta Support)

- When using external Cloudflare DNS, CNAME records to Kinsta must be **proxied** (orange cloud)
- Domain pbservices.ge DNS management confirmed

---

## pbnova.com

### 2026-06-17 — Migration Completed (Cosmin, Kinsta Support)

- Site migrated to Kinsta. Backup available for 14 days in MyKinsta panel.
- Site is a multisite — sub-site DNS pointing may differ from primary domain.

---

## pbproperty.ge

### 2026-06-22 — Database Restored from Backup (Fredrick, Kinsta Support)

- Database restored from backup after transient cleanup operation caused timeout
- Kinsta's internal transient-clear tool also timed out due to volume (768K+ rows)
- Backup imported from `/public/pbp-database.sql.gz`

### 2026-06-17 — Migration Completed (Paola, Kinsta Support)

- Site migrated to Kinsta. Backup available for 14 days in MyKinsta panel.

---

## Template for New Entries

```markdown
### YYYY-MM-DD — Brief Description (Engineer Name, Kinsta Support)

**Action category:**
- Specific action taken — scope, parameters, limitations if any
- Another action — scope, parameters
```
