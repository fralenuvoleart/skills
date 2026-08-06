# Operational Playbook — Kinsta Log Analyzer

Expert-level guidance for each anomaly type found in the report.

---

## Cache Health

### HIT Rate Too Low (<50%)

**Why it matters**: Every MISS hits the origin server (PHP + database), consuming resources and slowing response. A 50% HIT rate means half your traffic is uncached.

**Diagnose**:
1. In MyKinsta → Edge Caching, check which URLs are MISSing.
2. Look for BYPASS patterns in the cache-perf log: query strings (`?page=2`, `?utm_source=...`), cookies, or `wp-admin` paths.
3. Check if you have cache exclusion rules in MyKinsta that are too broad.

**Fix**:
- **Query strings**: WordPress pagination (`?page=`) and UTM tracking params bypass Kinsta cache. Consider using path-based pagination or excluding marketing URLs from cache expectations.
- **Cookies**: Any `Set-Cookie` response header prevents caching. Common causes: WooCommerce cart, wpForo sessions, comment cookies on pages with closed comments.
- **Cache warming**: After deploys or cache clears, run a crawler (e.g., `wget --mirror`) against your sitemap to pre-warm the edge cache.
- **Kinsta edge cache exclusions**: In MyKinsta → Edge Caching, add paths that should NEVER be cached (e.g., `/checkout/`, `/my-account/`) so MISSes there don't dilute your HIT ratio.

### BYPASS Rate Too High (>10%)

**Normal BYPASS**: `wp-cron.php`, `/wp-admin/*`, sitemaps, API endpoints.

**Abnormal BYPASS**: Public-facing pages with query strings or cookies.

**Fix**:
- Check DB for `wordpress_logged_in_*` cookies set on pages that don't need them (plugin conflict).
- Audit marketing UTM params — consider stripping them via JavaScript redirect or server-side before the request hits WordPress.
- In MyKinsta → Edge Caching → "Force cache for URLs with query strings", selectively enable for known-safe params.

### MISS Response Times >1s

The origin server is slow. Common causes:
- **Uncached WP REST API calls blocking the main thread**
- **Heavy database queries** on uncached pages — use Kinsta APM to trace
- **External API calls** during page generation (currency converters, chat widgets)
- **PHP worker exhaustion** — check MyKinsta → Resource Usage for PHP worker limit hits

---

## Bot Traffic Management

**Before choosing a mitigation, read [`bot-taxonomy.md`](bot-taxonomy.md)** — it tells you which
bots are autonomous crawlers vs. real-time user-triggered agents, which ones have a documented
compliance mechanism, and which mitigation tier will actually have an effect for that specific bot.
Do not skip straight to blocking based on raw request count alone.

### ⚠️ Crawl-Delay does not work on most AI/answer-engine bots

