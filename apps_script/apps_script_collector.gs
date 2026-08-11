// ============================================================
// TNI Asset Collector — Google Apps Script
// ============================================================
// Deploy as Web App:
//   Execute as: Me | Who has access: Anyone
// v2026-06-26c — CRITICAL FIX: store_site_down routing confirmed in doPost (line 57)
//                + getNoteB2B5 self-contained + handleStoreSiteDownDirect self-contained
// ============================================================


const SHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8";

// Tab where collected data is stored (gid = 199426270)
const DATA_TAB        = "Asset order and request";

// Tab where authorised users are listed (gid = 1236389870)
// Layout: Col A = Field Name (existing)  |  Col B = Name  |  Col C = Telegram ID
const CFG_TAB         = "Config";

// Tab for search activity log
const SEARCH_LOG_TAB  = "Search Log";

// Tab for aggregated search stats (one row per user)
const SEARCH_STATS_TAB = "Search Stats";

// Tab for general combined report (Name + ID + Content + Search stats)
const GENERAL_TAB      = "General";

// GID of the daily report sheet (gid=133591305)
const REPORT_GID       = "133591305";

// ============================================================
// ENTRY POINTS
// ============================================================

function doPost(e) {
  try {
    const body  = JSON.parse(e.postData.contents);

    // Route Telegram Callback Query (nút bấm nhận việc)
    if (body.callback_query) return handleCallbackQuery(body);

    const ss    = SpreadsheetApp.openById(SHEET_ID);
    const sheet = getDataSheet(ss);

    // Route Telegram webhook format (site down bot) → doPostSiteDown
    if (body.message || body.channel_post) return doPostSiteDown_(e);

    if (body.action === "add")              return handleAdd(sheet, body);
    if (body.action === "done")             return handleDone(sheet, ss, body);
    if (body.action === "find")             return handleFind(sheet, body);
    if (body.action === "add_photo")        return handleAddPhoto(sheet, body);
    if (body.action === "register_chat")    return handleRegisterChat(ss, body);
    if (body.action === "register_user")    return handleRegisterUser(ss, body);
    if (body.action === "get_users")        return handleGetUsers(ss);
    if (body.action === "log_search")       return handleLogSearch(ss, body);
    if (body.action === "log_read_group")   return handleLogReadGroup(ss, body);
    if (body.action === "clean_search_log") return handleCleanSearchLog(ss);
    if (body.action === "refresh_general") return handleRefreshGeneral(ss);
    if (body.action === "get_general")      return handleGetGeneral(ss);
    if (body.action === "get_report_data")   return handleGetReportData(ss);
    if (body.action === "get_asset_stats")   return handleGetAssetStats(ss);
    if (body.action === "store_site_down")   return handleStoreSiteDownDirect(body);
    if (body.action === "save_note_msgids")   return handleSaveNoteMsgIds(body);
    if (body.action === "save_msgids")          return handleSaveMsgIds(body);
    if (body.action === "get_msg_id")           return handleGetMsgId(body);
    if (body.action === "set_msg_id")           return handleSetMsgId(body);
    if (body.action === "clean_blank_rows")      return handleCleanBlankRows(sheet);

    // ── Daily Report Collector ─────────────────────────────────────────────
    if (body.action === "daily_add" ||
        body.action === "daily_photo" ||
        body.action === "sync_headers" ||
        body.action === "store_daily_plan" ||
        body.action === "get_daily_plans" ||
        body.action === "get_daily_reports")  return doPostDaily_(e);

    // ── Cable Collector ───────────────────────────────────────────────────
    if (body.action === "cable_add" ||
        body.action === "cable_confirm" ||
        body.action === "cable_add_photo" ||
        body.action === "cable_get_stats")   return doPostCable_(e);

    // ── MDG + Inventory Collector ──────────────────────────────────────────
    if (body.action === "mdg_add" ||
        body.action === "mdg_confirm" ||
        body.action === "mdg_add_photo" ||
        body.action === "mdg_get_stats" ||
        body.action === "inv_add" ||
        body.action === "inv_confirm" ||
        body.action === "inv_add_photo" ||
        body.action === "process_photo")     return doPostMdg_(e);

    // ── Refuel Plan Collector ──────────────────────────────────────────────
    if (body.action === "collect_message" ||
        body.action === "collect_photo")     return doPostRefuelPlan_(e);

    return json({ status: "error", message: "Unknown action: " + body.action });
  } catch (err) {
    return json({ status: "error", message: err.message, stack: err.stack });
  }
}

function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || "";

    // ── Site Down data endpoint (cho Python Telethon sender) ──
    if (action === "get_site_down_data") return getSiteDownData();
    if (action === "debug_properties") {
      var props = PropertiesService.getScriptProperties().getProperties();
      var debugSs = SpreadsheetApp.openById("1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow");
      var debugSheet = debugSs.getSheets()[0];
      var a1 = debugSheet.getRange("A1").getValue().toString().trim();
      var ts1 = "";
      try {
        var m1 = a1.match(/(\d{2}\/\d{2}\/\d{4}[\s\-T]+\d{2}:\d{2}:\d{2})/);
        if (m1) ts1 = m1[1].replace(/[\-T]/g, " ").trim();
        else {
          var m2 = a1.match(/(\d{2}\/\d{2}\/\d{4}[\s\-T]+\d{2}:\d{2})/);
          if (m2) ts1 = m2[1].replace(/[\-T]/g, " ").trim();
        }
      } catch(e) {}
      var storeKey = ts1 ? (ts1 + "|" + a1.substring(0, 60)) : a1.substring(0, 200);
      return json({ status: "ok", props: props, a1: a1, ts1: ts1, storeKey: storeKey });
    }
    // ── Note B2:B5 từ SD Sheet (cho botlookup_relay.py gửi từ @Phongha79) ──
    if (action === "get_note_b2b5")       return getNoteB2B5();
    if (action === "get_note_msgids")     return handleGetNoteMsgIds();
    if (action === "get_msgids")          return handleGetMsgIds(e.parameter || {});
    if (action === "get_refuel_data")     return doGetRefuelData_(e);
    if (action === "get_bod_formulas") {
      const ss = SpreadsheetApp.openById("1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8");
      const sh = ss.getSheetByName("BOD assign");
      const lastRow = sh.getLastRow();
      const allFormulas = sh.getRange(2, 18, lastRow - 1, 3).getFormulas(); // Columns R, S, T
      const allValues = sh.getRange(2, 18, lastRow - 1, 3).getValues();
      const list = [];
      for (let i = 0; i < allValues.length; i++) {
        const valR = String(allValues[i][0]).trim();
        const valT = String(allValues[i][2]).trim();
        if (valR || valT) {
          list.push({
            row: i + 2,
            values: [valR, String(allValues[i][1]).trim(), valT],
            formulas: [allFormulas[i][0], allFormulas[i][1], allFormulas[i][2]]
          });
        }
      }
      return json({ status: "ok", total: list.length, list: list });
    }
    if (action === "debug_bod_sheet") {
      const ss = SpreadsheetApp.openById("1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8");
      const sh = ss.getSheetByName("BOD assign");
      const lastRow = sh.getLastRow();
      const lastCol = sh.getLastColumn();
      const range = sh.getRange(1, 1, Math.min(100, lastRow), lastCol).getValues();
      return json({ status: "ok", lastRow: lastRow, lastCol: lastCol, data: range });
    }
    if (action === "setup_bod_triggers") {
      setupBodAssignTrigger();
      setupBodAssignMETrigger();
      return json({ status: "ok", message: "BOD triggers setup successfully to 1 minute" });
    }
    if (action === "fix_all_configs") {
      const result = fixAllMismatchedConfigs();
      return json({ status: "ok", message: result });
    }
    if (action === "run_auto_copy") {
      runAutoCopyProcessor(true);
      return json({ status: "ok", message: "Auto copy processor executed successfully" });
    }

    // ── Cable / MDG GET endpoints ─────────────────────────────────────────
    if (action === "cable_get_stats" || action === "cable_check_row") return doGetCable_(e);
    if (action === "mdg_get_stats"   || action === "mdg_check_row")   return doGetMdg_(e);
    if (action === "get_fields")                                       return doGetDaily_(e);

    if (action === "trigger_16h" || action === "trigger_report" || action === "relay_all") return handleWebhookRequest_(e);
    if (action === "run_dashboard_build") {
      drStep1_BuildTables();
      return json({ status: "ok", message: "Dashboard build triggered" });
    }
    if (action === "get_team_wo_stats") return handleGetTeamWoStats_();
    if (action === "debug_sum_sheet")   return handleDebugSumSheet_();


    // ── Default: status check ─────────────────────────────────
    const ss = SpreadsheetApp.openById(SHEET_ID);
    getDataSheet(ss);
    setupConfigHeaders(ss);
    const ids = getAllowedIds(ss);
    return json({ status: "ok", message: "TNI Collector running", allowed: ids.size });
  } catch (err) {
    return json({ status: "error", message: err.message });
  }
}

// ============================================================
// GET_SITE_DOWN_DATA — đọc Sheet site down, trả JSON cho Python
// Sheet: 1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow (GID=0)
// ============================================================
function getSiteDownData() {
  try {
    const SD_SHEET_ID  = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow";
    const SD_SHEET_GID = "0";

    const ss = SpreadsheetApp.openById(SD_SHEET_ID);
    let sheet = null;
    for (const s of ss.getSheets()) {
      if (s.getSheetId().toString() === SD_SHEET_GID) { sheet = s; break; }
    }
    if (!sheet) return json({ status: "error", message: "Sheet not found" });

    // A1: timestamp/nội dung báo cáo mới nhất
    const a1 = sheet.getRange("A1").getValue().toString().trim();

    // Col C: toàn bộ dữ liệu đã tính bằng formula
    const lastRow = sheet.getLastRow();
    const colC = lastRow > 0
      ? sheet.getRange(1, 3, lastRow, 1).getValues().flat()
              .map(c => (c || "").toString().trim())
              .filter(c => c.length > 0)
      : [];

    // AW7:AZ15 (9 rows × 4 cols) — summary per team (skip header row 6)
    const awaz = sheet.getRange(7, 49, 9, 4).getValues();

    // AW7 timestamp
    const aw7 = sheet.getRange("AW7").getValue().toString().trim();

    // Fetch team config
    let cfgSheet = ss.getSheetByName("TeamConfig");
    let teamConfig = [];
    if (cfgSheet) {
      teamConfig = cfgSheet.getDataRange().getValues();
    }

    return json({ status: "ok", a1, colC, awaz, aw7, teamConfig });
  } catch (err) {
    return json({ status: "error", message: err.message });
  }
}


// ============================================================
// MSG IDS — L\u01b0u / \u0110\u1ecdc message_ids c\u1ee7a c\u00e1c b\u00e1o c\u00e1o (cron_send, bod_assign, v.v.)
// D\u00f9ng b\u1edfi delete_old_helper.py \u0111\u1ec3 x\u00f3a tin c\u0169 tr\u01b0\u1edbc khi g\u1eedi m\u1edbi.
// PropertiesService key: MSGIDS_{key}
// ============================================================

/** POST {action:"save_msgids", key:"CRON_TEAM_T1", msgids:[123,456]} */
function handleSaveMsgIds(body) {
  try {
    const key    = (body.key    || "").toString().trim();
    const msgids = body.msgids  || [];
    if (!key) return json({ status: "error", message: "key required" });
    const propKey = "MSGIDS_" + key;
    const props   = PropertiesService.getScriptProperties();
    if (!msgids || msgids.length === 0) {
      props.deleteProperty(propKey);
      Logger.log("[MsgIds] DELETE " + propKey);
    } else {
      props.setProperty(propKey, JSON.stringify(msgids.map(Number)));
      Logger.log("[MsgIds] SAVE " + propKey + " = " + JSON.stringify(msgids));
    }
    return json({ status: "ok", key: key, count: msgids.length });
  } catch(e) {
    return json({ status: "error", message: e.message });
  }
}

/** GET ?action=get_msgids&key=CRON_TEAM_T1 */
function handleGetMsgIds(params) {
  try {
    const key     = (params.key || "").toString().trim();
    if (!key) return json({ status: "error", message: "key required", msgids: [] });
    const propKey = "MSGIDS_" + key;
    const raw     = PropertiesService.getScriptProperties().getProperty(propKey) || "[]";
    let msgids    = [];
    try { msgids = JSON.parse(raw); } catch(e2) { msgids = []; }
    if (!Array.isArray(msgids)) msgids = [];
    Logger.log("[MsgIds] GET " + propKey + " = " + JSON.stringify(msgids));
    return json({ status: "ok", key: key, msgids: msgids });
  } catch(e) {
    return json({ status: "error", message: e.message, msgids: [] });
  }
}

/** GET ?action=get_msg_id&key=... (alias, backward compat) */
function handleGetMsgId(params) { return handleGetMsgIds(params); }

/** POST {action:"set_msg_id", key:..., msgids:[...]} (alias) */
function handleSetMsgId(body) { return handleSaveMsgIds(body); }


// ============================================================
// ACTION: CLEAN_BLANK_ROWS — xóa hàng trắng trong data sheet
// ============================================================
function handleCleanBlankRows(sheet) {
  const lastRow = sheet.getLastRow();
  const lastCol = 5; // A–E
  if (lastRow < 2) return json({ status: "ok", deleted: 0 });

  const values  = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
  // Collect blank row indices (1-indexed, bottom-up for safe deletion)
  const toDelete = [];
  for (let i = values.length - 1; i >= 0; i--) {
    const isEmpty = values[i].slice(0, lastCol).every(function(c) { return c === "" || c === null; });
    if (isEmpty) toDelete.push(i + 2);
  }
  // Batch delete: group consecutive rows, delete from bottom up
  let deleted = 0;
  let i = 0;
  while (i < toDelete.length) {
    const start = toDelete[i];
    let count = 1;
    while (i + count < toDelete.length && toDelete[i + count] === start - count) count++;
    sheet.deleteRows(start - count + 1, count);
    deleted += count;
    i += count;
  }
  return json({ status: "ok", deleted: deleted, rows: toDelete });
}

// ============================================================
// ACTION: ADD — write new row to data sheet
// Payload: { action, date, chat_id, msg }
// Sheet columns: A=Date Sent  B=Telegram ID  C=Content  D=Asset action done
// ============================================================

