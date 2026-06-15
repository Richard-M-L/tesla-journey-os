"""Pytest fixtures for TJOS tests."""

import sys
from pathlib import Path

# Ensure backend is importable
backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
