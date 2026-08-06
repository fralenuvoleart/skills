#!/usr/bin/env python3
"""
Integration test for web-to-pdf skill — full pipeline: orchestrator → LLM mapping → build PDF.

Run: python3 .agents/skills/web-to-pdf/scripts/tests/test_integration.py
"""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer, SimpleHTTPRequestHandler

class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a temporary directory for the test server
        cls.server_dir = tempfile.mkdtemp()
        cls.html_path = os.path.join(cls.server_dir, "index.html")
        with open(cls.html_path, "w", encoding="utf-8") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Integration Test</h1>
                <p>This is a test paragraph with enough content to pass the validation threshold.</p>
                <p>Adding more text to ensure we hit the 50 character minimum for content extraction.</p>
            </body>
            </html>
            """)

        # Start a simple HTTP server in a background thread
        cls.server = HTTPServer(('localhost', 0), SimpleHTTPRequestHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()

        # Change working directory to server_dir for the handler
        cls.original_cwd = os.getcwd()
        os.chdir(cls.server_dir)

        # Create a temporary output directory for the skill
        cls.output_dir = tempfile.mkdtemp()
        os.environ["WEB_TO_PDF_OUTPUT_DIR"] = cls.output_dir

        cls.skill_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.original_cwd)
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()
        shutil.rmtree(cls.server_dir)
        shutil.rmtree(cls.output_dir)
        if "WEB_TO_PDF_OUTPUT_DIR" in os.environ:
            del os.environ["WEB_TO_PDF_OUTPUT_DIR"]

    def test_full_pipeline(self):
        url = f"http://localhost:{self.port}/index.html"
        
        # Phase 1: Orchestrator
        orchestrator_script = os.path.join(self.skill_dir, "scripts", "orchestrator.py")
        result = subprocess.run(
            ["python3", orchestrator_script, "--url", url],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"Orchestrator failed: {result.stderr}")

        # Validate Phase 1
        result = subprocess.run(
            ["python3", orchestrator_script, "--validate"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"Validation failed: {result.stderr}")

        # Phase 2: Mock LLM Mapping
        state_path = os.path.join(self.output_dir, ".run_state.json")
        with open(state_path, "r") as f:
            state = json.load(f)
        
        run_dir = state["step1"]["run_dir"]
        mapping_path = os.path.join(run_dir, "analyst_mapping.json")
        
        mapping = {
            "template": "business-default",
            "slots": {
                "hero": {
                    "heading": "Integration Test",
                    "subheading": "This is a test paragraph with enough content to pass the validation threshold."
                },
                "about": {
                    "heading": "About",
                    "body": "This is a test paragraph with enough content to pass the validation threshold."
                }
            }
        }
        with open(mapping_path, "w") as f:
            json.dump(mapping, f)

        # Phase 3: Build PDF
        build_script = os.path.join(self.skill_dir, "scripts", "build_pdf.py")
        result = subprocess.run(
            ["python3", build_script, "--mapping", mapping_path, "--no-cleanup"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"Build PDF failed: {result.stderr}")

        # Verify PDF exists and is > 1KB
        with open(state_path, "r") as f:
            state = json.load(f)
        
        pdf_path = state["step3"]["pdf_path"]
        self.assertTrue(os.path.exists(pdf_path), "PDF file was not created")
        self.assertGreater(os.path.getsize(pdf_path), 1024, "PDF file is too small")

if __name__ == "__main__":
    unittest.main()
