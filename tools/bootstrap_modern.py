from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MARKER = VENV / ".requirements.sha256"


def main() -> int:
    if not (VENV / "Scripts" / "python.exe").exists():
        print("Preparing the modern desktop runtime. This is needed only once...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    python = VENV / "Scripts" / "python.exe"
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    installed = MARKER.read_text(encoding="ascii").strip() if MARKER.exists() else ""
    if installed != digest:
        print("Installing desktop components. This is needed only after an app update...")
        subprocess.check_call([
            str(python), "-m", "pip", "install", "--disable-pip-version-check",
            "--requirement", str(REQUIREMENTS),
        ])
        MARKER.write_text(digest, encoding="ascii")
    subprocess.check_call([str(python), "-c", "import PIL, PySide6"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
