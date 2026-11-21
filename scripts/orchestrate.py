#!/usr/bin/env python3
"""Convenient entry point for the auto-research CLI."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autoresearch.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