`Crawl-delay` is a non-standard robots.txt extension. Only Bingbot, YandexBot, AhrefsBot,
SemrushBot, and MJ12bot have documented support for it. **GPTBot, ChatGPT-User, OAI-SearchBot,
ClaudeBot, PerplexityBot, Bytespider, Amazonbot, Applebot, and Googlebot do not** — Googlebot
explicitly says to use Search Console instead, and the AI-crawler operators' own robots.txt docs
only mention `Disallow`/`Allow`. Recommending `Crawl-delay:` for any of these bots is very likely a
silent no-op. See [`bot-taxonomy.md`](bot-taxonomy.md#the-crawl-delay-correction-read-first) for
the full compliance matrix before writing this recommendation into any report.

### Identify the Threat

Look at the access log for:
- Single IP hitting many URLs rapidly (look for same IP in top list with >20 req)
- User agents like `Go-http-client`, `python-requests`, or empty UAs
- Requests to nonexistent paths (scanner behavior)
- **Check the ASN/Provider column** (added to the Top Visitor IPs / Scanner IPs tables) — a
  "hosting/proxy" tag means the country flag next to it does not represent a real visitor's
  location; it's infrastructure. Don't build a mitigation plan around a misread geo-IP tag.

### Mitigation Tiers (ordered by reliability, not effort)

**Report-writing note:** only Tiers 2–4 below are things the report's reader can act on directly
from MyKinsta or a support ticket. An application-level UA throttle (internal-reference-only —
see `bot-taxonomy.md`'s "Internal-Reference-Only" section) may already exist in the hosted app's
own code; use that fact only to judge severity ("already mitigated" vs. "needs escalation"),
never cite it by file/constant/function name in the generated report — see Step 6.5 of `SKILL.md`.

1. **Application-level User-Agent throttle** (most reliable for AI/answer-engine bots without
   stable published IP ranges, if the hosted app has one): returns HTTP 429 before WordPress loads,
   keyed by real client IP, works regardless of whether the bot honors robots.txt. This is a
   code-level mechanism the report's reader (an infrastructure manager) cannot adjust from MyKinsta
   — treat its presence/absence as input to your severity judgment only, and phrase any resulting
   report recommendation generically ("flag this for whoever maintains the site's code"), never by
   naming the mechanism.

2. **Kinsta IP Deny** (MyKinsta → Tools → Denied IPs): guaranteed at the nginx layer, but only
   works if the bot's operator publishes stable IP ranges (OpenAI does, for GPTBot/ChatGPT-User/
   OAI-SearchBot; ByteDance does not for Bytespider, making this tier unusable against it).

3. **robots.txt `Disallow`** (best-effort only): works only for bots documented AND observed to
   comply. See the compliance matrix in [`bot-taxonomy.md`](bot-taxonomy.md) before assuming this
   will have any effect — do not pair it with `Crawl-delay` for bots that don't support it.

4. **Kinsta support ticket for `limit_req` nginx zones, or Cloudflare WAF** (if Cloudflare sits in
   front of Kinsta): use when Tiers 1–3 don't apply or aren't actionable by the reader — e.g.
   non-WordPress traffic, or an application-level throttle not being something they can adjust
   themselves. This is usually the correct *visible* escalation to put in the report.

5. **WordPress-level blocking** (Wordfence, BBQ Block Bad Queries, `.htaccess` `Deny from`): lowest
   priority — redundant with Tier 1 for UA-based throttling if an application-level mechanism
   already runs earlier in the request lifecycle.

### Legitimate Bot Balance — Apply the Same Criteria to Every Bot

Don't default to "keep Western bots, block others." Apply the same three questions from
[`bot-taxonomy.md`](bot-taxonomy.md) to every bot: what does it actually do, does it comply with
any stated mechanism, and does it feed a product whose users overlap this site's actual audience.
Googlebot/Bingbot pass on all three for virtually any site and should always be kept; regional or
AI-answer-engine bots need the specific per-bot assessment in that reference, not a blanket rule.

---

## Error Response Patterns

### 5xx Errors (Server Errors)

These mean visitors saw error pages.

**Immediate actions**:
1. Check MyKinsta → Analytics → HTTP Status Codes for the 5xx trend (spike or constant).
2. Enable Kinsta APM to capture full traces of failing transactions.
3. Check PHP error log for corresponding fatal errors at the same timestamp.
4. If correlated with high traffic, check PHP worker limits (MyKinsta → Resource Usage).

**Common fixes**:
- **PHP memory exhaustion**: increase `memory_limit` in MyKinsta → Tools → PHP Engine.
- **PHP worker exhaustion**: upgrade PHP workers or optimize slow endpoints.
- **Plugin/theme fatal errors**: roll back recent deploys, check error log for the file and line.

### 403 Forbidden Spikes

- Normal: Kinsta nginx blocks directory listing by default — scan bots get 403.
- Abnormal: legitimate users getting 403 from IP Deny or WAF rules.
- Check MyKinsta → Tools → Denied IPs for overly broad CIDR blocks.

### 404 Not Found

- Top 404 URLs in the access log → redirect or fix broken links.
- If from a specific referrer, contact the linking site.
- Set up 301 redirects in WordPress (Redirection plugin) or nginx.

---

## Response Time Optimization

### Pages >2s

**Diagnose** with Kinsta APM:
1. Sort transactions by duration.
2. Look for slow MySQL queries (often the #1 cause).
3. Check external HTTP calls (API integrations, webhooks).

**Kinsta-specific optimizations**:
- Enable **Edge Caching** for static assets (CSS/JS/images already cached by Kinsta CDN).
- Use Kinsta's **Image Optimization** (lossy/lossless) to reduce payload size.
- Verify PHP version is 8.0+ (MyKinsta → Tools → PHP Engine) — PHP 8.x is 2-3x faster than 7.x.
- Check MyKinsta → Resource Usage → PHP workers: if frequently hitting the limit, upgrade.

---

## Traffic Spikes

### Sudden Traffic Increase

**Determine if legitimate**:
- Check top IPs — are they known bots or real visitors?
- Check top URLs — news article going viral, or DDoS?
- Check referrers — social media, news aggregators, or none?

**If legitimate** (viral content):
- Edge cache should absorb most requests to cached pages.
- Monitor PHP worker usage — only uncached dynamic requests hit PHP.
- Consider temporarily upgrading PHP workers.

**If attack** (DDoS):
- Contact Kinsta support immediately — they have DDoS mitigation at the network edge.
- Enable Kinsta's DDoS protection in MyKinsta if not already on.
- Block source IPs/networks in MyKinsta → Tools → Denied IPs.

---

## SSL & Security

### SSL Certificate Issues

- Check MyKinsta → Domains → SSL certificate expiry.
- Kinsta auto-renews Let's Encrypt certs — manual action only needed for custom certs.
- If using Cloudflare, ensure SSL mode is "Full (strict)".

### Suspicious Login Attempts

- Look for repeated POST to `/wp-login.php` or `/xmlrpc.php` from same IP.
- Block in MyKinsta → Tools → Denied IPs.
- Consider disabling XML-RPC if not needed (Kinsta can do this at nginx level).
