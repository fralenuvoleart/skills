#!/usr/bin/env python3
"""
build_pdf.py -- Phase 3: PDF Generation
Merges analyst_mapping.json with an HTML/CSS template and renders via WeasyPrint (default) or Chromium.

Interface contract: references/interface-contracts.md
Validates analyst_mapping.json against template-schema.json before rendering.

Configuration: config/defaults.json (overridable via WEB_TO_PDF_OUTPUT_DIR env var)
Template schemas: references/template-schema.json (machine-parseable)

Template engine: chevron (pure Python Mustache, pip install chevron).
Rendering: monolithic -- chevron.render(template.html, data) where data contains both
  root-level slot access (e.g., {{ hero.heading }}) and namespaced blocks
  (e.g., {{#slots.hero}}...{{/slots.hero}}). Sub-template resolution
  (slots/{name}.html) is automatic with monolithic fallback.

Dependencies: chevron, weasyprint, Chromium (subprocess, fallback engine)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

# Optional dependencies
try:
    import chevron
except ImportError:
    chevron = None


# -- Config ----------------------------------------------------------------

from config_loader import load_config, resolve_output_dir, lock_state_file, unlock_state_file


def load_template_schema(skill_dir: str) -> dict:
    """Load template-schema.json."""
    schema_file = os.path.join(skill_dir, "references", "template-schema.json")
    with open(schema_file, "r") as f:
        return json.load(f)


# -- Field Type Validation -------------------------------------------------

def is_array_field(field_def) -> bool:
    if isinstance(field_def, list):
        return True
    if isinstance(field_def, dict):
        return False
    if isinstance(field_def, str):
        return field_def.endswith("[]")
    return False


def check_field_type(slot_name: str, field_name: str, value, field_def, errors: list):
    if is_array_field(field_def):
        if not isinstance(value, list):
            errors.append(
                f"Slot '{slot_name}.{field_name}': expected array, got {type(value).__name__}"
            )
        elif isinstance(field_def, str):
            # String syntax like "items[]" — array of any type; no per-item schema to validate
            pass
        elif isinstance(field_def, list) and len(field_def) > 0 and len(value) > 0:
            item_schema = field_def[0]
            for i, item in enumerate(value):
                if isinstance(item_schema, dict):
                    if isinstance(item, dict):
                        for item_field, item_field_def in item_schema.items():
                            if item_field in item:
                                check_field_type(
                                    f"{slot_name}.{field_name}[{i}]",
                                    item_field,
                                    item[item_field],
                                    item_field_def,
                                    errors,
                                )
                    else:
                        errors.append(
                            f"Slot '{slot_name}.{field_name}[{i}]': expected object, got {type(item).__name__}"
                        )
                # If item_schema is not a dict (e.g., a primitive type string),
                # skip per-item validation — primitive array schemas are not yet supported.
    elif isinstance(field_def, str) and "|null" in field_def:
        if value is not None and not isinstance(value, str):
            errors.append(
                f"Slot '{slot_name}.{field_name}': expected string or null, got {type(value).__name__}"
            )
    elif isinstance(field_def, str):
        if field_def == "string" and not isinstance(value, str):
            errors.append(
                f"Slot '{slot_name}.{field_name}': expected string, got {type(value).__name__}"
            )
        elif field_def in ("number", "integer") and not isinstance(value, (int, float)):
            errors.append(
                f"Slot '{slot_name}.{field_name}': expected number, got {type(value).__name__}"
            )
        elif field_def == "boolean" and not isinstance(value, bool):
            errors.append(
                f"Slot '{slot_name}.{field_name}': expected boolean, got {type(value).__name__}"
            )
        elif field_def not in ("string", "number", "integer", "boolean"):
            errors.append(
                f"Slot '{slot_name}.{field_name}': unrecognized field type definition: {field_def!r}"
            )
    else:
        errors.append(
            f"Slot '{slot_name}.{field_name}': unrecognized field type definition: {field_def!r}"
        )


def validate_mapping(mapping: dict, state: dict, skill_dir: str) -> bool:
    errors = []
    template = mapping.get("template")
    if not template:
        print("VALIDATION FAILED:", file=sys.stderr)
        print("  - analyst_mapping.json missing 'template' field", file=sys.stderr)
        return False

    template_dir = os.path.join(skill_dir, "assets", "templates", template)
    if not os.path.isdir(template_dir):
        errors.append(f"Template '{template}' not found at {template_dir}")

    schema_file = os.path.join(skill_dir, "references", "template-schema.json")
    if not os.path.isfile(schema_file):
        errors.append(f"Schema file not found: {schema_file}")
    else:
        try:
            schema = load_template_schema(skill_dir)
            template_schema = schema.get("templates", {}).get(template, {})
            template_slots = template_schema.get("slots", {})

            if not template_slots:
                errors.append(f"No slot definitions found for template '{template}' in template-schema.json")

            slots = mapping.get("slots", {})
            if not slots:
                errors.append("analyst_mapping.json missing 'slots' key or slots is empty")

            for slot_name, slot_def in template_slots.items():
                if slot_def.get("required", False):
                    if slot_name not in slots or not slots[slot_name]:
                        errors.append(f"Required slot '{slot_name}' is missing or empty")

            for slot_name, slot_value in slots.items():
                if slot_name not in template_slots:
                    print(f"Warning: slot '{slot_name}' in mapping but not in template schema -- will be ignored",
                          file=sys.stderr)
                    continue
                slot_def = template_slots[slot_name]
                field_defs = slot_def.get("fields", {})
                if not isinstance(slot_value, dict):
                    errors.append(f"Slot '{slot_name}': expected object, got {type(slot_value).__name__}")
                    continue
                for field_name, field_def in field_defs.items():
                    if field_name in slot_value:
                        check_field_type(slot_name, field_name, slot_value[field_name], field_def, errors)
        except (json.JSONDecodeError, KeyError) as e:
            errors.append(f"Failed to parse template-schema.json: {e}")

    # Image references
    step1 = state.get("step1", {})
    image_map = step1.get("image_map", {})
    if image_map:
        mapping_str = json.dumps(mapping)
        img_refs = re.findall(r'__IMG_[a-f0-9]{6}__', mapping_str)
        for ref in img_refs:
            if ref not in image_map:
                errors.append(f"Image ID {ref} referenced in mapping but not found in image_map")
            else:
                img_path = os.path.expanduser(image_map[ref])
                if img_path and not os.path.isfile(img_path):
                    errors.append(f"Image file missing: {img_path}")

    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return False
    print("VALIDATION PASSED: analyst_mapping.json conforms to template schema.")
    return True


# -- Image Resolution ------------------------------------------------------

def resolve_images(mapping: dict, image_map: dict) -> dict:
    """Deep-replace all __IMG_*__ IDs in the mapping with real filesystem paths."""
    def replace(obj):
        if isinstance(obj, str):
            def replacer(match):
                img_id = match.group(0)
                if img_id in image_map and image_map[img_id]:
                    return image_map[img_id]
                return img_id
            return re.sub(r'__IMG_[a-f0-9]{6}__', replacer, obj)
        elif isinstance(obj, dict):
            return {k: replace(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [replace(item) for item in obj]
        return obj
    return replace(mapping)


# -- PDF Rendering ---------------------------------------------------------

def render_pdf(html_content: str, output_path: str, config: dict, engine: str = "chromium") -> bool:
    if engine == "chromium":
        return render_pdf_chromium(html_content, output_path, config)
    elif engine == "weasyprint":
        return render_pdf_weasyprint(html_content, output_path, config)
    elif engine == "typst":
        return render_pdf_typst(html_content, output_path, config)
    else:
        print(f"Unknown engine: {engine}", file=sys.stderr)
        return False


def render_pdf_chromium(html_content: str, output_path: str, config: dict) -> bool:
    chromium_bin = os.path.expanduser(config.get("chromium_bin", "chromium"))
    print_background = config.get("pdf_print_background", True)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        temp_html = f.name

    try:
        cmd = [
            chromium_bin, "--headless", "--disable-gpu", "--no-sandbox",
            f"--print-to-pdf={output_path}",
            "--no-pdf-header-footer",
        ]
        if print_background:
            cmd.append("--print-to-pdf-background")
        cmd.append(temp_html)

        print(f"  Rendering PDF: {chromium_bin} --headless --print-to-pdf=...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            print(f"  WARNING Chromium error: {result.stderr[:300]}", file=sys.stderr)
            return False
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            print(f"  PDF rendered: {output_path} ({os.path.getsize(output_path)} bytes)")
            return True
        else:
            print(f"  WARNING PDF not created or empty", file=sys.stderr)
            return False
    except FileNotFoundError:
        print(f"  WARNING Chromium not found at {chromium_bin}. Set CHROMIUM_BIN env var.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"  WARNING PDF rendering timed out after 60s", file=sys.stderr)
        return False
    finally:
        if os.path.exists(temp_html):
            os.unlink(temp_html)


def render_pdf_weasyprint(html_content: str, output_path: str, config: dict) -> bool:
    """Render PDF via WeasyPrint with native @page margin box support."""
    try:
        from weasyprint import HTML
    except ImportError:
        print("FATAL: weasyprint not installed. Run: pip install weasyprint", file=sys.stderr)
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        HTML(string=html_content, base_url="/").write_pdf(output_path)
    except Exception as e:
        print(f"  WARNING WeasyPrint error: {type(e).__name__}: {e}", file=sys.stderr)
        return False

    if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
        print(f"  PDF rendered: {output_path} ({os.path.getsize(output_path)} bytes)")
        return True
    else:
        print(f"  WARNING PDF not created or empty", file=sys.stderr)
        return False


def render_pdf_typst(html_content: str, output_path: str, config: dict) -> bool:
    """Render PDF via Typst — PLANNED, not yet implemented.
    Typst is a modern markup-based typesetting engine with native headers/footers.
    Implementation: convert rendered HTML to Typst markup, compile via `typst compile`.
    See SKILL.md → Future Engines."""
    print("Typst engine planned but not yet implemented.", file=sys.stderr)
    return False


# -- Cleanup ---------------------------------------------------------------

def cleanup(state: dict, output_dir: str):
    step1 = state.get("step1", {})
    run_dir = os.path.expanduser(step1.get("run_dir", ""))
    state_path = os.path.join(output_dir, ".run_state.json")
    lock_path = os.path.join(output_dir, ".run_state.lock")

    # Acquire exclusive lock before cleanup to prevent race conditions
    # with concurrent readers/writers. If lock acquisition fails (e.g.,
    # state file already deleted), proceed with best-effort cleanup.
    lock_fd = None
    try:
        lock_fd = lock_state_file(state_path, "exclusive")
    except Exception:
        pass

    try:
        if run_dir and os.path.isdir(run_dir):
            print(f"  Cleaning up run directory: {run_dir}")
            shutil.rmtree(run_dir, ignore_errors=True)

        for path in [state_path, lock_path]:
            if os.path.exists(path):
                os.remove(path)
                print(f"  Removed: {path}")
    finally:
        if lock_fd is not None:
            unlock_state_file(lock_fd)


# -- Slot Rendering (Sub-Template + Monolithic Fallback) --------------------

def render_slots(slots_data: dict, template_dir: str, template_html: str) -> str:
    """Render each filled slot to HTML.

    For each slot:
    1. If slots/{slot_name}.html exists -> render it via chevron (sub-template path)
    2. Otherwise -> extract the {{#slots.{name}}}...{{/slots.{name}}} block
       from template.html and render it (monolithic fallback).

    Returns concatenated HTML of all rendered slots.
    """
    if chevron is None:
        print("Warning: chevron not installed, skipping slot rendering", file=sys.stderr)
        return ""
    rendered_sections = []

    for slot_name, slot_value in slots_data.items():
        if not isinstance(slot_value, dict):
            continue

        sub_template = os.path.join(template_dir, "slots", f"{slot_name}.html")
        if os.path.isfile(sub_template):
            # Sub-template path
            with open(sub_template, "r", encoding="utf-8") as f:
                sub_html = f.read()
            try:
                rendered = chevron.render(sub_html, slot_value)
                rendered_sections.append(rendered)
                continue
            except Exception as e:
                print(f"  Warning: sub-template render failed for '{slot_name}': {e}",
                      file=sys.stderr)
                # Fall through to monolithic extraction

        # Monolithic fallback: extract the {{#slots.{name}}}...{{/slots.{name}}} block
        pattern = (
            r'\{\{#slots\.' + re.escape(slot_name)
            + r'\}\}(.*?)\{\{/slots\.' + re.escape(slot_name) + r'\}\}'
        )
        match = re.search(pattern, template_html, re.DOTALL)
        if match:
            slot_template = match.group(1)
            # The extracted inner content (inside {{#slots.X}}...{{/slots.X}})
            # expects slot fields at the top level (e.g., {{ heading }}, not {{ X.heading }})
            ctx = slot_value
            try:
                rendered = chevron.render(slot_template, ctx)
                rendered_sections.append(rendered)
            except Exception as e:
                print(f"  Warning: inline render failed for '{slot_name}': {e}",
                      file=sys.stderr)

    return "\n".join(rendered_sections)


# -- Main ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build PDF from analyst mapping and template.")
    parser.add_argument("--mapping", required=True, help="Path to analyst_mapping.json")
    parser.add_argument("--template", default=None, help="Template name (defaults to config)")
    parser.add_argument("--engine", default=None, choices=["chromium", "weasyprint", "typst"],
                        help="PDF rendering engine (defaults to config)")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="Skip cleanup of runtime artifacts")
    args = parser.parse_args()

    if chevron is None:
        print("FATAL: chevron not installed. Run: pip install chevron", file=sys.stderr)
        sys.exit(1)

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_config(skill_dir)
    output_dir = resolve_output_dir(config)

    template = args.template or config["default_template"]
    engine = args.engine or config["default_engine"]

    # Load state
    state_path = os.path.join(output_dir, ".run_state.json")
    if not os.path.exists(state_path):
        print(f"Error: .run_state.json not found at {state_path}. Run orchestrator first.", file=sys.stderr)
        sys.exit(1)

    lock_fd = None
    try:
        lock_fd = lock_state_file(state_path, "shared")
        with open(state_path, "r") as f:
            state = json.load(f)
    finally:
        if lock_fd is not None:
            unlock_state_file(lock_fd)

    # Load mapping
    mapping_path = os.path.expanduser(args.mapping)
    if not os.path.exists(mapping_path):
        print(f"Error: mapping file not found: {mapping_path}", file=sys.stderr)
        sys.exit(1)

    with open(mapping_path, "r") as f:
        mapping = json.load(f)

    # Validate
    if not validate_mapping(mapping, state, skill_dir):
        print("Aborting: validation failed. Fix analyst_mapping.json and retry.", file=sys.stderr)
        sys.exit(1)

    # LLM auto-selection: template from mapping overrides CLI/config
    template = mapping.get("template", template)
    if not isinstance(template, str):
        print(f"Error: 'template' field must be a string, got {type(template).__name__}", file=sys.stderr)
        sys.exit(1)
    template_dir = os.path.join(skill_dir, "assets", "templates", template)
    template_file = os.path.join(template_dir, "template.html")

    if not os.path.isfile(template_file):
        print(f"Error: template.html not found at {template_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Building PDF with template: {template}")
    print(f"Engine: {engine}")
    print(f"Slots mapped: {list(mapping.get('slots', {}).keys())}")
    print()

    # Resolve __IMG_*__ IDs to real paths
    step1 = state.get("step1", {})
    image_map = step1.get("image_map", {})
    resolved_mapping = resolve_images(mapping, image_map)

    # Load template
    with open(template_file, "r", encoding="utf-8") as f:
        template_html = f.read()

    # Build Mustache data: root-level access ({{ hero.heading }}) + namespaced ({{#slots.hero}})
    slots_data = resolved_mapping.get("slots", {})
    mustache_data = {}
    mustache_data["slots"] = slots_data
    # Also add each slot at root level for convenience access like {{ hero.heading }}
    for slot_name, slot_value in slots_data.items():
        if isinstance(slot_value, dict):
            mustache_data[slot_name] = slot_value

    # Render slots: try per-slot sub-templates first, fall back to monolithic inline blocks
    print("  Rendering slots...")
    slots_html = render_slots(slots_data, template_dir, template_html)

    # WeasyPrint: we'll inject the string-set span after the cover section
    # in the final HTML to avoid creating a page before the cover.
    weasyprint_header_html = ""
    if engine == "weasyprint":
        logo_path = step1.get("logo", "")
        logo_img = f'<img src="{logo_path}" alt="" class="doc-header-logo">' if logo_path else ""
        title = step1.get("site_title", "")
        weasyprint_header_html = f'<div class="doc-header-run">{logo_img}<span>{title}</span></div>'

    # Build final HTML: strip all {{#slots.X}}...{{/slots.X}} blocks from the shell,
    # inject pre-rendered slot HTML before </body>
    shell_html = re.sub(
        r'\{\{#slots\.[\w-]+\}\}.*?\{\{/slots\.[\w-]+\}\}',
        '',
        template_html,
        flags=re.DOTALL,
    )
    mustache_data["_slots"] = slots_html

    # Pass logo path to templates (detected by orchestrator in Phase 1)
    step1_logo = step1.get("logo")
    if step1_logo and os.path.isfile(os.path.expanduser(step1_logo)):
        mustache_data["logo"] = step1_logo

    # Pass site title to templates (extracted from <title> tag in Phase 1)
    site_title = step1.get("site_title", "")
    if site_title:
        mustache_data["site_title"] = site_title

    # Inject pdf_format as a Mustache variable -- templates use {{ pdf_format }} in @page rule.
    # Replaces the old brittle string-replace approach. See assets/templates/*/template.html.
    mustache_data["pdf_format"] = config.get("pdf_format", "A4")

    # Engine-awareness: templates can conditionally render Chromium-only markup
    mustache_data["is_weasyprint"] = (engine == "weasyprint")

    final_html = shell_html.replace('</body>', '{{{ _slots }}}\n</body>')

    print("  Rendering template with chevron...")
    try:
        rendered_html = chevron.render(final_html, mustache_data)
    except Exception as e:
        print(f"FATAL: chevron rendering failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Inline shared CSS into the rendered HTML.
    # WeasyPrint uses @page margin boxes (shared-weasyprint.css); Chromium uses position:fixed (shared.css).
    # This replacement happens AFTER chevron rendering to avoid Mustache escaping issues.
    if engine == "weasyprint":
        shared_css_path = os.path.join(skill_dir, "assets", "css", "shared-weasyprint.css")
    else:
        shared_css_path = os.path.join(skill_dir, "assets", "css", "shared.css")

    if os.path.isfile(shared_css_path):
        with open(shared_css_path, "r", encoding="utf-8") as _cssf:
            shared_css = _cssf.read()
        shared_css = shared_css.replace("PDF_FORMAT", config.get("pdf_format", "A4"))
        rendered_html = rendered_html.replace("/* SHARED_CSS */", shared_css)
        print(f"  Inlined {os.path.basename(shared_css_path)}")
    else:
        print(f"  Warning: {os.path.basename(shared_css_path)} not found — using template-only styles", file=sys.stderr)

    # Inline per-template CSS (assets/templates/{name}/template.css) into the rendered HTML.
    template_css_path = os.path.join(template_dir, "template.css")
    if os.path.isfile(template_css_path):
        with open(template_css_path, "r", encoding="utf-8") as _tcssf:
            template_css = _tcssf.read()
        rendered_html = rendered_html.replace("/* TEMPLATE_CSS */", template_css)
        print("  Inlined template.css")
    else:
        print("  template.css not found — template may use inline <style>", file=sys.stderr)

    if engine == "weasyprint" and weasyprint_header_html:
        # Insert header element after the cover section, targeting it by class
        # rather than relying on first </section> (fragile if slot order changes).
        rendered_html = re.sub(
            r'(<section\s+class="cover"[^>]*>.*?</section>)',
            r'\1\n' + weasyprint_header_html,
            rendered_html,
            count=1,
            flags=re.DOTALL,
        )
    # Generate PDF filename
    step1_url = step1.get("url", "unknown")
    domain = step1_url.replace("https://", "").replace("http://", "").split("/")[0].replace(":", "_")
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    pdfs_dir = os.path.join(output_dir, "pdfs")
    pdf_filename = f"{domain}_{template}_{timestamp}.pdf"
    pdf_path = os.path.join(pdfs_dir, pdf_filename)

    # Render
    ok = render_pdf(rendered_html, pdf_path, config, engine)
    if not ok:
        print("FATAL: PDF rendering failed.", file=sys.stderr)
        sys.exit(1)

    # Write step3
    lock_fd2 = None
    try:
        lock_fd2 = lock_state_file(state_path, "exclusive")
        with open(state_path, "r") as f:
            state = json.load(f)
        state["step3"] = {
            "pdf_path": pdf_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    finally:
        if lock_fd2 is not None:
            unlock_state_file(lock_fd2)

    print()
    print("-" * 50)
    print(f"PDF generated: {pdf_path}")

    # Cleanup
    if not args.no_cleanup and config.get("cleanup_after_build", True):
        print()
        cleanup(state, output_dir)
        print()
        print("Runtime artifacts cleaned up. Only the PDF survives.")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
