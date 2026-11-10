"""Puts the core package on the path; it is importable without OrcaSlicer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "line_art_studio"))
