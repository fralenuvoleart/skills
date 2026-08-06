"""
Shared configuration loader and utilities for web-to-pdf scripts.
Loads config/defaults.json with env-var overrides; also provides
file locking for concurrent .run_state.json access.
"""

import json
import os

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows: file locking unavailable; concurrent access is not guarded


def load_config(skill_dir: str) -> dict:
    """Load defaults.json. output_dir can be overridden by WEB_TO_PDF_OUTPUT_DIR env var,
    chromium_bin by CHROMIUM_BIN env var."""
    config_path = os.path.join(skill_dir, "config", "defaults.json")
    with open(config_path, "r") as f:
        config = json.load(f)
    env_output = os.environ.get("WEB_TO_PDF_OUTPUT_DIR")
    if env_output:
        config["output_dir"] = env_output
    env_chromium = os.environ.get("CHROMIUM_BIN")
    if env_chromium:
        config["chromium_bin"] = env_chromium
    return config


def resolve_output_dir(config: dict) -> str:
    """Resolve output_dir from config, expanding ~ and env vars."""
    return os.path.expanduser(os.path.expandvars(config["output_dir"]))


# -- File Locking (shared by orchestrator.py and build_pdf.py) ----------------

def lock_state_file(state_path: str, mode: str = "exclusive") -> object:
    """Acquire a file lock on .run_state.json for concurrency safety.
    On platforms without fcntl (Windows), locking is a no-op."""
    lock_dir = os.path.dirname(state_path)
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, ".run_state.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    if fcntl is not None:
        lock_op = fcntl.LOCK_SH if mode == "shared" else fcntl.LOCK_EX
        fcntl.flock(lock_fd, lock_op)
    return lock_fd


def unlock_state_file(lock_fd: object):
    """Release the file lock. On platforms without fcntl, just closes the fd."""
    if fcntl is not None:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
