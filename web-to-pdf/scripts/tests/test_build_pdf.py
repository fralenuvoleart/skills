#!/usr/bin/env python3
"""
Tests for build_pdf.py -- Phase 3 PDF generation.

Run: python3 .agents/skills/web-to-pdf/scripts/tests/test_build_pdf.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

# Add parent script dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config_loader import load_config
from build_pdf import (
    validate_mapping,
    resolve_images,
    check_field_type,
    render_slots,
    load_template_schema,
    is_array_field,
)


class TestCheckFieldType(unittest.TestCase):
    """Test recursive field type validation."""

    def test_string_ok(self):
        errors = []
        check_field_type("hero", "heading", "Hello", "string", errors)
        self.assertEqual(len(errors), 0)

    def test_string_wrong_type(self):
        errors = []
        check_field_type("hero", "heading", 123, "string", errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("expected string", errors[0])

    def test_nullable_string_with_none(self):
        errors = []
        check_field_type("hero", "image", None, "string|null", errors)
        self.assertEqual(len(errors), 0)

    def test_nullable_string_with_string(self):
        errors = []
        check_field_type("hero", "image", "path/to/img.jpg", "string|null", errors)
        self.assertEqual(len(errors), 0)

    def test_nullable_string_with_int(self):
        errors = []
        check_field_type("hero", "image", 42, "string|null", errors)
        self.assertEqual(len(errors), 1)

    def test_array_ok(self):
        errors = []
        item_schema = {"title": "string", "description": "string"}
        check_field_type("features", "items",
                         [{"title": "A", "description": "B"}],
                         [item_schema], errors)
        self.assertEqual(len(errors), 0)

    def test_array_wrong_type(self):
        errors = []
        item_schema = {"title": "string", "description": "string"}
        check_field_type("features", "items", "not-an-array", [item_schema], errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("expected array", errors[0])

    def test_array_item_field_wrong_type(self):
        errors = []
        item_schema = {"title": "string", "description": "string"}
        check_field_type("features", "items",
                         [{"title": 123, "description": "B"}],
                         [item_schema], errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("expected string", errors[0])

    def test_nested_slot_name_in_error(self):
        errors = []
        item_schema = {"title": "string"}
        check_field_type("features", "items",
                         [{"title": 456}],
                         [item_schema], errors)
        self.assertIn("features.items[0]", errors[0])


class TestIsArrayField(unittest.TestCase):
    """Test array field detection."""

    def test_list_is_array(self):
        self.assertTrue(is_array_field([{"key": "string"}]))

    def test_dict_is_not_array(self):
        self.assertFalse(is_array_field({"key": "string"}))

    def test_string_with_brackets(self):
        self.assertTrue(is_array_field("items[]"))

    def test_plain_string(self):
        self.assertFalse(is_array_field("string"))


class TestResolveImages(unittest.TestCase):
    """Test __IMG_*__ -> real path resolution."""

    def test_replaces_image_ids(self):
        mapping = {
            "slots": {
                "hero": {
                    "heading": "Hello",
                    "image": "__IMG_abc123__"
                }
            }
        }
        image_map = {"__IMG_abc123__": "/tmp/images/abc123.jpg"}
        result = resolve_images(mapping, image_map)
        self.assertEqual(result["slots"]["hero"]["image"], "/tmp/images/abc123.jpg")

    def test_keeps_unmapped_ids(self):
        mapping = {
            "slots": {
                "hero": {
                    "image": "__IMG_unknown__"
                }
            }
        }
        image_map = {}
        result = resolve_images(mapping, image_map)
        self.assertEqual(result["slots"]["hero"]["image"], "__IMG_unknown__")

    def test_nested_resolution(self):
        mapping = {
            "slots": {
                "features": {
                    "items": [
                        {"icon": "__IMG_a1b2c3__", "title": "Feature 1"},
                        {"icon": "__IMG_d4e5f6__", "title": "Feature 2"}
                    ]
                }
            }
        }
        image_map = {
            "__IMG_a1b2c3__": "/tmp/a.png",
            "__IMG_d4e5f6__": "/tmp/b.png"
        }
        result = resolve_images(mapping, image_map)
        self.assertEqual(result["slots"]["features"]["items"][0]["icon"], "/tmp/a.png")
        self.assertEqual(result["slots"]["features"]["items"][1]["icon"], "/tmp/b.png")

    def test_handles_empty_image_map(self):
        mapping = {"slots": {"hero": {"image": None}}}
        image_map = {}
        result = resolve_images(mapping, image_map)
        self.assertIsNone(result["slots"]["hero"]["image"])


class TestValidateMapping(unittest.TestCase):
    """Test analyst_mapping.json validation."""

    def setUp(self):
        self.skill_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        with open(os.path.join(fixture_dir, "sample_state.json"), "r") as f:
            self.state = json.load(f)
        with open(os.path.join(fixture_dir, "sample_mapping.json"), "r") as f:
            self.valid_mapping = json.load(f)
        # Create temp image files referenced in sample_state.json
        self._tmp_dir = tempfile.mkdtemp(prefix="web-to-pdf-test-")
        img_dir = os.path.join(self._tmp_dir, "runs", "example.com_20260725_120000", "images")
        os.makedirs(img_dir, exist_ok=True)
        for fname in ["abc123.jpg", "def456.png"]:
            with open(os.path.join(img_dir, fname), "wb") as f:
                f.write(b"fake-image-data")
        # Update state paths to point to real temp files
        base = os.path.join(self._tmp_dir, "runs", "example.com_20260725_120000")
        self.state["step1"]["run_dir"] = base
        self.state["step1"]["images_dir"] = os.path.join(base, "images")
        self.state["step1"]["image_map"]["__IMG_abc123__"] = os.path.join(base, "images", "abc123.jpg")
        self.state["step1"]["image_map"]["__IMG_def456__"] = os.path.join(base, "images", "def456.png")

    def tearDown(self):
        if hasattr(self, "_tmp_dir") and os.path.isdir(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_valid_mapping_passes(self):
        self.assertTrue(
            validate_mapping(self.valid_mapping, self.state, self.skill_dir)
        )

    def test_missing_template_field(self):
        mapping = {"slots": {"hero": {"heading": "Test"}}}
        self.assertFalse(
            validate_mapping(mapping, self.state, self.skill_dir)
        )

    def test_nonexistent_template(self):
        mapping = {"template": "nonexistent", "slots": {"hero": {"heading": "Test"}}}
        self.assertFalse(
            validate_mapping(mapping, self.state, self.skill_dir)
        )

    def test_missing_required_slot(self):
        mapping = {
            "template": "business-default",
            "slots": {
                "hero": {"heading": "Test", "subheading": "Sub", "image": None}
                # missing required "about" slot
            }
        }
        self.assertFalse(
            validate_mapping(mapping, self.state, self.skill_dir)
        )

    def test_missing_slots_key(self):
        mapping = {"template": "business-default"}
        self.assertFalse(
            validate_mapping(mapping, self.state, self.skill_dir)
        )

    def test_unresolved_image_id(self):
        mapping = {
            "template": "business-default",
            "slots": {
                "hero": {"heading": "H", "subheading": "S", "image": "__IMG_deadbe__"},
                "about": {"heading": "A", "body": "text"}
            }
        }
        self.assertFalse(
            validate_mapping(mapping, self.state, self.skill_dir)
        )


class TestTemplateSchema(unittest.TestCase):
    """Test template-schema.json loading."""

    def test_load_schema(self):
        skill_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        schema = load_template_schema(skill_dir)
        self.assertIn("templates", schema)
        self.assertIn("business-default", schema["templates"])
        template = schema["templates"]["business-default"]
        self.assertIn("slots", template)
        self.assertIn("hero", template["slots"])
        self.assertTrue(template["slots"]["hero"]["required"])
        self.assertIn("about", template["slots"])
        self.assertTrue(template["slots"]["about"]["required"])
        self.assertIn("features", template["slots"])
        self.assertFalse(template["slots"]["features"]["required"])


class TestConfig(unittest.TestCase):
    """Test build_pdf config loading."""

    def test_load_config(self):
        skill_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        config = load_config(skill_dir)
        self.assertIn("output_dir", config)
        self.assertIn("default_template", config)
        self.assertIn("default_engine", config)
        self.assertEqual(config["default_engine"], "weasyprint")


class TestRenderSlots(unittest.TestCase):
    """Test sub-template + monolithic fallback rendering."""

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp(prefix="web-to-pdf-slots-test-")
        self.template_dir = os.path.join(self._tmp_dir, "test-template")
        self.slots_dir = os.path.join(self.template_dir, "slots")
        os.makedirs(self.slots_dir, exist_ok=True)

        # Create template.html with monolithic slot blocks
        template_html = """<!DOCTYPE html>
