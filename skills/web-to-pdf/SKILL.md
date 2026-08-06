---
name: web-to-pdf
description: Extract webpage content into structured blocks (headings, text, images), map them to template slots via LLM analysis, and generate a high-quality PDF from an HTML/CSS template using WeasyPrint (default) or Chromium (fallback). For portfolio PDFs, service page exports, and company brochures — not articles. Use when user asks to "convert webpage to PDF", "create portfolio PDF from URL", "export page as PDF", "generate PDF from website", "make a brochure from my site".
license: MIT
compatibility: Requires Python 3.8+, requests, beautifulsoup4, chevron, weasyprint, Chromium (for screenshots and fallback PDF engine), and optionally poppler-utils (pdfinfo) for page count validation
---

# Web to PDF

## 🚨 Mechanical steps in this skill (URL fetching, content extraction, image caching, PDF rendering, validation) must be followed exactly as written. Analytical steps (block mapping, content curation, slot assignment, template selection) require professional judgment within the stated guardrails.

## When to Use
- User asks to "convert webpage to PDF", "create portfolio PDF", "export page as PDF"
- Generating a company portfolio or brochure from an existing service page
- Creating a formatted PDF handout from web content
- Batch-exporting multiple pages using a consistent template

## When NOT to Use
- Article/blog post extraction for reading (use readability/trafilatura directly — this skill is for designed pages with semantic blocks)
- Code debugging or source code analysis
- Real-time web scraping or monitoring
- Pages that require authentication (out of scope for Phase 1 extraction)

## Scope
This skill produces a **template-driven, graphic-rich PDF** from webpage content. It answers questions like:
- "Can I get a PDF brochure from my services page?"
- "How do I turn this landing page into a portfolio handout?"
- "Can I export multiple pages into a consistent branded PDF?"

It does NOT extract articles for reading, scrape data for analysis, or debug webpage structure.

---

## Architecture Blueprint
This skill uses the **Orchestrate-Analyze-Build (OAB)** pattern, which separates mechanical work (scripts), analytical work (LLM), and formatting work (build pipeline) into three independently testable phases. In summary:

- **Phase 1 (Orchestrate):** A script fetches the URL, strips structural chrome, converts content to Markdown with image ID placeholders, downloads images, captures a screenshot, and writes `.run_state.json`.
- **Phase 2 (Analyze):** The LLM reads the Markdown + screenshot, identifies the page type (business, portfolio, SaaS, etc.), selects the best-fit template, maps semantic blocks to template slots, and writes `analyst_mapping.json` (including the chosen template name).
- **Phase 3 (Build):** A script validates the mapping against the template schema, resolves image IDs to real paths, renders each slot via per-slot sub-templates (or monolithic fallback) using the `chevron` Mustache engine, assembles the full HTML, renders PDF via **WeasyPrint** (default) or **Chromium** (`--engine chromium`), then cleans up all runtime artifacts.

### PDF Engines

| Engine | Default | Header/Footer | Image Support | Styling |
|---|---|---|---|---|
| **WeasyPrint** | ✓ | `@page` margin boxes (`@top-left`, `@bottom-right`) via `position: running()` + `element()` | `base_url="/"` for local paths | Full CSS, limited Grid |
| **Chromium** | Fallback | `position: fixed` bars + table-wrapped content with spacer divs | Native browser rendering | Full CSS, full Grid/Flexbox |

Switch engines with `--engine weasyprint` (default) or `--engine chromium`.

### Template System: Option B — Per-Slot Sub-Templates

Each template directory can contain a `slots/` subdirectory with one HTML file per slot type. `build_pdf.py` resolves templates in this order:

