#!/usr/bin/env python3
"""
Tests for orchestrator.py -- Phase 1 data gathering.

Run: python3 .agents/skills/web-to-pdf/scripts/tests/test_orchestrator.py
"""

import json
import os
import sys
import tempfile
import unittest

# Add parent script dir to path so we can import orchestrator and config_loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config_loader import load_config, resolve_output_dir
from orchestrator import (
    html_to_markdown,
    make_image_id,
)
from bs4 import BeautifulSoup


class TestMakeImageId(unittest.TestCase):
    """Test __IMG_*__ ID generation."""

    def test_deterministic(self):
        url = "https://example.com/image.jpg"
        id1 = make_image_id(url)
        id2 = make_image_id(url)
        self.assertEqual(id1, id2, "Same URL should produce same ID")

    def test_format(self):
        url = "https://example.com/image.jpg"
        img_id = make_image_id(url)
        self.assertTrue(img_id.startswith("__IMG_"), f"Expected __IMG_ prefix, got: {img_id}")
        self.assertTrue(img_id.endswith("__"), f"Expected __ suffix, got: {img_id}")
        self.assertEqual(len(img_id), 14, f"Expected 14 chars, got: {len(img_id)}")

    def test_different_urls_different_ids(self):
        id1 = make_image_id("https://example.com/a.jpg")
        id2 = make_image_id("https://example.com/b.jpg")
        self.assertNotEqual(id1, id2, "Different URLs should produce different IDs")


class TestHtmlToMarkdown(unittest.TestCase):
    """Test HTML -> Markdown conversion."""

    def test_strips_nav_and_footer(self):
        html = "<html><body><nav>Skip me</nav><p>Keep me</p><footer>Skip too</footer></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("Keep me", result)
        self.assertNotIn("Skip me", result)
        self.assertNotIn("Skip too", result)

    def test_strips_script_and_style(self):
        html = "<html><body><script>alert(1)</script><style>body{}</style><p>Content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("Content", result)
        self.assertNotIn("alert", result)
        self.assertNotIn("body{}", result)

    def test_headings(self):
        html = "<html><body><h1>Title</h1><h2>Subtitle</h2><p>Text</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("# Title", result)
        self.assertIn("## Subtitle", result)

    def test_images_with_ids(self):
        html = '<html><body><img src="https://example.com/a.jpg" alt="Photo"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("![Photo]", result)
        self.assertIn("__IMG_", result)
        self.assertEqual(len(image_map), 1, "Should have 1 image mapped")
        img_id = list(image_map.keys())[0]
        self.assertEqual(image_map[img_id], "https://example.com/a.jpg")

    def test_image_deduplication(self):
        """Same URL twice should produce same image ID."""
        html = '<html><body><img src="https://example.com/a.jpg"><img src="https://example.com/a.jpg"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertEqual(len(image_map), 1, "Duplicate URL should only be mapped once")

    def test_strong_and_em(self):
        html = "<html><body><p><strong>Bold</strong> and <em>italic</em></p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("**Bold**", result)
        self.assertIn("*italic*", result)

    def test_links(self):
        html = '<html><body><a href="https://example.com">Click here</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("[Click here](https://example.com)", result)

    def test_lists(self):
        html = "<html><body><ul><li>Item 1</li><li>Item 2</li></ul></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("- Item 1", result)
        self.assertIn("- Item 2", result)

    def test_code_inline(self):
        html = "<html><body><code>print('hello')</code></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("`print('hello')`", result)

    def test_skips_empty_image_src(self):
        html = '<html><body><img src=""><img alt="no src"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertEqual(len(image_map), 0, "Empty src should not be mapped")

    def test_empty_page(self):
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertEqual(result.strip(), "", "Empty page should produce empty markdown")

    def test_skips_anchor_links(self):
        html = '<html><body><a href="#section">Jump</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)
        self.assertIn("Jump", result)
        self.assertNotIn("(#section)", result)

    def test_sample_page(self):
        """Integration test with the fixture HTML."""
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_page.html")
        with open(fixture_path, "r") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        image_map = {}
        result = html_to_markdown(soup, image_map)

        # Should contain headings
        self.assertIn("# We Build Amazing Software", result)
        self.assertIn("## Why Choose Us", result)
        self.assertIn("## Our Services", result)
        self.assertIn("## What Our Clients Say", result)

        # Should contain content
        self.assertIn("Web Development", result)
        self.assertIn("Mobile Apps", result)
        self.assertIn("Cloud Infrastructure", result)

        # Should contain images
        self.assertGreater(len(image_map), 0, "Should have mapped at least one image")

        # Should NOT contain nav or footer
        self.assertNotIn("Home", result.split("# ")[0])  # nav text in first section
        self.assertNotIn("\xc2\xa9 2024", result)

        print(f"\nSample page conversion ({len(result)} chars):")
        print(result[:500])


class TestConfig(unittest.TestCase):
    """Test config loading."""

    def test_load_config(self):
        skill_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        config = load_config(skill_dir)
        self.assertIn("output_dir", config)
        self.assertIn("default_template", config)
        self.assertIn("validation", config)
        self.assertEqual(config["default_template"], "business-default")

    def test_resolve_output_dir(self):
        config = {"output_dir": "~/test-output"}
        resolved = resolve_output_dir(config)
        self.assertNotIn("~", resolved)
        self.assertTrue(os.path.isabs(resolved))


if __name__ == "__main__":
    unittest.main(verbosity=2)