function handleAdd(sheet, body) {
  const dateTime = body.date    || "";
  const chatId   = body.chat_id || "";

  // NEW format: body.msg = "Order: TNI0002 ..."
  // OLD format: body.fields = {order:"...", revoke:"..."} + body.sender_name
  let content = body.msg || "";
  if (!content && body.fields && typeof body.fields === "object") {
    const parts = [];
    for (const [k, v] of Object.entries(body.fields)) {
      if (v) parts.push(k.charAt(0).toUpperCase() + k.slice(1) + ": " + v);
    }
    content = parts.join("\n");
  }

  // Guard: if content is empty, don't insert anything
  if (!content) return json({ status: "error", message: "Empty content — row not inserted" });

  const row = ["", dateTime, chatId, content, ""];
  sheet.insertRowBefore(2);
  try {
    sheet.getRange(2, 1, 1, row.length).setValues([row]);
  } catch (writeErr) {
    // Rollback: xóa hàng trắng vừa insert để tránh để lại blank row
    try { sheet.deleteRow(2); } catch(e) {}
    throw writeErr; // re-throw để doPost catch block xử lý
  }

  const rowNum = 2;
  const seqId  = sheet.getLastRow() - 1;

  // Ghi REF vào cột A
  sheet.getRange(2, 1).setValue(seqId);

  // Gắn ảnh pending (nếu user đã gửi ảnh trước khi gửi text)
  const props   = PropertiesService.getScriptProperties();
  const pKey    = "PENDING_PHOTO_" + chatId;
  const pending = JSON.parse(props.getProperty(pKey) || "[]");
  if (pending.length > 0) {
    pending.forEach(function(link, idx) {
      if (idx < 12) {
        sheet.getRange(2, 6 + idx).setValue(link); // F=6 ... Q=17
      }
    });
    props.deleteProperty(pKey);
  }

  const bg = seqId % 2 === 0 ? "#EBF3FB" : "#FFFFFF";
  sheet.getRange(2, 1, 1, 17).setBackground(bg); // A–Q

  // Lưu ACTIVE_REF + reset PHOTO_COUNT cho user này
  // Ảnh gửi sau sẽ tự gắn vào đây, dừng sau 12 ảnh
  props.setProperty("ACTIVE_REF_"   + chatId, String(seqId));
  props.setProperty("PHOTO_COUNT_"  + chatId, "0");  // reset đếm

  return json({ status: "ok", message: "Row added", row: seqId });
}

// ============================================================
// ACTION: ADD_PHOTO — ảnh Telegram → Google Drive → link vào cột F–Q
// Payload: { action, user_id, tg_url, date }
// Cột F=6, G=7, H=8, I=9, J=10, K=11, L=12, M=13, N=14, O=15, P=16, Q=17 (tối đa 12 ảnh)
// ============================================================
function handleAddPhoto(sheet, body) {
  const userId = String(body.user_id || "").trim();
  if (!userId) {
    return json({ status: "error", message: "Missing user_id" });
  }

  // 1. Tạo blob từ base64 (Python đã download sẵn) hoặc download từ URL (fallback cũ)
  let blob;
  try {
    if (body.photo_b64) {
      // ✅ Cách mới: Python gửi binary dạng base64
      const bytes = Utilities.base64Decode(body.photo_b64);
      const ext   = (body.photo_ext || "jpg").toLowerCase();
      const mime  = ext === "png" ? "image/png" : "image/jpeg";
      blob = Utilities.newBlob(bytes, mime, "photo_" + new Date().getTime() + "." + ext);
    } else if (body.tg_url) {
      // 🔄 Fallback cũ: GAS tự download từ Telegram URL
      const resp = UrlFetchApp.fetch(body.tg_url, { muteHttpExceptions: true });
      const code = resp.getResponseCode();
      if (code !== 200) {
        return json({ status: "error", message: "Telegram fetch HTTP " + code });
      }
      blob = resp.getBlob();
      const ct = blob.getContentType() || "";
      if (ct.indexOf("image") === -1 && ct.indexOf("octet") === -1) {
        return json({ status: "error", message: "Invalid content type: " + ct });
      }
    } else {
      return json({ status: "error", message: "Missing photo_b64 or tg_url" });
    }
  } catch(e) {
    return json({ status: "error", message: "Blob error: " + e.message });
  }


  // 2. Upload lên Google Drive folder 'TNI_Asset_Photos'
  const folder   = getOrCreatePhotoFolder_();
  const file     = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  const driveLink = "https://drive.google.com/file/d/" + file.getId() + "/view";

  // 3. Gắn ảnh vào đúng row
  let refId  = body.ref_id ? parseInt(body.ref_id) : null;
  const WIN_MS = 30 * 60 * 1000;
  const nowMs  = new Date().getTime();
  let attached = false;

  // Ưu tiên 1a: ref_id từ Reply/caption
  // Ưu tiên 1b: ACTIVE_REF_{userId} — lệnh text gần nhất của user
  if (!refId) {
    const activeStr = PropertiesService.getScriptProperties().getProperty("ACTIVE_REF_" + userId);
    if (activeStr) refId = parseInt(activeStr);
  }

  const props2    = PropertiesService.getScriptProperties();
  const countKey  = "PHOTO_COUNT_" + userId;
  const photoCount = parseInt(props2.getProperty(countKey) || "0");

  // Dừng nếu đã đủ 12 ảnh
  if (photoCount >= 12) {
    return json({ status: "ok", attached: false, reason: "max_photos_reached" });
  }

  // Tính thẳng row: seqId = rowNum - 1 → rowNum = refId + 1
  if (refId) {
    const targetRow = refId + 1;
    const lastRow   = sheet.getLastRow();
    if (targetRow >= 2 && targetRow <= lastRow) {
      // Đọc cột F–Q (col 6–17) của row đó
      const photoCols = sheet.getRange(targetRow, 6, 1, 12).getValues()[0];
      for (let c = 0; c < 12; c++) {
        if (!photoCols[c]) {
          sheet.getRange(targetRow, 6 + c).setValue(driveLink);
          attached = true;
          // Tăng đếm ảnh
          props2.setProperty(countKey, String(photoCount + 1));
          break;
        }
      }
    }
  }

  // Ưu tiên 2 (fallback): tìm row gần nhất của user trong 30 phút
  if (!attached) {
    const data = sheet.getDataRange().getValues();
    for (let i = data.length - 1; i >= 0; i--) {
      if (String(data[i][2] || "").trim() !== userId) continue;  // Col C = user_id
      const rowTime = parseSheetDate_(String(data[i][1] || ""));
      if (!rowTime || (nowMs - rowTime.getTime()) > WIN_MS) break; // quá cũ

      // Tìm cột ảnh trống (F=col5 → Q=col16, index 0-based)
      for (let c = 5; c <= 16; c++) {
        if (!data[i][c]) {
          sheet.getRange(i + 1, c + 1).setValue(driveLink);
          attached = true;
          break;
        }
      }
      break;
    }
  }

  // 4. Nếu chưa có dòng → lưu tạm (chờ text gửi sau)
  if (!attached) {
    const props = PropertiesService.getScriptProperties();
    const key   = "PENDING_PHOTO_" + userId;
    const arr   = JSON.parse(props.getProperty(key) || "[]");
    if (arr.length < 12) {
      arr.push(driveLink);
      props.setProperty(key, JSON.stringify(arr));
    }
  }

  return json({ status: "ok", attached: attached, ref_id: refId, link: driveLink });
}

// Lấy folder '2.2 TNIASSET TELEGRAM' bằng ID trực tiếp
function getOrCreatePhotoFolder_() {
  const FOLDER_ID = "1yvTYN5Dmjh-6QGjjNTwVb43CpzXVIpH6";
  try {
    return DriveApp.getFolderById(FOLDER_ID);
  } catch(e) {
    // Fallback: tìm theo tên nếu ID không truy cập được
    const PARENT_NAME = "1 VCM BRANCH TNI";
    const CHILD_NAME  = "2.2 TNIASSET TELEGRAM";
    const parents = DriveApp.getFoldersByName(PARENT_NAME);
    const parent  = parents.hasNext() ? parents.next() : DriveApp.getRootFolder();
    const children = parent.getFoldersByName(CHILD_NAME);
    return children.hasNext() ? children.next() : parent.createFolder(CHILD_NAME);
  }
}


// Parse date string "dd/MM/yyyy HH:mm" → Date object
function parseSheetDate_(str) {
  const m = str.match(/(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})/);
  if (!m) return null;
  return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]);
}


// ============================================================
// ACTION: DONE — fill column D for a specific row
// Payload: { action, ref_id, done_date, done_time, chat_id }
// Only allowed Telegram IDs (from Config col C) can do this.
// ============================================================

function handleDone(sheet, ss, body) {
  const doerId = String(body.chat_id || "").trim();
  const refId  = parseInt(body.ref_id);

  // Validate ref_id
  if (!refId || isNaN(refId)) {
    return json({ status: "error", message: "Invalid ref_id: " + body.ref_id });
  }

  // Authorisation check
  const allowed = getAllowedIds(ss);
  if (allowed.size > 0 && !allowed.has(doerId)) {
    return json({
      status:  "denied",
      message: "Telegram ID " + doerId + " is not authorised."
    });
  }

  // Tìm hàng bằng cách quét cột A (REF ID) — an toàn khi xóa dòng
  const lastRow   = sheet.getLastRow();
  if (lastRow < 2) {
    return json({ status: "error", message: "Sheet trống" });
  }

  const colA      = sheet.getRange(2, 1, lastRow - 1, 1).getValues().flat();
  const rowIndex  = colA.findIndex(v => parseInt(v) === refId);

  if (rowIndex === -1) {
    return json({ status: "error", message: "Không tìm thấy REF:" + String(refId).padStart(5,"0") + " (có thể đã bị xóa)" });
  }

  const targetRow = rowIndex + 2;   // +1 header, +1 vì findIndex bắt đầu từ 0

  // Cột E (col 5): gộp Done nhiều lần vào 1 ô (append)
  const existing = sheet.getRange(targetRow, 5).getValue().toString().trim();

  const doneDate   = body.done_date   || "";
  const doneTime   = body.done_time   || "";
  const doneDetail = body.done        || "";
  const doneNote   = body.note        || "";
  const configName = getNameById(ss, doerId) || (body.sender_name || "");

  let newEntry = "Done";
  if (doneDetail) newEntry += " " + doneDetail;
  newEntry += " + " + doneDate + " " + doneTime;
  if (configName) newEntry += " (" + configName + ")";
  if (doneNote)   newEntry += " | " + doneNote;

  // Gộp vào ô hiện có (nếu đã có nội dung trước đó)
  const doneText = existing ? existing + "\n" + newEntry : newEntry;

  sheet.getRange(targetRow, 5)
       .setValue(doneText)
       .setBackground("#D9EAD3")
       .setFontColor("#137333")
       .setFontWeight("bold")
       .setWrap(true);

  return json({ status: "ok", message: "Done updated", row: refId, done_text: newEntry });
}

// ============================================================
// ACTION: REGISTER_CHAT — lưu tên + ID nhóm vào sheet "Chat IDs"
// ============================================================
function handleRegisterChat(ss, body) {
  const chatId    = String(body.chat_id    || "").trim();
  const chatTitle = String(body.chat_title || "").trim();
  const chatType  = String(body.chat_type  || "").trim();
  const regBy     = String(body.reg_by     || "").trim();
  const now       = new Date();
  const dateStr   = Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy HH:mm");

  if (!chatId) return json({ status: "error", message: "chat_id is required" });

  // Tạo hoặc lấy sheet "Chat IDs"
  let sheet = ss.getSheetByName("Chat IDs");
  if (!sheet) {
    sheet = ss.insertSheet("Chat IDs");
    const headers = ["Chat Title", "Chat ID", "Type", "Registered By", "Date"];
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, 5)
         .setFontWeight("bold")
         .setBackground("#4472C4")
         .setFontColor("#FFFFFF")
         .setHorizontalAlignment("center");
    sheet.setFrozenRows(1);
    sheet.setColumnWidths(1, 5, 180);
    SpreadsheetApp.flush();
  }

  // Kiểm tra trùng chat_id
  const lastRow = sheet.getLastRow();
  if (lastRow >= 2) {
    const ids = sheet.getRange(2, 2, lastRow - 1, 1).getValues().flat().map(String);
    if (ids.includes(chatId)) {
      return json({ status: "duplicate", message: "Chat \"" + chatTitle + "\" (" + chatId + ") đã có rồi" });
    }
  }

  sheet.appendRow([chatTitle, chatId, chatType, regBy, dateStr]);
  return json({ status: "ok", message: "Đã lưu: " + chatTitle + " (" + chatId + ")" });
}

// ============================================================
// ACTION: FIND — search column C for matching content text
// Returns the first matching row ID (sequential, not row number)
// Payload: { action, text }
// ============================================================
function handleFind(sheet, body) {
  const searchText = (body.text || "").trim().toLowerCase();
  if (!searchText) return json({ status: "error", message: "text is required" });

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return json({ status: "not_found", message: "Sheet is empty" });

  // Col A = REF, Col D = Content (sau khi thêm cột A)
  const data = sheet.getRange(2, 1, lastRow - 1, 4).getValues(); // A,B,C,D

  // Tìm từ dưới lên (ưu tiên dòng mới nhất nếu trùng nội dung)
  for (let i = data.length - 1; i >= 0; i--) {
    const refVal  = data[i][0];  // col A = REF
    const content = (data[i][3] || "").toString().trim().toLowerCase(); // col D = content
    if (!content) continue;
    // Bi-directional: content chứa searchText HOẶC searchText chứa content
    if (content === searchText || content.includes(searchText) || searchText.includes(content)) {
      return json({ status: "ok", row: parseInt(refVal) || (i + 1) });
    }
  }
  return json({ status: "not_found", message: "No matching request found" });
}

// ============================================================
// ACTION: REGISTER_USER — lưu tên + Telegram ID vào tab Config
// Col B = Name  |  Col C = Telegram ID
// ============================================================
function handleRegisterUser(ss, body) {
  const userId   = String(body.user_id   || "").trim();
  const userName = String(body.user_name || "").trim();

  if (!userId) return json({ status: "error", message: "user_id is required" });

  // Tạo hoặc lấy sheet "User IDs"
  let sheet = ss.getSheetByName("User IDs");
  if (!sheet) {
    sheet = ss.insertSheet("User IDs");
    const headers = ["Name", "Telegram ID", "Date"];
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, 3)
         .setFontWeight("bold")
         .setBackground("#4472C4")
         .setFontColor("#FFFFFF")
         .setHorizontalAlignment("center");
    sheet.setFrozenRows(1);
    sheet.setColumnWidth(1, 220);
    sheet.setColumnWidth(2, 160);
    sheet.setColumnWidth(3, 160);
    SpreadsheetApp.flush();
  }

  // Kiểm tra trùng Telegram ID (col B)
  const lastRow = sheet.getLastRow();
  if (lastRow >= 2) {
    const ids = sheet.getRange(2, 2, lastRow - 1, 1).getValues().flat().map(String);
    if (ids.includes(userId)) {
      return json({ status: "duplicate", message: "ID " + userId + " đã có rồi" });
    }
  }

  const now     = new Date();
  const dateStr = Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy HH:mm");
  sheet.appendRow([userName, userId, dateStr]);
  return json({ status: "ok", message: "Đã lưu: " + userName + " (" + userId + ")" });
}

// ============================================================
// ACTION: GET_USERS — trả về danh sách Name + Telegram ID từ Config
// Dùng bởi send_now.py để tra cứu ID theo tên
// ============================================================
function handleGetUsers(ss) {
  const config = ss.getSheetByName("Config");
  if (!config) return json({ status: "error", message: "Config sheet not found" });

  const lastRow = config.getLastRow();
  if (lastRow < 2) return json({ status: "ok", users: [] });

  const data  = config.getRange(2, 1, lastRow - 1, 3).getValues(); // col A,B,C
  const users = [];
  for (const row of data) {
    const name = (row[0] || "").toString().trim();
    const id   = (row[1] || "").toString().trim();
    if (name && id) users.push({ name, id });
  }
  return json({ status: "ok", users });
}

