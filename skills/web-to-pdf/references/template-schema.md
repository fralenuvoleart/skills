# Template Slot Schema

> **Human-readable slot documentation for the LLM (Phase 2).** Machine-parseable schema used by `build_pdf.py` validation is in [`template-schema.json`](template-schema.json). When adding a new template, the JSON file is required; this Markdown file is optional documentation.

## Template: business-default

### Available Slots

| Slot ID | Required | Description | Fields |
|---|---|---|---|
| `cover` | No | Cover page (first page, full-bleed) | `heading`, `subheading`, `image` |
| `hero` | Yes | Hero section with main heading, subheading, and background image | `heading`, `subheading`, `image` |
| `about` | Yes | Company/service description paragraph | `heading`, `body` |
| `features` | No | Feature/benefit grid with icons (max 6 items) | `heading`, `items[]` (each: `icon`, `title`, `description`) |
| `benefits` | No | Benefits list with optional icons (max 8 items) | `heading`, `items[]` (each: `icon`, `title`, `description`) |
| `steps` | No | Numbered step-by-step process (max 8 items) | `heading`, `items[]` (each: `step_number`, `title`, `description`) |
| `how-to` | No | How-to/service guide with optional images (max 6 items) | `heading`, `items[]` (each: `title`, `description`, `image`) |
| `faq` | No | Frequently asked questions accordion-style | `heading`, `items[]` (each: `question`, `answer`) |
| `testimonials` | No | Client testimonials (max 3) | `heading`, `items[]` (each: `quote`, `author`, `role`) |
| `cta` | No | Call to action | `heading`, `body`, `button_text`, `button_url` |
| `stats` | No | Key statistics bar | `items[]` (each: `value`, `label`) |
| `contact` | No | Contact information | `email`, `phone`, `address` |

### Permanent Template Elements

These are always rendered regardless of slot mapping:

| Element | Description | Data Source |
|---|---|---|
| Document header | Fixed top bar on every page with company name | `hero.heading` (required) |
| Document footer | Fixed bottom bar on every page with page numbers | CSS `counter(page)` |

### JSON Schema for analyst_mapping.json

```json
{
  "template": "business-default",
  "slots": {
    "cover": {
      "heading": "string",
      "subheading": "string",
      "image": "__IMG_*__ ID or null"
    },
    "hero": {
      "heading": "string",
      "subheading": "string",
      "image": "__IMG_*__ ID or null"
    },
    "about": {
      "heading": "string",
      "body": "string (Markdown allowed)"
    },
    "features": {
      "heading": "string",
      "items": [
        {
          "icon": "__IMG_*__ ID or null",
          "title": "string",
          "description": "string"
        }
      ]
    },
    "benefits": {
      "heading": "string",
      "items": [
        {
          "icon": "__IMG_*__ ID or null",
          "title": "string",
          "description": "string"
        }
      ]
    },
    "steps": {
      "heading": "string",
      "items": [
        {
          "step_number": "string (e.g., \"1\", \"01\", \"Step 1\")",
          "title": "string",
          "description": "string"
        }
      ]
    },
    "how-to": {
      "heading": "string",
      "items": [
        {
          "title": "string",
          "description": "string",
          "image": "__IMG_*__ ID or null"
        }
      ]
    },
    "faq": {
      "heading": "string",
      "items": [
        {
          "question": "string",
          "answer": "string (Markdown allowed)"
        }
      ]
    },
    "testimonials": {
      "heading": "string",
      "items": [
        {
          "quote": "string",
          "author": "string",
          "role": "string (optional)"
        }
      ]
    },
    "cta": {
      "heading": "string",
      "body": "string",
      "button_text": "string",
      "button_url": "string"
    },
    "stats": {
      "items": [
        {
          "value": "string (preserve formatting: \"10K+\", \"98%\")",
          "label": "string"
        }
      ]
    },
    "contact": {
      "email": "string or null",
      "phone": "string or null",
      "address": "string or null"
    }
  }
}
```

### Adding New Templates

1. Create a new subdirectory in [`assets/templates/`](../assets/templates/) (e.g., `proposal/`)
2. Add the template HTML/CSS files
3. **Add slot definitions to [`template-schema.json`](template-schema.json)** — this is required; `build_pdf.py` reads it for validation
4. Optionally add human-readable slot documentation to this file
5. Update [`config/defaults.json`](../config/defaults.json) if the new template should be the default
