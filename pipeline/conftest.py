import sys
from pathlib import Path

# Make preflight_pipeline importable without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent))
