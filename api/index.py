import os, sys, json, logging
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

# ── SSOT Delegation to Search Bot Engine ─────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from api.search_bot import handler as SearchBotHandler
except ImportError:
    try:
        from search_bot import handler as SearchBotHandler
    except ImportError:
        SearchBotHandler = BaseHTTPRequestHandler

class handler(SearchBotHandler):
    """Vercel Serverless Function entrypoint for /api/index delegating 100% to SSOT Search Engine."""
    pass
