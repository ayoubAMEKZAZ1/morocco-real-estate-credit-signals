"""Local test server: simulates (1) the BAM IPAI page with its PDFs and (2) a release API.
For tests only (see tests/test_pipeline_end_to_end.py)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def make_server(pdfs, port=0, api_key="test-key", fail_api=False, bam_403=False):
    """pdfs = {file_name: bytes}. Return (server, received_uploads)."""
    received = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _empty(self, code):
            self.send_response(code)
            self.end_headers()

        def do_GET(self):
            if self.path == "/robots.txt":
                return self._empty(404)
            if self.path == "/page":
                if bam_403:
                    return self._empty(403)
                links = "".join(f'<a href="/files/{n}">Bulletin {n}</a>' for n in pdfs)
                body = f"<html><body><h1>IPAI</h1>{links}<a href='/other.html'>x</a></body></html>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/files/"):
                n = self.path.split("/files/")[1]
                if n in pdfs:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.end_headers()
                    self.wfile.write(pdfs[n])
                    return
            self._empty(404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            if self.headers.get("X-API-Key") != api_key:
                return self._empty(401)
            if fail_api:
                return self._empty(500)
            received.append({"idempotency": self.headers.get("Idempotency-Key"),
                             "bytes": len(body), "has_audience": b'name="audience"' in body})
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, received
