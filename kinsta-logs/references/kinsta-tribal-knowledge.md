# Kinsta Tribal Knowledge

Platform behaviors confirmed through direct Kinsta support interactions, not fully documented in the public Knowledge Base. Each entry cites the source transcript and describes what the skill should do differently because of this knowledge.

**Maintenance:** When a new support transcript confirms or refines a platform behavior, add an entry under the relevant category. Keep entries factual — state what was confirmed, by whom, and when.

---

## 🛡️ Default Kinsta Platform Behaviors

### Static Assets: Nginx `expires max` by Default
- **Fact:** Kinsta already sets `expires max;` in Nginx for all static asset types (`.txt`, `.xml`, `.js`, `.css`, images, fonts, media files). The CDN also caches these static assets for one year. Users do not need to add custom Nginx `expires` rules — they are already present.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing cache performance, note that static asset caching is already maximized at the server level. Do not recommend adding expires headers or static asset cache TTL changes.

### No CSP Headers by Default
- **Fact:** Kinsta does not add Content Security Policy (CSP) headers by default. Unless the user explicitly requested CSP headers via support, the Nginx configuration has none.
- **Source:** Kinsta Support Chat
- **Skill impact:** If the report or analysis mentions CSP-related issues, note that Kinsta has no default CSP — any CSP present comes from a plugin or custom support request.

### No Russian/Country-Specific Traffic Blocking by Default
- **Fact:** Kinsta does not block traffic from any specific country (including Russia) by default. IP-based blocking only occurs during DDoS attacks when a threshold is reached, and only the attacking IPs are blocked — not the entire country.
- **Source:** Kinsta Support Chat
- **Skill impact:** When the report shows traffic from Russia or other regions that might be flagged by geo-based firewalls, note that Kinsta does not block by country. Traffic drop-offs from specific countries are unlikely to be Kinsta-caused.

### xmlrpc.php Blocked by Default
- **Fact:** Kinsta blocks `/xmlrpc.php` at the platform level by default.
- **Source:** Kinsta Support Chat
- **Skill impact:** When the analyzer finds xmlrpc probe attempts in logs, note "Kinsta blocks xmlrpc.php at platform level — these are probe attempts, not successful accesses." Do not recommend blocking it — it's already blocked.

### Default wp-login.php Rate Limit
- **Fact:** Kinsta applies a default rate limit of 6 requests/minute with burst on `/wp-login.php`.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing brute-force patterns on wp-login.php, reference this 6 req/min baseline. Only recommend changes if the user explicitly requests a different limit (e.g., 20 req/min was proposed but the user chose to keep the default). A higher-than-6 count in logs does not mean the limit was exceeded — it means multiple IPs are attempting.

### Default Server Cron Interval
- **Fact:** The default Kinsta server-level cron interval is 15 minutes. Support can adjust it to 5 minutes (or other intervals) upon request.
- **Source:** Kinsta Support Chat
- **Skill impact:** If the analysis surfaces cron-timing-sensitive issues (e.g., scheduled tasks not running frequently enough), note the default interval and that support can adjust it.

### Static Assets Excluded from Rate Limiting
- **Fact:** Static assets (`.css`, `.js`, `.png`, `.jpg`, `.webp`) are excluded from rate limiting by default because they are served separately from PHP/dynamic requests.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending rate limits, note that static assets are already excluded — no need to add explicit exclusions. Do not recommend rate-limiting static asset paths.

### Memcache(d) NOT Supported on Kinsta
- **Fact:** Memcache/Memcached is not supported on Kinsta's platform and is known to cause both performance issues and various unexpected behaviors. If a Memcached drop-in or plugin is detected, it should be removed.
- **Source:** Kinsta Support Chat
- **Skill impact:** If the report or analysis detects Memcache(d) usage, flag it as incompatible with Kinsta — recommend removal.

### Mobile Edge Caching: Skip for Responsive Themes
- **Fact:** Kinsta's Mobile Edge Caching serves separate cached pages for mobile vs desktop. For sites using responsive themes (same HTML served to all devices), mobile edge caching provides no benefit and should remain disabled.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing cache configuration, note that mobile edge caching is only beneficial for sites with separate mobile/desktop themes. For responsive themes, it adds unnecessary complexity.

