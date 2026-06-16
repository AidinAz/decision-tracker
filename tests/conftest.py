from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ["PYTHONPATH"] = (
    f"{SRC}{os.pathsep}{os.environ['PYTHONPATH']}" if os.environ.get("PYTHONPATH") else str(SRC)
)

BIN_DIR = Path(tempfile.mkdtemp(prefix="dt-test-bin-"))
atexit.register(lambda: shutil.rmtree(BIN_DIR, ignore_errors=True))

DT_SHIM = BIN_DIR / "dt"
DT_SHIM.write_text(
    "\n".join(
        [
            "#!/bin/sh",
            f'export PYTHONPATH="{SRC}${{PYTHONPATH:+:${{PYTHONPATH}}}}"',
            f'exec "{sys.executable}" -m dt.cli "$@"',
            "",
        ]
    ),
    encoding="utf-8",
)
DT_SHIM.chmod(0o755)

os.environ["PATH"] = f"{BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"
