"""Repository-local entry point for Ulta swatch color extraction."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.colors.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