---

## 🔧 Nginx Rule Capabilities & Limitations

### Path-Based Blocks
- **Fact:** Kinsta support can add Nginx blocks for specific paths (e.g., `/wp-admin/install.php`). This is a straightforward `location` block.
- **Source:** Kinsta Support Chat
- **Skill impact:** When a finding involves unauthorized access to a specific path, recommend asking Kinsta support to add an Nginx path block.

### URI Keyword Matching
- **Fact:** Nginx can match keywords in the request URI (e.g., `yinlang388`, `388ym.com`). This uses `$request_uri` matching.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending spam/phishing keyword blocks in URLs, phrase as "ask Kinsta support to add URI keyword matching for [keyword]."

### POST Request Body Inspection — NOT SUPPORTED
- **Fact:** Nginx on Kinsta's infrastructure **cannot** inspect POST request bodies. Body-level filtering requires a WAF solution, which is outside the scope of what Kinsta support can configure in Nginx.
- **Source:** Kinsta Support Chat
- **Skill impact:** Never recommend "block POST requests containing [pattern]" — Kinsta cannot implement this at the Nginx level. Instead, recommend a WAF or application-level filtering.

### Query-String Keyword Matching — No URL-Decoding
- **Fact:** Nginx matches raw query strings **without URL-decoding**. A rule for `UPDATEXML` will NOT catch `%55PDATEXML` (URL-encoded variant). For full SQLi protection including encoded variants, a WAF is required.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending SQLi keyword blocks at the Nginx level, always append: "⚠️ Nginx does not URL-decode query strings — encoded variants (e.g., `%55PDATEXML`) will bypass this rule. Full coverage requires a WAF."

### Rate Limiting by IP + User-Agent
- **Fact:** Nginx rate limit zones can be keyed on `$binary_remote_addr` (client IP) combined with a conditional on `$http_user_agent`. Each IP with the matching UA gets its own independent rate limit bucket — it's not a global shared pool.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending rate limits for specific bots, describe the mechanism accurately: "per-IP rate limit triggered only for requests with [User-Agent]."

### Rate Limiting: Logged-In vs Logged-Out
- **Fact:** Nginx can differentiate logged-in from logged-out users by checking for the presence/absence of the `wordpress_logged_in` cookie. This enables path-specific rate limits that exempt logged-in users (e.g., rate-limit `admin-ajax.php` for logged-out users only).
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending rate limits on WordPress-specific paths (admin-ajax.php, wp-login.php), note that logged-in users can be exempted via cookie check.

### Rate Limiting: Burst + Nodelay
- **Fact:** Kinsta support can add `burst=N nodelay` to rate limit rules. This allows short bursts above the rate limit before throttling kicks in.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending rate limits for bots that exhibit bursty behavior (e.g., ChatGPT-User making 12 requests in one second), suggest a burst buffer: "ask Kinsta support to add `burst=20 nodelay` to the rate limit rule."

### Edge Caching/CDN Bypasses Nginx Rules
- **Fact:** When Edge Caching and/or Kinsta CDN are enabled, most requests are served from Cloudflare's edge cache and **never reach Nginx**. Nginx rules (path blocks, rate limits, keyword matching) only apply to cold-cache requests that reach the origin server.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending Nginx-level rules, note: "These rules apply only to requests that reach the origin server (cold cache). Requests served by Cloudflare's edge cache (~85% of traffic) bypass Nginx entirely."

### ChatGPT-User: Recommended Starting Rate
- **Fact:** Kinsta support recommended 30 requests/minute as a reasonable starting rate for ChatGPT-User. "This is generous enough that legitimate ChatGPT browsing or indexing won't be affected (normal crawling behavior is much slower), but it will catch any aggressive automated scraping."
- **Source:** Kinsta Support Chat
- **Skill impact:** When the report identifies excessive ChatGPT-User traffic, cite this Kinsta-vetted threshold as the recommended starting point for a rate limit.