// ============================================================
// HELPER: dateToStr — convert Date object hoặc string thành "dd/MM/yyyy"
// getValues() trả Date object, toString() cho "Fri Jun 26..." → split("/") fail
// Hàm này xử lý cả 2 kiểu để parse date luôn đúng
// ============================================================
function dateToStr(val) {
  if (val instanceof Date) {
    return Utilities.formatDate(val, "Asia/Rangoon", "dd/MM/yyyy");
  }
  return (val || "").toString().trim();
}

// ============================================================
// ACTION: LOG_SEARCH — ghi nhật ký tìm kiếm TNI + cập nhật stats
// ============================================================
function handleLogSearch(ss, body) {
  const userName = (body.user_name || "").toString().trim();
  const userId   = (body.user_id   || "").toString().trim();
  const tniCode  = (body.tni_code  || "").toString().trim().toUpperCase();
  const timeStr  = (body.time      || "").toString().trim();
  // Ưu tiên date_iso (YYYY-MM-DD) — Google Sheets nhận dạng tốt hơn dd/mm/yyyy
  const dateStr  = (body.date_iso  || body.date || "").toString().trim();

  if (!userId || !tniCode) {
    return json({ status: "error", message: "Thiếu user_id hoặc tni_code" });
  }

  // ss = SHEET_ID = "1Etd2P..." = "Team All Find - Sum WO and Task" — ĐÚNG SHEET!
  // KHÔNG dùng SD_SHEET_ID (= Site Down sheet khác, sai chỗ)
  let logSheet = ss.getSheetByName(SEARCH_LOG_TAB);
  if (!logSheet) {
    logSheet = ss.insertSheet(SEARCH_LOG_TAB);
    logSheet.appendRow(["REF", "Date", "Time", "User Name", "User ID", "TNI Code"]);
    logSheet.getRange(1, 1, 1, 6).setFontWeight("bold")
            .setBackground("#34A853").setFontColor("#FFFFFF");
  }
  logSheet.setFrozenRows(1);

  // Tính REF bằng cách quét giá trị cột A hiện tại để tìm số lớn nhất (tránh lỗi dòng trống hoặc bị xóa hàng)
  const lastRow = logSheet.getLastRow();
  let maxRef = 0;
  if (lastRow > 1) {
    const refValues = logSheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (let i = 0; i < refValues.length; i++) {
      const val = parseInt(refValues[i][0], 10);
      if (!isNaN(val) && val > maxRef) {
        maxRef = val;
      }
    }
  }
  const ref = String(maxRef + 1).padStart(5, "0");

  // Lấy ngày giờ từ GAS (Myanmar UTC+6:30)
  const TZ      = "Asia/Rangoon";
  const nowDate = new Date();
  const dateObj = new Date(nowDate.getFullYear(), nowDate.getMonth(), nowDate.getDate());
  const gasTime = Utilities.formatDate(nowDate, TZ, "HH:mm");

  // Chèn dòng mới tại dòng 2 (ngay dưới header) để tìm kiếm mới nhất luôn nằm ở đầu
  logSheet.insertRowBefore(2);
  logSheet.getRange(2, 1).setValue(ref).setFontWeight("bold").setHorizontalAlignment("center");
  logSheet.getRange(2, 2, 1, 5).setValues([[dateObj, gasTime, userName, userId, tniCode]]);
  logSheet.getRange(2, 2).setNumberFormat("dd/MM/yyyy");
  logSheet.getRange(2, 3).setNumberFormat("HH:mm");

  // Cập nhật Search Stats
  refreshStats(ss);
  return json({ status: "ok", ref: ref });
}

// ============================================================
// ACTION: LOG_READ_GROUP — Ghi lịch sử đọc tin nhắn vào tab "Read Group"
// ============================================================
function handleLogReadGroup(ss, body) {
  const records = body.records || [];
  if (!records || !records.length) {
    return json({ status: "ok", message: "No records to save" });
  }

  const READ_GROUP_TAB = "Read Group";
  let sheet = ss.getSheetByName(READ_GROUP_TAB);
  if (!sheet) {
    sheet = ss.insertSheet(READ_GROUP_TAB);
    sheet.appendRow(["Date", "Time", "Team", "Employee Name", "Telegram ID", "Read Status", "3Day", "7Day", "Month", "Note Message"]);
    sheet.getRange(1, 1, 1, 10).setFontWeight("bold")
         .setBackground("#4285F4").setFontColor("#FFFFFF");
    sheet.setFrozenRows(1);
  }

  const TZ = "Asia/Rangoon";
  const rows = [];
  records.forEach(r => {
    rows.push([
      r.date || Utilities.formatDate(new Date(), TZ, "dd/MM/yyyy"),
      r.time || Utilities.formatDate(new Date(), TZ, "HH:mm"),
      r.team || "",
      r.name || "",
      r.telegram_id || "",
      r.status || "Unread",
      r.trend_3day || "0/0/0",
      r.count_7day != null ? r.count_7day : 0,
      r.count_month != null ? r.count_month : 0,
      r.note_msg || ""
    ]);
  });

  if (rows.length > 0) {
    // Chèn các dòng mới lên trên cùng (dưới row 1 header) để luôn xem dữ liệu mới nhất
    sheet.insertRowsBefore(2, rows.length);
    sheet.getRange(2, 1, rows.length, 10).setValues(rows);
  }

  return json({ status: "ok", count: rows.length });
}


// ============================================================
// ACTION: CLEAN_SEARCH_LOG — xóa rows 133+ (test data) để reset về đúng vị trí
// ============================================================
function handleCleanSearchLog(ss) {
  const logSheet = ss.getSheetByName(SEARCH_LOG_TAB);
  if (!logSheet) return json({ status: "ok", message: "no sheet" });

  const maxRows = logSheet.getMaxRows();
  const deleted = maxRows - 132;

  // Xóa tất cả rows sau row 132 (toàn bộ là data test hôm nay)
  if (maxRows > 132) {
    logSheet.deleteRows(133, maxRows - 132);
  }

  // Khôi phục format dd/MM/yyyy cho cột B rows 2-132 (cột B là Date, cột C là Time)
  logSheet.getRange(2, 2, 131, 1).setNumberFormat("dd/MM/yyyy");
  logSheet.getRange(2, 3, 131, 1).setNumberFormat("HH:mm");

  return json({ status: "ok", deleted_rows: deleted, remaining: logSheet.getLastRow() });
}


// ============================================================
// HELPER: refreshStats — tính lại thống kê, ghi vào "Search Stats"
// Format: "Name & ID & Day:D-2/D-1/Today & Week:X & Month:Y"
// ============================================================
function refreshStats(ss) {
  const logSheet = ss.getSheetByName(SEARCH_LOG_TAB);
  if (!logSheet || logSheet.getLastRow() < 2) return;

  // Đọc toàn bộ log (bỏ header) — 6 cột (REF, Date, Time, UserName, UserID, TNICode)
  const lastRow = logSheet.getLastRow();
  const data    = logSheet.getRange(2, 1, lastRow - 1, 6).getValues();
  // Cols: 0=REF, 1=Date, 2=Time, 3=UserName, 4=UserID, 5=TNICode

  // Ngày hôm nay (Rangoon UTC+6:30)
  const now     = new Date();
  const tz      = "Asia/Rangoon";
  const today   = Utilities.formatDate(now, tz, "dd/MM/yyyy");
  const d1      = Utilities.formatDate(new Date(now - 86400000),   tz, "dd/MM/yyyy");
  const d2      = Utilities.formatDate(new Date(now - 2*86400000), tz, "dd/MM/yyyy");
  const msWeek  = 7  * 86400000;
  const msMonth = 30 * 86400000;

  // Tổng hợp theo user
  const users = {};  // key = userId
  for (const row of data) {
    const dateVal  = dateToStr(row[1]); // Cột B (Date) -> index 1
    const userName = (row[3] || "").toString().trim(); // Cột D (UserName) -> index 3
    const userId   = (row[4] || "").toString().trim(); // Cột E (UserID) -> index 4
    if (!userId) continue;

    if (!users[userId]) {
      users[userId] = { name: userName, today: 0, d1: 0, d2: 0, week: 0, month: 0 };
    }
    const u = users[userId];

    // Parse dd/MM/yyyy → Date
    const parts = dateVal.split("/");
    let rowDate = null;
    if (parts.length === 3) {
      rowDate = new Date(+parts[2], +parts[1]-1, +parts[0]);
    }
    if (!rowDate) continue;

    const diffMs = now - rowDate;
    if (dateVal === today)   u.today++;
    if (dateVal === d1)      u.d1++;
    if (dateVal === d2)      u.d2++;
    if (diffMs <= msWeek)    u.week++;
    if (diffMs <= msMonth)   u.month++;
  }

  // Lấy / tạo tab "Search Stats"
  let statsSheet = ss.getSheetByName(SEARCH_STATS_TAB);
  if (!statsSheet) {
    statsSheet = ss.insertSheet(SEARCH_STATS_TAB);
    statsSheet.getRange(1, 1).setValue("Search Stats (auto-updated)");
    statsSheet.getRange(1, 1).setFontWeight("bold")
              .setBackground("#4285F4").setFontColor("#FFFFFF");
  }
  statsSheet.setFrozenRows(1);

  // Xóa dữ liệu cũ (từ hàng 2 trở đi)
  const statLast = statsSheet.getLastRow();
  if (statLast >= 2) statsSheet.getRange(2, 1, statLast - 1, 1).clearContent();

  // Ghi từng dòng tổng hợp bằng batch setValues để tránh chậm/timeout
  const output = [];
  for (const uid of Object.keys(users)) {
    const u = users[uid];
    const summary = `${u.name} & ${uid} & Day:${u.d2}/${u.d1}/${u.today} & Week:${u.week} & Month:${u.month}`;
    output.push([summary]);
  }
  if (output.length > 0) {
    statsSheet.getRange(2, 1, output.length, 1).setValues(output);
  }
}

// Get or create the data sheet
function getDataSheet(ss) {
  let sheet = ss.getSheetByName(DATA_TAB);

  // Try finding by GID if name not found
  if (!sheet) {
    for (const s of ss.getSheets()) {
      if (s.getSheetId().toString() === "199426270") { sheet = s; break; }
    }
  }

  // Create new tab if still not found
  if (!sheet) sheet = ss.insertSheet(DATA_TAB);

  // Add headers if sheet is empty
  if (sheet.getLastRow() === 0) {
    const headers = ["Date Sent", "Telegram ID", "Content", "Asset action done"];
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, 4)
         .setFontWeight("bold")
         .setBackground("#4472C4")
         .setFontColor("#FFFFFF")
         .setHorizontalAlignment("center");
    sheet.setFrozenRows(1);
    sheet.setColumnWidth(1, 170);
    sheet.setColumnWidth(2, 150);
    sheet.setColumnWidth(3, 420);
    sheet.setColumnWidth(4, 220);
    SpreadsheetApp.flush();
  }

  return sheet;
}

// Tìm tên trong Config (col B) theo Telegram ID (col C)
function getNameById(ss, telegramId) {
  let cfg = ss.getSheetByName(CFG_TAB);
  if (!cfg) {
    for (const s of ss.getSheets()) {
      if (s.getSheetId().toString() === "1236389870") { cfg = s; break; }
    }
  }
  if (!cfg || cfg.getLastRow() < 2) return "";

  const rows = cfg.getRange(2, 1, cfg.getLastRow() - 1, 3).getValues();
  for (const r of rows) {
    if (String(r[2]).trim() === String(telegramId).trim()) {
      return String(r[1]).trim();  // col B = Name
    }
  }
  return "";
}

// Read allowed Telegram IDs from Config tab, column C
function getAllowedIds(ss) {
  let cfg = ss.getSheetByName(CFG_TAB);
  if (!cfg) {
    for (const s of ss.getSheets()) {
      if (s.getSheetId().toString() === "1236389870") { cfg = s; break; }
    }
  }
  if (!cfg || cfg.getLastRow() < 2) return new Set();

  const rows = cfg.getRange(2, 1, cfg.getLastRow() - 1, 3).getValues();
  return new Set(
    rows
      .map(r => String(r[2]).trim())          // column C = Telegram ID
      .filter(v => /^\d+$/.test(v))           // only numeric strings
  );
}

// Ensure Config tab has headers in col B and C
function setupConfigHeaders(ss) {
  let cfg = ss.getSheetByName(CFG_TAB);
  if (!cfg) return;

  const maxCol = Math.max(cfg.getLastColumn(), 3);
  const row1   = cfg.getRange(1, 1, 1, maxCol).getValues()[0];

  if (!row1[1] || row1[1].toString().trim() === "") {
    cfg.getRange(1, 2).setValue("Name")
       .setFontWeight("bold").setBackground("#4472C4")
       .setFontColor("#FFFFFF").setHorizontalAlignment("center");
    cfg.setColumnWidth(2, 200);
  }
  if (!row1[2] || row1[2].toString().trim() === "") {
    cfg.getRange(1, 3).setValue("Telegram ID")
       .setFontWeight("bold").setBackground("#4472C4")
       .setFontColor("#FFFFFF").setHorizontalAlignment("center");
    cfg.setColumnWidth(3, 160);
  }
  SpreadsheetApp.flush();
}

// ============================================================
// HELPER: buildSearchStatsMap
// ============================================================
function buildSearchStatsMap(ss) {
  const idMap  = {};   // key = userId (col E)
  const nameMap = {};  // key = userName.toLowerCase() (col D) — fallback khi UID không match
  const logSheet = ss.getSheetByName(SEARCH_LOG_TAB);
  if (!logSheet || logSheet.getLastRow() < 2) return { idMap, nameMap };
  const tz = 'Asia/Rangoon';
  const now = new Date();
  const today = Utilities.formatDate(now, tz, 'dd/MM/yyyy');
  const d1 = Utilities.formatDate(new Date(now - 86400000), tz, 'dd/MM/yyyy');
  const d2 = Utilities.formatDate(new Date(now - 2*86400000), tz, 'dd/MM/yyyy');
  const msWeek = 7 * 86400000;
  const msMonth = 30 * 86400000;
  const last = logSheet.getLastRow();
  const data = logSheet.getRange(2, 1, last - 1, 6).getValues(); // Doc 6 cot A-F
  for (const row of data) {
    const dateVal = dateToStr(row[1]); // Cot B (Date) -> index 1
    // Cot E (UserID) -> index 4
    const userId   = (row[4] || '').toString().trim();
    // Cot D (UserName) -> index 3 — fallback key
    const userName = (row[3] || '').toString().trim().toLowerCase();
    if (!userId && !userName) continue;
    // Bo qua lenh CLEAR TNIxxxx — khong tinh vao search stats
    const tniCode = (row[5] || '').toString().trim();
    if (/^clear\b/i.test(tniCode)) continue;
    // Tinh ngay
    const parts = dateVal.split('/');
    if (parts.length !== 3) continue;
    const rowDate = new Date(+parts[2], +parts[1]-1, +parts[0]);
    const diffMs = now - rowDate;
    // Accumulate idMap
    if (userId) {
      if (!idMap[userId]) idMap[userId] = { today: 0, d1: 0, d2: 0, week: 0, month: 0 };
      const u = idMap[userId];
      if (dateVal === today) u.today++;
      if (dateVal === d1)    u.d1++;
      if (dateVal === d2)    u.d2++;
      if (diffMs <= msWeek)  u.week++;
      if (diffMs <= msMonth) u.month++;
    }
    // Accumulate nameMap (dung shortName — chu sau dau cach dau tien de match linh hoat)
    if (userName) {
      const shortName = userName.split(/\s+/)[0]; // lay tu dau tien: "maung maung" -> "maung"
      if (!nameMap[shortName]) nameMap[shortName] = { today: 0, d1: 0, d2: 0, week: 0, month: 0 };
      const n = nameMap[shortName];
      if (dateVal === today) n.today++;
      if (dateVal === d1)    n.d1++;
      if (dateVal === d2)    n.d2++;
      if (diffMs <= msWeek)  n.week++;
      if (diffMs <= msMonth) n.month++;
    }
  }

  return { idMap, nameMap };
}




