"""
# api/trigger_workflow.py
===========================
Vercel API endpoint to FORCE trigger GitHub Actions workflow via workflow_dispatch API.
Executes instantly within 2-5 seconds, bypassing free runner queue delays.

Endpoint: https://tni-bot.vercel.app/api/trigger_workflow
"""
import os, json, logging, requests
from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GH_PAT_TOKEN = os.environ.get("GH_PAT_TOKEN", "").strip()
REPO_OWNER = "phonghdpxd-cmd"
REPO_NAME = "tni-bot"
WORKFLOW_FILE = "train_5min.yml"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.trigger_github()

    def do_POST(self):
        self.trigger_github()

    def trigger_github(self):
        if not GH_PAT_TOKEN:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "GH_PAT_TOKEN not set"}).encode("utf-8"))
            return

        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches"
        headers = {
            "Authorization": f"Bearer {GH_PAT_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Vercel-Trigger-Engine"
        }
        payload = {"ref": "main"}

        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            if r.status_code == 240 or r.status_code == 204 or r.status_code == 200:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "message": f"Successfully forced workflow_dispatch for {WORKFLOW_FILE}!"}).encode("utf-8"))
                logger.info(f"Forced workflow_dispatch for {WORKFLOW_FILE} successfully.")
            else:
                self.send_response(r.status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "status": r.status_code, "response": r.text}).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error triggering GitHub workflow: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