---

## 📦 Cache Architecture Nuances

### Recommended Routine Cache Clearing
- **Fact:** For routine cache clearing after content updates, Kinsta support recommends clearing Server cache, CDN, and Edge Caching individually while keeping Redis (Object Cache) intact.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending a cache clear as a fix action, specify: "Clear Server Cache, CDN, and Edge Caching individually — avoid 'Clear All Caches' which also purges Redis and causes a temporary slowdown."

### PHP Addon Changes Trigger PHP Restart
- **Fact:** Activating or changing PHP performance add-ons triggers a PHP restart, which can cause temporary 502 errors during the restart window. This is normal and self-resolving.
- **Source:** Kinsta Support Chat
- **Skill impact:** If the error log shows 502 errors or PHP-FPM connection failures coinciding with a PHP configuration change window, note this as a likely explanation rather than a genuine outage.

### PHP Thread Limit: Brief Spikes Normal After Cache Clears
- **Fact:** Brief PHP thread limit spikes are normal after cache clears or admin maintenance — they don't indicate a problem on their own. Only repeated or extended periods of maxed-out threads are concerning, as those would affect site performance.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing PHP thread usage in performance data, distinguish between brief post-cache-clear spikes (normal) and sustained saturation (actionable). Don't flag transient spikes as issues.

---

## 🤖 Bot Protection Mechanism

### CF ML-Based Bot Scoring
- **Fact:** Kinsta's Bot Protection uses Cloudflare's ML-based bot scoring system (1-99 scale). Score 1 = definitely unauthorized bot, 2-29 = likely bot, 30-99 = likely human. Kinsta adds WordPress-specific tailored rules on top of Cloudflare's base classification and selectively reclassifies aggressive AI crawlers if they consume excessive server resources.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing bot traffic in logs that still reaches origin (i.e., was not blocked by Bot Protection), note the scoring context. Bots with scores 30+ pass as "likely human" — the fact they appear in origin logs means they were not blocked, not that protection is absent.

### "Block Automations" Setting
- **Fact:** "Block Automations" is the least aggressive Bot Protection setting. It targets automation tools/scripts rather than all bots. Support recommends testing on staging before enabling on production.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending Bot Protection configuration changes, note the aggression scale: Block Automations (least) → likely bots → all bots (most). Recommend starting with the least aggressive.

### Custom Bot Rules via Support
- **Fact:** Kinsta support can add custom bot rules (block/challenge/skip) based on IP, user-agent, country, or path. These are configured at Kinsta's Cloudflare level by support engineers — users cannot access the Cloudflare panel directly.
- **Source:** Kinsta Support Chat
- **Skill impact:** When the Bot Strategy section recommends blocking or challenging a specific bot, phrase the action as: "Ask Kinsta support to add a [block/challenge/skip] rule for [bot name / IP range / country]."

---

## 🌐 Cloudflare & DNS

### Kinsta's Cloudflare Enterprise Architecture
- **Fact:** Kinsta's Cloudflare Enterprise is Kinsta's own account. Users cannot access the Cloudflare panel directly to configure custom rules — all customizations go through Kinsta support. Users can also bring their own Cloudflare account and use it alongside Kinsta.
- **Source:** Kinsta Support Chat
- **Skill impact:** Never recommend "log into Cloudflare and add a rule" — users cannot access Kinsta's Cloudflare panel. Always phrase Cloudflare-level actions as "ask Kinsta support to..."

### DNS Pointing: CNAME Must Be Proxied
- **Fact:** When using an external Cloudflare account to manage DNS, CNAME records pointing to Kinsta must be proxied (orange cloud). Do not use DNS-only (grey cloud) or direct A records.
- **Source:** Kinsta Support Chat
- **Skill impact:** Not directly relevant to log analysis, but useful context if a report mentions DNS or domain configuration issues.

### DDoS, HTTP3, Firewall — Enabled by Default
- **Fact:** DDoS protection, HTTP3, and Kinsta's firewall are enabled by default for all Kinsta-hosted sites. No user action is needed.
- **Source:** Kinsta Support Chat
- **Skill impact:** When the report mentions DDoS or firewall concerns, note that Kinsta's defaults already cover this — no additional configuration is needed unless the user wants custom rules.