// ============================================================

// HELPER: fetchReportSheet
// ============================================================
function fetchReportSheet() {
  // Dung SpreadsheetApp doc truc tiep (khong can UrlFetchApp)
  // Report sheet co GID = 133591305, nam trong cung spreadsheet
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let reportSheet = null;
  for (const s of ss.getSheets()) {
    if (s.getSheetId().toString() === REPORT_GID) { reportSheet = s; break; }
  }
  if (!reportSheet) return { employees: [], leaders: [] };

  const lastRow = reportSheet.getLastRow();
  if (lastRow < 3) return { employees: [], leaders: [] };

  // Doc tu dong 1 den cuoi — doc toi 6 cot (A-F) de co them du lieu neu co
  const maxCol = Math.max(reportSheet.getLastColumn(), 6);
  const data = reportSheet.getRange(1, 1, lastRow, maxCol).getValues();
  const employees = [];
  const leaders   = [];
  const managers  = [];

  for (let i = 0; i < data.length; i++) {
    const row  = data[i];
    const sheetRow = i + 1; // 1-indexed row number
    const team = (row[0] || '').toString().trim();
    const name = (row[1] || '').toString().trim();
    const colC = (row[2] || '').toString().trim();
    const cont = (row[3] || '').toString().trim();
    const colE = (row[4] || '').toString().trim();
    // colF (index 5) dự phòng nếu có thêm cột (username hệ thống)
    const colF = row.length > 5 ? (row[5] || '').toString().trim() : '';

    // Bo qua dong header
    if (team === 'Assign Site' || team.indexOf('Export time') >= 0) continue;
    if (name === 'Assign Site' || name === 'Name System') continue;
    // Bo qua team "All WO" (gia)
    if (team === 'All WO') continue;

    const isTeamRow = (sheetRow >= 4 && sheetRow <= 59);
    const isTechRow = (sheetRow >= 75 && sheetRow <= 87);

    if (isTeamRow || isTechRow) {
      // Chỉ lấy các dòng có tên Team hợp lệ bắt đầu bằng MYT_TNI cho nhóm Team
      if (isTeamRow && !team.toUpperCase().startsWith("MYT_TNI")) {
        continue;
      }
      
      if (/Team leader/i.test(colC)) {
        // Doi truong: co team, ten, noi dung
        leaders.push({ team: team, name: name, content: cont, chat_id: colE, sys_name: colF });
      } else if (team && name) {
        // Nhan vien: co ca team va ten - lay chat_id tu cot E
        employees.push({ team: team, name: name, content: cont, chat_id: colE, sys_name: colF });
      }
    } else if (sheetRow >= 63 && sheetRow <= 69) {
      if (colE && /^\d{5,}$/.test(colE.trim())) {
        // Quan ly: co ID cot E la so (Telegram ID dang so, khong phai "-")
        const mgName = name || team || colC || ('ID:' + colE);
        managers.push({ role: colC || 'Manager', name: mgName, chat_id: colE.trim() });
      }
    }
  }
  return { employees: employees, leaders: leaders, managers: managers };
}

// ============================================================
// ACTION: REFRESH_GENERAL
// ============================================================
function handleRefreshGeneral(ss) {
  const { idMap, nameMap } = buildSearchStatsMap(ss);
  const data = fetchReportSheet();
  const employees = data.employees;
  let gen = ss.getSheetByName(GENERAL_TAB);
  if (!gen) gen = ss.insertSheet(GENERAL_TAB);
  gen.clearContents();
  gen.appendRow(['Team', 'Nhan vien', 'Hom nay', 'Hom qua', 'Hom kia', 'Tuan', 'Thang']);
  gen.getRange(1, 1, 1, 7).setFontWeight('bold').setBackground('#1565C0').setFontColor('#FFFFFF');
  for (const emp of employees) {
    const empId = (emp.chat_id || '').toString().trim();
    const shortN = (emp.name || '').toLowerCase().split(/\s+/)[0];
    const s = idMap[empId] || nameMap[shortN] || { today: 0, d1: 0, d2: 0, week: 0, month: 0 };
    gen.appendRow([emp.team, emp.name, s.today, s.d1, s.d2, s.week, s.month]);
  }
  gen.setColumnWidth(1, 200);
  gen.setColumnWidth(2, 160);
  SpreadsheetApp.flush();
  return json({ status: 'ok', message: 'General refreshed — ' + employees.length + ' rows' });
}

// ============================================================
// ACTION: GET_REPORT_DATA — for send_now.py / cron_send.py
// Trả về đầy đủ: search stats + WO stats + assign task + dep breakdown
// ============================================================
function handleGetReportData(ss) {
  const { idMap, nameMap } = buildSearchStatsMap(ss);
  // Helper: lookup stats theo uid (primary) hoặc short name (fallback)
  function lookupStats(chatId, fullName) {
    const uid = (chatId || '').toString().trim();
    const shortN = (fullName || '').toLowerCase().split(/\s+/)[0];
    return idMap[uid] || nameMap[shortN] || { today: 0, d1: 0, d2: 0, week: 0, month: 0 };
  }
  const cfgIdMap = {};
  const cfg = ss.getSheetByName(CFG_TAB);
  if (cfg && cfg.getLastRow() >= 2) {
    const cfgData = cfg.getRange(2, 1, cfg.getLastRow() - 1, 2).getValues();
    for (const row of cfgData) {
      const n = (row[0] || '').toString().trim().toLowerCase();
      const id = (row[1] || '').toString().trim();
      if (n && id) cfgIdMap[n] = id;
    }
  }

  const data = fetchReportSheet();
  const employees = data.employees;
  const leaders   = data.leaders;
  const managers  = data.managers;

  // ── Tính số ngày trong kỳ tháng (từ 21 tháng trước đến hôm nay) ──
  const tz = 'Asia/Rangoon';
  const now = new Date();
  const nowLocal = new Date(now.getTime() + 6.5 * 3600000);
  const dayNow = nowLocal.getUTCDate();
  let monthStart;
  if (dayNow <= 20) {
    monthStart = new Date(Date.UTC(nowLocal.getUTCFullYear(), nowLocal.getUTCMonth() - 1, 21) - 6.5 * 3600000);
  } else {
    monthStart = new Date(Date.UTC(nowLocal.getUTCFullYear(), nowLocal.getUTCMonth(), 21) - 6.5 * 3600000);
  }
  const monthDays = Math.floor((now - monthStart) / 86400000) + 1;

  // ── Parse WO stats từ cột D (content) của mỗi nhân viên/TL ──
  // Format cột D chứa sẵn báo cáo WO: ta parse ra các trường cần
  function parseWoFromContent(content) {
    const result = {
      wo_remain:    0,   // WO còn lại tổng
      site_remain:  0,   // Site còn lại
      wo_total:     0,   // Tổng WO
      wo_month_close: 0, // WO đóng trong kỳ tháng
      wo_week_close:  0, // WO đóng 7 ngày
      wo_d0: 0, wo_d1: 0, wo_d2: 0, // WO đóng hôm nay/qua/kia
      assign_remain: 0,  // Assign task còn lại
      assign_month_close: 0,
      dep_stats: {},     // { Asset: {remain:N, point:P}, CM: {...}, ... }
      eod_reported: 0,   // Số NV báo cáo cuối ngày (chỉ dùng cho TL)
    };
    if (!content) return result;

    // WO remain: "WO remain : 34" hoặc "WO remain: 34"
    const woRm = content.match(/WO\s*remain\s*[:\s]+?(\d+)/i);
    if (woRm) result.wo_remain = parseInt(woRm[1]) || 0;

    // Site remain: "Site: 11" hoặc "Site : 11"
    const siteRm = content.match(/Site\s*:\s*(\d+)/i);
    if (siteRm) result.site_remain = parseInt(siteRm[1]) || 0;

    // Month close (kỳ tháng): "Month Xday :77" hoặc "Month 18day :77"
    const moClose = content.match(/Month\s+\d+day\s*:\s*(\d+)/i);
    if (moClose) result.wo_month_close = parseInt(moClose[1]) || 0;

    // WO close 7 day: "/Close 7day: 26"
    const wkClose = content.match(/Close\s+7day\s*:\s*(\d+)/i);
    if (wkClose) result.wo_week_close = parseInt(wkClose[1]) || 0;

    // WO total: "M: 0 /26" — 26 là tổng WO tháng
    const mTotal = content.match(/M:\s*\d+\s*\/\s*(\d+)/i);
    if (mTotal) result.wo_total = parseInt(mTotal[1]) || 0;

    // Daily: "<:> 0/0/2/209" (TL: hôm nay/qua/kia/tổng team)
    // hoặc "<0/0/0>" (NV: 3day hôm nay/qua/kia)
    const dailyTL = content.match(/<:>\s*(\d+)\/(\d+)\/(\d+)\/(\d+)/);
    if (dailyTL) {
      result.wo_d0 = parseInt(dailyTL[1]) || 0;
      result.wo_d1 = parseInt(dailyTL[2]) || 0;
      result.wo_d2 = parseInt(dailyTL[3]) || 0;
      result.wo_total = parseInt(dailyTL[4]) || result.wo_total;
    } else {
      const daily3 = content.match(/<(\d+)\/(\d+)\/(\d+)>/);
      if (daily3) {
        result.wo_d0 = parseInt(daily3[1]) || 0;
        result.wo_d1 = parseInt(daily3[2]) || 0;
        result.wo_d2 = parseInt(daily3[3]) || 0;
      }
    }

    // Assign remain: "Assign: 30" hoặc "Assign: *60"
    const assignRm = content.match(/Assign\s*:\s*\*?(\d+)/i);
    if (assignRm) result.assign_remain = parseInt(assignRm[1]) || 0;

    // Assign month close: "Task Close Month: 0: 0/0/0" — lấy số đầu
    const assignMo = content.match(/Task\s*Close\s*Month\s*:\s*(\d+)/i);
    if (assignMo) result.assign_month_close = parseInt(assignMo[1]) || 0;

    // EOD (báo cáo cuối ngày): "3-Day Result: 11/0/0/0" — 11=tổng NV, 3 số sau là báo cáo hôm nay/qua/kia
    const eod = content.match(/3-Day\s*Result\s*:\s*(\d+)\/(\d+)\/(\d+)\/(\d+)/i);
    if (eod) result.eod_reported = parseInt(eod[2]) || 0; // số NV báo cáo hôm nay

    // Dep stats: "Asset : 3/P: 0" hoặc "Asset : TL:6 /13 P:0"
    // Pattern NV: "DepName : N/P: P_score"
    // Pattern TL: "DepName : TL:tl_count /total P:score"
    const depNV = /([A-Za-z&\s]+?)\s*:\s*(\d+)\/P:\s*(\d+)/g;
    const depTL = /([A-Za-z&\s]+?)\s*:\s*TL:(\d+)\s*\/(\d+)\s*P:(\d+)/g;
    let m;
    while ((m = depTL.exec(content)) !== null) {
      const dep = m[1].trim();
      if (dep && !['WO remain', 'Assign', 'Task Close Month', 'All Task Close', 'Close'].includes(dep)) {
        result.dep_stats[dep] = { tl_count: parseInt(m[2])||0, total: parseInt(m[3])||0, point: parseInt(m[4])||0, is_tl: true };
      }
    }
    // Chỉ parse NV nếu không có TL pattern
    if (Object.keys(result.dep_stats).length === 0) {
      while ((m = depNV.exec(content)) !== null) {
        const dep = m[1].trim();
        if (dep && !['WO remain', 'Assign', 'Task Close Month', 'All Task Close', 'Close', 'M', 'Site'].includes(dep)) {
          result.dep_stats[dep] = { remain: parseInt(m[2])||0, point: parseInt(m[3])||0, is_tl: false };
        }
      }
    }

    return result;
  }

  // ── Tính rank dựa trên % close WO theo tuần lũy kế ──
  // Tuần trong tháng: tuần 1=25%, tuần 2=50%, tuần 3=75%, tuần 4=100%
  function calcRank(wo_total, wo_month_close, month_days) {
    if (!wo_total) return 0;
    const weekNum = Math.min(4, Math.ceil(month_days / 7));  // tuần 1-4
    const target_pct = weekNum * 25;                          // 25/50/75/100%
    const actual_pct = Math.round(wo_month_close / wo_total * 100);
    // rank = điểm delta so với target (>0 tốt, <0 trễ)
    return actual_pct - target_pct;
  }

  // ── Tính % close ──
  function calcClosePct(wo_total, wo_month_close) {
    if (!wo_total) return 0;
    return Math.round(wo_month_close / wo_total * 100);
  }

  // ── Search team stats ──
  const teamStats = {};
  for (const emp of employees) {
    const empId = (emp.chat_id || cfgIdMap[(emp.name || '').toLowerCase()] || '').toString().trim();
    const s = lookupStats(empId, emp.name);
    if (!teamStats[emp.team]) teamStats[emp.team] = { today: 0, d1: 0, d2: 0, week: 0, month: 0 };
    const t = teamStats[emp.team];
    t.today += s.today; t.d1 += s.d1; t.d2 += s.d2; t.week += s.week; t.month += s.month;
  }

  // ── Team WO totals (tổng từ nhân viên trong team) ──
  const teamWo = {}; // team -> { wo_remain, wo_total, wo_month_close, wo_week_close, wo_d0,d1,d2, assign_remain, member_count }
  for (const emp of employees) {
    const wo = parseWoFromContent(emp.content);
    if (!teamWo[emp.team]) teamWo[emp.team] = { wo_remain:0, wo_total:0, wo_month_close:0, wo_week_close:0, wo_d0:0, wo_d1:0, wo_d2:0, assign_remain:0, assign_month_close:0, member_count:0 };
    const t = teamWo[emp.team];
    t.wo_remain       += wo.wo_remain;
    t.wo_total        += wo.wo_total;
    t.wo_month_close  += wo.wo_month_close;
    t.wo_week_close   += wo.wo_week_close;
    t.wo_d0           += wo.wo_d0;
    t.wo_d1           += wo.wo_d1;
    t.wo_d2           += wo.wo_d2;
    t.assign_remain   += wo.assign_remain;
    t.assign_month_close += wo.assign_month_close;
    t.member_count    += 1;
  }

  // ── Assign task stats từ Input task sheet ──
  const INPUT_GID = '1755404595';
  const inputSh = ss.getSheets().find(s => s.getSheetId().toString() === INPUT_GID);
  const assignByDep = {}; // dep -> { total, done, remain }
  if (inputSh && inputSh.getLastRow() >= 2) {
    const rows = inputSh.getRange(2, 1, inputSh.getLastRow() - 1, 10).getValues();
    for (const r of rows) {
      const dep  = (r[1] || '').toString().trim();
      const con  = (r[3] || '').toString().trim();
      const done = (r[9] || '').toString().trim();
      if (!dep || !con || ['nan','dep assign','sum'].includes(dep.toLowerCase())) continue;
      if (!assignByDep[dep]) assignByDep[dep] = { total: 0, done: 0, remain: 0 };
      assignByDep[dep].total++;
      if (done) assignByDep[dep].done++; else assignByDep[dep].remain++;
    }
  }

  // ── Build employee result ──
  // Tính rank toàn bộ NV rồi sắp xếp để gán rank số thứ tự
  const empWithWo = employees.map(emp => {
    const empId = (emp.chat_id || cfgIdMap[(emp.name || '').toLowerCase()] || '').toString().trim();
    const s = lookupStats(empId, emp.name);
    const chatId = emp.chat_id || cfgIdMap[emp.name.toLowerCase()] || '';
    const wo = parseWoFromContent(emp.content);
    const close_pct = calcClosePct(wo.wo_total, wo.wo_month_close);
    return { name: emp.name, sys_name: emp.sys_name, team: emp.team, chat_id: chatId,
             content: emp.content,
             search_today: s.today, search_d1: s.d1, search_d2: s.d2, search_week: s.week, search_month: s.month,
             wo_remain: wo.wo_remain, site_remain: wo.site_remain, wo_total: wo.wo_total,
             wo_month_close: wo.wo_month_close, wo_week_close: wo.wo_week_close,
             wo_d0: wo.wo_d0, wo_d1: wo.wo_d1, wo_d2: wo.wo_d2,
             assign_remain: wo.assign_remain, assign_month_close: wo.assign_month_close,
             dep_stats: wo.dep_stats,
             close_pct: close_pct,
             _rank_score: close_pct };
  });
  // Sắp xếp theo % close giảm dần để gán rank
  const sorted = [...empWithWo].sort((a,b) => b._rank_score - a._rank_score);
  const rankMap = {};
  sorted.forEach((e, idx) => { rankMap[e.name] = idx + 1; });
  const empResult = empWithWo.map(e => ({ ...e, rank: rankMap[e.name] || 0 }));

  // ── Build leader result ──
  const ldResult = [];
  let leaderRankIdx = 1;
  // Sắp xếp leader theo % close để gán rank
  const ldWithScore = leaders.map(ld => {
    const wo = parseWoFromContent(ld.content);
    // Fallback: nếu chat_id trống, tra bằng tên từ Config tab
    const ldId = (ld.chat_id || cfgIdMap[(ld.name || '').toLowerCase()] || '').toString().trim();
    const s = lookupStats(ldId, ld.name);
    // Đọc thêm từ TL content: "3-Day Result: 11/0/0/0" → member_count / eod_today / eod_d1 / eod_d2
    const eodM = ld.content.match(/3-Day\s*Result\s*:\s*(\d+)\/(\d+)\/(\d+)\/(\d+)/i);
    const member_count   = eodM ? parseInt(eodM[1]) || 0 : 0;
    const eod_today      = eodM ? parseInt(eodM[2]) || 0 : 0;
    const eod_d1         = eodM ? parseInt(eodM[3]) || 0 : 0;
    const eod_d2         = eodM ? parseInt(eodM[4]) || 0 : 0;
    // TL task close: "Team leader task Close: X"
    const tlCloseM = ld.content.match(/Team\s*leader\s*task\s*Close\s*:\s*(\d+)/i);
    const tl_task_close = tlCloseM ? parseInt(tlCloseM[1]) || 0 : 0;
    // All Task Close: "All Task Close: 1 : 0 : 0 : 0" — 4 kỳ trong tháng
    const allCloseM = ld.content.match(/All\s*Task\s*Close\s*:\s*(\d+)\s*:\s*(\d+)\s*:\s*(\d+)\s*:\s*(\d+)/i);
    const all_task_close = allCloseM ? [parseInt(allCloseM[1])||0, parseInt(allCloseM[2])||0, parseInt(allCloseM[3])||0, parseInt(allCloseM[4])||0] : [0,0,0,0];
    const close_pct = calcClosePct(wo.wo_total, wo.wo_month_close);
    const chatId = ld.chat_id || cfgIdMap[ld.name.toLowerCase()] || '';
    const twStats = teamWo[ld.team] || { wo_remain:0, wo_total:0, wo_month_close:0, wo_week_close:0, wo_d0:0, wo_d1:0, wo_d2:0, assign_remain:0, member_count:0 };
    return {
      name: ld.name, sys_name: ld.sys_name, team: ld.team, chat_id: chatId, content: ld.content,
      member_count: member_count || twStats.member_count,
      eod_today, eod_d1, eod_d2,
      search_today: s.today, search_d1: s.d1, search_d2: s.d2, search_week: s.week, search_month: s.month,
      wo_remain: wo.wo_remain || twStats.wo_remain,
      wo_total: wo.wo_total || twStats.wo_total,
      wo_month_close: wo.wo_month_close || twStats.wo_month_close,
      wo_week_close: wo.wo_week_close || twStats.wo_week_close,
      wo_d0: wo.wo_d0 || twStats.wo_d0,
      wo_d1: wo.wo_d1 || twStats.wo_d1,
      wo_d2: wo.wo_d2 || twStats.wo_d2,
      assign_remain: wo.assign_remain || twStats.assign_remain,
      assign_month_close: wo.assign_month_close || twStats.assign_month_close,
      dep_stats: wo.dep_stats,
      tl_task_close, all_task_close,
      close_pct: close_pct,
      _rank_score: close_pct
    };
  });
  const ldSorted = [...ldWithScore].sort((a,b) => b._rank_score - a._rank_score);
  const ldRankMap = {};
  ldSorted.forEach((e, idx) => { ldRankMap[e.name] = idx + 1; });
  ldWithScore.forEach(ld => ldResult.push({ ...ld, rank: ldRankMap[ld.name] || 0 }));

  // --- Tổng toàn bộ (cho ban quản lý) ---
  const grandTotal = { today: 0, d1: 0, d2: 0, week: 0, month: 0 };
  for (const t of Object.values(teamStats)) {
    grandTotal.today += t.today; grandTotal.d1 += t.d1; grandTotal.d2 += t.d2;
    grandTotal.week += t.week;   grandTotal.month += t.month;
  }

  // --- Team summary list (for management message) ---
  const teamSummary = [];
  for (const [team, s] of Object.entries(teamStats)) {
    const tw = teamWo[team] || {};
    teamSummary.push({ team, today: s.today, d1: s.d1, d2: s.d2, week: s.week, month: s.month,
                       wo_remain: tw.wo_remain||0, assign_remain: tw.assign_remain||0 });
  }

  handleRefreshGeneral(ss);
  return json({
    status: 'ok',
    month_days: monthDays,
    employees: empResult,
    leaders: ldResult,
    managers: managers,
    teamSummary: teamSummary,
    grandTotal: grandTotal,
    assignByDep: assignByDep,
    searchStats: idMap,
    searchStatsByName: nameMap
  });
}

