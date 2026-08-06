# Kinsta API — Log Retrieval Constraints

**Read this file before fetching or interpreting logs.** It documents API behavior, line-count estimates, log rotation handling, and the critical origin-vs-edge-cache scope distinction that must be stated in every report.

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
- **`kinsta-cache-perf` log data is pulled from Cloudflare logs for the site.** ≈85% of all requests
  are served by Cloudflare's Edge cache and never reach Nginx. Only ≈15% pass through Cloudflare to
  Nginx — broken down as dynamic (≈13.5%), miss (≈1%), and bypass (≈0.5%). Nginx handles page
  caching for these remaining 15%, and the `kinsta-cache-perf` log's HIT/MISS/BYPASS data represents
  the cache status for this subset only — not total site traffic. When interpreting cache HIT rates
  from this log, remember: a 60% HIT rate here means 60% of 15% = ≈9% of total traffic got an
  Nginx page-cache HIT, on top of the ≈85% already served by Cloudflare's edge cache (combined
  ≈94% of all requests served from cache).

  **⚠️ The cache-perf log's HIT rate is a narrow-scope snapshot, NOT an authoritative full-day
  cache health metric.** Two reasons it will often disagree with MyKinsta's "Server cache"
  dashboard number:
  1. **Time window:** the log covers only its fetch window (often 3–5 hours), while the dashboard
     covers the full 24h day. Any 3-hour slice of an hourly-varying metric can differ from the
     24h average purely from sampling a different mix of traffic.
  2. **Scope:** the log is Nginx page cache only (the ≈15% origin-reaching subset); the dashboard
     may aggregate across multiple cache layers.

  **Never present the cache-perf HIT rate as "the" cache health verdict without stating its time
  window and Nginx-page-cache scope.** When the user provides a dashboard number that differs, cite
  both numbers, explain the gap (time window + scope), and identify the dashboard as the
  authoritative full-day metric.


