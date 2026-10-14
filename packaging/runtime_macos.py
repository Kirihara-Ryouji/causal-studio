"""Use writable per-user caches when launched from /Applications."""
import os
from pathlib import Path

cache = Path.home() / "Library" / "Caches" / "CausalStudio"
cache.mkdir(parents=True, exist_ok=True)
for variable, directory in (("MPLCONFIGDIR", "matplotlib"), ("NUMBA_CACHE_DIR", "numba")):
    path = cache / directory
    path.mkdir(exist_ok=True)
    os.environ.setdefault(variable, str(path))
