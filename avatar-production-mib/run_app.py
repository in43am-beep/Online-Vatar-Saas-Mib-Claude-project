"""run_app.py — frozen-exe entry shim.

Why this file exists: PyInstaller runs the entry script as __main__ with no
parent package, so the relative imports inside mib/ (``from . import ...``)
crash with "attempted relative import with no known parent package" in the
frozen exe. This shim lives at the repo root and imports the real entry point
via ABSOLUTE import, which works both in dev and in the frozen exe.

Dev:      python run_app.py            (or: python -m mib.app)
Smoke:    QT_QPA_PLATFORM=offscreen python run_app.py --smoke
Frozen:   build-exe.spec uses THIS file as the Analysis entry script.
"""
import sys

from mib.app import main

if __name__ == "__main__":
    sys.exit(main())
