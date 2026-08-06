#!/usr/bin/env python3
"""
orchestrator.py — Phase 1: Data Gathering
Fetches a URL, extracts content to Markdown, captures screenshot, caches images.

Interface contract: references/interface-contracts.md
Outputs: content.md (with __IMG_*__ IDs), page.png, images/, .run_state.json (step1 namespace)

Configuration: config/defaults.json (overridable via WEB_TO_PDF_OUTPUT_DIR env var)

Dependencies: requests, beautifulsoup4, Chromium (subprocess)
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

# Optional dependency -- graceful error if not installed
try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup, Comment, NavigableString
except ImportError:
    BeautifulSoup = None
    Comment = None
    NavigableString = None


# -- Config ----------------------------------------------------------------

from config_loader import load_config, resolve_output_dir, lock_state_file, unlock_state_file


# -- HTTP Retry Helper -----------------------------------------------------

def _fetch_with_retry(url: str, timeout: int = 30, max_retries: int = 3, stream: bool = False):
    """Fetch URL with exponential backoff for transient network errors.
    Retries on ConnectionError and Timeout; does NOT retry HTTPError (4xx/5xx).
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout, stream=stream, headers={
                "User-Agent": "Mozilla/5.0 (compatible; WebToPdf/1.0)"
            })
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt + 1}/{max_retries} after {wait}s: {e}")
                time.sleep(wait)
        # HTTPError (4xx/5xx) — do not retry, let caller handle
    raise last_exc  # type: ignore[misc]


# -- HTML Fetching & Parsing -----------------------------------------------

STRIP_TAGS = {"nav", "footer", "script", "style", "noscript", "svg", "iframe", "form"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "header", "aside",
              "blockquote", "pre", "figure", "figcaption", "table", "hr"}

# Hard-fail guard during extraction -- catches catastrophic failures (empty pages,
# JS-only SPAs) before the config-driven quality gate in validate_output().
# The validate_output() step applies config->validation->min_content_chars (default: 50)
# as the actual quality threshold.
_MIN_CONTENT_CHARS_HARDFAIL = 20

# Logo detection — CSS class/id patterns that indicate a logo image
_LOGO_PATTERNS = ["logo", "brand", "site-logo", "header-logo", "navbar-brand"]


def detect_logo(soup: BeautifulSoup, base_url: str) -> str | None:
    """Multi-strategy logo URL detection. Returns resolved URL or None.

    Strategies (first match wins):
    1. <link rel="icon"> or <link rel="apple-touch-icon"> (favicon)
    2. <meta property="og:image"> (Open Graph image)
    3. <img> with logo semantics in class/id/alt/src
    4. First <img> inside <header> (semantic HTML)
    5. JSON-LD Schema.org Organization.logo
    """
    # Strategy 1: favicon / apple-touch-icon
    for rel_val in ("icon", "shortcut icon", "apple-touch-icon", "apple-touch-icon-precomposed"):
        icon = soup.find("link", rel=lambda r: r and r.lower() == rel_val)
        if icon and icon.get("href"):
            href = icon["href"]
            if not href.startswith("data:"):
                return urljoin(base_url, href)

    # Strategy 2: og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        content = og["content"]
        if not content.startswith("data:"):
            return urljoin(base_url, content)

    # Strategy 3: <img> with logo semantics
    for img in soup.find_all("img"):
        combined = " ".join([
            " ".join(img.get("class", [])),
            img.get("id", ""),
            img.get("alt", ""),
            img.get("src", ""),
        ]).lower()
        if any(pat in combined for pat in _LOGO_PATTERNS):
            src = img.get("src", "")
            if src and not src.startswith("data:"):
                return urljoin(base_url, src)

    # Strategy 4: first <img> inside <header>
    header = soup.find("header")
    if header:
        first_img = header.find("img")
        if first_img and first_img.get("src"):
            src = first_img["src"]
            if not src.startswith("data:"):
                return urljoin(base_url, src)

    # Strategy 5: JSON-LD Organization.logo
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            org = data if isinstance(data, dict) and data.get("@type") == "Organization" else None
            if isinstance(data, list):
                org = next((d for d in data if isinstance(d, dict) and d.get("@type") == "Organization"), None)
            if org:
                logo = org.get("logo")
                if isinstance(logo, str) and not logo.startswith("data:"):
                    return urljoin(base_url, logo)
                if isinstance(logo, dict) and logo.get("url"):
                    logo_url = logo["url"]
                    if not logo_url.startswith("data:"):
                        return urljoin(base_url, logo_url)
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    return None


