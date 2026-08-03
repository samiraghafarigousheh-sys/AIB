"""Make the vendored engine importable before any test module is loaded.

TWO SEPARATE LOADING HAZARDS LIVE HERE, BOTH OF WHICH MADE PYTEST EXIT 2

Exit 2 is a *collection* error, not a test failure (that is exit 1). A suite that
cannot be collected runs no assertions at all, which is easy to mistake for a
suite that passes if only the exit code is glanced at. Both causes are import
resolution, and neither is fixed by changing a test.

1.  The repository root contains a directory literally named
    ``pybuildingenergy/`` -- the vendored checkout, holding ``src/``, ``docs/``,
    ``tests/`` and so on. It has no ``__init__.py``, so under PEP 420 it is a
    perfectly valid *namespace package* called ``pybuildingenergy``. Running
    ``python -m pytest`` puts the repository root at ``sys.path[0]``, so a test
    module that imports ``pybuildingenergy.source.utils`` before anything has put
    ``pybuildingenergy/src`` on the path resolves the name to that directory --
    which has no ``source`` submodule -- and fails.

    It then fails for *every* remaining module too, because the broken resolution
    is cached in ``sys.modules``. That is why the suite could pass when three
    files were named explicitly (each does its own ``sys.path.insert``) and fail
    with nine collection errors when the whole directory was collected: one file
    without the insert poisons the rest. Ordering, not correctness.

    A regular package beats a namespace package in the path scan, so putting
    ``pybuildingenergy/src`` on ``sys.path`` here -- once, before any test module
    is imported -- resolves it for the whole session regardless of collection
    order or working directory.

2.  ``examples/`` holds the building dictionaries the tests drive (``apt305_building``).
    Added for the same reason.

The per-module ``sys.path.insert`` lines are left in place: they let a single
test file be run directly, outside pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

for path in (REPO_ROOT / "pybuildingenergy" / "src", REPO_ROOT / "examples"):
    entry = str(path)
    if path.is_dir() and entry not in sys.path:
        sys.path.insert(0, entry)
