"""
Pytest configuration and environment bootstrap for Pico.
Ensures 'pico' is importable whether running from inside repo, from parent,
or when cloned into a directory not named 'pico'.
"""
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 1. Add REPO_ROOT and its parent to sys.path
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 2. If the folder name is not 'pico', set up an environment alias so 'import pico' always succeeds
if REPO_ROOT.name != "pico" and "pico" not in sys.modules:
    import tempfile
    alias_dir = Path(tempfile.gettempdir()) / "pico_alias_env"
    alias_dir.mkdir(parents=True, exist_ok=True)
    symlink_pico = alias_dir / "pico"
    if symlink_pico.is_symlink() or symlink_pico.exists():
        try:
            symlink_pico.unlink()
        except Exception:
            pass
    try:
        symlink_pico.symlink_to(REPO_ROOT)
    except Exception:
        pass
    if str(alias_dir) not in sys.path:
        sys.path.insert(0, str(alias_dir))
    curr_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(alias_dir), str(REPO_ROOT.parent), str(REPO_ROOT), curr_pythonpath]))
