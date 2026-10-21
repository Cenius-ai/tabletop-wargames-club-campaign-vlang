"""Pytest bootstrap: keep the project importable from any working directory.

The suite is started as ``pytest -q`` (sometimes from outside the project root),
so the application package must be on ``sys.path`` regardless of cwd/rootdir.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