// JSON response helper
function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ============================================================
// ACTION: GET_ASSET_STATS
// Đếm Order/Revoke/... theo Team + theo khoảng thời gian
// Col A=REF | Col B=Date | Col C=chat_id | Col D=Content | Col E=Done
// Periods: today(1) / yesterday(1) / 2days / 6days / 15days
// ============================================================
function handleGetAssetStats(ss) {
  const TEAMS = [
    'MYT_TNI_TEAM01_Dawei',
    'MYT_TNI_TEAM02_Myeik',
    'MYT_TNI_TEAM03_Bokpyin',
    'MYT_TNI_TEAM04_Kawthoung'
  ];
  const PERIODS = [0, 1, 2, 6, 15]; // ngày: 0=hôm nay, 1=hôm qua, 2=2 ngày trước, 6=tuần, 15=nửa tháng

  // Mốc thời gian (giờ Myanmar = UTC+6:30)
  const now   = new Date();
  const tzOff = 6.5 * 60 * 60 * 1000;
  const today = new Date(Math.floor((now.getTime() + tzOff) / 86400000) * 86400000 - tzOff);
  // today = đầu ngày hôm nay theo giờ Myanmar

  function dayStart(daysAgo) {
    return new Date(today.getTime() - daysAgo * 86400000);
  }

  // --- Bước 1: Config ---
  const cfgSheet   = ss.getSheetByName(CFG_TAB);
  const actionTypes = [];
  const recipients  = [];
  if (cfgSheet && cfgSheet.getLastRow() >= 2) {
    const cfgData = cfgSheet.getRange(2, 1, cfgSheet.getLastRow() - 1, 3).getValues();
    for (const row of cfgData) {
      const colA = (row[0] || '').toString().trim();
      const colC = (row[2] || '').toString().trim();
      if (colC && /^\d{5,}$/.test(colC)) recipients.push(colC);
      if (colA) {
        const type = colA.split(':')[0].trim();
        if (type && !actionTypes.includes(type)) actionTypes.push(type);
      }
    }
  }

  // --- Bước 2: Map chat_id → team ---
  const reportSheet = SpreadsheetApp.openById(SHEET_ID).getSheets()
    .find(s => s.getSheetId().toString() === REPORT_GID);
  const idToTeam = {};
  if (reportSheet && reportSheet.getLastRow() >= 2) {
    const rData = reportSheet.getRange(2, 1, reportSheet.getLastRow() - 1, 5).getValues();
    for (const r of rData) {
      const team   = (r[0] || '').toString().trim();
      const chatId = (r[4] || '').toString().trim();
      if (team && chatId && TEAMS.includes(team)) idToTeam[chatId] = team;
    }
  }

  // --- Bước 3: Khởi tạo stats ---
  // stats[at][team] = { d0,d1,d2,d6,d15,done_d0,done_d1,done_d2,done_d6,done_d15,total,done }
  function emptyPeriod() {
    return { d0:0,d1:0,d2:0,d6:0,d15:0, done_d0:0,done_d1:0,done_d2:0,done_d6:0,done_d15:0, total:0,done:0 };
  }
  const stats = {};
  for (const at of actionTypes) {
    stats[at] = {};
    for (const tm of TEAMS) stats[at][tm] = emptyPeriod();
  }

  // --- Bước 4: Đọc và đếm ---
  const dataSh = ss.getSheetByName(DATA_TAB);
  if (dataSh && dataSh.getLastRow() >= 2) {
    const rows = dataSh.getRange(2, 1, dataSh.getLastRow() - 1, 5).getValues();
    for (const r of rows) {
      const rawDate = r[1];                                    // Col B = date
      const chatId  = (r[2] || '').toString().trim();         // Col C
      const content = (r[3] || '').toString().trim();         // Col D
      const doneVal = (r[4] || '').toString().trim();         // Col E
      if (!content) continue;

      const actionType = content.split(':')[0].trim();
      if (!actionTypes.includes(actionType)) continue;

      let team = idToTeam[chatId] || null;

      // Fallback: nếu không tìm được team từ chat_id (VD: BOD gửi hộ),
      // thử parse team từ nội dung tin nhắn
      if (!team) {
        const c = content.toLowerCase();
        if      (/\bteam\s*0?1\b|t\s*0?1\b|dawei/i.test(content))     team = 'MYT_TNI_TEAM01_Dawei';
        else if (/\bteam\s*0?2\b|t\s*0?2\b|myeik|sub\s*team\s*2/i.test(content)) team = 'MYT_TNI_TEAM02_Myeik';
        else if (/\bteam\s*0?3\b|t\s*0?3\b|bokpyin/i.test(content))   team = 'MYT_TNI_TEAM03_Bokpyin';
        else if (/\bteam\s*0?4\b|t\s*0?4\b|kawthoung/i.test(content)) team = 'MYT_TNI_TEAM04_Kawthoung';
        else if (/\bteam\s*0?5\b|t\s*0?5\b/i.test(content))           team = 'MYT_TNI_TEAM02_Myeik'; // T5 gộp với T2
      }

      if (!team) continue;  // vẫn không xác định được team → bỏ qua

      // Parse ngày
      let rowDate = null;
      if (rawDate instanceof Date) {
        rowDate = rawDate;
      } else if (rawDate) {
        // Tách chỉ phần date từ "DD/MM/YYYY HH:MM" (collector lưu cả giờ)
        const dateStr = rawDate.toString().split(' ')[0]; // "10/06/2026"
        const parts = dateStr.split('/');
        if (parts.length === 3) {
          rowDate = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
        }
      }

      const isDone = doneVal.length > 0;
      const s = stats[actionType][team];
      s.total += 1;
      if (isDone) s.done += 1;

      if (rowDate) {
        const diffDays = Math.floor((today.getTime() - rowDate.getTime()) / 86400000);
        if (diffDays === 0)  { s.d0++;  if (isDone) s.done_d0++;  }
        if (diffDays === 1)  { s.d1++;  if (isDone) s.done_d1++;  }
        if (diffDays === 2)  { s.d2++;  if (isDone) s.done_d2++;  }
        if (diffDays <  6)  { s.d6++;  if (isDone) s.done_d6++;  }
        if (diffDays < 15)  { s.d15++; if (isDone) s.done_d15++; }
      }
    }
  }

  // --- Bước 5: Grand total ---
  const grandTotal = {};
  for (const at of actionTypes) {
    grandTotal[at] = emptyPeriod();
    for (const tm of TEAMS) {
      const s = stats[at][tm];
      const g = grandTotal[at];
      ['d0','d1','d2','d6','d15','done_d0','done_d1','done_d2','done_d6','done_d15','total','done']
        .forEach(k => g[k] += s[k]);
    }
  }


  // Ghi log vào sheet "Asset Stats Log" để làm báo cáo
  writeAssetStatsLog(ss, stats, grandTotal, actionTypes, TEAMS);

  return json({
    status:      'ok',
    actionTypes: actionTypes,
    teams:       TEAMS,
    stats:       stats,
    grandTotal:  grandTotal,
    recipients:  recipients
  });
}

// ============================================================
// ASSET STATS LOG — Ghi số liệu hàng ngày vào sheet báo cáo
// Sheet: "Asset Stats Log"
// Cột: Date | Time | Team | Action | Total | Done | Today | Yesterday | 2DayAgo | Week | Month
// ============================================================