```
assets/
├── css/
│   ├── shared.css               # Chromium base styles (position:fixed header/footer)
│   └── shared-weasyprint.css    # WeasyPrint base styles (@page margin boxes)
└── templates/
    └── {template-name}/
        ├── template.html         # Shell: <html>, <head> with <style> (CSS placeholders), <body>
        ├── template.css          # Per-template component styles (both engines)
        └── slots/                # Per-slot HTML fragments (no <html>/<head>/<body>)

### Future Engines

| Engine | Status | Planned Approach |
|---|---|---|
| **Typst** | Stub — ready for implementation | Convert rendered HTML to Typst markup, compile via `typst compile`. Typst has native header/footer support and fast compilation. Use `--engine typst` when implemented. |
| **Playwright** | Not started | JavaScript-rendered page extraction for SPA-only sites. Replace `requests` fetch with Playwright browser automation. |
```

For each filled slot, `build_pdf.py`:
1. Checks if `slots/{slot_name}.html` exists → uses it (sub-template)
2. Otherwise, falls back to inline markup in `template.html` (monolithic compatibility)

Sub-templates are standalone HTML fragments using the same Mustache syntax. They are reusable — the same `features.html` can be shared across multiple parent templates. Template authors can also keep the monolithic approach by omitting the `slots/` directory entirely.

### Key Principles (from OAB)

1. **Zero Formatting Risk:** The LLM outputs JSON (`analyst_mapping.json`). The build script renders the PDF via `chevron` + WeasyPrint/Chromium. The LLM never touches HTML/CSS or the PDF pipeline.
2. **Progressive Disclosure:** Dense rules (template slot schemas, mapping heuristics, interface contracts) live in `references/` and are loaded only when needed.
3. **Mechanical Validation:** Every phase boundary has an explicit contract. `orchestrator.py --validate` checks Phase 1 outputs. `build_pdf.py` validates the mapping against [`template-schema.json`](references/template-schema.json) — required slots AND field types — before rendering. See [`references/interface-contracts.md`](references/interface-contracts.md).
4. **State Files:** `.run_state.json` uses namespaced, append-only keys (`step1`, `step2`, `step3`). Intermediary steps insert their own namespace without touching existing data. File locking (`fcntl.flock`) prevents corruption from concurrent access.
5. **Image ID Convention:** `content.md` uses `__IMG_*__` placeholders, never real paths. The mapping lives in `.run_state.json`. An intermediary image-processing step only updates the mapping; Markdown is never touched.
6. **Skill Directory Pristine:** All runtime artifacts live under the configured output directory. The skill directory (`.agents/skills/web-to-pdf/`) contains only source files. After Phase 3, the run directory and `.run_state.json` are deleted — only the PDF survives.

## Configuration

All paths and thresholds are set in [`config/defaults.json`](config/defaults.json). Override at runtime:

| Env Var | Overrides |
|---|---|
| `WEB_TO_PDF_OUTPUT_DIR` | `output_dir` (default: `~/Downloads/web-to-pdf`) |
| `CHROMIUM_BIN` | `chromium_bin` (default: `/usr/bin/chromium`) |

See [`config/defaults.json`](config/defaults.json) for validation thresholds (min/max content length, PDF size, page count, screenshot dimensions).

Template slot definitions live in two files:
- [`references/template-schema.md`](references/template-schema.md) — human-readable documentation for the LLM (Phase 2)
- [`references/template-schema.json`](references/template-schema.json) — machine-parseable schema for `build_pdf.py` validation (Phase 3). **Add new templates here.**

