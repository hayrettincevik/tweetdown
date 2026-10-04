"""Open the exported likes in the HTML viewer.

Browsers block ``fetch()`` on ``file://`` pages, so to auto-load a JSON the app
starts a tiny loopback HTTP server that serves the bundled viewer at ``/`` and
the chosen export at ``/data.json``, then points the default browser at it.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VIEWER_FILENAME = "tweetdown_viewer.html"

_server: ThreadingHTTPServer | None = None
_port: int = 0
_current_json: Path | None = None
_html_cache: bytes | None = None


def _viewer_html() -> bytes:
    global _html_cache
    if _html_cache is not None:
        return _html_cache
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent  # project root
    _html_cache = (base / VIEWER_FILENAME).read_bytes()
    return _html_cache


class _Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/viewer.html", "/index.html"):
            self._send(_viewer_html(), "text/html; charset=utf-8")
        elif path == "/data.json":
            if _current_json and _current_json.exists():
                self._send(_current_json.read_bytes(), "application/json; charset=utf-8")
            else:
                self.send_error(404, "no data")
        else:
            self.send_error(404)

    def log_message(self, *args: object) -> None:  # silence console output
        pass


def _ensure_server() -> int:
    global _server, _port
    if _server is not None:
        return _port
    _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _port = _server.server_address[1]
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _port


def open_in_viewer(json_path: Path | None = None) -> None:
    """Open the viewer in the default browser.

    If ``json_path`` points to an existing file it is served at ``/data.json``
    and the viewer loads it automatically. Otherwise the viewer opens with its
    file picker so the user can choose a file themselves.
    """
    global _current_json
    if json_path is not None and Path(json_path).exists():
        _current_json = Path(json_path)
    else:
        _current_json = None
    port = _ensure_server()
    webbrowser.open(f"http://127.0.0.1:{port}/viewer.html")
