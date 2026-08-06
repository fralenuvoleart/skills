# Interface Contracts

> Defines the data contracts between OAB phases. Every script validates its inputs against the contract for its phase boundary before proceeding. This is what makes phases independently modifiable and intermediary steps safe to insert.
>
> **All paths derive from `output_dir` in [`config/defaults.json`](../config/defaults.json)** (default: `~/Downloads/web-to-pdf`, overridable via `WEB_TO_PDF_OUTPUT_DIR` env var). This document uses `{output_dir}` as a placeholder for that value.

---

## Table of Contents
1. [`.run_state.json` Schema](#run_statejson-schema)
2. [Image ID Convention](#image-id-convention)
3. [Phase 1 → Phase 2 Contract](#phase-1--phase-2-contract)
4. [Phase 2 → Phase 3 Contract](#phase-2--phase-3-contract)
5. [Intermediary Step Rules](#intermediary-step-rules)

---

## `.run_state.json` Schema

**Location:** `{output_dir}/.run_state.json`
**Lifecycle:** Created by Phase 1, read by all subsequent phases, deleted on cleanup.
**Skill directory remains clean** — no runtime artifacts touch `.agents/skills/web-to-pdf/`.

### Namespaced, Append-Only Design

Each phase writes under its own top-level key. Later phases append; they never overwrite earlier keys. This allows intermediary steps to insert their own namespace without touching existing data.

```json
{
  "step1": {
    "url": "https://example.com/services",
    "template": "business-default",
    "run_dir": "{output_dir}/runs/20260725_120000/",
    "content_md": "{output_dir}/runs/20260725_120000/content.md",
    "screenshot_png": "{output_dir}/runs/20260725_120000/page.png",
    "images_dir": "{output_dir}/runs/20260725_120000/images/",
    "image_map": {
      "__IMG_a1b2c3__": "{output_dir}/runs/20260725_120000/images/a1b2c3.jpg",
      "__IMG_d4e5f6__": "{output_dir}/runs/20260725_120000/images/d4e5f6.png"
    },
    "timestamp": "2026-07-25T12:00:00Z"
  },
  "step2": {
    "analyst_mapping_json": "{output_dir}/runs/20260725_120000/analyst_mapping.json",
    "timestamp": "2026-07-25T12:05:00Z"
  },
  "step3": {
    "pdf_path": "{output_dir}/pdfs/example.com_business-default_202607251205.pdf",
    "timestamp": "2026-07-25T12:06:00Z"
  }
}
```

### Key Rules

| Rule | Rationale |
|---|---|
| Each phase writes under `stepN` (1, 2, 3) | Namespacing prevents key collisions when intermediary steps are inserted |
| Intermediary steps use `step1.5`, `step2.5`, etc. | Decimal notation preserves ordering while allowing insertion |
| No key is ever overwritten | Append-only guarantees that any step can read any prior step's output |
| All runtime paths are under `{output_dir}` | Skill directory (`.agents/skills/web-to-pdf/`) stays pristine |
| `run_dir` is set once by Phase 1 and never changed | All artifacts for one run live under one directory; cleanup is `rm -rf $run_dir` |

### Required Fields per Step

| Step | Required Keys |
|---|---|
| `step1` | `url`, `template`, `run_dir`, `content_md`, `screenshot_png`, `images_dir`, `image_map`, `timestamp` |
| `step2` | `analyst_mapping_json`, `timestamp` |
| `step3` | `pdf_path`, `timestamp` |

---

## Image ID Convention

To decouple image references from filesystem paths, `content.md` uses **image IDs** rather than real paths. The mapping lives in `step1.image_map` in `.run_state.json`.

### Format

```
In content.md:    ![Company logo](__IMG_a1b2c3__)
In run_state:     "step1.image_map.__IMG_a1b2c3__" → "{output_dir}/runs/{ts}/images/a1b2c3.jpg"
```

### Rules

| Rule | Rationale |
|---|---|
| Image IDs are `__IMG_` + hex digest of the original URL (first 6 chars) + `__` | Deterministic, unique, no collision risk |
| `content.md` never contains real filesystem paths | An intermediary step that reprocesses images only updates `image_map`; Markdown is untouched |
| `build_pdf.py` resolves `__IMG_*__` placeholders to real paths at render time | Late binding — template HTML gets real paths only in the final render pass |

---

## Phase 1 → Phase 2 Contract

**Producer:** `orchestrator.py` (Step 1)
**Consumer:** LLM (Step 2)

### Outputs (must exist before Phase 2 starts)

| Artifact | Format | Validated By |
|---|---|---|
| `content.md` | Markdown with `#`–`######` headings, `![alt](__IMG_*__)` image references, plain paragraphs and lists. Minimum length set in `config/defaults.json` → `validation.min_content_chars`. | `orchestrator.py --validate` |
| `page.png` | PNG or JPEG image. Minimum file size set in `config/defaults.json` → `validation.min_screenshot_bytes`. | `orchestrator.py --validate` |
| `images/` directory | Contains ≥ 1 image file, all referenced `__IMG_*__` IDs resolve in `image_map` | `orchestrator.py --validate` |
| `.run_state.json` | Contains all `step1` required keys | `orchestrator.py --validate` |

### Validation Command
```bash
python3 .agents/skills/web-to-pdf/scripts/orchestrator.py --validate
```
Reads `.run_state.json` from `{output_dir}`, checks every `step1` artifact exists and is well-formed. Thresholds from [`config/defaults.json`](../config/defaults.json) → `validation`. Exit code 0 = ready for Phase 2.

---

## Phase 2 → Phase 3 Contract

**Producer:** LLM (Step 2)
**Consumer:** `build_pdf.py` (Step 3)

### Outputs (must exist before Phase 3 starts)

| Artifact | Format | Validated By |
|---|---|---|
| `analyst_mapping.json` | JSON conforming to the template schema (LLM reads [`template-schema.md`](template-schema.md); machine validation uses [`template-schema.json`](template-schema.json)) | `build_pdf.py` (inline validation) |
| `.run_state.json` | Contains `step2.analyst_mapping_json` pointing to the file above; `step1.image_map` for image resolution | `build_pdf.py` (inline check) |

### Validation (built into build_pdf.py)

`build_pdf.py` performs these checks before rendering:
1. `analyst_mapping.json` parses as valid JSON
2. `template` field matches a directory in `assets/templates/`
3. All `required: true` slots (per [`template-schema.json`](template-schema.json)) are present and non-null
4. All `__IMG_*__` references in slot content resolve in `step1.image_map`
5. Every image path in `step1.image_map` exists on disk

Failure produces a specific error message; no partial PDF is generated.

---

## Intermediary Step Rules

To insert a step between existing phases (e.g., `step1.5` image optimization):

### What the intermediary MUST do
1. Read `.run_state.json` from `{output_dir}` — find inputs from the prior step (`step1` for a 1.5, `step2` for a 2.5)
2. Do work — read/write only within `run_dir` (from `step1.run_dir`)
3. Write output under its own namespace in `.run_state.json` (`step1.5` or `step2.5`)
4. Update `step1.image_map` if image paths change (replace old paths, keep same `__IMG_*__` keys)
5. Never overwrite keys from `step1`, `step2`, or `step3`

### What the intermediary MUST NOT do
1. Modify `content.md` or `analyst_mapping.json` — these are owned by Phase 1 and Phase 2 respectively
2. Change `run_dir` — all artifacts for a run stay together
3. Delete files from prior steps — append-only
4. Write anything into `.agents/skills/web-to-pdf/` — skill directory stays clean

### What downstream phases do
- Phase 2 reads `step1.content_md`, `step1.screenshot_png`, `step1.image_map` — unaffected by `step1.5`
- Phase 3 reads `step2.analyst_mapping_json` and `step1.image_map` — picks up image path changes from `step1.5` via `image_map`

---

## Cleanup

After Phase 3 completes successfully, delete the run directory and state file:

```bash
RUN_DIR=$(python3 -c "import json, os; d=json.load(open(os.path.expanduser('{output_dir}/.run_state.json'))); print(d['step1']['run_dir'])")
rm -rf "$RUN_DIR"
rm {output_dir}/.run_state.json
```

Only the generated PDF (at `step3.pdf_path`) survives. The skill directory (`.agents/skills/web-to-pdf/`) was never touched. `{output_dir}` is resolved from [`config/defaults.json`](../config/defaults.json) (default: `~/Downloads/web-to-pdf`).
