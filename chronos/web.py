"""Local HTTP application. No credentials or arbitrary files are served."""
import argparse
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .service import BusyError, Controller


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, controller=None):
        super().__init__(address, Handler)
        self.controller = controller or Controller()

    @property
    def simulation(self):
        return self.controller.simulation


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, content, content_type="application/json; charset=utf-8"):
        body = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def trusted(self):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin = self.headers.get("Origin")
        return host in allowed and (origin is None or origin in {f"http://{h}" for h in allowed})

    def do_GET(self):
        if self.path == "/healthz":
            self.respond(200, {"status": "ok"})
            return
        if not self.trusted():
            self.respond(403, {"error": "Local access only"})
            return
        assets = {"/": ("dashboard.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if self.path in assets:
            filename, mime = assets[self.path]
            self.respond(200, Path(__file__).with_name(filename).read_bytes(), mime)
        elif self.path == "/api/state":
            self.respond(200, self.server.controller.state())
        elif self.path == "/api/runs":
            self.respond(200, self.server.controller.store.list())
        elif self.path.startswith("/api/runs/"):
            try:
                self.respond(200, self.server.controller.store.load(self.path.removeprefix("/api/runs/")))
            except ValueError as exc:
                self.respond(404, {"error": str(exc)})
        else:
            self.respond(404, {"error": "Not found"})

    def do_POST(self):
        if not self.trusted() or self.headers.get("X-Chronos") != "dashboard":
            self.respond(403, {"error": "Local dashboard request required"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            controller = self.server.controller
            routes = {"/api/reset": lambda: controller.reset(payload), "/api/step": lambda: controller.start(False),
                      "/api/run": lambda: controller.start(True), "/api/pause": controller.pause,
                      "/api/evaluate": lambda: controller.evaluate(payload), "/api/evaluate/cancel": controller.cancel_comparison}
            if self.path not in routes:
                self.respond(404, {"error": "Not found"})
                return
            self.respond(200, routes[self.path]())
        except BusyError as exc:
            self.respond(409, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            self.respond(400, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="Chronos local operations console")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    with DashboardServer((args.host, args.port)) as server:
        print(f"Chronos: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.controller.pause()
            server.controller.cancel_comparison()


if __name__ == "__main__":
    main()