### DNS Propagation: Non-Proxied Causes Visit Drops
- **Fact:** When DNS is NOT proxied (DNS-only/grey cloud), changing DNS records causes the IP address to actually change for visitors. Some ISPs cache old DNS records for 1-2 days, causing visit drops during and after migration. When DNS IS proxied (orange cloud), Cloudflare's IPs remain stable regardless of backend changes — no propagation delay.
- **Source:** Kinsta Support Chat
- **Skill impact:** If a report shows visit drops coinciding with DNS changes or migration, note DNS propagation as a likely cause when records are not proxied. Recommend verifying proxied (orange cloud) status.

### Bot Protection Requires Domain Pointed to Kinsta
- **Fact:** The Bot Protection tool in MyKinsta returns an error if the domain is not yet pointed to Kinsta. Once the domain is pointed, the tool functions normally.
- **Source:** Kinsta Support Chat
- **Skill impact:** Not directly relevant to log analysis, but useful context if a report mentions Bot Protection configuration issues.

---

## 🏗️ Staging Environment

### Staging and Production Are Fully Isolated
- **Fact:** Staging and production environments run on completely separate containers with no shared services. Cache actions on staging (Clear All Caches, Clear Redis, Clear CDN, etc.) NEVER affect the production environment.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending cache-clearing as a troubleshooting step, note that staging actions are safe and isolated.

### Standard Staging Has Limited Caching
- **Fact:** Standard (non-premium) staging environments have limited caching: only Redis available by default. Edge Cache and CDN are NOT available in Standard staging.
- **Source:** Kinsta Support Chat
- **Skill impact:** If analyzing staging environment logs, expect different cache behavior than production.

---

## 📦 Cache Architecture: Query Parameters

### Query Parameters Bypass Cache by Default
- **Fact:** Kinsta only forces cache on specific known-safe query parameters (e.g., `?p=`). Any URL with a query string bypasses page cache by default. Support can add custom force-cache rules for specific safe parameters (e.g., `?yclid=`, `?eopreload`, UTM params) upon request.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing cache BYPASS rates correlated with query params, note this is normal default behavior. Recommend asking support to force-cache specific safe marketing/tracking params individually.

### Do Not Blindly Force Cache on All Queries
- **Fact:** Kinsta discourages blindly forcing cache on all query parameters — it will likely break features in WordPress or plugins (e.g., WooCommerce `?add_to_cart`). Each parameter must be evaluated individually.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending query-parameter cache fixes, specify individual safe parameters by name. Never recommend "cache all query parameters."

### Cache MISS Rate Naturally Higher on Multilingual Sites
- **Fact:** Sites with content in multiple languages have naturally higher cache MISS ratios because different language paths (/en/blog, /es/blog) mean different cache entries. This is expected.
- **Source:** Kinsta Support Chat
- **Skill impact:** When evaluating cache HIT rates, factor in language count. Don't flag as anomaly without accounting for language diversity.

---

## 📦 Cache Architecture: TTLs & Auto-Clearing

### Default Kinsta Cache TTLs
- **Fact:** Kinsta has three caching layers with distinct default TTLs: Server page cache = 24 hours, Edge cache = 24 hours, CDN = 1 year.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing cache expiration patterns, reference these defaults. A MISS after 24h is expected TTL expiry, not a problem.

### Server Cache Emptied Every 24 Hours at ≈Midnight UTC
- **Fact:** The server page cache is emptied (full purge) every 24 hours at approximately Midnight UTC. This is a scheduled platform-level cache reset, not triggered by content changes or TTL expiry. After this event, all subsequent requests will be cache MISS until the cache is repopulated by actual traffic.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing cache HIT/MISS ratios, check whether the log window spans a Midnight UTC cache-purge event. A cache-perf log that starts after midnight UTC will show a cold cache with near-zero HIT rate for the first hours, which is expected behavior, not a configuration problem. When the cache-perf window is short and post-midnight, explicitly note this in the Cache Root Cause analysis: the low HIT rate may be primarily a cold-start artifact, not representative of steady-state daytime performance. Also note that a MISS observed in the access log within a few hours after midnight UTC is likely a post-purge cold-start MISS, not a TTL-expiry MISS.