function writeAssetStatsLog(ss, stats, grandTotal, actionTypes, teams) {
  try {
    const LOG_TAB = 'Asset Stats Log';
    let logSheet = ss.getSheetByName(LOG_TAB);

    // Tạo sheet mới nếu chưa có
    if (!logSheet) {
      logSheet = ss.insertSheet(LOG_TAB);
      // Header row
      const headers = [
        'Date', 'Time', 'Team', 'Team Short', 'Action',
        'Total', 'Done',
        'Today', 'Yesterday', '2 Days Ago', 'Week(7d)', 'Month(15d)',
        'Done Today', 'Done Yesterday', 'Done 2Days', 'Done Week', 'Done Month'
      ];
      logSheet.getRange(1, 1, 1, headers.length).setValues([headers])
        .setBackground('#1565C0').setFontColor('#FFFFFF')
        .setFontWeight('bold').setHorizontalAlignment('center');
      logSheet.setFrozenRows(1);
      logSheet.setColumnWidth(1, 100);  // Date
      logSheet.setColumnWidth(2, 70);   // Time
      logSheet.setColumnWidth(3, 220);  // Team
      logSheet.setColumnWidth(4, 120);  // Team Short
      logSheet.setColumnWidth(5, 120);  // Action
      for (let c = 6; c <= headers.length; c++) logSheet.setColumnWidth(c, 75);
    }

    const TEAM_SHORT = {
      'MYT_TNI_TEAM01_Dawei':     'Team1(Dawei)',
      'MYT_TNI_TEAM02_Myeik':     'Team2(Myeik)',
      'MYT_TNI_TEAM03_Bokpyin':   'Team3(Bokpyin)',
      'MYT_TNI_TEAM04_Kawthoung': 'Team4(Kawthoung)',
    };

    const now     = new Date();
    const dateStr = Utilities.formatDate(now, 'Asia/Yangon', 'dd/MM/yyyy');
    const timeStr = Utilities.formatDate(now, 'Asia/Yangon', 'HH:mm');

    const rows = [];

    // Ghi từng team × từng action type
    for (const team of teams) {
      for (const at of actionTypes) {
        const s = (stats[at] || {})[team] || {};
        rows.push([
          dateStr, timeStr,
          team, TEAM_SHORT[team] || team, at,
          s.total || 0, s.done || 0,
          s.d0 || 0, s.d1 || 0, s.d2 || 0, s.d6 || 0, s.d15 || 0,
          s.done_d0 || 0, s.done_d1 || 0, s.done_d2 || 0, s.done_d6 || 0, s.done_d15 || 0
        ]);
      }
    }

    // Ghi dòng Grand Total cho mỗi action type
    for (const at of actionTypes) {
      const g = grandTotal[at] || {};
      rows.push([
        dateStr, timeStr,
        'GRAND TOTAL', 'Total', at,
        g.total || 0, g.done || 0,
        g.d0 || 0, g.d1 || 0, g.d2 || 0, g.d6 || 0, g.d15 || 0,
        g.done_d0 || 0, g.done_d1 || 0, g.done_d2 || 0, g.done_d6 || 0, g.done_d15 || 0
      ]);
    }

    if (rows.length > 0) {
      const lastRow = logSheet.getLastRow();
      logSheet.getRange(lastRow + 1, 1, rows.length, rows[0].length).setValues(rows);
      // Batch color — 1 API call thay vì 40
      const bgs = rows.map(function(row, i) {
        const color = row[2] === 'GRAND TOTAL' ? '#FFF9C4' :
                      ((lastRow + 1 + i) % 2 === 0 ? '#F8F9FA' : '#FFFFFF');
        return new Array(row.length).fill(color);
      });
      logSheet.getRange(lastRow + 1, 1, rows.length, rows[0].length).setBackgrounds(bgs);
    }

    Logger.log(`✅ writeAssetStatsLog: ${rows.length} rows written to "${LOG_TAB}"`);
  } catch (e) {
    Logger.log(`❌ writeAssetStatsLog error: ${e.message}`);
  }
}

// Sheet: SEND_TELEGRAM | Cột B=Tên | C=Nội dung | D=Chat ID | E=Kết quả
// ============================================================

const TG_SEND_TOKEN  = PropertiesService.getScriptProperties().getProperty("SEND_BOT_TOKEN") || "";
const SEND_TAB_NAME  = 'SEND_TELEGRAM';

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('📲 Gửi Telegram')
    .addItem('🆕 Tạo Sheet Gửi',   'setupSendTelegramSheet')
    .addItem('📤 Gửi tin nhắn',    'sendTelegramBulk')
    .addItem('🗑️ Xóa kết quả',    'clearTelegramResults')
    .addItem('🧪 Test 1 tin nhắn', 'sendTestMessage')
    .addToUi();

  if (typeof drRegisterMenu_ === "function") {
    drRegisterMenu_(ui);
  }
}

function setupSendTelegramSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SEND_TAB_NAME);
  if (sh) ss.deleteSheet(sh);
  sh = ss.insertSheet(SEND_TAB_NAME);

  // Tiêu đề
  sh.getRange('A1:E1').merge()
    .setValue('📲 GỬI TIN NHẮN TELEGRAM HÀNG LOẠT')
    .setBackground('#1565C0').setFontColor('#FFFFFF')
    .setFontSize(14).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.setRowHeight(1, 45);

  // Hướng dẫn
  sh.getRange('A2:E2').merge()
    .setValue('💡 Điền Tên (B) + Nội dung (C) + Chat ID Telegram (D) → Bấm nút GỬI')
    .setBackground('#E3F2FD').setFontColor('#0D47A1').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.setRowHeight(2, 30);

  // Header
  sh.getRange('A3:E3')
    .setValues([['STT','TÊN NHÂN VIÊN','NỘI DUNG TIN NHẮN','CHAT ID TELEGRAM','KẾT QUẢ']])
    .setBackground('#1976D2').setFontColor('#FFFFFF').setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.setRowHeight(3, 35);

  // Độ rộng cột
  sh.setColumnWidth(1, 50);
  sh.setColumnWidth(2, 160);
  sh.setColumnWidth(3, 380);
  sh.setColumnWidth(4, 170);
  sh.setColumnWidth(5, 200);

  // 100 dòng
  for (let i = 1; i <= 100; i++) {
    const r  = i + 3;
    const bg = (r % 2 === 0) ? '#F8F9FA' : '#FFFFFF';
    sh.getRange(r, 1).setValue(i);
    sh.getRange(r, 1, 1, 5).setBackground(bg);
  }
  // Dòng mẫu
  sh.getRange('B4').setValue('Ví dụ: Maung Aung');
  sh.getRange('C4').setValue('📋 Xin chào! Đây là tin nhắn thử nghiệm từ hệ thống TNI.');

  // Định dạng
  sh.getRange('A4:E103').setBorder(true,true,true,true,true,true,'#BBDEFB',SpreadsheetApp.BorderStyle.SOLID).setVerticalAlignment('middle');
  sh.getRange('B4:B103').setHorizontalAlignment('left').setFontSize(10).setFontWeight('bold');
  sh.getRange('C4:C103').setWrap(true).setHorizontalAlignment('left').setFontSize(10);
  sh.getRange('D4:D103').setHorizontalAlignment('center').setFontSize(10).setFontFamily('Courier New');
  sh.getRange('E4:E103').setHorizontalAlignment('center').setFontSize(10);

  // Nút bấm (ô màu)
  sh.setColumnWidth(6, 20);
  sh.setColumnWidth(7, 145);
  sh.setColumnWidth(8, 145);

  sh.getRange('G1:H2').merge()
    .setValue('📤 GỬI TIN NHẮN')
    .setBackground('#E53935').setFontColor('#FFFFFF')
    .setFontSize(13).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle')
    .setBorder(true,true,true,true,false,false,'#B71C1C',SpreadsheetApp.BorderStyle.SOLID_MEDIUM);

  sh.getRange('G3:H3').merge()
    .setValue('🗑️ XÓA KẾT QUẢ')
    .setBackground('#757575').setFontColor('#FFFFFF')
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.setRowHeight(3, 28);

  // Thống kê tự động
  sh.getRange('G4').setValue('📊 THỐNG KÊ').setBackground('#E8EAF6').setFontWeight('bold').setHorizontalAlignment('center');
  sh.getRange('G5').setValue('✅ Thành công:').setBackground('#E8F5E9');
  sh.getRange('H5').setFormula('=COUNTIF(E4:E103,"✅*")').setBackground('#E8F5E9').setFontWeight('bold').setHorizontalAlignment('center');
  sh.getRange('G6').setValue('❌ Thất bại:').setBackground('#FFEBEE');
  sh.getRange('H6').setFormula('=COUNTIF(E4:E103,"❌*")').setBackground('#FFEBEE').setFontWeight('bold').setHorizontalAlignment('center');
  sh.getRange('G7').setValue('📋 Tổng có ID:').setBackground('#E3F2FD');
  sh.getRange('H7').setFormula('=COUNTA(D4:D103)').setBackground('#E3F2FD').setFontWeight('bold').setHorizontalAlignment('center');

  sh.setFrozenRows(3);
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(ss.getNumSheets());

  SpreadsheetApp.getUi().alert(
    '✅ Tạo sheet xong! (100 dòng)\n\n' +
    '📌 Gán nút đỏ:\n' +
    '   Click ô đỏ → 3 chấm ⋮ → Assign script\n' +
    '   → Gõ: sendTelegramBulk → OK\n\n' +
    '📌 Gán nút xám:\n' +
    '   → Gõ: clearTelegramResults → OK'
  );
}

function sendTelegramBulk() {
  const ss  = SpreadsheetApp.getActiveSpreadsheet();
  const sh  = ss.getSheetByName(SEND_TAB_NAME);
  if (!sh) { SpreadsheetApp.getUi().alert('❌ Chưa tạo sheet!\nVào menu 📲 → Tạo Sheet Gửi'); return; }

  const lastRow = sh.getLastRow();
  if (lastRow < 4) { SpreadsheetApp.getUi().alert('⚠️ Chưa có dữ liệu!'); return; }

  const data   = sh.getRange(4, 2, lastRow - 3, 3).getValues(); // B, C, D
  const resCol = sh.getRange(4, 5, lastRow - 3, 1);             // E
  const now    = Utilities.formatDate(new Date(), 'Asia/Rangoon', 'dd/MM/yyyy HH:mm');

  let ok = 0, fail = 0, skip = 0;
  const results = [];

  for (let i = 0; i < data.length; i++) {
    const content = String(data[i][1] || '').trim();   // C
    const chatId  = String(data[i][2] || '').trim().replace(/\.0$/, ''); // D

    if (!content && !chatId) { results.push(['']); skip++; continue; }
    if (!content)            { results.push(['⚠️ Thiếu nội dung']); skip++; continue; }
    if (!chatId)             { results.push(['⚠️ Thiếu Chat ID']);   skip++; continue; }

    const r = _tgSendMsg(chatId, content);
    if (r.ok) { results.push([`✅ ${now}`]); ok++; }
    else       { results.push([`❌ ${r.error}`]);  fail++; }
    Utilities.sleep(300);
  }

  if (results.length > 0) {
    resCol.setValues(results);
    for (let i = 0; i < results.length; i++) {
      const cell = sh.getRange(4 + i, 5);
      const val  = results[i][0];
      if      (val.startsWith('✅')) cell.setBackground('#E8F5E9').setFontColor('#1B5E20');
      else if (val.startsWith('❌')) cell.setBackground('#FFEBEE').setFontColor('#B71C1C');
      else if (val.startsWith('⚠️')) cell.setBackground('#FFF8E1').setFontColor('#E65100');
      else                           cell.setBackground('#FFFFFF').setFontColor('#000000');
    }
  }
  SpreadsheetApp.getUi().alert(`📊 KẾT QUẢ\n\n✅ Thành công : ${ok}\n❌ Thất bại  : ${fail}\n⚠️ Bỏ qua    : ${skip}`);
}

function clearTelegramResults() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SEND_TAB_NAME);
  if (!sh) return;
  sh.getRange(4, 5, 100, 1).clearContent().setBackground('#FFFFFF').setFontColor('#000000');
  SpreadsheetApp.getUi().alert('🗑️ Đã xóa kết quả cột E!');
}

