import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

events: dict[str, dict] = {}
attempts: dict[str, int] = {}
lock = Lock()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        event_id = self.headers['X-Webhook-Event-Id']
        with lock:
            attempts[event_id] = attempts.get(event_id, 0) + 1
            count = attempts[event_id]
            fail = self.path == '/always-fail' or (self.path == '/fail-twice' and count <= 2)
            if not fail:
                events[event_id] = data
        self.send_response(503 if fail else 204)
        self.end_headers()

    def do_GET(self) -> None:
        with lock:
            result = json.dumps({'events': events, 'attempts': attempts}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(result)))
        self.end_headers()
        self.wfile.write(result)


ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
