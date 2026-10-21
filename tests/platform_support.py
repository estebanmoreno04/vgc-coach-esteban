"""Platform capabilities some upstream tests rely on.

Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach so the suite is
green on Windows: a few upstream tests need POSIX process groups, symlink
creation, or a temporary directory on the same drive as the repository.
They still run everywhere those hold (for example in CI on Linux).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

POSIX = os.name == "posix"
SAME_DRIVE_TEMP = Path(tempfile.gettempdir()).resolve().drive.lower() == REPO_ROOT.resolve().drive.lower()


def _can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "target"
        target.write_text("x")
        try:
            os.symlink(target, Path(tmp) / "link")
        except (OSError, NotImplementedError):
            return False
    return True


SYMLINKS = _can_symlink()

NEEDS_POSIX = "needs POSIX process groups (agent-browser cleanup is POSIX-only by design)"
NEEDS_SYMLINKS = "needs permission to create symlinks (Windows requires Developer Mode or admin rights)"
NEEDS_SAME_DRIVE = "needs the temporary directory on the same drive as the repository"