def download_logo(logo_url: str, images_dir: str, base_url: str) -> str | None:
    """Download the logo image. Returns local file path or None on failure."""
    if requests is None:
        return None
    try:
        full_url = urljoin(base_url, logo_url)
        parsed = urlparse(full_url)
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico"):
            ext = ".png"
        local_name = f"logo{ext}"
        local_path = os.path.join(images_dir, local_name)

        print(f"  Logo detected: {full_url[:80]}...")
        resp = _fetch_with_retry(full_url, timeout=15)

        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"    -> {local_name} ({len(resp.content)} bytes)")
        return local_path
    except Exception as e:
        print(f"    WARNING Logo download failed: {e}", file=sys.stderr)
        return None


def make_image_id(url: str) -> str:
    """Generate a deterministic __IMG_*__ ID from an image URL."""
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return f"__IMG_{digest[:6]}__"


def html_to_markdown(soup: BeautifulSoup, image_map: dict) -> str:
    """
    Recursively convert a BeautifulSoup tree to Markdown.
    - Strips tags in STRIP_TAGS entirely.
    - Converts headings to # markers.
    - Converts <img> to ![alt](__IMG_*__) and records in image_map.
    - Converts <a> to [text](url) or bare text.
    - Converts <li> to - / 1. markers.
    - Preserves <strong>/<em> as ** / *.
    - Strips all other tags, preserving inner text.
    """
    output = []

    def walk(element, list_depth=0):
        if isinstance(element, NavigableString):
            text = str(element)
            # Skip pure whitespace between block elements
            if not output and text.strip() == "":
                return
            output.append(text)
            return

        if element.name is None:
            # Fragment -- process children
            for child in element.children:
                walk(child, list_depth)
            return

        tag = element.name.lower()

        # Strip unwanted tags and their children
        if tag in STRIP_TAGS:
            return

        # Skip HTML comments
        if isinstance(element, Comment):
            return

        # Headings
        if tag in HEADING_TAGS:
            level = int(tag[1])
            text = element.get_text(" ", strip=True)
            if text:
                output.append("\n\n" + "#" * level + " " + text + "\n\n")
            return

        # Images
        if tag == "img":
            src = element.get("src", "")
            if src:
                # Skip data: URIs — inline/base64 images cannot be fetched via HTTP
                # and would create orphan __IMG_*__ IDs that never resolve in image_map.
                if src.startswith("data:"):
                    alt = element.get("alt", "").strip()
                    output.append(f"\n\n[Inline image: {alt or 'no alt text'}]\n\n")
                    return
                alt = element.get("alt", "").strip()
                img_id = make_image_id(src)
                # Deduplicate: if this URL is already mapped under any ID, reuse that ID
                found_id = None
                for existing_id, existing_url in image_map.items():
                    if existing_url == src:
                        found_id = existing_id
                        break
                if found_id:
                    img_id = found_id
                elif img_id not in image_map:
                    image_map[img_id] = src

                output.append(f"\n\n![{alt}]({img_id})\n\n")
            return

        # Links
        if tag == "a":
            href = element.get("href", "")
            text = element.get_text(" ", strip=True)
            if text and href and not href.startswith("#"):
                output.append(f"[{text}]({href})")
            elif text:
                output.append(text)
            return

        # Line breaks
        if tag == "br":
            output.append("\n")
            return

        # Lists
        if tag == "li":
            marker = "- " if list_depth == 0 else "  1. " if list_depth == 1 else "  - "
            output.append("\n" + marker)
            for child in element.children:
                walk(child, list_depth + 1)
            return

        # Block elements -- add spacing
        if tag in BLOCK_TAGS:
            output.append("\n\n")
            for child in element.children:
                walk(child, list_depth)
            output.append("\n\n")
            return

        # Inline elements -- no spacing
        if tag == "strong" or tag == "b":
            output.append("**")
            for child in element.children:
                walk(child, list_depth)
            output.append("**")
            return

        if tag == "em" or tag == "i":
            output.append("*")
            for child in element.children:
                walk(child, list_depth)
            output.append("*")
            return

        if tag == "code":
            text = element.get_text()
            if "\n" in text:
                output.append(f"\n\n```\n{text}\n```\n\n")
            else:
                output.append(f"`{text}`")
            return

        # Picture element — process children to find the fallback <img>.
        # <source> children are void elements with no text; they are harmless.
        if tag == "picture":
            for child in element.children:
                walk(child, list_depth)
            return

        # Unknown tags -- process children
        for child in element.children:
            walk(child, list_depth)

    # Start walking from body if available, otherwise from root
    body = soup.find("body")
    root = body if body else soup
    for child in root.children:
        walk(child)

    # Clean up: collapse 3+ newlines to 2, trim
    md = "".join(output)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = md.strip()
    return md


