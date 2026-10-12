import requests
from http.server import BaseHTTPRequestHandler
import json

GAS_ATTENDANCE_URL = "https://script.google.com/macros/s/AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg/exec"

def _tg_secret_ok(headers, env_name):
    """PM-97 R5: constant-time Telegram webhook secret check when configured; allow if env not set."""
    import hmac as _hmac
    import os as _os
    exp = _os.environ.get(env_name, "").strip()
    if not exp:
        return True
    got = headers.get("X-Telegram-Bot-Api-Secret-Token", "").strip()
    return bool(got) and _hmac.compare_digest(got.encode("utf-8"), exp.encode("utf-8"))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not _tg_secret_ok(self.headers, "ATTENDANCE_WEBHOOK_SECRET"):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"error":"Forbidden"}')
            return
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # Forward payload to Google Apps Script with 302 redirect following
            resp = requests.post(
                GAS_ATTENDANCE_URL,
                data=post_data,
                headers={'Content-Type': 'application/json'},
                timeout=25
            )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            self.send_response(504)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"TNI Attendance Proxy Active 24/7")
