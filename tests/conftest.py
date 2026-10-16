import os
import sys

# Make the repo root importable so `from processor...` works under pytest
# without an install step (same as PYTHONPATH=/app in the image).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