Template rendering uses **[chevron](https://pypi.org/project/chevron/)** (`pip install chevron`), a pure-Python Mustache engine. Templates use standard Mustache syntax: `{{variable}}`, `{{#section}}...{{/section}}`, `{{{unescaped}}}`, `{{^inverted}}...{{/inverted}}`.

---

## Workflow

### Step 1: Orchestrate Data Gathering

1. **Execute the orchestrator:**
   ```bash
   python3 .agents/skills/web-to-pdf/scripts/orchestrator.py --url "https://example.com/services"
   ```

   The orchestrator:
   - Fetches the URL and strips `<nav>`, `<footer>`, `<script>`, `<style>`, `<noscript>`, `<svg>`
   - Converts remaining content to a clean Markdown file (`content.md`) in reading order
   - Uses `__IMG_<hex>__` placeholders for images (not real paths — see [`references/interface-contracts.md`](references/interface-contracts.md))
   - Skips `data:` URIs gracefully (inline/base64 images cannot be downloaded over HTTP)
   - Downloads all images to `{output_dir}/runs/{domain}_{timestamp}/images/`
   - Captures a full-page screenshot (`page.png`) via Chromium at configured width
   - Writes `.run_state.json` to `{output_dir}/` with `step1` namespace (uses exclusive file lock)

   All paths derive from `output_dir` in [`config/defaults.json`](config/defaults.json) (override via `WEB_TO_PDF_OUTPUT_DIR`).

2. **Validate Phase 1 outputs:**
   ```bash
   python3 .agents/skills/web-to-pdf/scripts/orchestrator.py --validate
   ```
   Checks: `content.md` meets minimum length and has headings, `page.png` is a valid image above minimum size, image IDs resolve in `image_map`, all mapped images exist on disk. Reads state with shared file lock. Thresholds are in [`config/defaults.json`](config/defaults.json) → `validation`. Exit code 0 = ready for Phase 2.

### Step 2: Analyze & Map Content to Template Slots

**This is LLM reasoning, not automated.** You must read the generated `content.md` and `page.png`, then select a template and map content to slots.

1. **Read the data:**
   - Read `content.md` (exact text content, heading hierarchy, `__IMG_*__` image placeholders)
   - View `page.png` (visual layout, card groupings, design density, image prominence)
   - Read [`references/template-schema.md`](references/template-schema.md) for available slots per template
   - Read [`references/block-mapping-rules.md`](references/block-mapping-rules.md) for decision heuristics
   - Read [`references/interface-contracts.md`](references/interface-contracts.md) for the Phase 2 → Phase 3 contract

2. **Select the best-fit template (auto-selection):**
   - Inspect `content.md` and `page.png` to identify the page type.
   - Review available templates in [`template-schema.json`](references/template-schema.json) (keys under `"templates"`). Currently, only `business-default` is available.
   - Write the chosen template name as `"template"` in `analyst_mapping.json` — this overrides the CLI/config default.
   - If unsure, present the user with a choice: list available templates, describe each, ask which to use.

3. **Map content to slots:**
   - Identify semantic blocks from the combined text + visual evidence
   - Assign each block to a template slot defined in the chosen template's schema
   - Curate ordering for the PDF flow (may differ from page order)
   - Extract exact text content — do NOT paraphrase unless the slot schema explicitly allows adaptation
   - Use `__IMG_*__` IDs from `content.md` for image references (do not write real paths)
   - Ensure field types match the schema (e.g., `items` must be an array, `heading` must be a string)

4. **Write mapping to JSON:**
   Create `analyst_mapping.json` in the run directory (path is `step1.run_dir` from `.run_state.json`). Must include:
   ```json
   {
     "template": "business-default",
     "slots": { ... }
   }
   ```
   The schema per template is defined in [`references/template-schema.md`](references/template-schema.md).

5. **Update `.run_state.json`:**
   Add a `step2` namespace with `analyst_mapping_json` (path to the file) and `timestamp`.

### Step 3: Build, Validate & Clean Up

1. **Build the PDF:**
   ```bash
   python3 .agents/skills/web-to-pdf/scripts/build_pdf.py --mapping "$RUN_DIR/analyst_mapping.json"
   ```
   Optional flags: `--template <name>` (override LLM selection), `--engine <weasyprint|chromium>` (default: weasyprint), `--no-cleanup` (keep runtime artifacts for debugging).

   Before rendering, this loads [`template-schema.json`](references/template-schema.json) and validates the mapping: required slots filled, field types correct, image IDs resolve, template exists. Extra slots trigger a warning.

   On success: for each filled slot, loads `slots/{slot_name}.html` (sub-template) or extracts inline markup from `template.html` (monolithic fallback). Renders each slot via `chevron.render()`, assembles the final HTML with engine-specific CSS inlined, and renders PDF. Output: `{output_dir}/pdfs/{domain}_{template}_{timestamp}.pdf`. Writes `step3` namespace to `.run_state.json`.

2. **Validate the PDF:**
   ```bash
   python3 .agents/skills/web-to-pdf/scripts/validate_output.py "$PDF_PATH"
   ```
   Checks: PDF file size within configured range, page count within range (requires `pdfinfo` from `poppler-utils`; skipped gracefully if unavailable).

3. **Clean up runtime artifacts:**
   Handled automatically by `build_pdf.py` (unless `--no-cleanup`). Only the generated PDF survives.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Orchestrator fails to fetch URL | Network issue or page requires JavaScript rendering | Verify URL is accessible. For SPA-only pages, use the Playwright-based extraction (future: `--engine playwright` flag). |
| `content.md` is empty or nearly empty | Page has no extractable content after stripping chrome | Check the raw HTML — the page may be entirely JS-rendered or have unusual DOM structure |
| `--validate` fails: content too short | Page produced less content than `min_content_chars` in config | Increase threshold in config, or verify the page has real content |
| `--validate` fails: image ID not in image_map | Content extraction produced an image reference without mapping it | Re-run orchestrator. This should not happen — it indicates an orchestrator bug |
| Orchestrator WARNING about `data:image/...` | Inline SVG/PNG data URIs in `src` attributes | Fixed: orchestrator now skips `data:` URIs with an info message. These cannot be downloaded over HTTP. |
| WeasyPrint: images missing from PDF | Local file paths not resolved | `build_pdf.py` passes `base_url="/"` to WeasyPrint's `HTML()`. Verify image paths exist in the run directory at build time. |
| WeasyPrint: cover page shows header/footer | Body content renders before the `page: cover` element | Fixed: header/logo element injected after first `</section>` (cover) in the final HTML. No body content precedes the cover. |
| WeasyPrint: header text missing when element uses `display: none` | `display: none` kills `string-set` in WeasyPrint | Use `visibility: hidden; position: absolute;` instead. Running elements (`position: running()`) are not affected. |
| WeasyPrint: `@top-left` header not full width | Margin box width is content-dependent | Use all three top boxes (`@top-left`, `@top-center`, `@top-right`) with identical `background` for a continuous bar. Or use `position: running()` + `element()`. |
| WeasyPrint: `AssertionError` with no message | Missing CSS variable in `calc()` (e.g., `--header-height` undefined) | Both `shared.css` and `shared-weasyprint.css` must define `--header-height` and `--footer-height`. WeasyPrint sets them to `0px`. |
| LLM can't identify blocks | Page has flat structure without clear headings or sections | Provide the LLM with more context about the page's purpose. The screenshot helps with visual grouping even without headings. |
| LLM can't decide which template to use | Page content is ambiguous or doesn't match any template's slots | Present available templates to the user with descriptions. Fall back to `business-default` (the generic business/services template) if no better fit. |
| PDF build fails: validation error | `analyst_mapping.json` doesn't conform to template schema | Read the error message — it specifies which slot is missing, which field has wrong type, or which image ID doesn't resolve. Fix the JSON and retry. |
| PDF build fails: field type mismatch | LLM wrote a string where an array was expected (e.g., `"items": "text"` instead of `"items": [...]`) | Correct the field type in `analyst_mapping.json`. See [`template-schema.md`](references/template-schema.md) for expected types per slot. |
| PDF build fails: template not in schema | Template exists in `assets/templates/` but not in [`template-schema.json`](references/template-schema.json) | Add the template's slot definitions to [`template-schema.json`](references/template-schema.json). See existing `business-default` entry as a template. |
| PDF build fails: slot has no sub-template | `slots/{slot_name}.html` missing and slot not in monolithic `template.html` | Either create the sub-template file or add inline `{{#slots.{name}}}...{{/slots.{name}}}` markup to `template.html`. |
| Images broken in PDF | Image ID resolves but file was deleted from cache | Re-run orchestrator. Do not manually delete files from the run directory. |
| Template slot unfilled | LLM didn't find matching content for a required slot | Review `content.md` — the page may genuinely lack that content type. If acceptable, mark the slot as `"required": false` in [`template-schema.json`](references/template-schema.json). |
| `validate_output.py` fails: PDF too large | PDF exceeds `max_pdf_bytes` in config | Increase threshold or optimize template (fewer images, simpler layout) |
| PDF page count out of range | Template produced too many/few pages | Adjust `min_pages`/`max_pages` in config, or review content mapping |
| `pdfinfo` not found for page count check | `poppler-utils` not installed | Install with system package manager, or page count validation is skipped safely |
| Concurrent run error | Another process holds the `.run_state.lock` | Wait for the other run to complete. The lock is released automatically when the other process exits. |
| `ImportError: No module named 'chevron'` | chevron not installed | `pip install chevron` |
| `ImportError: No module named 'weasyprint'` | weasyprint not installed | `pip install weasyprint` |

---

## Files

| File | Purpose | Action |
|---|---|---|
| [`scripts/orchestrator.py`](scripts/orchestrator.py) | Fetch URL, extract content to Markdown (with `__IMG_*__` IDs), capture screenshot, cache images, write `.run_state.json` (step1). Supports `--validate`. File locking for concurrency. Skips `data:` URIs. | **Execute** in Step 1 |
| [`scripts/build_pdf.py`](scripts/build_pdf.py) | Validate `analyst_mapping.json` against [`template-schema.json`](references/template-schema.json) (required slots + field types), resolve image IDs, render slots via sub-templates (or monolithic fallback) using `chevron`, assemble HTML with engine-specific CSS, render PDF via WeasyPrint (default) or Chromium (`--engine`), write step3. LLM auto-selection via `mapping.template`. | **Execute** in Step 3 |
| [`scripts/validate_output.py`](scripts/validate_output.py) | Mechanical checks: PDF file size, page count (via pdfinfo). Thresholds from config → validation. | **Execute** in Step 3 |
| [`scripts/tests/test_orchestrator.py`](scripts/tests/test_orchestrator.py) | 18 unit tests for `html_to_markdown`, `make_image_id`, config loading. Uses fixture HTML. | **Execute** after making script changes — `python3 scripts/tests/test_orchestrator.py` |
| [`scripts/tests/test_build_pdf.py`](scripts/tests/test_build_pdf.py) | 30 unit tests for `validate_mapping`, `check_field_type`, `resolve_images`, `load_template_schema`, `render_slots`. Uses fixture JSON. | **Execute** after making script changes — `python3 scripts/tests/test_build_pdf.py` |
| [`references/template-schema.md`](references/template-schema.md) | Human-readable template slot documentation for LLM: available slots per template, required fields, JSON schema examples | **Read** in Step 2 before writing mapping |
| [`references/template-schema.json`](references/template-schema.json) | Machine-parseable template slot schema for `build_pdf.py` validation. **Add new templates here.** | Read automatically by `build_pdf.py` |
| [`references/block-mapping-rules.md`](references/block-mapping-rules.md) | LLM decision heuristics: how to identify block types from headings, content patterns, and visual layout. Includes edge cases. | **Read** in Step 2 before writing mapping |
| [`references/interface-contracts.md`](references/interface-contracts.md) | `.run_state.json` schema (namespaced, append-only), image ID convention, Phase 1→2 and Phase 2→3 contracts, intermediary step rules, cleanup procedure | **Read** when inserting intermediary steps or debugging contract violations |
| [`assets/css/shared.css`](assets/css/shared.css) | Chromium base CSS (variables, reset, typography, `position: fixed` header/footer, `@page`). Inlined at build time. | **Edit** to change global styles |
| [`assets/css/shared-weasyprint.css`](assets/css/shared-weasyprint.css) | WeasyPrint base CSS (variables, reset, typography, `@page` margin boxes with `position: running()` header, `@page cover` for full-bleed). Inlined at build time. | **Edit** to change global WeasyPrint styles |
| `assets/templates/{name}/template.css` | Per-template component styles (hero, features, cta, etc.). Used by both engines. | **Edit** to change template-specific styles |
| [`assets/templates/`](assets/templates/) | Template directories. Each contains `template.html` (shell with CSS placeholders, engine-conditional markup via `{{^is_weasyprint}}`), `template.css`, and optionally `slots/`. | Used automatically by `build_pdf.py` |
| [`config/defaults.json`](config/defaults.json) | All configurable values: output directory, template, engine, Chromium path, validation thresholds, cleanup behavior | Read by all scripts; edit to change defaults. Override `output_dir` via `WEB_TO_PDF_OUTPUT_DIR` env var |

## CSS Architecture

CSS is split by engine and by template — zero CSS lives inline in HTML:

| Layer | File | Engine | What It Contains |
|---|---|---|---|
| **Shared (Chromium)** | [`assets/css/shared.css`](assets/css/shared.css) | Chromium | CSS variables, reset, `position: fixed` header/footer bars, `@page` margins |
| **Shared (WeasyPrint)** | [`assets/css/shared-weasyprint.css`](assets/css/shared-weasyprint.css) | WeasyPrint | CSS variables, reset, `@page` margin boxes (`@top-left` + `element()`, `@bottom-right`), `@page cover` |
| **Per-template** | `assets/templates/{name}/template.css` | Both | Component styles (`.hero`, `.feature-grid`, `.cta`, etc.) |

`template.html` contains only HTML structure and Mustache placeholders. Its `<style>` block holds two comments that `build_pdf.py` replaces at build time:
- `/* SHARED_CSS */` → replaced with engine-specific CSS (`shared.css` or `shared-weasyprint.css`)
- `/* TEMPLATE_CSS */` → replaced with `template.css`

`build_pdf.py` selects the shared CSS file based on the engine. Engine-conditional markup in `template.html` uses `{{^is_weasyprint}}` (Chromium-only) and `{{#is_weasyprint}}` (WeasyPrint-only).

To restyle the PDF:
1. Edit [`assets/css/shared.css`](assets/css/shared.css) or [`shared-weasyprint.css`](assets/css/shared-weasyprint.css) for global changes
2. Edit `assets/templates/{name}/template.css` for per-template changes
3. Run `build_pdf.py` — all CSS is inlined automatically

## Configuration Reference
All configurable values live in [`config/defaults.json`](config/defaults.json):

| Key | Default | Description |
|---|---|---|
| `default_template` | `business-default` | Template subdirectory in `assets/templates/` |
| `default_engine` | `weasyprint` | PDF engine (`weasyprint`, `chromium`, or `typst` stub) |
| `output_dir` | `~/Downloads/web-to-pdf` | Root for runtime artifacts and PDFs. Override via `WEB_TO_PDF_OUTPUT_DIR` |
| `chromium_bin` | `/usr/bin/chromium` | Chromium binary path. Override via `CHROMIUM_BIN` |
| `screenshot_width` | `1280` | Viewport width for full-page screenshot |
| `screenshot_full_page` | `true` | Capture full page height |
| `pdf_format` | `A4` | PDF page format (injected into shared CSS `@page` rule at build time as `PDF_FORMAT` placeholder) |
| `pdf_print_background` | `true` | Print CSS backgrounds (Chromium only; WeasyPrint always prints backgrounds) |
| `cleanup_after_build` | `true` | Delete run directory and `.run_state.json` after PDF generation |
| `validation.min_content_chars` | `50` | Minimum characters in `content.md` |
| `validation.min_screenshot_bytes` | `10240` | Minimum screenshot file size (10 KB) |
| `validation.min_pdf_bytes` | `1024` | Minimum PDF file size (1 KB) |
| `validation.max_pdf_bytes` | `52428800` | Maximum PDF file size (50 MB) |
| `validation.min_pages` | `1` | Minimum PDF page count |
| `validation.max_pages` | `20` | Maximum PDF page count |

## Adding a New Template

1. Create directory: `assets/templates/{template-name}/` with `template.html` (HTML shell with `/* SHARED_CSS */` and `/* TEMPLATE_CSS */` placeholders, engine-conditional markup via `{{^is_weasyprint}}`/`{{#is_weasyprint}}`) and `template.css` (shared component styles)
2. Add template-specific component styles to `template.css`
3. Optionally create `assets/templates/{template-name}/slots/` with per-slot `.html` files (Mustache fragments):
   - File name must match slot name: `hero.html`, `features.html`, etc.
   - Each file is a standalone HTML fragment (no `<html>`/`<head>`/`<body>`)
   - If a slot has no sub-template, `build_pdf.py` falls back to inline markup in `template.html`
4. Add slot definitions to [`references/template-schema.json`](references/template-schema.json) following the `business-default` format — set `"required": true` for mandatory slots, define field types
5. Optionally add human-readable documentation in [`references/template-schema.md`](references/template-schema.md)
6. Set `default_template` in [`config/defaults.json`](config/defaults.json) or let the LLM auto-select by writing `"template": "{name}"` in `analyst_mapping.json`

No script changes needed. `build_pdf.py` reads `template-schema.json` and discovers available templates at runtime. Both shared CSS files are inlined at build time — new templates inherit them automatically.

## Template Rendering

Templates use **[chevron](https://pypi.org/project/chevron/)** (`pip install chevron`), a pure-Python Mustache engine with zero dependencies. Syntax:

| Mustache | Meaning | Example |
|---|---|---|
| `{{ variable }}` | Insert escaped value | `{{ heading }}` |
| `{{{ variable }}}` | Insert unescaped HTML | `{{{ body }}}` for Markdown content |
| `{{#section}}...{{/section}}` | Conditional block (renders if section exists and is truthy) | `{{#items}}<li>{{ title }}</li>{{/items}}` |
| `{{^section}}...{{/section}}` | Inverted block (renders if section is empty/false/null) | `{{^image}}No image{{/image}}` |
| `{{#list}}{{.}}{{/list}}` | Loop: renders block for each item | `{{#items}}<div>{{ title }}</div>{{/items}}` |

### Engine-Conditional Markup

The template receives `is_weasyprint` (boolean) from the build script. Use it to conditionally include Chromium-only or WeasyPrint-only markup:

```html
{{^is_weasyprint}}
<!-- Chromium-only: fixed header/footer bars, table wrappers -->
{{/is_weasyprint}}

{{#is_weasyprint}}
<!-- WeasyPrint-only: string-set elements, running headers -->
{{/is_weasyprint}}
```

## Output Structure
```
{output_dir}/ (default: ~/Downloads/web-to-pdf)
├── .run_state.json            ← deleted on cleanup
├── .run_state.lock            ← deleted on cleanup
├── runs/
│   └── {domain}_{timestamp}/  ← deleted on cleanup
│       ├── content.md
│       ├── page.png
│       ├── images/
│       │   ├── logo.png
│       │   └── IMG_<hex>.jpg
│       └── analyst_mapping.json
└── pdfs/                      ← survives cleanup
    ├── {domain}_{template}_{YYYYMMDDHHMM}.pdf
    └── ...
```
**Skill directory** (`.agents/skills/web-to-pdf/`) contains only source files. No runtime artifacts.

## Template Directory Structure
```
assets/
├── css/
│   ├── shared.css              # Chromium base styles
│   └── shared-weasyprint.css   # WeasyPrint base styles
└── templates/
    └── {name}/
        ├── template.html        # Shell with engine-conditional markup
        ├── template.css         # Per-template component styles
        └── slots/               # Optional: per-slot sub-templates
            ├── cover.html
            ├── hero.html
            ├── about.html
            ├── features.html
            ├── benefits.html
            ├── steps.html
            ├── how-to.html
            ├── faq.html
            ├── testimonials.html
            ├── cta.html
            ├── stats.html
            └── contact.html
```
