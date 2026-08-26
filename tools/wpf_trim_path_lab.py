from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba2k_jersey_modder.trim_path_web_session import TrimPathWebSession
from nba2k_jersey_modder.web_editor import WebEditorServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--project-folder", required=True)
    arguments = parser.parse_args()
    session = TrimPathWebSession(
        Path(arguments.project),
        Path(arguments.pattern),
        Path(arguments.state),
        Path(arguments.project_folder),
    )
    server = WebEditorServer(session, port=8815)
    url = server.start().rstrip("/") + "/trim-path"
    print(json.dumps({"url": url}), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
