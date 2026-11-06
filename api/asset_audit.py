# -*- coding: utf-8 -*-
"""
Enterprise Asset BI & Inventory Audit Cloud Proxy API (/api/asset_audit)
------------------------------------------------------------------------
Connects:
1. Master Asset Sheet (61,000+ rows x 9 cols): 1Q9wzp-1-HYp9FjGHQxiHbF8u6H1N59jMjIgS2Nz8DBo
   - Column Q (index 16): 865 exact Site / Cable / MW / JB names ("List database")
   - Column O (index 14): 15 Warehouse Stock filter keys ("VCM TNI ware house inventory")
   - Columns A..I: No, Station code, Equipment name, Code, Serial number, Quality, Issue Date, Group manager, Stock code
2. Asset Audit Collection & Progress Sheet: 1Z1mRG_skVoRifOjw08T0zon4nCGa7ZfXZSZMdf7kFt0
3. Google Apps Script Backend (Drive 1440x1088 Photo Upload + Multi-Tab Writer + Transfer Approval):
   https://script.google.com/macros/s/AKfycbx09J8PPi_IN3_n_ho8QF4RapsPh5uzLchVfS9T89iuw-4QMZWU_ynlhzDvav4wRvj4/exec
"""

from http.server import BaseHTTPRequestHandler
import json
import time
import urllib.parse
import urllib.request

MASTER_SHEET_ID = "1Q9wzp-1-HYp9FjGHQxiHbF8u6H1N59jMjIgS2Nz8DBo"
COLLECT_SHEET_ID = "1Z1mRG_skVoRifOjw08T0zon4nCGa7ZfXZSZMdf7kFt0"
GAS_ASSET_URL = "https://script.google.com/macros/s/AKfycbx09J8PPi_IN3_n_ho8QF4RapsPh5uzLchVfS9T89iuw-4QMZWU_ynlhzDvav4wRvj4/exec"

_CATALOG_CACHE = {
    "ts": 0,
    "data": None
}


def _gviz_query(sheet_id, tq, gid="0", sheet_name=None, timeout=20):
    params = {"tqx": "out:json", "tq": tq}
    if sheet_name:
        params["sheet"] = sheet_name
    else:
        params["gid"] = str(gid)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AssetBI/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    start = raw.find("({")
    end = raw.rfind("});")
    if start == -1 or end == -1:
        raise ValueError("Invalid GViz response")
    payload = json.loads(raw[start + 1 : end + 1])
    table = payload.get("table", {})
    rows = table.get("rows", [])
    out = []
    for r in rows:
        c = r.get("c", [])
        row_vals = []
        for cell in c:
            if cell is None:
                row_vals.append("")
            else:
                v = cell.get("f") if cell.get("f") is not None else cell.get("v")
                row_vals.append("" if v is None else str(v).strip())
        out.append(row_vals)
    return out


def _clean_num_str(val):
    s = str(val or "").strip()
    if s.endswith(".0"):
        return s[:-2]
    return s


def _fetch_catalog(force=False):
    now = time.time()
    if not force and _CATALOG_CACHE["data"] and (now - _CATALOG_CACHE["ts"] < 300):
        return _CATALOG_CACHE["data"]

    q_rows = _gviz_query(MASTER_SHEET_ID, "select Q where Q is not null limit 2000")
    o_rows = _gviz_query(MASTER_SHEET_ID, "select O where O is not null limit 100")

    sites = []
    seen_s = set()
    for r in q_rows:
        if not r:
            continue
        val = r[0].strip()
        if not val or val.lower() in ("list database", "q"):
            continue
        if val not in seen_s:
            seen_s.add(val)
            sites.append(val)

    warehouses = []
    seen_w = set()
    for r in o_rows:
        if not r:
            continue
        val = r[0].strip()
        if not val or val.lower().startswith("vcm tni") or val.lower() == "o":
            continue
        if val not in seen_w:
            seen_w.add(val)
            warehouses.append(val)

    data = {
        "ok": True,
        "sites": sites,
        "warehouses": warehouses,
        "totalSites": len(sites),
        "totalWarehouses": len(warehouses),
        "cachedAt": int(now)
    }
    _CATALOG_CACHE["ts"] = now
    _CATALOG_CACHE["data"] = data
    return data


def _map_group_to_team(group_mgr):
    g = str(group_mgr or "").upper()
    if "TEAM 01" in g or "TEAM 1" in g or "DAWEI" in g:
        return "Team 1"
    if "TEAM 02" in g or "TEAM 2" in g or "MYEIK" in g:
        return "Team 2"
    if "TEAM 03" in g or "TEAM 3" in g or "BOKPYIN" in g:
        return "Team 3"
    if "TEAM 04" in g or "TEAM 4" in g or "KAWTHOUNG" in g:
        return "Team 4"
    return "Warehouse / Branch"