def fetch_and_extract(url: str, output_dir: str, timestamp: str) -> tuple:
    """
    Fetch URL, extract content to Markdown, return (markdown, image_map, run_dir,
    images_dir, content_path, soup).
    Raises RuntimeError on failure.
    """
    if requests is None or BeautifulSoup is None:
        raise RuntimeError(
            "Missing dependencies. Install with: pip install requests beautifulsoup4"
        )

    print(f"  Fetching: {url}")
    resp = _fetch_with_retry(url, timeout=30)
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract domain for run directory
    domain = urlparse(url).netloc.replace(":", "_")
    run_dir = os.path.join(output_dir, "runs", f"{domain}_{timestamp}")
    images_dir = os.path.join(run_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # Convert to Markdown
    image_url_map = {}  # img_id -> original_url
    markdown = html_to_markdown(soup, image_url_map)

    # Hard-fail guard: catch empty/JS-only pages early.
    # The real quality threshold is config->validation->min_content_chars applied by --validate.
    if not markdown or len(markdown.strip()) < _MIN_CONTENT_CHARS_HARDFAIL:
        # Check for common SPA root elements
        spa_roots = soup.find_all(id=re.compile(r'^(root|app|__next)$', re.IGNORECASE))
        if spa_roots and not any(root.get_text(strip=True) for root in spa_roots):
            raise RuntimeError(
                f"Extracted content is too short ({len(markdown.strip()) if markdown else 0} chars). "
                f"Detected empty SPA root element (<div id='{spa_roots[0].get('id')}'>). "
                f"This page requires JavaScript rendering. Use Playwright-based extraction."
            )
        raise RuntimeError(
            f"Extracted content is too short ({len(markdown.strip()) if markdown else 0} chars, "
            f"hard-fail guard at {_MIN_CONTENT_CHARS_HARDFAIL}). "
            f"The page may be JS-rendered or have no extractable content."
        )

    # Write content.md
    content_path = os.path.join(run_dir, "content.md")
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    # Extract page title for header/footer
    title_tag = soup.find("title")
    site_title = title_tag.get_text(strip=True) if title_tag else url

    print(f"  Content extracted: {len(markdown)} chars, {len(image_url_map)} images found")

    return markdown, image_url_map, run_dir, images_dir, content_path, soup, site_title


# -- Image Download --------------------------------------------------------

def download_images(image_url_map: dict, images_dir: str, base_url: str) -> dict:
    """
    Download all images from image_url_map to images_dir.
    Returns image_map: __IMG_*__ -> local_path.
    """
    if requests is None:
        raise RuntimeError("Missing dependency: pip install requests")

    image_map = {}
    for img_id, original_url in image_url_map.items():
        # Skip data: URIs — they are inline/base64 and cannot be fetched via HTTP
        if original_url.startswith("data:"):
            print(f"  Skipping inline data URI: {img_id}")
            continue

        try:
            # Resolve relative URLs
            full_url = urljoin(base_url, original_url)

            print(f"  Downloading: {full_url[:80]}...")
            resp = _fetch_with_retry(full_url, timeout=15)

            # Determine extension from URL or Content-Type
            parsed = urlparse(full_url)
            ext = os.path.splitext(parsed.path)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
                content_type = resp.headers.get("Content-Type", "").lower()
                if "image/png" in content_type:
                    ext = ".png"
                elif "image/gif" in content_type:
                    ext = ".gif"
                elif "image/webp" in content_type:
                    ext = ".webp"
                elif "image/svg+xml" in content_type:
                    ext = ".svg"
                else:
                    ext = ".jpg"  # default fallback

            local_name = f"{img_id[2:-2]}{ext}"  # strip __IMG_ and __
            local_path = os.path.join(images_dir, local_name)

            with open(local_path, "wb") as f:
                f.write(resp.content)

            image_map[img_id] = local_path
            print(f"    -> {local_name} ({len(resp.content)} bytes)")

        except Exception as e:
            print(f"    WARNING Failed to download {original_url}: {e}", file=sys.stderr)
            # Do not add failed downloads to image_map -- validation treats
            # missing entries as warnings, not hard failures.

    return image_map


# -- Screenshot Capture ----------------------------------------------------

def capture_screenshot(url: str, screenshot_path: str, config: dict) -> bool:
    """
    Capture a full-page screenshot via Chromium headless.
    Returns True on success.
    """
    chromium_bin = os.path.expanduser(config.get("chromium_bin", "chromium"))
    width = config.get("screenshot_width", 1280)
    full_page = config.get("screenshot_full_page", True)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)

    cmd = [
        chromium_bin,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--screenshot={screenshot_path}",
        f"--window-size={width},1024",
    ]
    if full_page:
        # Chromium --screenshot captures only the viewport.
        # Set a very tall viewport (20000px) and use --virtual-time-budget
        # to let the page fully render before capture. This handles virtually
        # all real-world pages. Pages taller than 20000px will be truncated.
        cmd.append(f"--window-size={width},20000")
        cmd.append("--virtual-time-budget=10000")

    cmd.append(url)

    try:
        print(f"  Capturing screenshot: {chromium_bin} --headless --screenshot=...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  WARNING Chromium stderr: {result.stderr[:200]}", file=sys.stderr)
            return False
        if os.path.isfile(screenshot_path) and os.path.getsize(screenshot_path) > 0:
            print(f"  Screenshot saved: {screenshot_path} ({os.path.getsize(screenshot_path)} bytes)")
            return True
        else:
            print(f"  WARNING Screenshot file not created or empty", file=sys.stderr)
            return False
    except FileNotFoundError:
        print(f"  WARNING Chromium not found at {chromium_bin}. Set CHROMIUM_BIN env var.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"  WARNING Screenshot timed out after 30s", file=sys.stderr)
        return False


# -- State Writing ---------------------------------------------------------

def write_run_state(
    state_path: str,
    url: str,
    template: str,
    run_dir: str,
    content_md: str,
    screenshot_png: str,
    images_dir: str,
    image_map: dict,
    screenshot_skipped: bool = False,
    logo_path: str | None = None,
    site_title: str = "",
):
    """Write step1 namespace to .run_state.json with exclusive lock."""
    lock_fd = lock_state_file(state_path, "exclusive")
    try:
        # Read existing state if any (for append-only)
        state = {}
        if os.path.exists(state_path):
            with open(state_path, "r") as f:
                try:
                    state = json.load(f)
                except json.JSONDecodeError:
                    state = {}

        state["step1"] = {
            "url": url,
            "template": template,
            "run_dir": run_dir,
            "content_md": content_md,
            "screenshot_png": screenshot_png,
            "images_dir": images_dir,
            "image_map": image_map,
            "logo": logo_path,
            "site_title": site_title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "screenshot_skipped": screenshot_skipped,
        }

        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        print(f"  State written: {state_path}")
    finally:
        unlock_state_file(lock_fd)


# -- Validation ------------------------------------------------------------

def validate_output(state_path: str, config: dict) -> bool:
    """Validate that all Phase 1 outputs exist and conform to the interface contract."""
    state_path = os.path.expanduser(state_path)
    v = config.get("validation", {})

    if not os.path.exists(state_path):
        print(f"FAIL: .run_state.json not found at {state_path}", file=sys.stderr)
        return False

    # Use shared lock for reading during validation
    lock_fd = None
    try:
        lock_fd = lock_state_file(state_path, "shared")

        with open(state_path, "r") as f:
            state = json.load(f)
    finally:
        if lock_fd is not None:
            unlock_state_file(lock_fd)

    step1 = state.get("step1", {})
    errors = []

    for key in ["url", "template", "run_dir", "content_md", "screenshot_png",
                "images_dir", "image_map", "timestamp"]:
        if key not in step1:
            errors.append(f"Missing required key: step1.{key}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return False

    content_md = os.path.expanduser(step1["content_md"])
    screenshot_png = os.path.expanduser(step1["screenshot_png"])
    images_dir = os.path.expanduser(step1["images_dir"])

    if not os.path.isfile(content_md):
        print(f"FAIL: content.md not found at {content_md}", file=sys.stderr)
        return False

    with open(content_md, "r") as f:
        content = f.read()
    min_chars = v.get("min_content_chars", 50)
    if len(content.strip()) < min_chars:
        print(f"FAIL: content.md too short ({len(content.strip())} chars, min {min_chars})", file=sys.stderr)
        return False
    if "#" not in content:
        print(f"FAIL: content.md has no headings", file=sys.stderr)
        return False

    img_refs_found = re.findall(r'!\[.*?\]\((__IMG_[a-f0-9]{6}__)\)', content)
    if img_refs_found:
        for ref in img_refs_found:
            if ref not in step1["image_map"]:
                print(f"WARNING: image ID {ref} in content.md not in image_map (download likely failed)", file=sys.stderr)
                # Not a hard fail -- download failures were already reported by download_images()

    if step1.get("screenshot_skipped"):
        print("  Screenshot was skipped (--no-screenshot or capture failed) — skipping screenshot validation")
    elif not os.path.isfile(screenshot_png):
        print(f"FAIL: page.png not found at {screenshot_png}", file=sys.stderr)
        return False
    else:
        # Validate image via magic bytes (replaces deprecated imghdr, removed in Python 3.13)
        with open(screenshot_png, "rb") as _f:
            _header = _f.read(8)
        if _header[:8] != b'\x89PNG\r\n\x1a\n' and _header[:2] != b'\xff\xd8':
            print(f"FAIL: page.png is not a valid PNG or JPEG image", file=sys.stderr)
            return False
        file_size = os.path.getsize(screenshot_png)
        min_bytes = v.get("min_screenshot_bytes", 10240)
        if file_size < min_bytes:
            print(f"FAIL: page.png too small ({file_size} bytes, min {min_bytes})", file=sys.stderr)
            return False

    if not os.path.isdir(images_dir):
        print(f"FAIL: images/ directory not found at {images_dir}", file=sys.stderr)
        return False

    for img_id, img_path in step1["image_map"].items():
        if not img_path or not os.path.isfile(img_path):
            print(f"FAIL: image_map references missing file: {img_id} -> {img_path}", file=sys.stderr)
            return False

    # Logo validation (optional — warn if missing but don't fail)
    logo_path = step1.get("logo")
    if logo_path and not os.path.isfile(os.path.expanduser(logo_path)):
        print(f"WARNING: logo file missing at {logo_path}", file=sys.stderr)

    print("VALIDATION PASSED: All Phase 1 outputs present and well-formed.")
    return True


# -- Main ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate webpage content extraction for PDF generation."
    )
    parser.add_argument("--url", help="URL of the webpage to extract")
    parser.add_argument(
        "--template",
        default=None,
        help="Template name (defaults to config/defaults.json)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate Phase 1 outputs against the interface contract",
    )
    parser.add_argument(
        "--no-screenshot",
        action="store_true",
        help="Skip screenshot capture",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image download (image_map will be empty)",
    )
    parser.add_argument(
        "--no-logo",
        action="store_true",
        help="Skip logo detection and download",
    )
    args = parser.parse_args()

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_config(skill_dir)
    output_dir = resolve_output_dir(config)
    state_path = os.path.join(output_dir, ".run_state.json")

    # --validate mode
    if args.validate:
        ok = validate_output(state_path, config)
        sys.exit(0 if ok else 1)

    # Normal mode
    if not args.url:
        parser.error("--url is required (or use --validate to check existing outputs)")

    # Validate URL scheme
    parsed_url = urlparse(args.url)
    if parsed_url.scheme not in ("http", "https"):
        print(f"Error: URL scheme must be http or https, got: '{parsed_url.scheme or 'none'}'",
              file=sys.stderr)
        sys.exit(1)

    template = args.template or config["default_template"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Orchestrating extraction for: {args.url}")
    print(f"Template: {template}")
    print(f"Output directory: {output_dir}")
    print()

    try:
        # Step 1: Fetch and extract content (now also returns soup for logo detection)
        markdown, image_url_map, run_dir, images_dir, content_path, soup, site_title = fetch_and_extract(
            args.url, output_dir, timestamp
        )

        # Step 1.5: Logo detection and download
        logo_path = None
        if not args.no_logo:
            logo_url = detect_logo(soup, args.url)
            if logo_url:
                logo_path = download_logo(logo_url, images_dir, args.url)
            else:
                print("  Logo: not detected")

        # Step 2: Download images
        image_map = {}
        if not args.no_images and image_url_map:
            image_map = download_images(image_url_map, images_dir, args.url)
        elif image_url_map:
            # --no-images: skip image download; map stays empty.
            # content.md still references __IMG_*__ IDs, but without local paths
            # they will be skipped gracefully at render time.
            image_map = {}

        # Step 3: Capture screenshot
        screenshot_path = os.path.join(run_dir, "page.png")
        screenshot_ok = False
        if not args.no_screenshot:
            screenshot_ok = capture_screenshot(args.url, screenshot_path, config)
        if not screenshot_ok:
            # Create a minimal placeholder so validation doesn't hard-fail
            # (validation will still flag it as too small)
            print(f"  WARNING Screenshot skipped or failed -- creating placeholder", file=sys.stderr)
            with open(screenshot_path, "wb") as f:
                f.write(b"")

        # Step 4: Write state
        write_run_state(
            state_path,
            args.url,
            template,
            run_dir,
            content_path,
            screenshot_path,
            images_dir,
            image_map,
            screenshot_skipped=(not screenshot_ok),
            logo_path=logo_path,
            site_title=site_title,
        )

        print()
        print("-" * 50)
        print("Phase 1 complete. Outputs:")
        print(f"  Run directory:  {run_dir}")
        print(f"  Content:        {content_path} ({len(markdown)} chars)")
        print(f"  Screenshot:     {screenshot_path}")
        print(f"  Images:         {len(image_map)} downloaded")
        if logo_path:
            print(f"  Logo:           {logo_path}")
        else:
            print(f"  Logo:           not detected")
        print(f"  State:          {state_path}")
        print()
        print("Next: validate with --validate, then proceed to Phase 2 (LLM analysis).")

    except Exception as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