<html><head><title>Test</title></head><body>
{{#slots.hero}}<section class="hero"><h1>{{ heading }}</h1></section>{{/slots.hero}}
{{#slots.about}}<section class="about"><h2>{{ heading }}</h2><p>{{{ body }}}</p></section>{{/slots.about}}
{{#slots.features}}<section class="features"><h2>{{ heading }}</h2>{{#items}}<div>{{ title }}</div>{{/items}}</section>{{/slots.features}}
</body></html>"""
        with open(os.path.join(self.template_dir, "template.html"), "w") as f:
            f.write(template_html)

        # Create a sub-template for hero slot
        hero_sub = '<section class="hero-custom"><h1>{{ heading }}</h1><p>{{ subheading }}</p></section>'
        with open(os.path.join(self.slots_dir, "hero.html"), "w") as f:
            f.write(hero_sub)

        # No sub-template for about or features (monolithic fallback)

    def tearDown(self):
        if hasattr(self, "_tmp_dir") and os.path.isdir(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_sub_template_used(self):
        """Slot with sub-template renders via slots/{name}.html."""
        slots = {"hero": {"heading": "Hello", "subheading": "World"}}
        with open(os.path.join(self.template_dir, "template.html"), "r") as f:
            tpl = f.read()
        result = render_slots(slots, self.template_dir, tpl)
        self.assertIn("hero-custom", result)
        self.assertIn("Hello", result)
        self.assertIn("World", result)

    def test_monolithic_fallback(self):
        """Slot without sub-template falls back to extracting from template.html."""
        slots = {"about": {"heading": "About Us", "body": "Some <b>rich</b> text"}}
        with open(os.path.join(self.template_dir, "template.html"), "r") as f:
            tpl = f.read()
        result = render_slots(slots, self.template_dir, tpl)
        self.assertIn("About Us", result)
        self.assertIn("<b>rich</b>", result)

    def test_mixed_sub_and_monolithic(self):
        """Mix of slots: hero uses sub-template, features uses monolithic."""
        slots = {
            "hero": {"heading": "H", "subheading": "S"},
            "features": {"heading": "Features", "items": [{"title": "F1"}, {"title": "F2"}]},
        }
        with open(os.path.join(self.template_dir, "template.html"), "r") as f:
            tpl = f.read()
        result = render_slots(slots, self.template_dir, tpl)
        self.assertIn("hero-custom", result)  # sub-template
        self.assertIn("Features", result)     # monolithic

    def test_skips_non_dict_slots(self):
        """Slots that are not dicts are skipped gracefully."""
        slots = {"hero": "not-a-dict", "about": {"heading": "A", "body": "text"}}
        with open(os.path.join(self.template_dir, "template.html"), "r") as f:
            tpl = f.read()
        result = render_slots(slots, self.template_dir, tpl)
        self.assertNotIn("not-a-dict", result)
        self.assertIn("A", result, "about slot should still render when preceded by a non-dict slot")

    def test_sub_template_render_failure_falls_back(self):
        """If sub-template rendering fails (bad Mustache), falls back to monolithic."""
        # Create a broken sub-template for hero
        with open(os.path.join(self.slots_dir, "hero.html"), "w") as f:
            f.write('<section>{{#broken}}{{/missing}}</section>')  # unclosed section
        slots = {"hero": {"heading": "H", "subheading": "S"}}
        with open(os.path.join(self.template_dir, "template.html"), "r") as f:
            tpl = f.read()
        result = render_slots(slots, self.template_dir, tpl)
        # Should fall back to monolithic: contains "hero" class, not "hero-custom"
        self.assertIn('class="hero"', result)
        self.assertNotIn("hero-custom", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
