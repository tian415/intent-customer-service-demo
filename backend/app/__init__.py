"""Backend package with the repository-local, dependency-free ml module."""
import sys
from pathlib import Path

# Both `uvicorn app.main` from backend/ and `python -m ml.train` from root use
# the same local module. No copied implementations or global package install.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