### Kinsta MU Plugin Auto-Clears Page Cache on Edits
- **Fact:** When editing a page in WordPress admin, Kinsta's MU plugin automatically clears the cache for: that specific page, the homepage, the blog page, and any paths added in Kinsta custom cache settings. It does NOT clear the entire site cache.
- **Source:** Kinsta Support Chat
- **Skill impact:** When the report shows cache MISS patterns coinciding with content update times, note that Kinsta's MU plugin auto-clears related caches — this is expected behavior, not a bug.

### Logged-In Users Always BYPASS Cache
- **Fact:** Kinsta does not cache requests from logged-in WordPress users, and it is not recommended to do so. All wp-admin and logged-in frontend requests show BYPASS by design.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing BYPASS rates, note that logged-in/admin traffic always bypasses. Do not flag wp-admin BYPASS as an issue.

### 404 Responses Cached for 15 Minutes by Default
- **Fact:** Kinsta caches 404 responses for 15 minutes by default. This can amplify intermittent 404s — a momentary glitch becomes 15 minutes of unavailability. Support can configure the server to not cache 404 responses.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing 404 patterns, note the 15-minute cache amplification. If intermittent 404s are found on translated/non-English pages, recommend asking support to disable 404 caching.

### Cache + Permalink Flush Combination: Polylang 404 Risk
- **Fact:** Flushing page cache AND permalinks simultaneously causes a brief window where Polylang rewrite rules are regenerating — translated URLs momentarily return 404. Combined with Kinsta's default 15-minute 404 caching, this turns a sub-second glitch into 15+ minutes of broken translated pages. Flushing page cache alone does NOT cause this; it's the permalink flush during the cache-cold window that triggers it.
- **Source:** Kinsta Support Chat
- **Skill impact:** When analyzing 404 patterns on multilingual sites, check whether cache + permalink flushes coincide. If translated-page 404s are found, recommend: (a) avoid flushing permalinks routinely — re-save Settings → Permalinks instead; (b) ask support to disable 404 caching; (c) clear only page cache (not Redis, not permalinks) for routine maintenance.

### `__cf_bm` Cookie — Cloudflare Bot Management
- **Fact:** The `__cf_bm` cookie (Set-Cookie header on responses) comes from Kinsta's platform-level Cloudflare Managed Protection. It is part of Cloudflare's Bot Management system and should NOT affect human visitors or the cache system. It is NOT a WordPress/plugin cookie.
- **Source:** Kinsta Support Chat
- **Skill impact:** When probe cross-match finds a `Set-Cookie: __cf_bm` header, do NOT misattribute it as a WordPress/Polylang cookie causing cache BYPASS. It's Cloudflare Bot Management — expected and harmless.

---

## 📦 Cache Architecture: Edge vs CDN

### Edge Cache vs CDN — Separate Layers
- **Fact:** Edge Cache stores cached full-page HTML at Cloudflare edge locations. CDN cache stores static assets only (CSS, JS, images, fonts). They are SEPARATE layers. Clearing CDN does NOT clear Edge. Clearing Site cache also clears Edge (Edge is an extension of the full-page cache layer).
- **Source:** Kinsta Support Chat
- **Skill impact:** Distinguish between Edge (page HTML) and CDN (static assets). A cache MISS on a static asset may indicate a CDN issue; a MISS on a page may indicate a Site/Edge issue.

### MyKinsta Cache Purge Button Reference
- **Fact:** "Clear All Caches" = Edge + CDN + Server + Redis; "Clear Site Cache" = Server + Edge (NOT CDN); "Clear CDN" = CDN static assets only; "Clear Object Caching" = Redis only. ⚠️ "Clear All Caches" includes Redis/Object Cache — avoid it for routine clears; clearing Redis causes temporary performance degradation while it rebuilds.
- **Source:** Kinsta Support Chat
- **Skill impact:** When recommending cache clearing, use exact button names and describe what each clears. For routine updates: CSS/JS only → Clear CDN; page HTML changes → Clear Site Cache (also clears Edge); both → Site + CDN. Avoid "Clear All Caches" unless a full reset is needed.

