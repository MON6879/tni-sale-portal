"""
tni_search_core.py
==================
Single Source of Truth (SSOT) Search Engine for TNI Bot System.
Shared by:
  - api/search_bot.py (Vercel Cloud Handler)
  - tni_site_down_repo/telegram_bot.py (Telethon / Local Bot)

Provides deterministic query classification, exact anchor length matching,
and deduplication to prevent misrouting and duplicated replies.
"""

import re
import time
import logging

logger = logging.getLogger(__name__)

# ── CANONICAL REGULAR EXPRESSIONS ─────────────────────────────────────────────
# 1. Info Match: /info TNI0061 or info: TNI0061 (Exact anchor ^ ... $)
INFO_RE = re.compile(r"^\s*(?:/info|info)[:\s]+\s*(TNI\d{4}(?:_\d+)?)\s*$", re.IGNORECASE)

# 2. Clear Match: /clear TNI0061 or clear TNI0061
CLEAR_RE = re.compile(r"^\s*(?:/clear|clear)[:\s]+\s*(TNI\d{4}(?:_\d+)?)\s*$", re.IGNORECASE)

# 3. Not Close Match: /t1notclose, t1notclose, t1_notclose, t1 not close, /t4notclose
NOTCLOSE_RE = re.compile(r"^\s*/?(T[1-4])[\s_]?(not[\s_]?close|notclose)\s*$", re.IGNORECASE)

# 4. Wait CD Match: /t1waitcd, t1waitcd, t1_waitcd, t1 wait cd, /t4waitcd
WAITCD_RE = re.compile(r"^\s*/?(T[1-4])[\s_]?(wait[\s_]?cd|waitcd)\s*$", re.IGNORECASE)

# 5. Construction Search Match: cons TNI0310, /cons TNI0310, pro TNI0310, /pro TNI0310, construction TNI0310
CONS_RE = re.compile(r"^\s*(?:/cons|cons|/pro|pro|construction)[:\s]+\s*(TNI\d{4}(?:_\d+)?)\s*$", re.IGNORECASE)

# 6. Menu / Help Match: menu, /menu, men, /men, help, /help, /start
MENU_RE = re.compile(r"^\s*/?(menu|men|help|start)\s*$", re.IGNORECASE)

# 7. TNI Match: /tni TNI0061 or TNI0061 (Exact anchor ^ ... $, rejects noise like 'TNI0061 440L')
TNI_RE = re.compile(r"^\s*(?:/tni|/find|tni)?[:\s]*\b(TNI\d{4}(?:_\d+)?)\s*$", re.IGNORECASE)

# 8. Admin / Staff Lookup Match: mydata 123456, /mysite 123456
ADMIN_LOOKUP_RE = re.compile(r"^\s*/?(my\S+)\s+(\d{6,12})\s*$", re.IGNORECASE)

# ── DEDUPLICATION CACHE ENGINE ────────────────────────────────────────────────
_recent_search_keys = {}
DEDUP_TTL_SECONDS = 10.0

def is_duplicate_search(chat_id: int, user_id: int, query: str, ttl: float = DEDUP_TTL_SECONDS) -> bool:
    """
    Check if (chat_id, user_id, query) was processed within TTL seconds.
    Returns True if duplicate (should skip), False if new request.
    """
    key = (chat_id, user_id, query.strip().upper())
    now = time.time()
    
    # Cleanup stale entries if cache grows large
    if len(_recent_search_keys) > 1000:
        stale = [k for k, ts in _recent_search_keys.items() if now - ts > ttl]
        for k in stale:
            _recent_search_keys.pop(k, None)
            
    if key in _recent_search_keys and (now - _recent_search_keys[key]) < ttl:
        logger.info(f"[SSOT Dedup] Dropping duplicate query: {key}")
        return True
        
    _recent_search_keys[key] = now
    return False

# ── QUERY CLASSIFIER ROUTER ───────────────────────────────────────────────────
def classify_query(text: str) -> dict:
    """
    Classify input text according to canonical priority order.
    Returns dict:
      {
        "action": "INFO" | "CLEAR" | "NOTCLOSE" | "WAITCD" | "CONS" | "MENU" | "TNI" | "ADMIN_LOOKUP" | "IGNORE",
        "code": extracted_tni_or_team_code_or_id,
        "raw_text": text
      }
    """
    if not text or not isinstance(text, str):
        return {"action": "IGNORE", "code": None, "raw_text": text}
        
    clean_text = text.strip()
    
    # Priority 1: MENU / HELP MATCH (menu, /menu, help)
    m_menu = MENU_RE.match(clean_text)
    if m_menu:
        return {"action": "MENU", "code": "MENU", "raw_text": clean_text}

    # Priority 2: INFO MATCH (info: TNIxxxx) -> Site/Cable/GPON/DIA info
    m_info = INFO_RE.match(clean_text)
    if m_info:
        return {"action": "INFO", "code": m_info.group(1).upper(), "raw_text": clean_text}
        
    # Priority 3: CLEAR MATCH (clear TNIxxxx) -> Clear history
    m_clear = CLEAR_RE.match(clean_text)
    if m_clear:
        return {"action": "CLEAR", "code": m_clear.group(1).upper(), "raw_text": clean_text}

    # Priority 4: CONSTRUCTION SEARCH MATCH (cons TNIxxxx, pro TNIxxxx) -> Construction info
    m_cons = CONS_RE.match(clean_text)
    if m_cons:
        return {"action": "CONS", "code": m_cons.group(1).upper(), "raw_text": clean_text}

    # Priority 5: NOT CLOSE MATCH (/t1notclose, t4notclose) -> Open WOs
    m_nc = NOTCLOSE_RE.match(clean_text)
    if m_nc:
        return {"action": "NOTCLOSE", "code": m_nc.group(1).upper(), "raw_text": clean_text}

    # Priority 6: WAIT CD MATCH (/t1waitcd, t4waitcd) -> Wait CD WOs
    m_wc = WAITCD_RE.match(clean_text)
    if m_wc:
        return {"action": "WAITCD", "code": m_wc.group(1).upper(), "raw_text": clean_text}
        
    # Priority 7: TNI MATCH (TNIxxxx exact) -> Task & WO details
    m_tni = TNI_RE.match(clean_text)
    if m_tni:
        return {"action": "TNI", "code": m_tni.group(1).upper(), "raw_text": clean_text}
        
    # Priority 8: ADMIN / STAFF LOOKUP (mydata <ID>)
    m_admin = ADMIN_LOOKUP_RE.match(clean_text)
    if m_admin:
        return {
            "action": "ADMIN_LOOKUP",
            "field": m_admin.group(1).lower().lstrip("/"),
            "target_id": m_admin.group(2),
            "raw_text": clean_text
        }
        
    # Default: Not a search command -> IGNORE (do not reply)
    return {"action": "IGNORE", "code": None, "raw_text": clean_text}