def _search_site_assets(target, staff_team="ALL", can_view_all=True):
    target = str(target or "").strip()
    if not target:
        return {"ok": False, "error": "Missing target Station / Cable / Warehouse name."}

    safe_target = target.replace("'", "\\'")
    is_warehouse_query = (" - " in target and "Tanintharyi" in target)

    if is_warehouse_query:
        parts = target.split(" - ", 1)
        grp_part = parts[0].strip().replace("'", "\\'")
        stk_part = parts[1].strip().replace("'", "\\'") if len(parts) > 1 else ""
        if stk_part:
            tq = f"select A,B,C,D,E,F,G,H,I where H = '{grp_part}' and I = '{stk_part}' limit 1500"
        else:
            tq = f"select A,B,C,D,E,F,G,H,I where H = '{grp_part}' and (B is null or B = '') limit 1500"
        rows = _gviz_query(MASTER_SHEET_ID, tq)
    else:
        tq = f"select A,B,C,D,E,F,G,H,I where B = '{safe_target}' limit 1500"
        rows = _gviz_query(MASTER_SHEET_ID, tq)
        if not rows:
            tq_ci = f"select A,B,C,D,E,F,G,H,I where upper(B) = '{safe_target.upper()}' limit 1500"
            rows = _gviz_query(MASTER_SHEET_ID, tq_ci)

    items = []
    detected_teams = set()
    for r in rows:
        while len(r) < 9:
            r.append("")
        no_id = _clean_num_str(r[0])
        if no_id.lower() == "no":
            continue
        station_code = r[1]
        equip_name = r[2]
        equip_code = _clean_num_str(r[3])
        serial_no = _clean_num_str(r[4])
        quality = _clean_num_str(r[5])
        issue_date = r[6]
        group_mgr = r[7]
        stock_code = r[8]

        row_team = _map_group_to_team(group_mgr)
        detected_teams.add(row_team)

        items.append({
            "no": no_id,
            "siteCode": station_code or stock_code or target,
            "equipmentName": equip_name,
            "code": equip_code,
            "serial": serial_no,
            "quality": quality,
            "issueDate": issue_date,
            "groupManager": group_mgr,
            "stockCode": stock_code,
            "team": row_team
        })

    # Enforce Team RBAC if staff is restricted to a single team
    norm_staff_team = str(staff_team or "ALL").strip().upper()
    if not can_view_all and norm_staff_team not in ("ALL", "", "BOD", "ASSET"):
        allowed_items = [
            it for it in items
            if it["team"].upper() == norm_staff_team or it["team"] == "Warehouse / Branch"
        ]
        if items and not allowed_items:
            return {
                "ok": False,
                "error": f"Access Denied (Team Isolation): Target '{target}' belongs to {', '.join(sorted(detected_teams))}, while your account is assigned to {staff_team}."
            }
        items = allowed_items

    primary_team = sorted(detected_teams)[0] if detected_teams else (staff_team if staff_team != "ALL" else "Team 1")

    return {
        "ok": True,
        "target": target,
        "team": primary_team,
        "totalItems": len(items),
        "items": items
    }


def _lookup_serial_in_system(serial_query):
    q = str(serial_query or "").strip()
    if not q or len(q) < 3:
        return {"ok": False, "error": "Enter at least 3 characters of the serial number."}

    safe_q = q.replace("'", "\\'").upper()
    tq = f"select A,B,C,D,E,F,H,I where upper(E) contains '{safe_q}' limit 15"
    rows = _gviz_query(MASTER_SHEET_ID, tq)

    matches = []
    formulas = []
    for r in rows:
        while len(r) < 8:
            r.append("")
        no_id = _clean_num_str(r[0])
        if no_id.lower() == "no":
            continue
        st_code = r[1].strip()
        eq_name = r[2].strip()
        eq_code = _clean_num_str(r[3])
        full_serial = _clean_num_str(r[4])
        qty = _clean_num_str(r[5])
        grp_mgr = r[6].strip()
        stk_code = r[7].strip()

        loc = st_code if st_code else (stk_code if stk_code else grp_mgr)
        formula_str = f"{full_serial} = {loc}"
        formulas.append(formula_str)
        matches.append({
            "no": no_id,
            "serial": full_serial,
            "location": loc,
            "stationCode": st_code,
            "stockCode": stk_code,
            "equipmentName": eq_name,
            "code": eq_code,
            "quality": qty,
            "groupManager": grp_mgr,
            "formula": formula_str
        })

    if not matches:
        return {
            "ok": True,
            "query": q,
            "found": False,
            "formula": f"{q} = Not Found in System (61K DB)",
            "matches": []
        }

    return {
        "ok": True,
        "query": q,
        "found": True,
        "formula": " | ".join(formulas[:3]),
        "matches": matches
    }


def _proxy_gas_get(params_dict):
    qs = urllib.parse.urlencode(params_dict)
    url = f"{GAS_ASSET_URL}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AssetBI/1.0)"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _proxy_gas_post(body_dict):
    data_bytes = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        GAS_ASSET_URL,
        data=data_bytes,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (AssetBI/1.0)"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({"ok": True})

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            action = (qs.get("action", ["catalog"])[0] or "catalog").strip()

            if action == "catalog":
                force = qs.get("force", ["0"])[0] == "1"
                return self._send_json(_fetch_catalog(force=force))

            if action == "search_site":
                target = qs.get("target", [""])[0]
                team = qs.get("team", ["ALL"])[0]
                can_all = qs.get("canViewAll", ["1"])[0] == "1"
                return self._send_json(_search_site_assets(target, staff_team=team, can_view_all=can_all))

            if action == "lookup_serial":
                q = qs.get("q", [""])[0]
                return self._send_json(_lookup_serial_in_system(q))

            if action in ("verify_staff", "asset_verify_staff"):
                code = qs.get("code", [""])[0]
                return self._send_json(_proxy_gas_get({"action": "asset_verify_staff", "code": code}))

            if action in ("dashboard", "asset_dashboard_data"):
                return self._send_json(_proxy_gas_get({"action": "asset_dashboard_data"}))

            if action in ("init_sheets", "asset_init_sheets"):
                return self._send_json(_proxy_gas_get({"action": "asset_init_sheets"}))

            return self._send_json({"ok": False, "error": f"Unknown GET action: {action}"}, 400)
        except Exception as e:
            return self._send_json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else "{}"
            body = json.loads(raw_body)
            action = str(body.get("action", "")).strip()

            if not action.startswith("asset_"):
                action = "asset_" + action
                body["action"] = action

            res = _proxy_gas_post(body)
            return self._send_json(res)
        except Exception as e:
            return self._send_json({"ok": False, "error": str(e)}, 500)
