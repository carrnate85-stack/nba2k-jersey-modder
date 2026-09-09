from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba2k_jersey_modder.editor_assets import load_editor_html

from nba2k_jersey_modder.logo_web_session import LogoWebSession


HTML = load_editor_html("wpf_logo_web_html.html")


EDITOR_HTML = load_editor_html("wpf_logo_web_editor_html.html")


def handler_class(session: LogoWebSession):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *args):
            return

        def do_GET(self):  # noqa: N802
            try:
                path = urlparse(self.path).path
                if path in ("/", "/logo"):
                    self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/edit":
                    self._send(EDITOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/api/project":
                    self._json(session.project())
                elif path == "/api/reference":
                    self._send(*session.reference_bytes())
                elif path.startswith("/api/preview/"):
                    self._send(*session.preview_bytes(unquote(path.rsplit("/", 1)[1])))
                else:
                    self.send_error(404)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)

        def do_POST(self):  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                path = urlparse(self.path).path
                action = {
                    "/api/stage": lambda: session.stage(payload),
                    "/api/import": lambda: session.import_image(payload),
                    "/api/update": lambda: session.update(payload),
                    "/api/select": lambda: session.select(payload),
                    "/api/remove": lambda: session.remove(payload),
                    "/api/clear": session.clear,
                    "/api/return": session.request_return,
                }.get(path)
                if action is None:
                    self.send_error(404)
                    return
                self._json(action())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 400)

        def _json(self, value: dict, status: int = 200):
            self._send(json.dumps(value).encode("utf-8"), "application/json", status)

        def _send(self, data: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store" if content_type == "application/json" else "private, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--initial-state")
    args = parser.parse_args()
    initial = json.loads(Path(args.initial_state).read_text(encoding="utf-8")) if args.initial_state else {}
    session = LogoWebSession(Path(args.reference), Path(args.state), initial)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class(session))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(json.dumps({"url": url}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