### Caching Plugins & Preloaders: Counterproductive on Kinsta
- **Fact:** Kinsta support warns that caching plugins "will deteriorate performance and, in most cases, will not work on our platform." Server-level caching is "much better than any plugin can do on a PHP level." Additionally, third-party cache preloaders (e.g., Easy Optimizer) are redundant with Kinsta's built-in edge caching/CDN and can actively harm performance by saturating PHP workers with aggressive crawls (100+ pages/min) after cache clears.
- **Source:** Kinsta Support Chat
- **Skill impact:** Never recommend installing/enabling a caching plugin or cache preloader. If one is detected, note that it's redundant with Kinsta's server-level caching and can cause PHP worker saturation during cache rebuilds.

### Stale Asset 404s After Plugin/Optimizer Removal — Normal, Not a Bug

- **Fact:** After uninstalling a plugin that generated hashed/versioned static assets (e.g., LiteSpeed Cache's JS optimization, Easy Optimizer's minified bundles), browsers, search engine crawlers, and security scanners continue requesting those stale asset URLs for months. Flushing all Kinsta caches (CDN, Edge, Server, Redis) does NOT stop these requests — those caches only control what Kinsta serves, not what external entities ask for.
- **Three sources of stale requests:**
  1. **Stale browser HTML caches** — a returning visitor's browser may hold cached HTML from months ago containing hardcoded `<script src="/wp-content/litespeed/js/abc123.js">` links. When the browser re-validates, it requests the stale URL from the server.
  2. **Crawlers and bots** — search engines (Googlebot, Bingbot) and malicious security scanners index old URLs from historical sitemaps or common vulnerability probe lists. They request these paths indefinitely until explicitly told to stop.
  3. **Service Workers (PWAs)** — if the removed plugin installed a Service Worker (`sw.js` or `service-worker.js`), it runs persistently in past visitors' browsers and continues fetching assets from its old manifest until explicitly unregistered.
- **Are real visitors seeing broken layouts?** No. Browser HTML cache rarely persists for months (typically hours to weeks). The requests seen in Kinsta access logs months after removal are almost certainly bots/crawlers/scanners, not human visitors staring at broken pages. A browser with fully stale cached HTML + expired CSS would see a broken layout, but this combination almost never survives months.
- **Mitigation options (in order of effectiveness):**
  1. **Nginx 410 rule (best)** — ask Kinsta support to add a rule returning `410 Gone` (not `404 Not Found`) for the removed directory. Search engines drop `410` URLs from their index much faster than `404`. Example: `"Please add an Nginx rule to return 410 for all requests hitting /wp-content/litespeed/js/"`. Kinsta already sets `expires max` on static assets, so the CDN caches these for 1 year — a CDN purge after adding the 410 rule ensures cached stale assets also get the 410.
  2. **MyKinsta Redirect tool** — add a 301 redirect from the stale asset path to a blank file or the active theme's stylesheet. This prevents broken layouts if a real browser ever hits the old URL. A 410 via Nginx is cleaner for SEO; a 301 is a panel-level workaround that doesn't need a support ticket.
  3. **robots.txt `Disallow`** — only effective for compliant bots; does nothing for scanners, service workers, or browsers.
  4. **Kill old Service Workers** — if the removed plugin was a PWA or used service workers, briefly upload a dummy `sw.js` with an `self.addEventListener('install', () => self.skipWaiting()); self.registration.unregister();` pattern to force unregistration in existing visitors' browsers.
