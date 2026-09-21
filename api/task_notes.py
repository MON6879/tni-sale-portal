"""
api/task_notes.py
=================
Vercel serverless proxy & handler for BI Portal "Note Ghi Chú Đầu Việc" tab.
Provides same-origin access for the web frontend to communicate with Google Sheets via Main GAS backend.
Target Sheet: 1J4huU6zxJw-gC6_EtuOP1O4FQ2y8s38inxUM5rYYLzo (GID=0)
"""
import os
import json
import urllib.parse
import requests
from http.server import BaseHTTPRequestHandler

# Active GAS Web App URL (Main GAS Collector SSOT)
GAS_ENDPOINT = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = parsed.query
        params = urllib.parse.parse_qs(qs)
        action = params.get("action", ["get_task_notes"])[0]
        
        target_url = f"{GAS_ENDPOINT}?action={action}"
        response_data = None
        try:
            resp = requests.get(target_url, headers={"User-Agent": "TNI-BI-TaskNotes/1.0"}, timeout=20, allow_redirects=True)
            if resp.status_code == 200 and resp.text.strip().startswith("{"):
                response_data = resp.text
        except Exception as e:
            response_data = json.dumps({
                "status": "error",
                "version": "1.0",
                "data": [],
                "error": {"code": "PROXY_FETCH_ERROR", "message": str(e)}
            })

        if not response_data:
            response_data = json.dumps({
                "status": "error",
                "version": "1.0",
                "data": [],
                "error": {"code": "NO_RESPONSE", "message": "Could not connect to GAS backend"}
            })

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_data.encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length).decode("utf-8")
        
        response_data = None
        try:
            resp = requests.post(
                GAS_ENDPOINT,
                data=post_body,
                headers={"Content-Type": "text/plain;charset=utf-8"},
                timeout=25,
                allow_redirects=True
            )
            if resp.status_code == 200 and resp.text.strip().startswith("{"):
                response_data = resp.text
        except Exception as e:
            response_data = json.dumps({
                "status": "error",
                "version": "1.0",
                "error": {"code": "POST_ERROR", "message": str(e)}
            })

        if not response_data:
            response_data = json.dumps({
                "status": "error",
                "version": "1.0",
                "error": {"code": "POST_FAILED", "message": "Failed to proxy POST request to backend"}
            })

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_data.encode("utf-8"))

    def log_message(self, *a):
        pass