function sendTestMessage() {
  const ui = SpreadsheetApp.getUi();
  const r  = ui.prompt('🧪 TEST', 'Nhập Chat ID Telegram của bạn:', ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return;
  const chatId = r.getResponseText().trim();
  if (!chatId) { ui.alert('❌ Chưa nhập Chat ID!'); return; }
  const now = Utilities.formatDate(new Date(), 'Asia/Rangoon', 'dd/MM/yyyy HH:mm');
  const res = _tgSendMsg(chatId, `🧪 <b>Test thành công!</b>\n📅 ${now}\n✅ Bot hoạt động bình thường!`);
  ui.alert(res.ok ? '✅ Gửi thành công!\nKiểm tra Telegram.' : `❌ Lỗi: ${res.error}`);
}

function _tgSendMsg(chatId, text) {
  try {
    const resp = UrlFetchApp.fetch(
      `https://api.telegram.org/bot${TG_SEND_TOKEN}/sendMessage`,
      { method      : 'post',
        contentType : 'application/json',
        payload     : JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
        muteHttpExceptions: true,
        deadline    : 10   // ← tối đa 10 giây mỗi lần gọi
      }
    );
    const j = JSON.parse(resp.getContentText());
    return j.ok ? { ok: true } : { ok: false, error: j.description };
  } catch(e) {
    return { ok: false, error: e.message };
  }
}

// ── Chạy hàm này 1 lần để cấp quyền UrlFetchApp ──
function authorizeNow() {
  UrlFetchApp.fetch('https://api.telegram.org');
  SpreadsheetApp.getUi().alert('✅ Cấp quyền thành công!');
}

// ════════════════════════════════════════════════════════════
// ACTION: store_site_down
// Nhận raw text từ botlookup_relay.py → ghi Cột A → checkAndSend()
// Payload: { action: "store_site_down", text: "..." }
// ════════════════════════════════════════════════════════════
// SELF-CONTAINED: inline constants + writeToColumnA logic
// Không phụ thuộc site_down_notify.gs (2 file có thể ở 2 GAS project)
// ════════════════════════════════════════════════════════════
function handleStoreSiteDownDirect(body) {
  try {
    var text = (body.text || "").trim();
    if (!text) return json({ status: "error", message: "No text provided" });

    // ── Inline constants (không dùng SD_SHEET_ID từ site_down_notify.gs) ──
    var SD_SHEET_ID_LOCAL  = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow";
    var SD_SHEET_GID_LOCAL = 0;   // GID=0 là sheet đầu tiên

    // ── Mở spreadsheet ──
    var ss = SpreadsheetApp.openById(SD_SHEET_ID_LOCAL);

    // ── Tìm sheet theo GID (không dùng getSheetByGid từ site_down_notify.gs) ──
    var sheet = null;
    var allSheets = ss.getSheets();
    for (var si = 0; si < allSheets.length; si++) {
      if (allSheets[si].getSheetId() === SD_SHEET_GID_LOCAL) {
        sheet = allSheets[si];
        break;
      }
    }
    // Fallback: nếu không tìm theo GID, dùng sheet đầu tiên
    if (!sheet) sheet = ss.getSheets()[0];
    if (!sheet) return json({ status: "error", message: "SD sheet not found" });

    // ── Ghi vào Cột A: xóa cũ → ghi mới từng dòng ──
    var lines = text.split("\n");
    var lastRow = sheet.getLastRow();
    if (lastRow > 0) {
      sheet.getRange(1, 1, lastRow, 1).clearContent();
    }
    var writeData = lines.map(function(line) { return [line]; });
    if (writeData.length > 0) {
      sheet.getRange(1, 1, writeData.length, 1).setValues(writeData);
    }
    Logger.log("[store_site_down] ✅ Đã ghi " + writeData.length + " dòng vào Cột A (sheet: " + sheet.getName() + ")");

    SpreadsheetApp.flush();
    Utilities.sleep(10000);   // Chờ công thức Cột C và AW7:AZ15 cập nhật hoàn toàn

    // ── Gọi checkAndSend() nếu cùng GAS project; nếu khác project thì GAS trigger 5p sẽ xử lý ──
    var checkResult = { sent_tin1: false, sent_tin2: false };
    try {
      var r = checkAndSend(true);
      if (r && typeof r === "object") {
        checkResult = r;
      }
      Logger.log("[store_site_down] ✅ checkAndSend() xong. Result: " + JSON.stringify(checkResult));
    } catch(callErr) {
      Logger.log("[store_site_down] ⚠️ checkAndSend() không khả dụng từ project này — GAS trigger 5p sẽ xử lý. Chi tiết: " + callErr.message);
    }

    return json({ 
      status: "ok", 
      lines: writeData.length, 
      sheet: sheet.getName(),
      sent_tin1: !!checkResult.sent_tin1,
      sent_tin2: !!checkResult.sent_tin2
    });
  } catch(err) {
    Logger.log("[store_site_down] ❌ " + err.message);
    return json({ status: "error", message: err.message });
  }
}

// ════════════════════════════════════════════════════════════
    const GID_SUM = "1840482617";
    const TEAM_ORDER = ["team1", "team2", "team3", "team4"];
    const chartG = {};  // G col(6)  = Total FOT Close
    const chartP = {};  // P col(15) = Remain WO (CD not yet Close)
    const chartN = {};  // N col(13) = Overdue FOT not closed
    const chartA = {};  // A col(0)  = CD Not Yet Close
    const chartJ = {};  // J col(9)  = 3-day: closes on day-1 (11/08)
    const chartK = {};  // K col(10) = 3-day: closes on day-2 (10/08)
    const chartL = {};  // L col(11) = 3-day: closes on day-3 (09/08)
    const chartM = {};  // M col(12) = Plan for next date (12/08)
    let dynamicDateLabel = "";
    let dynamicPlanLabel = "";

    try {
      const sumSh = ss.getSheets().find(function(s) {
        return String(s.getSheetId()) === GID_SUM;
      });
      if (sumSh && sumSh.getLastRow() >= 56) {
        // Read row 2 headers for J, K, L, M
        const hdrRow2 = sumSh.getRange(2, 1, 1, 16).getValues()[0];
        const rawHdrJ = fmtCell(hdrRow2[9]);   // Col J header e.g. "Close at: 11/08/26"
        const rawHdrK = fmtCell(hdrRow2[10]);  // Col K header e.g. "Close at: 10/08/26"
        const rawHdrL = fmtCell(hdrRow2[11]);  // Col L header e.g. "Close at: 09/08/26"
        const rawHdrM = fmtCell(hdrRow2[12]);  // Col M header e.g. "Plan: 12/08/26"

        // Format dynamic labels
        const dJStr = (rawHdrJ.match(/(\d{2}\/\d{2})/)||[,"11/08"])[1];
        const dKStr = (rawHdrK.match(/(\d{2}\/\d{2})/)||[,"10/08"])[1];
        const dLStr = (rawHdrL.match(/(\d{2}\/\d{2})/)||[,"09/08"])[1];
        const dMStr = (rawHdrM.match(/(\d{2}\/\d{2}(?:\/\d{2,4})?)/)||[,"12/08/2026"])[1];

        const yrStr = Utilities.formatDate(new Date(), "Asia/Rangoon", "yyyy");
        const fullMDate = dMStr.includes("/") && dMStr.split("/").length === 3 ? dMStr : dMStr + "/" + yrStr;
        dynamicPlanLabel = "🎯 Plan " + fullMDate + " (M):";

        const mJ = dJStr.split("/")[0];
        const mK = dKStr.split("/")[0];
        const mL = dLStr.split("/")[0];
        const mMonth = (dJStr.split("/")[1] || "08");
        dynamicDateLabel = mJ + "/" + mK + "/" + mL + "-" + mMonth + "-" + yrStr;

        // Read rows 53-56, cols A(1) to P(16)
        const sumRng = sumSh.getRange(53, 1, 4, 16).getValues();
        for (let r = 0; r < 4; r++) {
          const tk  = TEAM_ORDER[r];
          const row = sumRng[r];
          const gv = row[6];   // col G (index 6) = FOT Close
          const pv = row[15];  // col P (index 15) = Remain WO
          const nv = row[13];  // col N (index 13) = Overdue FOT
          const av = row[0];   // col A (index 0)  = CD Not Yet Close
          const jv = row[9];   // col J (index 9)  = day-1 closes (11/08)
          const kv = row[10];  // col K (index 10) = day-2 closes (10/08)
          const lv = row[11];  // col L (index 11) = day-3 closes (09/08)
          const mv = row[12];  // col M (index 12) = Plan WOs (12/08)
          if (typeof gv === "number") chartG[tk] = gv;
          if (typeof pv === "number") chartP[tk] = pv;
          if (typeof nv === "number") chartN[tk] = nv;
          if (typeof av === "number") chartA[tk] = av;
          if (typeof jv === "number") chartJ[tk] = jv;
          if (typeof kv === "number") chartK[tk] = kv;
          if (typeof lv === "number") chartL[tk] = lv;
          if (typeof mv === "number") chartM[tk] = mv;
        }
      }
    } catch(eSum) {
      Logger.log("GID 1840482617 read error: " + eSum.message);
    }


    const TEAMS = {
      "MYT_TNI_TEAM01_Dawei":     "team1",
      "MYT_TNI_TEAM02_Myeik":     "team2",
      "MYT_TNI_TEAM03_Bokpyin":   "team3",
      "MYT_TNI_TEAM04_Kawthoung": "team4"
    };
    const TEAM_LABELS = {
      team1: "Team 1 Dawei",   team2: "Team 2 Myeik",
      team3: "Team 3 Bokpyin", team4: "Team 4 Kawthoung"
    };
    const TEAM_REGIONS = {
      team1: "MYT_TNI_TEAM01_Dawei",   team2: "MYT_TNI_TEAM02_Myeik",
      team3: "MYT_TNI_TEAM03_Bokpyin", team4: "MYT_TNI_TEAM04_Kawthoung"
    };

    const stats = {};
    for (const k of Object.keys(TEAM_LABELS)) {
      stats[k] = {
        remain: 0, closeMonth: 0, fotClose: 0,
        d0: 0, d1: 0, d2: 0, planM: 0,
        engineers: 0, waitCD: 0, cdNotYet: 0, closeRate: 0,
        rankFromText: 0
      };
    }

    // Parse header row 0 for report date range (cells may be Date objects)
    function fmtCell(v) {
      if (v instanceof Date) return Utilities.formatDate(v, "Asia/Rangoon", "dd/MM/yyyy");
      return String(v || "").replace(/\s+/g, " ").trim();
    }
    const hdr0 = fmtCell(raw[0][1]);  // period start e.g. "21/07/2026"
    const hdr1 = fmtCell(raw[0][2]);  // period end   e.g. "20/08/2026"

    for (let i = 3; i < raw.length; i++) {
      const teamRaw  = String(raw[i][0] || "").trim();
      const username = String(raw[i][2] || "").trim();
      const woText   = String(raw[i][3] || "").trim();

      if (!teamRaw || !woText || woText === "0" || woText === "") continue;

      let teamKey = null;
      for (const k of Object.keys(TEAMS)) {
        if (teamRaw === k) { teamKey = TEAMS[k]; break; }
      }
      if (!teamKey) continue;

      const s = stats[teamKey];
      const isLeaderSummary = username.startsWith("Team leader");

      function gi(pattern) {
        const m = woText.match(pattern);
        return m ? parseInt(m[1], 10) : 0;
      }
      function giAll(re) {
        // Sum ALL occurrences (handles T2 "Sub" sub-section)
        let total = 0, m;
        const g = new RegExp(re.source, "g");
        while ((m = g.exec(woText)) !== null) total += parseInt(m[1], 10);
        return total;
      }

      if (isLeaderSummary) {
        // Read ALL team metrics from this authoritative summary row
        s.closeMonth = giAll(/\/(\d+) WO Close/);
        s.remain     = giAll(/\/(\d+) WO Remain/);
        s.fotClose   = gi(/\/WO \/Overdue \/FOT \/NOT \/Close: \/(\d+)/);
        s.waitCD     = gi(/Wait CD : \/(\d+)/);
        s.cdNotYet   = gi(/CD Not Yet Close : \/(\d+)/);
        const rm = woText.match(/Close: \/(\d+(?:\.\d+)?)%/);
        s.closeRate  = rm ? parseFloat(rm[1]) : 0;
        s.rankFromText = gi(/Rank: \/(\d+)/);
        // 3-day close: sum all "3Day: D2 /D1 /D0" occurrences (includes Sub sections)
        const re3 = /3Day: (\d+) \/(\d+) \/(\d+)/g;
        let m3;
        while ((m3 = re3.exec(woText)) !== null) {
          s.d2 += parseInt(m3[1], 10);
          s.d1 += parseInt(m3[2], 10);
          s.d0 += parseInt(m3[3], 10);
        }
      } else {
        // Individual engineer row: count headcount only
        s.engineers++;
      }
    }

    // Date label — format: "JJ/KK/LL-MM-YYYY" where J=day-1, K=day-2, L=day-3
    const now     = new Date();
    function fmtDay(d)  { return Utilities.formatDate(d, DR_TZ2, "dd"); }
    function fmtMY(d)   { return Utilities.formatDate(d, DR_TZ2, "MM/yyyy"); }
    // e.g. "08/07/06-08-2026" (J-date/K-date/L-date then -month-year)
    const dateLabel = fmtDay(d0Date) + "/" + fmtDay(d1Date) + "/" + fmtDay(d2Date)
                    + "-" + Utilities.formatDate(now, DR_TZ2, "MM") + "-"
                    + Utilities.formatDate(now, DR_TZ2, "yyyy");

    // Build result
    const result = {};
    const ranks = [];
    for (const k of Object.keys(TEAM_LABELS)) {
      const s = stats[k];

      // v299: Prefer formula cells from GID 893574714 rows 53-56 (same source as chart)
      // Fall back to team leader text values if formula cells not available
      const fotClose = chartG[k] !== undefined ? chartG[k] : s.closeMonth; // G
      const remain   = chartP[k] !== undefined ? chartP[k] : s.remain;     // P
      const overdueF = chartN[k] !== undefined ? chartN[k] : s.fotClose;   // N
      const cdNotYet = chartA[k] !== undefined ? chartA[k] : s.cdNotYet;   // A
      // 3-day closes from chart (J=day-1, K=day-2, L=day-3) or fall back to text
      const dJ = chartJ[k] !== undefined ? chartJ[k] : s.d1;  // yesterday
      const dK = chartK[k] !== undefined ? chartK[k] : s.d2;  // 2 days ago
      const dL = chartL[k] !== undefined ? chartL[k] : s.d0;  // 3 days ago

      const total = fotClose + remain;   // G + P = Total WO
      const pct = s.closeRate > 0 ? Math.round(s.closeRate) : (total > 0 ? Math.round(fotClose / total * 100) : 0);
      ranks.push({ k: k, pct: s.closeRate > 0 ? s.closeRate : pct, rankT: s.rankFromText });
      result[k] = {
        name:          TEAM_LABELS[k],
        region:        TEAM_REGIONS[k],
        engineers:     s.engineers,
        totalAssigned: total,        // G + P
        fotClose:      fotClose,     // G = Total FOT Close
        remain:        remain,       // P = Remain WO
        overdueF:      overdueF,     // N = Overdue FOT not closed
        waitCD:        s.waitCD,     // Wait CD (from team leader text)
        cdNotYet:      cdNotYet,     // A = CD Not Yet Close
        d0: dL,  // L col = 3 days ago (Aug 6) — shown last  → 7
        d1: dK,  // K col = 2 days ago (Aug 7) — shown middle → 0
        d2: dJ,  // J col = yesterday  (Aug 8) — shown first  → 2
        // HTML: d2/d1/d0 = 2/0/7 ✅
        pct:           pct,
        closeRate:     s.closeRate,
        metTarget:     s.closeRate >= 50
      };
    }

    // Rank by close rate (highest = rank 1); if closeRate from text available use it for accurate sort
    ranks.sort(function(a,b){ return b.pct - a.pct; });
    ranks.forEach(function(r, i) { result[r.k].rank = i + 1; });

    const updatedAt = Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy HH:mm");
    return json({
      status:     "ok",
      updatedAt:  updatedAt,
      period:     hdr0 + " – " + hdr1,
      dateLabel:  dateLabel,
      sheetFound: sheetDebug,
      data:       result
    });

  } catch(e) {
    return json({ status: "error", message: e.message, stack: e.stack });
  }
}
// ─────────────────────────────────────────────────────────────────────
// DEBUG: Read rows 53-56 of ALL sheets — find which sheet has G/P/N/A
// GET ?action=debug_sum_sheet
// ─────────────────────────────────────────────────────────────────────
function handleDebugSumSheet_() {
  try {
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const sheets = ss.getSheets();
    const result = {};

    for (const sh of sheets) {
      const shId   = String(sh.getSheetId());
      const shName = sh.getName();
      const lastR  = sh.getLastRow();
      const lastC  = sh.getLastColumn();
      if (lastR < 53 || lastC < 1) continue;

      // Read rows 53-56 with up to 20 cols
      const cols = Math.min(lastC, 20);
      try {
        const vals = sh.getRange(53, 1, Math.min(4, lastR - 52), cols).getValues();
        const rows = [];
        for (let r = 0; r < vals.length; r++) {
          const rowObj = {};
          for (let c = 0; c < vals[r].length; c++) {
            const v = vals[r][c];
            if (v !== "" && v !== null && v !== 0) {
              // Column letter: A=1, G=7, J=10, K=11, L=12, N=14, P=16
              const colLetter = c < 26 ? String.fromCharCode(65 + c) : "COL"+(c+1);
              rowObj[colLetter] = v instanceof Date ? Utilities.formatDate(v,"Asia/Rangoon","dd/MM/yyyy") : v;
            }
          }
          rows.push({ row: 53 + r, data: rowObj });
        }
        if (rows.some(function(r){ return Object.keys(r.data).length > 0; })) {
          result[shId + "_" + shName] = rows;
        }
      } catch(e2) { /* skip inaccessible sheet */ }
    }
    return json({ status: "ok", sheets_with_data: result });
  } catch(e) {
    return json({ status: "error", message: e.message });
  }
}
// ============================================================
// NOTE MESSAGE_IDS — Lưu/đọc message_ids của Note gửi bởi @Phongha79
// botlookup_relay.py gọi GAS để lưu/đọc, rồi xóa Note cũ qua Telethon
// ============================================================

/** Lưu Note message_ids — gọi từ botlookup_relay.py */
function handleSaveNoteMsgIds(body) {
  var props = PropertiesService.getScriptProperties();
  props.setProperty("SD_NOTE_MSGIDS", JSON.stringify(body.msgids || {}));
  Logger.log("[Note] 💾 Saved Note msgids: " + JSON.stringify(body.msgids));
  return json({ status: "ok" });
}

/** Đọc Note message_ids — gọi từ botlookup_relay.py */
function handleGetNoteMsgIds() {
  var props = PropertiesService.getScriptProperties();
  var raw   = props.getProperty("SD_NOTE_MSGIDS") || "{}";
  try {
    return json({ status: "ok", msgids: JSON.parse(raw) });
  } catch(e) {
    return json({ status: "ok", msgids: {} });
  }
}

// ============================================================
// GENERIC MESSAGE_IDS — Lưu/đọc message_ids cho Python scripts
// Python gọi qua HTTP POST: action=save_msgids, body={key, msgids}
//                    GET: action=get_msgids&key=...
// Key format: SD_MSGID_{key} — VD: CRON_TEAM_T1, PLAN_CONTROL
// ============================================================

