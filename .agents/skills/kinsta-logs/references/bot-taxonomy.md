# Bot Taxonomy — Accurate, Unbiased Reference

**Read this file in Step 5 (Analyst Commentary) before writing ANY bot-related recommendation.**
It exists because generic "block the Chinese bots, keep the Western ones" reasoning is both
factually wrong (misidentifies what several bots actually do) and analytically lazy (applies a
nationality heuristic instead of the same objective criteria to every bot). Every verdict below
follows the same three questions — apply them yourself to any bot not yet listed here:

1. **What does this bot actually do, and who triggers it** — autonomous batch crawler, or a
   real-time agent triggered by a live human action?
2. **Does it have a documented compliance mechanism**, and does it actually honor it
   (`Disallow` vs. the non-standard `Crawl-delay` directive vs. neither)?
3. **Does it feed a product with users who overlap this site's actual target audience** — judged
   by language/region relevance, never by the bot vendor's country of origin alone?

---

## Contents
- [ASN Is Not Enough — Always Check Reverse DNS Too](#asn-is-not-enough)
- [The Crawl-Delay Correction (read first)](#the-crawl-delay-correction-read-first)
- [AI Assistant / Answer Engine](#ai-assistant--answer-engine)
- [Search Engine Crawlers](#search-engine-crawlers)
- [SEO / Marketing Crawlers](#seo--marketing-crawlers)
- [Social Media Link-Preview Fetchers](#social-media-link-preview-fetchers)
- [Regional / High-Volume Crawlers (assessed without bias)](#regional--high-volume-crawlers-assessed-without-bias)
- [Mitigation Tiers](#mitigation-tiers)

---

<a name="asn-is-not-enough"></a>

## ASN Is Not Enough — Always Check Reverse DNS Too

**A confirmed real miss from an earlier analysis run**: an IP was reported as "Google LLC" (ASN
lookup only) and assumed to be either a residential visitor or vaguely "some Google service."
The reverse-DNS (PTR) record — `googleusercontent.com` — revealed it was actually a **third
party's customer VM rented on Google Cloud**, completely unrelated to Google. The ASN/org lookup
alone cannot make this distinction; it only tells you who owns the IP block, not who is actually
running the traffic. **Always check both** (`ip_org()` for the ASN, `ip_hostname()` for the PTR
record — both implemented in `scripts/analyze_logs.py` and included in the Top Visitor IPs,
Scanner IPs, slowest-requests, and Bursts sections of the generated report).

Known PTR patterns worth recognizing on sight:

| PTR pattern | Meaning |
|---|---|
| `*.googleusercontent.com` | Google Cloud **customer** VM — NOT Google's own crawler infrastructure (Google's own bots resolve under `googlebot.com`/`google.com`) |
| `*.compute.amazonaws.com` / `*.amazonaws.com` | AWS EC2 **customer** VM — NOT Amazon's own crawler infrastructure |
| `*.siteaudit.bot.semrush.com` | **Confirmed** genuine Semrush site-audit infrastructure (not spoofed) |
| `*.dataproviderbot.com` | **Confirmed** genuine Dataprovider.com crawler |
| `*.contaboserver.net`, `*.ovh.net`, similar generic VPS PTR | A customer's rented VPS — could be anything from a legitimate monitoring tool to a scanner; the hostname alone doesn't tell you which, but it does tell you it's not the "vendor" implied by an ASN like "Contabo GmbH" (Contabo is a hosting company, not a bot operator) |
| AWS IPs with `no PTR record` under AS16509 | **Do NOT assume spoofing.** Anthropic (ClaudeBot) runs its crawlers on AWS infrastructure (Amazon is Anthropic's primary cloud partner and investor). The subnet `216.73.216.0/22` is officially reassigned to Anthropic, PBC per WHOIS — an AWS IP with no PTR under this range is a genuine Anthropic crawler, not a third-party VM. Same caution applies to other AI companies that may host crawlers on their cloud provider's IP space without custom PTR records. |

**Practical effect**: a PTR record under the bot operator's OWN domain (e.g. `bot.semrush.com`,
`dataproviderbot.com`) is positive confirmation the traffic is genuinely who it claims to be —
stronger evidence than the User-Agent string alone, which can be spoofed. A PTR record under a
generic cloud/VPS customer domain (`googleusercontent.com`, `contaboserver.net`) means the ASN
owner is just the landlord — the actual operator is unknown and must be judged by behavior
(request pattern, target URLs), not assumed from the ASN name.

---

## The Crawl-Delay Correction (read first)

`Crawl-delay` is a **non-standard** robots.txt extension. It is only meaningful for bots whose
operator has explicitly documented support for it. Do not recommend `Crawl-delay:` for any bot
not in the "Documented Crawl-delay support" list below — for everything else it is very likely a
silent no-op, and telling the site owner it will help is giving them false confidence.

| Documented `Crawl-delay` support | No documented `Crawl-delay` support (Disallow/Allow only, or nothing) |
|---|---|
| Bingbot, YandexBot, AhrefsBot, SemrushBot, MJ12bot, ClaudeBot | GPTBot, ChatGPT-User, OAI-SearchBot, PerplexityBot, Google-Extended, Bytespider, Amazonbot, Applebot, Googlebot (Google explicitly ignores it — use Search Console crawl-rate settings instead) |

**Consequence for AI/answer-engine bots specifically:** the only two levers that actually work are
(a) a full `Disallow` in robots.txt — which only works if the operator honors robots.txt at all
(compliance varies per bot, see tables below) — or (b) a hard technical block/throttle that doesn't
depend on the bot's cooperation (Kinsta Denied IPs, or this plugin's own MU-level throttle — see
[Mitigation Tiers](#mitigation-tiers)). Never present `Crawl-delay` as a solution for these bots.

---

## AI Assistant / Answer Engine

| Bot | Operator | What it actually is | Triggered by | robots.txt compliance |
|---|---|---|---|---|
| **ChatGPT-User** | OpenAI | **NOT a crawler.** A real-time retrieval agent that fetches a *specific* URL only when a live human asks ChatGPT to browse it, or a Custom GPT Action calls it. One human question → one (or a few) fetches. | Live human, per-request | Honors `Disallow` (self-reported); no `Crawl-delay` |
| **GPTBot** | OpenAI | Autonomous bulk crawler used to source model-training data. | Scheduled batch crawl | Honors `Disallow` (self-reported); no `Crawl-delay` |
| **OAI-SearchBot** | OpenAI | Autonomous crawler that builds the index behind **ChatGPT Search**. Functionally analogous to Googlebot, but for ChatGPT's search feature. | Scheduled batch crawl | Honors `Disallow` (self-reported); no `Crawl-delay` |
| **ClaudeBot** | Anthropic | Autonomous crawler for Claude's training data and web-citation/search features. | Scheduled batch crawl | Honors `Disallow` (self-reported); supports `Crawl-delay` |
| **PerplexityBot** | Perplexity AI | Autonomous crawler that builds Perplexity's answer-engine index. | Scheduled batch crawl | Self-reported `Disallow` support — **note**: Perplexity has faced public, documented accusations (e.g. from Cloudflare in 2024) of crawling sites that explicitly disallowed it. Treat compliance as unverified in practice, not assumed. |
| **Google-Extended** | Google | Not a separate crawler — a **control token**. Governs whether content Googlebot already crawled may be used for Gemini/AI Overviews, independent of normal Search indexing opt-out. | N/A (token, not a UA making requests) | Honors `Disallow` for this specific token |

**Diagnostic step, not optional:** before recommending any action on `ChatGPT-User`, check whether
its requests concentrate on a **narrow set of URLs** (consistent with real users asking about
specific pages — a positive signal that people are discussing/citing this content) or are
**scattered across many distinct/unique URLs** (consistent with a Custom GPT Action doing bulk
lookups, which behaves more like a crawler despite the UA). The per-bot "Top URLs" data in the
generated report (Step 3) tells you which pattern applies — cite the actual concentration ratio in
your commentary, don't guess.

---

## Search Engine Crawlers

| Bot | Operator | Primary market/product | robots.txt compliance | Default recommendation |
|---|---|---|---|---|
| **Googlebot** | Google | Google Search — global | Full compliance (reference implementation); ignores `Crawl-delay`, use Search Console instead | Keep, always |
| **Bingbot** | Microsoft | Bing Search + Copilot's index | Full compliance, documented `Crawl-delay` support | Keep, always |
| **YandexBot** | Yandex | Dominant search engine in Russia/CIS | Full compliance, documented `Crawl-delay` support | Keep if any CIS/Russian-speaking audience exists |
| **Baiduspider** | Baidu | Dominant search engine in mainland China | Generally honors `Disallow`, but has had periods of reported aggressive/non-compliant crawling — verify current volume before trusting blindly | **Case-by-case** — see below, not a blanket keep or block |
| **DuckDuckBot** | DuckDuckGo | DDG's own supplementary index (DDG mostly reuses Bing's index) | Full compliance | Keep — negligible volume, no downside |

**Baiduspider "monitor, don't guess" rationale:** the correct default is neither "keep" nor "block"
— it is "measure, then decide." Ask: (1) does this site have `/zh/` or other Chinese-targeted
content? (2) does analytics show any actual Chinese-locale conversions/engagement, or only bot
traffic and unrelated spam (e.g. gambling-URL injection attempts, which indicate unwanted rather
than wanted Chinese-web attention)? (3) is the crawl volume proportionate to (1) and (2)? If the
site has real Chinese-market business value and volume is proportionate, keep. If volume is
disproportionate to any measurable Chinese-market return, throttle via this plugin's MU-level
mechanism (see below) rather than blocking outright — Baidu compliance drift means a soft
`Disallow` alone is not guaranteed to work.

---

## SEO / Marketing Crawlers

| Bot | Operator | What it's for | robots.txt compliance | Value to *this* site (not the bot's operator) |
|---|---|---|---|---|
| **AhrefsBot** | Ahrefs | Backlink/SEO index sold as a SaaS product | Documented `Crawl-delay` support | Valuable **only if you personally use Ahrefs**; otherwise it is mostly competitors auditing your backlinks — zero direct value to you |
| **SemrushBot** | Semrush | Same category as Ahrefs | Documented `Crawl-delay` support | Same logic as AhrefsBot |
| **MJ12bot** | Majestic | Backlink index (Majestic SEO) | Documented `Crawl-delay` support | Same logic — valuable only to Majestic subscribers |
| **Dataprovider** | Dataprovider.com | Commercial web-data harvesting resold to third parties | No documented compliance mechanism found | No SEO value to the site at all — pure third-party data resale |

**Rule of thumb:** these bots only benefit *you* if you are a paying customer of that specific SEO
tool. If not, throttling/blocking has zero downside — this has nothing to do with "aggressiveness,"
it's a straightforward value calculation.

---

## Social Media Link-Preview Fetchers

| Bot | Operator | Nature | Recommendation |
|---|---|---|---|
| **facebookexternalhit** | Meta | Fetches a URL **only when a user shares/pastes it** on Facebook, Instagram, WhatsApp, or Messenger — not a crawler | Always keep — blocking breaks link previews across all Meta apps |
| **Twitterbot** (X) | X Corp | Same nature, triggered by a share/paste on X | Always keep |
| **LinkedInBot** | LinkedIn | Same nature | Always keep |
| **Discordbot** | Discord | Same nature, triggered by a link pasted in a Discord server/DM | Always keep |
| **Applebot** | Apple | Powers Siri, Spotlight, Safari previews, and (via the separate `Applebot-Extended` token) Apple Intelligence training opt-out | Keep — blocking removes the site from Siri/Spotlight results on every Apple device |

---

## Regional / High-Volume Crawlers (assessed without bias)

These are the bots most often flagged for blocking. Each one gets the **same three-question
framework** applied — the verdicts differ because the facts differ, not because of the operator's
home country.

| Bot | Operator | What it actually does | robots.txt compliance | Audience relevance | Verdict |
|---|---|---|---|---|
| **Bytespider** | ByteDance (TikTok's parent) | Crawls for ByteDance's products, most critically **Doubao** — China's #1 consumer AI search engine with 260M+ monthly active users (surpassed Baidu in Q1 2026). Also feeds TikTok/Toutiao content recommendation. Functionally analogous to Googlebot: a search-index crawler that also feeds AI training. | **Widely and repeatedly documented to ignore `Disallow`** (reported by Cloudflare, Originality.ai, DataDome, and many independent site operators) — non-compliance is confirmed, not alleged. | **Case-by-case — do NOT blanket-block.** If the site has Chinese-language content (`/zh/`) targeting a Chinese-speaking audience, Doubao is the dominant discovery surface for that market — blocking Bytespider removes the site from China's largest search engine. If the site has zero Chinese content and no Chinese-market relevance, low volume can be tolerated; disproportionate volume warrants throttling. | **Measure first, then decide** — same framework as Baiduspider. Ask: (1) does this site have `/zh/` or other Chinese-targeted content? (2) is crawl volume proportionate to that content? If yes to both → **keep** (non-compliance with robots.txt is a real concern, but losing visibility on China's #1 search engine is a bigger one — `Disallow` is best-effort, not guaranteed). If no ZH content or volume is disproportionate → **throttle** rather than hard-block (Doubao's market share means even sites without Chinese content may get incidental Chinese-audience traffic worth preserving). |
| **PetalBot** | Huawei | Crawls for Huawei's Petal Search, used on Huawei/Honor Android devices and some Huawei AI features | Inconsistent compliance reported by site operators | Huawei device penetration is meaningful in parts of the CIS, Middle East, and Eastern Europe — **not automatically irrelevant** for a Georgia-based site | **Do not blanket-block.** Check actual device/browser analytics (if available) for Huawei/Honor share among real visitors before deciding; if volume is disproportionate to any measurable relevance, throttle rather than hard-block |
| **Amazonbot** | Amazon | Crawls to improve **Alexa's voice-assistant answers** and Amazon's AI-driven product/answer features — this is *not* only an e-commerce-seller crawler, a common misconception | **Documented to honor `Disallow`** — this is a policy-compliant bot, unlike Bytespider | Relevant only if voice-assistant/Alexa answer visibility matters to the business; otherwise low direct value | Compliant + low relevance ≠ block-worthy on security grounds. If volume is high, prefer `Disallow` (it will actually work) over a hard block. Do not lump it in with Bytespider/scanner bots just because the raw request count is high — the *reason* for high volume matters. |

**Why this table matters:** notice that the verdicts don't correlate with country of origin —
Amazonbot (US) gets a "compliant, don't hard-block" verdict for objective reasons (documented
compliance + low relevance), Bytespider (China) gets a "measure first, keep if ZH content exists"
verdict under the same three-question framework (non-compliance is a real concern, but blocking
China's #1 search engine from a site with Chinese-language content is self-defeating), and
PetalBot (China) gets a "measure first" verdict identical to Baiduspider's. Apply this same test
to any bot not listed here rather than defaulting to a nationality heuristic.

---

## Mitigation Tiers

Ordered by reliability, not by effort. **Every tier here is something the report's reader can
actually act on from MyKinsta, robots.txt, or a support ticket — this skill never reads, checks, or
references the hosted application's own source code for bot mitigation, at any tier** (see
`SKILL.md`'s Scope and Step 6.5).

| Tier | Mechanism | Reliability | When to use |
|---|---|---|---|
| 1 | `robots.txt` `Disallow` | **Best-effort only** — works only if the specific bot is documented AND observed to comply | First try, for any compliant bot, especially ones without published IP ranges to block |
| 2 | Kinsta → Tools → Denied IPs (MyKinsta) | Guaranteed at the nginx layer, but requires the vendor to publish stable IP ranges (OpenAI publishes ranges for GPTBot/ChatGPT-User/OAI-SearchBot at platform.openai.com; many others, including Bytespider, do not) | When IP ranges are published and stable |
| 3 | Kinsta support ticket for `limit_req` nginx zones, or Cloudflare WAF rules (if Cloudflare sits in front) | Guaranteed, but requires an external request/config change | When Tiers 1–2 don't apply (no published IP ranges, or the bot doesn't honor `Disallow`) |
| 4 | Honest "no Kinsta-panel or documented fix exists for this pattern — flag it for whoever maintains the site's code" | N/A — explicitly the fallback, not a mechanism | When Tiers 1–3 genuinely don't cover the pattern (e.g. a bot spread across too many distinct IPs for rate-limiting to matter, with no published range to block) |
