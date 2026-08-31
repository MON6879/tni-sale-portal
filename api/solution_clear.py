import requests
from http.server import BaseHTTPRequestHandler
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GAS_SOLUTION_CLEAR_URL = "https://script.google.com/macros/s/AKfycbw-QYNefq1xX-kWS9zUzJCWUkiPh1fNbE2ANmw4p-LEx9QYbom5NHgLzr-Rk0BgZZMg4A/exec"

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # Forward payload to Google Apps Script with 302 redirect following
            resp = requests.post(
                GAS_SOLUTION_CLEAR_URL,
                data=post_data,
                headers={'Content-Type': 'application/json'},
                timeout=25
            )
            logger.info(f"Forwarded to GAS Solution Clear: status {resp.status_code}")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            logger.error(f"Error proxying to Solution Clear GAS: {e}")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"TNI Solution Clear Proxy Active 24/7")