/** Lưu generic message_ids — gọi từ Python scripts qua doPost */
function handleSaveMsgIds(body) {
  var key    = (body.key || "").toString().trim();
  var msgids = body.msgids || [];
  if (!key) return json({ status: "error", message: "Missing key" });

  var props = PropertiesService.getScriptProperties();
  var propKey = "SD_MSGID_" + key;
  var existing = [];
  try {
    var raw = props.getProperty(propKey) || "";
    if (raw) {
      existing = JSON.parse(raw);
      if (!Array.isArray(existing)) existing = [];
    }
  } catch(e) {}

  // Ghép các ID mới vào danh sách cũ
  var combined = existing.concat(msgids);

  // Chỉ giữ lại tối đa 20 ID gần nhất
  var toSave = combined.slice(-20);
  props.setProperty(propKey, JSON.stringify(toSave));
  Logger.log("[MsgIds] 💾 Saved " + key + " = " + JSON.stringify(toSave));
  return json({ status: "ok", key: key, count: toSave.length });
}

/** Đọc generic message_ids — gọi từ Python scripts qua doGet */
function handleGetMsgIds(params) {
  // params là e.parameter (GET) hoặc body (POST)
  var key = "";
  if (params && params.key) key = params.key.toString().trim();
  if (!key) return json({ status: "error", message: "Missing key" });

  var props = PropertiesService.getScriptProperties();
  var raw   = props.getProperty("SD_MSGID_" + key) || "[]";
  try {
    return json({ status: "ok", key: key, msgids: JSON.parse(raw) });
  } catch(e) {
    return json({ status: "ok", key: key, msgids: [] });
  }
}

// ============================================================
// REAL-TIME BOD ASSIGN TO M&E ALERTS
// ============================================================

/** Kiểm tra và gửi thông báo nếu có giao việc mới cho M&E hôm nay */
function checkBodAssignME() {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  const sheet = ss.getSheets().find(s => s.getSheetId() === 1482565085) || ss.getSheetByName("BOD assign");
  if (!sheet) {
    Logger.log("[checkBodAssignME] ❌ Không tìm thấy sheet BOD assign");
    return;
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  // Lấy dữ liệu các cột
  const rangeA = sheet.getRange(2, 1, lastRow - 1, 1).getValues(); // Cột A: Assign
  const rangeB = sheet.getRange(2, 2, lastRow - 1, 1).getValues(); // Cột B: PIC / Backoffice task
  const rangeC = sheet.getRange(2, 3, lastRow - 1, 1).getValues(); // Cột C: Group Assign (Content)
  const rangeD = sheet.getRange(2, 4, lastRow - 1, 1).getDisplayValues(); // Cột D: Date Assign
  const rangeO = sheet.getRange(2, 15, lastRow - 1, 1).getValues(); // Cột O: Status (New assign)

  const todayStr = Utilities.formatDate(new Date(), "Asia/Rangoon", "dd/MM/yyyy");
  const props = PropertiesService.getScriptProperties();
  const sentRowsKey = "BOD_ASSIGN_ALL_SENT_" + Utilities.formatDate(new Date(), "Asia/Rangoon", "yyyyMMdd");
  
  let sentRows = [];
  try {
    sentRows = JSON.parse(props.getProperty(sentRowsKey) || "[]");
  } catch (e) {
    sentRows = [];
  }

  let hasNewMatch = false;
  let newSentRows = [...sentRows];
  let matchedTasks = [];

  for (let i = 0; i < rangeA.length; i++) {
    const rowNum = i + 2;
    const statusVal = String(rangeO[i][0]).trim().toLowerCase();
    const dateStr = String(rangeD[i][0]).trim();

    if (statusVal === "new assign" && dateStr) {
      const datePart = dateStr.split(" ")[0].trim();
      if (datePart === todayStr) {
        matchedTasks.push({
          row: rowNum,
          assign: String(rangeA[i][0] || "").trim(),
          pic: String(rangeB[i][0] || "").trim(),
          content: String(rangeC[i][0] || "").trim()
        });

        if (sentRows.indexOf(rowNum) === -1) {
          hasNewMatch = true;
          newSentRows.push(rowNum);
        }
      }
    }
  }

  if (hasNewMatch) {
    Logger.log("[checkBodAssignME] 🔔 Phát hiện giao việc mới!");
    
    const token = props.getProperty("SEND_BOT_TOKEN") || "";
    const controlChatId = "-5251698940";
    
    if (!token) {
      Logger.log("[checkBodAssignME] ❌ Thiếu SEND_BOT_TOKEN");
      return;
    }

    const nowStr = Utilities.formatDate(new Date(), "Asia/Rangoon", "HH:mm");
    
    const lines = [
      "📋 1.1. Report — BOD Assign",
      "📅 " + todayStr + "  |  🕐 " + nowStr,
      "━━━━━━━━━━━━━━━━━━━━━━",
      "You have new Assign from BOD or Manager:",
      "━━━━━━━━━━━━━━━━━━━━━━"
    ];

    const inlineKeyboard = [];
    matchedTasks.forEach(function(task) {
      lines.push("• Row #" + task.row + " | Target: " + task.assign + " | PIC: " + task.pic + " | Content: " + task.content);
      inlineKeyboard.push([{
        text: "Yes, I received Row #" + task.row,
        callback_data: "ack_bod_assign_me_" + task.row
      }]);
    });

    lines.push("━━━━━━━━━━━━━━━━━━━━━━");
    const msgText = lines.join("\n");

    // Xóa tin cũ
    const oldMsgKey = "SD_MSGID_BOD_ASSIGN_1_1_CONTROL";
    const oldMsgIdsRaw = props.getProperty(oldMsgKey) || "[]";
    try {
      const oldMsgIds = JSON.parse(oldMsgIdsRaw);
      oldMsgIds.forEach(function(mid) {
        try {
          UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/deleteMessage", {
            method: "post",
            contentType: "application/json",
            payload: JSON.stringify({ chat_id: controlChatId, message_id: mid }),
            muteHttpExceptions: true
          });
        } catch(e) {
          Logger.log("[checkBodAssignME] ⚠️ Lỗi xóa tin cũ: " + e.message);
        }
      });
    } catch(e) {
      Logger.log("[checkBodAssignME] ⚠️ Lỗi parse tin cũ: " + e.message);
    }

    // Gửi tin mới kèm các button
    try {
      const resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/sendMessage", {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify({
          chat_id: controlChatId,
          text: msgText,
          reply_markup: {
            inline_keyboard: inlineKeyboard
          }
        }),
        muteHttpExceptions: true
      });
      const resData = JSON.parse(resp.getContentText());
      if (resData.ok) {
        const newMsgId = resData.result.message_id;
        props.setProperty(oldMsgKey, JSON.stringify([newMsgId]));
        Logger.log("[checkBodAssignME] ✅ Đã gửi tin mới và lưu ID: " + newMsgId);
        
        // Lưu lại danh sách hàng đã gửi thành công
        props.setProperty(sentRowsKey, JSON.stringify(newSentRows));
      } else {
        Logger.log("[checkBodAssignME] ❌ Gửi tin lỗi: " + resData.description);
      }
    } catch(e) {
      Logger.log("[checkBodAssignME] ❌ Lỗi gọi Telegram: " + e.message);
    }
  } else {
    Logger.log("[checkBodAssignME] 😴 Không có giao việc mới");
  }
}

/** Cài đặt trigger chạy checkBodAssignME mỗi 10 phút */
function setupBodAssignMETrigger() {
  const triggerName = "checkBodAssignME";
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(function(t) {
    if (t.getHandlerFunction() === triggerName) {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger(triggerName).timeBased().everyMinutes(1).create();
  Logger.log("✅ Đã cài trigger checkBodAssignME mỗi 1 phút");
}

// ════════════════════════════════════════════════════════════
// TELEGRAM CALLBACK QUERY HANDLER FOR REPORT 8.1 ACKNOWLEDGEMENT
// ════════════════════════════════════════════════════════════

function handleCallbackQuery(body) {
  const cb = body.callback_query;
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty("SEND_BOT_TOKEN") || "";
  
  if (!token) {
    return ContentService.createTextOutput("Missing Token");
  }

  if (cb.data === "ack_bod_assign_me") {
    const user = cb.from;
    const name = user.first_name + (user.last_name ? " " + user.last_name : "");
    const msg = cb.message;
    const chatId = msg.chat.id.toString();
    const msgId = msg.message_id;
    const oldText = msg.text || "";
    
    const ackHeader = "\n\n✅ Acknowledged by:";
    let newText = oldText;
    
    if (oldText.indexOf(name) === -1) {
      if (oldText.indexOf(ackHeader) === -1) {
        newText = oldText + ackHeader + "\n- " + name;
      } else {
        newText = oldText + "\n- " + name;
      }
      
      // Cập nhật lại nội dung tin nhắn trên Telegram để hiện danh sách đã xác nhận
      UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/editMessageText", {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify({
          chat_id: chatId,
          message_id: msgId,
          text: newText,
          reply_markup: {
            inline_keyboard: [
              [
                { text: "Yes, I received and will follow it", callback_data: "ack_bod_assign_me" }
              ]
            ]
          }
        }),
        muteHttpExceptions: true
      });
      
      answerCallback(token, cb.id, "Thank you! Acknowledgment recorded.");
    } else {
      answerCallback(token, cb.id, "You have already acknowledged this report.");
    }
  } else if (cb.data && cb.data.indexOf("ack_bod_task_") === 0) {
    const user = cb.from;
    const name = user.first_name + (user.last_name ? " " + user.last_name : "");
    const msg = cb.message;
    const chatId = msg.chat.id.toString();
    const msgId = msg.message_id;
    const oldText = msg.text || "";
    
    const ackHeader = "\n\n✅ Acknowledged by:";
    let newText = oldText;
    
    if (oldText.indexOf(name) === -1) {
      if (oldText.indexOf(ackHeader) === -1) {
        newText = oldText + ackHeader + "\n- " + name;
      } else {
        newText = oldText + "\n- " + name;
      }
      
      UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/editMessageText", {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify({
          chat_id: chatId,
          message_id: msgId,
          text: newText,
          reply_markup: {
            inline_keyboard: [
              [
                { text: "✅ Done", callback_data: cb.data }
              ]
            ]
          }
        }),
        muteHttpExceptions: true
      });
      
      answerCallback(token, cb.id, "Thank you! Task acknowledged.");
    } else {
      answerCallback(token, cb.id, "You have already acknowledged this task.");
    }
  }
  
  return ContentService.createTextOutput("OK");
}

function answerCallback(token, callbackQueryId, text) {
  UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/answerCallbackQuery", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      callback_query_id: callbackQueryId,
      text: text,
      show_alert: false
    }),
    muteHttpExceptions: true
  });
}

/** Cài đặt Webhook cho SEND_BOT để nhận sự kiện bấm nút */
function setupSendBotWebhook() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty("SEND_BOT_TOKEN") || "";
  const webAppUrl = props.getProperty("WEBAPP_URL") || "";
  
  if (!token || !webAppUrl) {
    Logger.log("❌ Thiếu SEND_BOT_TOKEN hoặc WEBAPP_URL trong Script Properties");
    return;
  }
  
  const url = "https://api.telegram.org/bot" + token + "/setWebhook";
  const payload = {
    url: webAppUrl,
    allowed_updates: JSON.stringify(["message", "callback_query"])
  };
  const resp = UrlFetchApp.fetch(url, {
    method: "post",
    payload: payload,
    muteHttpExceptions: true
  });
  Logger.log("Set Webhook Response: " + resp.getContentText());
}

/**
 * Đọc cột G (cột 7), từ dòng 2 đến dòng cuối cùng của sheet "Refuel"
 * từ Spreadsheet ID: 1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM
 */
function doGetRefuelData_(e) {
  try {
    const ssId = "1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM";
    const ss = SpreadsheetApp.openById(ssId);
    const sheet = ss.getSheetByName("Need Refuel");
    if (!sheet) {
      return json({ status: "error", message: "Sheet Need Refuel not found" });
    }
    // Đọc chính xác 4 ô Y2:Y5 (Column Y = 25) của sheet Need Refuel
    const values = sheet.getRange(2, 25, 4, 1).getValues();
    const data = [];
    for (let i = 0; i < values.length; i++) {
      const valTrim = String(values[i][0] || "").trim();
      if (valTrim) {
        data.push(valTrim);
      }
    }
    return json({ status: "ok", data: data });
  } catch (err) {
    return json({ status: "error", message: err.message });
  }
}


// ── BotState: lưu/đọc message_id để xóa tin cũ trước khi gửi mới ──────────

function getBotStateSheet_() {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let sh = ss.getSheetByName("BotState");
  if (!sh) {
    sh = ss.insertSheet("BotState");
    sh.getRange(1, 1, 1, 2).setValues([["key", "msg_id"]]);
  }
  return sh;
}

function handleGetMsgId(body) {
  try {
    const key  = String(body.key || "").trim();
    const sh   = getBotStateSheet_();
    const data = sh.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim() === key) {
        return json({ status: "ok", key: key, msg_id: String(data[i][1]) });
      }
    }
    return json({ status: "ok", key: key, msg_id: "" });
  } catch (err) {
    return json({ status: "error", message: err.message });
  }
}

function handleSetMsgId(body) {
  try {
    const key   = String(body.key    || "").trim();
    const msgId = String(body.msg_id || "").trim();
    const sh    = getBotStateSheet_();
    const data  = sh.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim() === key) {
        sh.getRange(i + 1, 2).setValue(msgId);
        return json({ status: "ok", key: key, msg_id: msgId });
      }
    }
    sh.appendRow([key, msgId]);
    return json({ status: "ok", key: key, msg_id: msgId });
  } catch (err) {
    return json({ status: "error", message: err.message });
  }
}

function fixAllMismatchedConfigs() {
  try {
    const ss = SpreadsheetApp.openById("19RBlwehMC6BLoueaTEzsJHMx4puB0CTE5i5x79-uI6c");
    const sh = ss.getSheetByName("Auto_Copy_Config");
    const lastRow = sh.getLastRow();
    const range = sh.getRange(2, 1, lastRow - 1, 10);
    const configRows = range.getValues();
    
    let count = 0;
    for (let i = 0; i < configRows.length; i++) {
      const rowNum = i + 2;
      const sourceSheet = String(configRows[i][1] || "").trim();
      const sourceColCond = String(configRows[i][2] || "").trim();
      const targetSheet = String(configRows[i][5] || "").trim();
      
      // Fix 3. see to Task
      if (sourceSheet === "3. see to Task!C:I" && sourceColCond === "3. see to Task!A:A" && targetSheet.indexOf("C4") !== -1) {
        sh.getRange(rowNum, 2).setValue("3. see to Task!C3:I");
        sh.getRange(rowNum, 3).setValue("3. see to Task!A3:A");
        count++;
      }
      // Fix 2. See alalysis
      if (sourceSheet === "2. See alalysis!C:Q" && sourceColCond === "2. See alalysis!A:A" && targetSheet.indexOf("C4") !== -1) {
        sh.getRange(rowNum, 2).setValue("2. See alalysis!C3:Q");
        sh.getRange(rowNum, 3).setValue("2. See alalysis!A3:A");
        count++;
      }
    }
    return "Successfully fixed " + count + " configuration rows in Auto_Copy_Config.";
  } catch (e) {
    return "Error: " + e.message;
  }
}



