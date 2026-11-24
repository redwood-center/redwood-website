"""Browse the archived site offline: python3 scripts/serve_archive.py [port]

Serves archive/ and rewrites absolute redwood.berkeley.edu URLs in HTML/CSS to
root-relative on the fly, so links and assets resolve locally.
"""
import http.server
import os
import re
import sys

ARCHIVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "archive"))
ABS = re.compile(rb"(?:https?:)?(?:\\?/\\?/)(?:www\.)?redwood\.berkeley\.edu")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ARCHIVE, **kw)

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if not path.endswith((".html", ".css")) or not os.path.isfile(path):
            return super().send_head()
        with open(path, "rb") as f:
            body = ABS.sub(b"", f.read())
        self.send_response(200)
        self.send_header("Content-Type", "text/css" if path.endswith(".css") else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Serving {ARCHIVE} at http://localhost:{port}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
