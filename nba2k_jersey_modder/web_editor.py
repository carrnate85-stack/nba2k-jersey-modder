from __future__ import annotations

from .editor_assets import load_editor_html

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote

from .trim_path_lab import TRIM_PATH_LAB_HTML


INDEX_HTML = load_editor_html("web_editor_index_html.html")


LOGO_SELECTOR_HTML = load_editor_html("web_editor_logo_selector_html.html")


NUMBER_SELECTOR_HTML = load_editor_html("web_editor_number_selector_html.html")


TRIM_SELECTOR_HTML = load_editor_html("web_editor_trim_selector_html.html")


class WebEditorServer:
    def __init__(self, app, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.app = app
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self.httpd is not None:
            return self.url

        handler = self._handler_class()
        for candidate in range(self.port, self.port + 25):
            try:
                self.httpd = ThreadingHTTPServer((self.host, candidate), handler)
                self.port = int(self.httpd.server_address[1])
                break
            except OSError:
                continue
        if self.httpd is None:
            raise RuntimeError("Could not start the web editor server.")

        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def _handler_class(self):
        app = self.app

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                try:
                    self._handle_get()
                except Exception as exc:  # noqa: BLE001 - HTTP boundary.
                    self.send_error(500, str(exc))

            def do_POST(self) -> None:  # noqa: N802
                try:
                    self._handle_post()
                except Exception as exc:  # noqa: BLE001 - HTTP boundary.
                    self.send_error(500, str(exc))

            def log_message(self, _format: str, *args) -> None:
                return

            def _handle_get(self) -> None:
                if self.path == "/" or self.path.startswith("/index") or self.path.startswith("/editor"):
                    self._send(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/trim-path"):
                    self._send(TRIM_PATH_LAB_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/logo"):
                    self._send(LOGO_SELECTOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/number"):
                    self._send(NUMBER_SELECTOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/trim"):
                    self._send(TRIM_SELECTOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/api/logo/project"):
                    data = app._run_on_ui_thread(app._logo_creator_web_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/logo/reference"):
                    data, content_type = app._run_on_ui_thread(app._logo_creator_reference_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/trim/project"):
                    data = app._run_on_ui_thread(app._trim_creator_web_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/trim/mockup"):
                    data, content_type = app._run_on_ui_thread(app._trim_creator_mockup_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/trim-path/project"):
                    data = app._run_on_ui_thread(app._trim_path_lab_web_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/trim-path/background"):
                    data, content_type = app._run_on_ui_thread(app._trim_path_lab_background_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/trim-path/uv"):
                    data, content_type = app._run_on_ui_thread(app._trim_path_lab_uv_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/trim-path/pattern"):
                    data, content_type = app._run_on_ui_thread(app._trim_path_lab_pattern_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/number/project"):
                    data = app._run_on_ui_thread(app._number_creator_web_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/number/reference"):
                    data, content_type = app._run_on_ui_thread(app._number_creator_reference_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/project"):
                    data = app._run_on_ui_thread(app._web_editor_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/base.png"):
                    self._send(app._run_on_ui_thread(app._web_editor_base_png), "image/png")
                    return
                if self.path.startswith("/api/region.png"):
                    self._send(app._run_on_ui_thread(app._web_editor_region_png), "image/png")
                    return
                if self.path.startswith("/api/uv.png"):
                    self._send(app._run_on_ui_thread(app._web_editor_uv_png), "image/png")
                    return
                if self.path.startswith("/api/image/"):
                    key = unquote(self.path.split("/api/image/", 1)[1].split("?", 1)[0])
                    data, content_type = app._run_on_ui_thread(
                        lambda: app._web_editor_image(key)
                    )
                    self._send(data, content_type)
                    return
                if not self.path.startswith("/api/") and self.path != "/favicon.ico":
                    self._send(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                self.send_error(404)

            def _handle_post(self) -> None:
                if self.path.startswith("/api/trim-path/return"):
                    callback = getattr(app, "_trim_path_lab_return", None)
                    result = app._run_on_ui_thread(callback) if callback is not None else {"ok": True}
                    self._send_json(result)
                    return
                if self.path.startswith("/api/trim-path/send"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = app._run_on_ui_thread(
                        lambda: app._trim_path_lab_send_to_generator(payload)
                    )
                    self._send_json(result)
                    return
                if self.path.startswith("/api/logo/lasso"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._logo_creator_web_lasso(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/logo/clear"):
                    app._run_on_ui_thread(app._logo_creator_web_clear)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/trim/line"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._trim_creator_web_line(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/trim/clear"):
                    app._run_on_ui_thread(app._trim_creator_web_clear)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/number/selection"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = app._run_on_ui_thread(
                        lambda: app._number_creator_web_selection(payload)
                    )
                    self._send_json(result)
                    return
                if self.path.startswith("/api/number/clear"):
                    app._run_on_ui_thread(app._number_creator_web_clear)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/update"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = app._run_on_ui_thread(lambda: app._web_editor_update(payload))
                    self._send_json({"ok": True, "overlay": result})
                    return
                if self.path.startswith("/api/reorder"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_reorder(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/transparency"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_transparency(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/paint/undo"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = app._run_on_ui_thread(lambda: app._web_editor_undo_paint(payload))
                    self._send_json(result)
                    return
                if self.path.startswith("/api/paint"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = app._run_on_ui_thread(lambda: app._web_editor_paint(payload))
                    self._send_json({"ok": True, **result})
                    return
                if self.path.startswith("/api/flip"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_flip(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/reset"):
                    app._run_on_ui_thread(app._web_editor_reset)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/return"):
                    callback = getattr(app, "_web_editor_return", None)
                    if callback is not None:
                        app._run_on_ui_thread(callback)
                    self._send_json({"ok": True})
                    return
                else:
                    self.send_error(404)
                    return

            def _send_json(self, payload) -> None:
                self._send(json.dumps(payload).encode("utf-8"), "application/json")

            def _send(self, body: bytes, content_type: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        return Handler


def image_content_type(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    if extension == ".gif":
        return "image/gif"
    if extension == ".bmp":
        return "image/bmp"
    return "image/png"