- **Source:** Kinsta Support Chat — confirmed that stale asset 404s months after plugin removal are normal and expected, not a configuration defect. The CPU cost of WordPress booting PHP just to serve a 404 for a static file is the real concern — a 410 Nginx rule eliminates this entirely by handling the request at the web-server layer before PHP loads.
- **Skill impact:** When the report shows `/wp-content/litespeed/js/` or similar stale hashed-asset 404s from a plugin removed months ago, do NOT recommend cache clearing (it won't help). Note that these are bot/crawler-origin requests, not broken visitor experiences. Recommend the Nginx 410 rule as the permanent fix and a CDN purge to clear cached 404 responses. If the volume is low (under ~20/day as in this report), note that natural decay will reduce them over time as CDN/browser caches expire — the 410 rule is a "clean up permanently" option, not an emergency.

## 🖼️ CDN Image Optimization

### Cloudflare Polish: `cf-polished: webp_bigger`
- **Fact:** When Lossy compression is enabled, Cloudflare Polish first compresses JPEG at quality 85 (`cf-bgj: imgq:85` header), then attempts WebP conversion. If the WebP output is larger than the already-compressed JPEG, it serves the JPEG with `cf-polished: webp_bigger` header. This is expected behavior, not a bug.
- **Source:** Kinsta Support Chat
- **Skill impact:** If analyzing image optimization or cache headers, recognize `cf-polished: webp_bigger` as normal behavior for already-optimized images. Do not flag it as an optimization failure.

---

### O2O Traffic Flow & Double-Caching
- **Fact:** Traffic routes through user's Cloudflare FIRST, then Kinsta's Cloudflare Enterprise. User's CF caches assets before they reach Kinsta — both layers may serve cached copies and both may need purging separately. User's rules apply first; Kinsta's are non-overridable. For images: if user's CF caches first, Kinsta's Polish may not apply. `ki-edge-o2o: yes` header confirms active O2O; `ki-cf-cache-status: OPTIMIZING` means Kinsta's CDN is still processing.
- **Source:** Kinsta Support Chat
- **Skill impact:** When cache or image optimization issues appear with O2O active, note both caches may need purging and user's CF may serve stale/unoptimized copies. When recommending Cloudflare-level actions, note the dual-layer architecture — user's rules apply first but cannot override Kinsta's.

### DNS Records: A Records (DNS-Only) vs CNAME (Proxied)
- **Fact:** To use ONLY Kinsta's Cloudflare (bypassing personal CF), use A records pointing to Kinsta IP (`162.159.135.42`) with DNS-only (not proxied). To use O2O, use CNAME records pointing to `{site}.hosting.kinsta.cloud` with proxied (orange cloud). Both setups are supported.
- **Source:** Kinsta Support Chat
- **Skill impact:** Not directly relevant to log analysis, but useful context for DNS/connectivity issues.

### Kinsta DNS as Alternative
- **Fact:** Kinsta offers its own DNS management as an alternative to personal Cloudflare DNS. Kinsta DNS can scan and import existing DNS records from Cloudflare.
- **Source:** Kinsta Support Chat
- **Skill impact:** Not directly relevant to log analysis, but useful context for DNS simplification recommendations.

### Universal SSL Must Be Disabled on User's Cloudflare
- **Fact:** Universal SSL in the user's own Cloudflare account conflicts with Kinsta's SSL certificate issuing. Kinsta SSL certs are issued from Cloudflare Enterprise and renewed every 90 days.
- **Source:** Kinsta Support Chat
- **Skill impact:** Not directly relevant to log analysis, but useful if SSL/certificate errors appear.

### TLS Minimum Version Configurable
- **Fact:** Kinsta can change the minimum TLS version. Default is 1.3 only. Can be set to 1.2 minimum (allows both 1.2 and 1.3). TLS 1.3 is faster and more secure, but 1.2 fallback can help with enterprise/corporate network middleboxes.
- **Source:** Kinsta Support Chat
- **Skill impact:** If ERR_HTTP2_PROTOCOL_ERROR appears in error patterns, note that TLS version may be a factor — support can adjust the minimum.

### Kinsta API Not Accessible
- **Fact:** Users cannot access Kinsta's Cloudflare integration via API token. The Cloudflare panel is entirely managed by Kinsta.
- **Source:** Kinsta Support Chat
- **Skill impact:** Never recommend "use the Cloudflare API" — it's not accessible.
