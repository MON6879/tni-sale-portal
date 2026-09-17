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

function doPostCollector_(e) {
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
    // ⚠️ v684: ĐÃ XÓA routing "store_site_down" — Handler chính nằm tại doPost() trong site_down_v2.gs dòng 97.
    // handleStoreSiteDownDirect() bên dưới (dòng ~1964) là dead code nguy hiểm có logic khác (clearContent + 10s sleep).
    if (body.action === "save_note_msgids")   return handleSaveNoteMsgIds(body);
    if (body.action === "save_msgids")          return handleSaveMsgIds(body);
    if (body.action === "get_msg_id")           return handleGetMsgId(body);
    if (body.action === "set_msg_id")           return handleSetMsgId(body);
    if (body.action === "get_msg_ids_batch")    return handleGetMsgIdsBatch(body);
    if (body.action === "set_msg_ids_batch")    return handleSetMsgIdsBatch(body);
    if (body.action === "clean_blank_rows")      return handleCleanBlankRows(sheet);

    // ── Daily Report Collector ─────────────────────────────────────────────
    if (body.action === "daily_add" ||
        body.action === "daily_photo" ||
        body.action === "sync_headers" ||
        body.action === "backfill_daily_names" ||
        body.action === "store_daily_plan" ||
        body.action === "get_daily_plans" ||
        body.action === "get_daily_reports")  return doPostDaily_(e);

    // ── Cable Collector ───────────────────────────────────────────────────
    if (body.action === "cable_add" ||
        body.action === "cable_add_template" ||
        body.action === "cable_route_broken" ||
        body.action === "cable_confirm" ||
        body.action === "cable_done" ||
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
        body.action === "oil_add" ||
        body.action === "oil_confirm" ||
        body.action === "oil_add_photo" ||
        body.action === "process_photo")     return doPostMdg_(e);

    // ── Refuel Plan Collector ──────────────────────────────────────────────
    if (body.action === "collect_message" ||
        body.action === "collect_photo" ||
        body.action === "sync_image3_requests" ||
        body.action === "log_read_group_refuel" ||
        body.action === "realtime_read" ||
        body.action === "clean_test_rows") return doPostRefuelPlan_(e);

    // ── Plan Dep Collector (BI Plan Week) ───────────────────────────────────
    if (body.action === "plan_dep_add" ||
        body.action === "plan_dep_update" ||
        body.action === "plan_dep_delete")   return handlePlanDepPost_(body);

    // ── Attendance Collector (Morning Attendance & Staff Leave) ─────────────
    if (body.action === "attendance_add" ||
        body.action === "collect_attendance") return handleAttendancePost_(body);

    // ── Train Schedule Sync (auto-publish at 01:46 MMT daily) ──────────────
    if (body.action === "sync_schedule")     return handleSyncSchedule_(body);

    // ── Sale Backend (Nhap/Ban/TamUng/KhaoSat/CRM...) ─────────────────────
    if (body.action && body.action.startsWith('sale_')) return handleSalePost_(body);

    return json({ status: "error", message: "Unknown action: " + body.action });
  } catch (err) {
    return json({ status: "error", message: err.message, stack: err.stack });
  }
}

function doGetCollector_(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || "";

    // ── Ultra-fast Keepalive / Ping & Status Endpoints (<50ms) ─────────────
    if (action === "ping") {
      return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: "pong", timestamp: new Date().toISOString() }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "get_general") {
      return ContentService.createTextOutput(JSON.stringify({
        status: "ok",
        service: "TNI Main GAS Backend",
        version: "@438",
        message: "TNI Collector running",
        timestamp: new Date().toISOString()
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // ── Construction Sheet Initialization Endpoint ──
    if (action === "init_input_construction") {
      if (typeof initInputConstructionSheet === "function") {
        return ContentService.createTextOutput(JSON.stringify(initInputConstructionSheet()))
          .setMimeType(ContentService.MimeType.JSON);
      }
      return ContentService.createTextOutput(JSON.stringify({ error: "initInputConstructionSheet not found" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "setup_general_summary") {
      if (typeof setupGeneralSummarySheet === "function") {
        return ContentService.createTextOutput(JSON.stringify(setupGeneralSummarySheet()))
          .setMimeType(ContentService.MimeType.JSON);
      }
      return ContentService.createTextOutput(JSON.stringify({ error: "setupGeneralSummarySheet not found" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "debug_general_summary") {
      var ssCons = SpreadsheetApp.openById("1ViXXv5P8jSgx5heBqEP419ZkSR77C3OsflK0xpHMoi8");
      var sh = ssCons.getSheetByName("General");
      var shInput = ssCons.getSheetByName("Input Construction");
      var a2Formula = sh ? sh.getRange("A2").getFormula() : "";
      var a2Val = sh ? sh.getRange("A2:D10").getValues() : [];
      var inputRows = shInput ? shInput.getRange(1, 1, Math.max(shInput.getLastRow(), 1), 10).getValues() : [];
      return ContentService.createTextOutput(JSON.stringify({
        a2Formula: a2Formula,
        a2Val: a2Val,
        inputRows: inputRows
      })).setMimeType(ContentService.MimeType.JSON);
    }

    if (action === "inspect_spreadsheet_tabs") {
      var targetId = (e && e.parameter && e.parameter.id) || "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow";
      var targetSs = SpreadsheetApp.openById(targetId);
      var tabList = targetSs.getSheets().map(function(s) {
        return { name: s.getName(), gid: s.getSheetId(), rows: s.getLastRow(), cols: s.getLastColumn() };
      });
      return ContentService.createTextOutput(JSON.stringify({ status: "ok", tabs: tabList }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "backfill_daily_names") {
      return handleBackfillDailyReportEmployeeNames();
    }

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
    if (action === "get_msg_id")          return handleGetMsgId(e.parameter || {});
    if (action === "set_msg_id")          return handleSetMsgId(e.parameter || {});
    if (action === "get_msg_ids_batch")   return handleGetMsgIdsBatch(e.parameter || {});
    if (action === "set_msg_ids_batch")   return handleSetMsgIdsBatch(e.parameter || {});
    if (action === "get_refuel_data")     return doGetRefuelData_(e);
    if (action === "get_read_group_today") {
      const ss2 = SpreadsheetApp.openById(SHEET_ID);
      const dateParam = (e && e.parameter && e.parameter.date) || "";
      return handleGetReadGroupToday(ss2, dateParam);
    }
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
    if (action === "run_partner_auto_update") {
      const res = (typeof runPartnerAutoRefuelUpdate === "function")
        ? runPartnerAutoRefuelUpdate(true)
        : { status: "error", message: "runPartnerAutoRefuelUpdate not found" };
      return json({ status: "ok", result: res });
    }
    if (action === "update_team1_partner_auto") {
      const res = (typeof updateTeam1PartnerAuto === "function")
        ? updateTeam1PartnerAuto()
        : { status: "error", message: "updateTeam1PartnerAuto not found" };
      return json(res);
    }

    // ── Cable / MDG GET endpoints ─────────────────────────────────────────
    if (action.indexOf("cable_") === 0) return doGetCable_(e);
    if (action === "mdg_get_stats"   || action === "mdg_check_row")   return doGetMdg_(e);
    if (action === "get_fields")                                       return doGetDaily_(e);

    if (action === "trigger_16h" || action === "trigger_report" || action === "relay_all") return handleWebhookRequest_(e);
    if (action === "run_dashboard_build") {
      drStep1_BuildTables();
      return json({ status: "ok", message: "Dashboard build triggered" });
    }
    if (action === "get_team_wo_stats") return handleGetTeamWoStats_();
    if (action === "debug_sum_sheet")   return handleDebugSumSheet_();

    // ── Plan Dep (BI Plan Week) ───────────────────────────────
    if (action === "get_plan_dep")        return handleGetPlanDep_();
    if (action === "get_plan_dep_permit") return handleGetPlanDepPermit_();
    if (action === "plan_dep_archive")    return handlePlanDepArchive_();

    if (action === "diagnose_site_clear") return handleDiagnoseSiteClear_();
    if (action === "clear_site_clear_morning") return handleClearSiteClearMorning_();
    if (action === "audit_capacity") return handleAuditCapacity_();

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

  // Gắn ảnh pending vào DUY NHẤT CỘT F
  const props   = PropertiesService.getScriptProperties();
  const pKey    = "PENDING_PHOTO_" + chatId;
  const pending = JSON.parse(props.getProperty(pKey) || "[]");
  if (pending.length > 0) {
    sheet.getRange(2, 6).setValue(pending.join("\n"));
    props.deleteProperty(pKey);
  }

  const bg = seqId % 2 === 0 ? "#EBF3FB" : "#FFFFFF";
  sheet.getRange(2, 1, 1, 6).setBackground(bg); // A–F

  // Lưu ACTIVE_REF + reset PHOTO_COUNT cho user này
  // Ảnh gửi sau sẽ tự gắn vào đây, dừng sau 12 ảnh
  props.setProperty("ACTIVE_REF_"   + chatId, String(seqId));
  props.setProperty("PHOTO_COUNT_"  + chatId, "0");  // reset đếm

  return json({ status: "ok", message: "Row added", row: seqId });
}

// ============================================================
// ACTION: ADD_PHOTO — ảnh Telegram → Google Drive Subfolder → link vào DUY NHẤT CỘT F
// ============================================================

function handleAddPhoto(sheet, body) {
  const userId = String(body.user_id || "").trim();
  if (!userId) {
    return json({ status: "error", message: "Missing user_id" });
  }

  let refId  = body.ref_id ? parseInt(body.ref_id) : null;
  if (!refId) {
    const activeStr = PropertiesService.getScriptProperties().getProperty("ACTIVE_REF_" + userId);
    if (activeStr) refId = parseInt(activeStr);
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
    } else {
      return json({ status: "error", message: "Missing photo_b64 or tg_url" });
    }
  } catch(e) {
    return json({ status: "error", message: "Blob error: " + e.message });
  }

  // 2. Tạo hoặc lấy subfolder riêng cho phiếu này trong thư mục '2.2 TNIASSET TELEGRAM'
  const parentFolder = getOrCreatePhotoFolder_();
  let targetFolder = parentFolder;
  let folderLink = "https://drive.google.com/drive/folders/" + parentFolder.getId();
  
  if (refId) {
    const subfolderName = "Asset_#" + Utilities.formatString("%05d", refId);
    const existing = parentFolder.getFoldersByName(subfolderName);
    if (existing.hasNext()) {
      targetFolder = existing.next();
    } else {
      targetFolder = parentFolder.createFolder(subfolderName);
      targetFolder.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    }
    folderLink = "https://drive.google.com/drive/folders/" + targetFolder.getId();
  }

  const file = targetFolder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  const driveLink = "https://drive.google.com/file/d/" + file.getId() + "/view";

  // 3. Gắn link folder tải all ảnh vào DUY NHẤT CỘT F của dòng tương ứng
  const WIN_MS = 30 * 60 * 1000;
  const nowMs  = new Date().getTime();
  let attached = false;

  if (refId) {
    let targetRow = null;
    const lastRow = sheet.getLastRow();
    if (lastRow >= 2) {
      const colA = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (let r = 0; r < colA.length; r++) {
        if (parseInt(colA[r][0]) === refId) {
          targetRow = r + 2;
          break;
        }
      }
    }

    if (targetRow) {
      const currentVal = sheet.getRange(targetRow, 6).getValue().toString().trim();
      let updatedVal = folderLink;
      if (currentVal && currentVal.indexOf(folderLink) === -1) {
        updatedVal = folderLink + "\n" + currentVal;
      }
      sheet.getRange(targetRow, 6).setValue(updatedVal);
      attached = true;
    }
  }

  // Fallback: tìm row gần nhất của user trong 30 phút
  if (!attached) {
    const data = sheet.getDataRange().getValues();
    for (let i = data.length - 1; i >= 0; i--) {
      if (String(data[i][2] || "").trim() !== userId) continue;  // Col C = user_id
      const rowTime = parseSheetDate_(String(data[i][1] || ""));
      if (!rowTime || (nowMs - rowTime.getTime()) > WIN_MS) break; // quá cũ

      const currentVal = (data[i][5] || "").toString().trim();
      let updatedVal = folderLink;
      if (currentVal && currentVal.indexOf(folderLink) === -1) {
        updatedVal = folderLink + "\n" + currentVal;
      }
      sheet.getRange(i + 1, 6).setValue(updatedVal);
      attached = true;
      break;
    }
  }

  // 4. Nếu chưa có dòng → lưu tạm (chờ text gửi sau)
  if (!attached) {
    const props = PropertiesService.getScriptProperties();
    const key   = "PENDING_PHOTO_" + userId;
    const arr   = JSON.parse(props.getProperty(key) || "[]");
    if (arr.length < 12) {
      arr.push(folderLink);
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
// v2: UPSERT theo key date+team+name, CHỈ GHI người ĐÃ ĐỌC (status=Read)
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
  const today = Utilities.formatDate(new Date(), TZ, "dd/MM/yyyy");

  // Helper: ép Date object → "dd/MM/yyyy" string (GAS sheet trả Date object, không phải string)
  function fmtDate_(val) {
    if (!val) return "";
    if (val instanceof Date) return Utilities.formatDate(val, TZ, "dd/MM/yyyy");
    return val.toString().trim();
  }

  // Đọc toàn bộ dữ liệu hiện tại để build UPSERT map
  const lastRow = sheet.getLastRow();
  let existingData = [];
  if (lastRow > 1) {
    existingData = sheet.getRange(2, 1, lastRow - 1, 10).getValues();
  }

  // Build map: "date|team|name" → sheet row number (1-based)
  const keyToSheetRow = {};
  for (let i = 0; i < existingData.length; i++) {
    const d = fmtDate_(existingData[i][0]);          // ✅ safe: handles Date object
    const t = (existingData[i][2] || "").toString().trim();
    const n = (existingData[i][3] || "").toString().trim();
    if (d && n) keyToSheetRow[d + "|" + t + "|" + n] = i + 2; // +2: 1 header + 0-based
  }

  const insertRows = [];
  const updateOps  = [];   // { sheetRow, rowData }
  let updatedCount = 0;
  const seenKeys = {};

  records.forEach(r => {
    // CHỈ GHI người ĐÃ ĐỌC
    if ((r.status || "") !== "Read") return;

    const dateVal = r.date || today;
    const team    = r.team || "";
    const name    = r.name || "";
    const key     = dateVal + "|" + team + "|" + name;

    // Bỏ qua nếu đã xử lý trong batch này
    if (seenKeys[key]) return;
    seenKeys[key] = true;

    const rowData = [
      dateVal,
      "'" + (r.time || Utilities.formatDate(new Date(), TZ, "HH:mm")),  // ' prefix → prevent Sheets time auto-convert
      team,
      name,
      r.telegram_id || "",
      "Read",
      "'" + (r.trend_3day || "1/0/0"),
      r.count_7day != null ? r.count_7day : 0,
      r.count_month != null ? r.count_month : 0,
      r.note_msg || ""
    ];

    if (keyToSheetRow[key] !== undefined) {
      // Ghi nhớ UPDATE — CHƯA ghi ngay, tránh bị lệch sau insertRowsBefore
      updateOps.push({ sheetRow: keyToSheetRow[key], rowData: rowData });
    } else {
      insertRows.push(rowData);
      keyToSheetRow[key] = -1;
    }
  });

  // ── BƯỚC 1: INSERT trước (chèn lên đầu) ──
  // Sau INSERT, các existing rows bị đẩy xuống insertRows.length dòng
  if (insertRows.length > 0) {
    sheet.insertRowsBefore(2, insertRows.length);
    sheet.getRange(2, 1, insertRows.length, 10).setValues(insertRows);
    updatedCount = 0;
  }

  // ── BƯỚC 2: UPDATE sau — cộng offset để bù lệch do insertRowsBefore ──
  const offset = insertRows.length; // mỗi INSERT đẩy existing row xuống 1
  for (const op of updateOps) {
    const correctedRow = op.sheetRow + offset;
    sheet.getRange(correctedRow, 1, 1, 10).setValues([op.rowData]);
    updatedCount++;
  }

  Logger.log("log_read_group: inserted=" + insertRows.length + " updated=" + updatedCount);
  return json({ status: "ok", inserted: insertRows.length, updated: updatedCount });
}


// ============================================================
// ACTION: GET_READ_GROUP_TODAY — Trả danh sách người ĐÃ ĐỌC trong ngày từ sheet
// Dùng cho daily_read_report.py đọc dữ liệu tổng hợp cả ngày thay vì Telethon trực tiếp
// ============================================================
function handleGetReadGroupToday(ss, dateParam) {
  const READ_GROUP_TAB = "Read Group";
  const sheet = ss.getSheetByName(READ_GROUP_TAB);
  if (!sheet || sheet.getLastRow() < 2) {
    return json({ status: "ok", records: [], count: 0 });
  }

  const TZ = "Asia/Rangoon";
  const today = dateParam || Utilities.formatDate(new Date(), TZ, "dd/MM/yyyy");
  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, 10).getValues();

  // Helper: ép Date object → "dd/MM/yyyy" string (GAS sheet trả Date object, không phải string)
  function fmtDateG_(val) {
    if (!val) return "";
    if (val instanceof Date) return Utilities.formatDate(val, TZ, "dd/MM/yyyy");
    return val.toString().trim();
  }

  const records = [];
  for (const row of data) {
    const rowDate = fmtDateG_(row[0]);                // ✅ safe: handles Date object
    if (rowDate !== today) continue;
    if ((row[5] || "").toString().trim() !== "Read") continue;
    // row[1] = time — Sheets may auto-convert "16:36" → Date object (Sat Dec 30 1899...)
    // or stored as "'16:36" (with apostrophe prefix to prevent conversion)
    const rawTime = row[1];
    let timeStr;
    if (rawTime instanceof Date) {
      timeStr = Utilities.formatDate(rawTime, TZ, "HH:mm");
    } else {
      timeStr = (rawTime || "").toString().trim().replace(/^'/, ""); // strip leading '
    }

    records.push({
      date:        rowDate,
      time:        timeStr,
      team:        (row[2] || "").toString().trim(),
      name:        (row[3] || "").toString().trim(),
      telegram_id: (row[4] || "").toString().trim(),
      trend_3day:  (row[6] || "0/0/0").toString().replace(/^'/, ""),
      count_7day:  Number(row[7]) || 0,
      count_month: Number(row[8]) || 0,
      note_msg:    (row[9] || "").toString().trim()
    });
  }

  Logger.log("get_read_group_today: date=" + today + " found=" + records.length + " rows");
  return json({ status: "ok", records: records, date: today, count: records.length });
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

function handleGetGeneral(ss) {
  return json({
    status: "ok",
    service: "TNI Main GAS Backend",
    version: "@438",
    message: "TNI Collector running",
    timestamp: new Date().toISOString()
  });
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


// ── BotState & MsgId State Management (Dual: PropertiesService 5ms + Sheet BotState backup) ──

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
    const key = String((body && body.key) || "").trim();
    if (!key) return json({ status: "error", message: "key required", msg_id: "" });

    // 1. Fast read from PropertiesService (5ms)
    const propKey = "MSGID_" + key;
    let msgId = PropertiesService.getScriptProperties().getProperty(propKey);
    if (msgId !== null && msgId !== undefined && msgId !== "") {
      return json({ status: "ok", key: key, msg_id: String(msgId) });
    }

    // 2. Fallback to BotState sheet
    const sh   = getBotStateSheet_();
    const data = sh.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim() === key) {
        msgId = String(data[i][1]).trim();
        if (msgId) {
          PropertiesService.getScriptProperties().setProperty(propKey, msgId);
        }
        return json({ status: "ok", key: key, msg_id: msgId });
      }
    }
    return json({ status: "ok", key: key, msg_id: "" });
  } catch (err) {
    return json({ status: "error", message: err.message, msg_id: "" });
  }
}

function handleSetMsgId(body) {
  try {
    const key   = String((body && body.key) || "").trim();
    const msgId = String((body && (body.msg_id !== undefined ? body.msg_id : body.msgid)) || "").trim();
    if (!key) return json({ status: "error", message: "key required" });

    // 1. Instant save to PropertiesService (5ms)
    const propKey = "MSGID_" + key;
    PropertiesService.getScriptProperties().setProperty(propKey, msgId);

    // 2. Persistent save to BotState sheet
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

/** Batch get multiple msg_ids in 1 single HTTP call (<10ms) */
function handleGetMsgIdsBatch(body) {
  try {
    let keys = (body && body.keys) || [];
    if (typeof keys === "string") {
      try { keys = JSON.parse(keys); } catch(e) { keys = keys.split(",").map(function(k){ return k.trim(); }); }
    }
    const props = PropertiesService.getScriptProperties().getProperties();
    const result = {};

    keys.forEach(function(k) {
      const trimmed = String(k).trim();
      const val = props["MSGID_" + trimmed];
      result[trimmed] = (val !== undefined && val !== null) ? String(val) : "";
    });

    return json({ status: "ok", states: result });
  } catch(err) {
    return json({ status: "error", message: err.message, states: {} });
  }
}

/** Batch set multiple msg_ids in 1 single HTTP call (<10ms) */
function handleSetMsgIdsBatch(body) {
  try {
    let states = (body && body.states) || {};
    if (typeof states === "string") {
      try { states = JSON.parse(states); } catch(e) { states = {}; }
    }

    // Instant batch write to PropertiesService (5ms) — Primary SSOT for Serverless Bots
    const propUpdates = {};
    for (const k in states) {
      propUpdates["MSGID_" + String(k).trim()] = String(states[k]).trim();
    }
    PropertiesService.getScriptProperties().setProperties(propUpdates);

    return json({ status: "ok", count: Object.keys(states).length, states: states });
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

// ============================================================
// PLAN DEP — BI Plan Week Tab Backend
// Sheet: 1grwuZpn4gIku2V66WC59-YccEN2yz1ItIuvgeuzO8W8
// Tabs: Plan Dep (active), History Plan Dep (archive), Permit BI (auth)
// ============================================================
function handleGetPlanDep_() {
  try {
    const PDEP_SS_ID = "1grwuZpn4gIku2V66WC59-YccEN2yz1ItIuvgeuzO8W8";
    const ss = SpreadsheetApp.openById(PDEP_SS_ID);
    const planSheet = ss.getSheetByName("Plan Dep");
    let planData = [];
    if (planSheet && planSheet.getLastRow() > 2) {
      const rows = planSheet.getRange(3, 1, planSheet.getLastRow() - 2, 6).getValues();
      planData = rows.filter(r => r.some(c => String(c).trim() !== "")).map((r, i) => ({
        row: i + 3,
        col_a: String(r[0] || "").trim(),
        dateAssign: r[1] instanceof Date ? Utilities.formatDate(r[1], "Asia/Yangon", "dd/MM/yyyy") : String(r[1] || "").trim(),
        techManager: String(r[2] || "").trim(),
        detailTask: String(r[3] || "").trim(),
        progress: String(r[4] || "").trim(),
        dateComplete: r[5] instanceof Date ? Utilities.formatDate(r[5], "Asia/Yangon", "dd/MM/yyyy") : String(r[5] || "").trim()
      }));
      
      function parseDateTs_(dStr) {
        if (!dStr) return 0;
        const p = dStr.split("/");
        if (p.length === 3) {
          const d = new Date(parseInt(p[2]), parseInt(p[1]) - 1, parseInt(p[0]));
          return isNaN(d.getTime()) ? 0 : d.getTime();
        }
        return 0;
      }
      planData.sort((a, b) => {
        const da = parseDateTs_(a.dateAssign);
        const db = parseDateTs_(b.dateAssign);
        if (db !== da) return db - da;
        return (a.techManager || "").localeCompare(b.techManager || "");
      });
    }
    
    let historySheet = ss.getSheetByName("History Plan Dep");
    let historyData = [];
    if (historySheet && historySheet.getLastRow() > 2) {
      const hRows = historySheet.getRange(3, 1, historySheet.getLastRow() - 2, 6).getValues();
      historyData = hRows.filter(r => r.some(c => String(c).trim() !== "")).map((r, i) => ({
        row: i + 3,
        col_a: String(r[0] || "").trim(),
        dateAssign: r[1] instanceof Date ? Utilities.formatDate(r[1], "Asia/Yangon", "dd/MM/yyyy") : String(r[1] || "").trim(),
        techManager: String(r[2] || "").trim(),
        detailTask: String(r[3] || "").trim(),
        progress: String(r[4] || "").trim(),
        dateComplete: r[5] instanceof Date ? Utilities.formatDate(r[5], "Asia/Yangon", "dd/MM/yyyy") : String(r[5] || "").trim()
      }));
    }
    
    const now = new Date();
    const startOfYear = new Date(now.getFullYear(), 0, 1);
    const dayOfYear = Math.ceil((now - startOfYear) / 86400000);
    const weekNumber = Math.ceil(dayOfYear / 7);
    const monday = new Date(now);
    monday.setDate(now.getDate() - (now.getDay() === 0 ? 6 : now.getDay() - 1));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    const fmt = d => Utilities.formatDate(d, "Asia/Yangon", "dd/MM/yyyy");
    
    let backofficeList = [];
    if (planSheet && planSheet.getLastRow() >= 2) {
      const colJRows = planSheet.getRange(2, 10, Math.min(planSheet.getLastRow() - 1, 50), 1).getValues();
      backofficeList = colJRows.map(r => String(r[0] || "").trim()).filter(v => v !== "");
    }
    if (!backofficeList.length) {
      backofficeList = ["Admin", "Asset", "CM", "Finance", "HR", "M&E", "Manager", "PM", "Transmission"];
    }

    return json({
      status: "ok",
      version: "1.0",
      timestamp: new Date().toISOString(),
      data: planData,
      history: historyData,
      meta: {
        totalPlan: planData.length,
        totalHistory: historyData.length,
        weekNumber: weekNumber,
        weekRange: fmt(monday) + " — " + fmt(sunday),
        sheetName: "Plan Dep",
        backofficeList: backofficeList
      },
      error: null
    });
  } catch (err) {
    return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: [], meta: {}, error: { code: "FETCH_FAIL", message: err.message } });
  }
}

function handleGetPlanDepPermit_() {
  try {
    const PDEP_SS_ID = "1grwuZpn4gIku2V66WC59-YccEN2yz1ItIuvgeuzO8W8";
    const ss = SpreadsheetApp.openById(PDEP_SS_ID);
    let permitSheet = ss.getSheetByName("Permit BI");
    if (!permitSheet) {
      permitSheet = ss.insertSheet("Permit BI");
      permitSheet.getRange(1, 1).setValue("list Gmail edit A:D");
      permitSheet.getRange(2, 1).setValue("phonghdpxd@gmail.com");
      permitSheet.getRange(3, 1).setValue("yelwin086683@gmail.com");
    }
    const lastRow = permitSheet.getLastRow();
    let permits = [];
    if (lastRow > 1) {
      const rows = permitSheet.getRange(2, 1, lastRow - 1, 1).getValues();
      permits = rows.filter(r => String(r[0]).trim() !== "").map(r => ({
        email: String(r[0]).trim().toLowerCase(),
        role: "ADMIN",
        dateAdded: Utilities.formatDate(new Date(), "Asia/Yangon", "dd/MM/yyyy")
      }));
    }
    return json({ status: "ok", version: "1.0", timestamp: new Date().toISOString(), data: permits, meta: { total: permits.length }, error: null });
  } catch (err) {
    return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: [], meta: {}, error: { code: "PERMIT_FAIL", message: err.message } });
  }
}

function handlePlanDepPost_(body) {
  try {
    const PDEP_SS_ID = "1grwuZpn4gIku2V66WC59-YccEN2yz1ItIuvgeuzO8W8";
    const ss = SpreadsheetApp.openById(PDEP_SS_ID);
    const planSheet = ss.getSheetByName("Plan Dep");
    if (!planSheet) return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: null, meta: {}, error: { code: "NO_SHEET", message: "Plan Dep sheet not found" } });
    
    // 🛡️ Quyền thao tác trực tiếp trên Portal
    function checkPermit_(email, requiredRole) {
      return true;
    }
    
    if (body.action === "plan_dep_add") {
      planSheet.insertRowBefore(3);
      planSheet.getRange(3, 1, 1, 6).setValues([[
        "",
        String(body.dateAssign || "").trim(),
        String(body.techManager || "").trim(),
        String(body.detailTask || "").trim(),
        "",
        ""
      ]]);
      return json({ status: "ok", version: "1.0", timestamp: new Date().toISOString(), data: { action: "added" }, meta: {}, error: null });
    }
    
    if (body.action === "plan_dep_update") {
      const row = parseInt(body.row);
      const col = parseInt(body.col);
      const value = String(body.value || "").trim();
      if (!row || !col || col < 1 || col > 6) {
        return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: null, meta: {}, error: { code: "INVALID", message: "Invalid row or column" } });
      }
      planSheet.getRange(row, col).setValue(value);
      return json({ status: "ok", version: "1.0", timestamp: new Date().toISOString(), data: { action: "updated", row: row, col: col }, meta: {}, error: null });
    }
    
    if (body.action === "plan_dep_delete") {
      const row = parseInt(body.row);
      if (!row || row < 3) {
        return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: null, meta: {}, error: { code: "INVALID", message: "Invalid row number" } });
      }
      planSheet.deleteRow(row);
      return json({ status: "ok", version: "1.0", timestamp: new Date().toISOString(), data: { action: "deleted", row: row }, meta: {}, error: null });
    }
    
    return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: null, meta: {}, error: { code: "UNKNOWN", message: "Unknown plan_dep action" } });
  } catch (err) {
    return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: null, meta: {}, error: { code: "SERVER_ERROR", message: err.message } });
  }
}

function handlePlanDepArchive_() {
  try {
    const PDEP_SS_ID = "1grwuZpn4gIku2V66WC59-YccEN2yz1ItIuvgeuzO8W8";
    const ss = SpreadsheetApp.openById(PDEP_SS_ID);
    const planSheet = ss.getSheetByName("Plan Dep");
    if (!planSheet || planSheet.getLastRow() < 3) {
      return json({ status: "ok", version: "1.0", timestamp: new Date().toISOString(), data: { archived: 0 }, meta: {}, error: null });
    }
    let historySheet = ss.getSheetByName("History Plan Dep");
    if (!historySheet) {
      historySheet = ss.insertSheet("History Plan Dep");
      const header = planSheet.getRange(1, 1, 2, 6).getValues();
      historySheet.getRange(1, 1, 2, 6).setValues(header);
    }
    const now = new Date();
    const monday = new Date(now);
    monday.setDate(now.getDate() - (now.getDay() === 0 ? 6 : now.getDay() - 1));
    monday.setHours(0, 0, 0, 0);
    
    const lastRow = planSheet.getLastRow();
    const allData = planSheet.getRange(3, 1, lastRow - 2, 6).getValues();
    const rowsToArchive = [];
    
    for (let i = allData.length - 1; i >= 0; i--) {
      const dateComplete = allData[i][5];
      if (dateComplete && dateComplete instanceof Date && dateComplete < monday) {
        rowsToArchive.push({ index: i + 3, data: allData[i] });
      } else if (dateComplete && typeof dateComplete === "string" && dateComplete.trim() !== "") {
        const parts = dateComplete.trim().split("/");
        if (parts.length === 3) {
          const parsed = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
          if (!isNaN(parsed.getTime()) && parsed < monday) {
            rowsToArchive.push({ index: i + 3, data: allData[i] });
          }
        }
      }
    }
    
    let archivedCount = 0;
    for (const item of rowsToArchive) {
      historySheet.insertRowBefore(3);
      historySheet.getRange(3, 1, 1, 6).setValues([item.data]);
      archivedCount++;
    }
    
    rowsToArchive.sort((a, b) => b.index - a.index);
    for (const item of rowsToArchive) {
      planSheet.deleteRow(item.index);
    }
    
    return json({
      status: "ok",
      version: "1.0",
      timestamp: new Date().toISOString(),
      data: { archived: archivedCount },
      meta: { message: archivedCount + " completed tasks archived to History Plan Dep" },
      error: null
    });
  } catch (err) {
    return json({ status: "error", version: "1.0", timestamp: new Date().toISOString(), data: null, meta: {}, error: { code: "ARCHIVE_FAIL", message: err.message } });
  }
}

// ============================================================
// ATTENDANCE COLLECTOR — Morning Attendance & Staff Leave Records
// v2026-08-17 — Split Team Leader Attendance & Staff Leave into Sheet
// Sheet ID: 18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54
// Tabs: "Sum report morning attendance" (Records), "Staff attendance" (Mapping)
// ============================================================

function handleAttendancePost_(body) {
  try {
    const ATT_SS_ID = "18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54";
    const ss = SpreadsheetApp.openById(ATT_SS_ID);
    const sumSheet = ss.getSheetByName("Sum report morning attendance");
    if (!sumSheet) {
      return json({ status: "error", message: "Sheet 'Sum report morning attendance' not found" });
    }

    // 1. Build staff lookup map from 'Staff attendance' (Col A: Telegram ID, Col C: Name Telegram, Col F: Full Name, Col H: VMY Code)
    const staffMap = {};
    const staffSheet = ss.getSheetByName("Staff attendance");
    if (staffSheet && staffSheet.getLastRow() > 1) {
      const staffValues = staffSheet.getRange(2, 1, staffSheet.getLastRow() - 1, 8).getValues();
      for (let i = 0; i < staffValues.length; i++) {
        const tgId = String(staffValues[i][0] || "").trim();
        const tgName = String(staffValues[i][2] || "").trim().toLowerCase();
        const fullName = String(staffValues[i][5] || "").trim().toLowerCase();
        const vmyCode = String(staffValues[i][7] || "").trim().toLowerCase();
        if (tgId) {
          if (fullName) staffMap[fullName] = tgId;
          if (tgName) staffMap[tgName] = tgId;
          if (vmyCode) staffMap[vmyCode] = tgId;
        }
      }
    }

    const items = body.items || [];
    if (!Array.isArray(items) || items.length === 0) {
      return json({ status: "error", message: "No attendance items provided" });
    }

    // 2. Determine base REF sequence
    let nextRefSeq = 1;
    if (sumSheet.getLastRow() > 1) {
      const topRef = String(sumSheet.getRange(2, 1).getValue() || "").trim();
      const m = topRef.match(/ATT-(\d+)/i);
      if (m) {
        nextRefSeq = parseInt(m[1], 10) + 1;
      } else {
        nextRefSeq = sumSheet.getLastRow();
      }
    }

    // 3. Prepare rows to insert (Strict Top Insertion Rule: insert at Row 2)
    const rowsToInsert = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const name = String(it.name || "").trim();
      const normName = name.toLowerCase();
      let tgId = String(it.telegramId || "").trim();
      if (!tgId && staffMap[normName]) {
        tgId = staffMap[normName];
      }
      
      const refStr = "ATT-" + String(nextRefSeq + i).padStart(4, "0");
      const dateStr = String(it.date || Utilities.formatDate(new Date(), "Asia/Yangon", "dd/MM/yyyy")).trim();
      const workStr = String(it.work || "").trim();
      const takeLeaveStr = String(it.takeLeave || "").trim();
      const halfDayStr = String(it.halfDay || "").trim();
      const reasonStr = String(it.reason || "").trim();

      rowsToInsert.push([
        refStr,
        dateStr,
        name,
        workStr,
        takeLeaveStr,
        halfDayStr,
        reasonStr,
        tgId
      ]);
    }

    if (rowsToInsert.length > 0) {
      sumSheet.insertRowsBefore(2, rowsToInsert.length);
      sumSheet.getRange(2, 1, rowsToInsert.length, 8).setValues(rowsToInsert);
    }

    return json({
      status: "ok",
      version: "1.0",
      timestamp: new Date().toISOString(),
      data: {
        inserted: rowsToInsert.length,
        items: rowsToInsert
      },
      error: null
    });
  } catch (err) {
    return json({ status: "error", message: err.message, stack: err.stack });
  }
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ═══════════════════════════════════════════════════════════════
// 🚂 TRAIN SCHEDULE SYNC — Ghi lịch trình đoàn tàu vào Google Sheet
// Tab: "Time Rain 5 min" (GID 2003037043) trên bảng Site Down
// Trigger: 01:46 MMT hàng ngày từ train_5min.yml
// ═══════════════════════════════════════════════════════════════
function handleSyncSchedule_(body) {
  try {
    var SD_SHEET_ID = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow";
    var ss = SpreadsheetApp.openById(SD_SHEET_ID);
    var sheet = ss.getSheetByName("Time Rain 5 min");
    if (!sheet) return json({ ok: false, msg: "Tab 'Time Rain 5 min' not found" });

    var rows = body.rows; // Array of arrays: [[#, Time, Toa, Report, Engine, Notes], ...]
    if (!rows || !rows.length) return json({ ok: false, msg: "No rows data" });

    // Clear old data and write new
    sheet.clearContents();
    sheet.getRange(1, 1, rows.length, rows[0].length).setValues(rows);

    // Format header row
    var headerRange = sheet.getRange(1, 1, 1, rows[0].length);
    headerRange.setFontWeight("bold");
    headerRange.setBackground("#4a86c8");
    headerRange.setFontColor("#ffffff");

    // Auto-resize columns
    for (var i = 1; i <= rows[0].length; i++) {
      sheet.autoResizeColumn(i);
    }

    // Add timestamp
    var tsRow = rows.length + 2;
    sheet.getRange(tsRow, 1).setValue("Last updated: " + Utilities.formatDate(new Date(), "Asia/Yangon", "dd/MM/yyyy HH:mm:ss") + " MMT (auto-sync)");

    return json({ ok: true, msg: "Schedule synced: " + (rows.length - 1) + " entries", ts: new Date().toISOString() });
  } catch (err) {
    return json({ ok: false, msg: err.message });
  }
}

// ============================================================
// AUDIT CAPACITY — Ghế AUDITOR-9.2 (Capacity Sentinel)
// Đếm số dòng trong các tab thu thập dữ liệu để cảnh báo sớm
// GET ?action=audit_capacity
// ============================================================
function handleAuditCapacity_() {
  try {
    var results = [];
    
    // ── 1. Team All Find (SHEET_ID) ──
    var ss1 = SpreadsheetApp.openById("1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8");
    var tabs1 = [
      {name: "Data", label: "Asset Orders"},
      {name: "Search Log", label: "Search Log"},
      {name: "Asset Stats Log", label: "Asset Stats Log"},
      {name: "Read Report Log", label: "Read Report Log"},
      {name: "General", label: "General Stats"}
    ];
    for (var i = 0; i < tabs1.length; i++) {
      var sh = ss1.getSheetByName(tabs1[i].name);
      results.push({
        spreadsheet: "Team All Find",
        tab: tabs1[i].name,
        label: tabs1[i].label,
        rows: sh ? sh.getLastRow() : 0,
        cols: sh ? sh.getLastColumn() : 0
      });
    }
    
    // ── 2. Attendance ──
    try {
      var ss2 = SpreadsheetApp.openById("18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54");
      var tabs2 = [
        {name: "List Attendance", label: "Attendance Records"},
        {name: "Logs", label: "Attendance Logs"}
      ];
      for (var j = 0; j < tabs2.length; j++) {
        var sh2 = ss2.getSheetByName(tabs2[j].name);
        results.push({
          spreadsheet: "Attendance",
          tab: tabs2[j].name,
          label: tabs2[j].label,
          rows: sh2 ? sh2.getLastRow() : 0,
          cols: sh2 ? sh2.getLastColumn() : 0
        });
      }
    } catch(e2) {
      results.push({spreadsheet: "Attendance", tab: "ERROR", label: e2.message, rows: -1, cols: 0});
    }
    
    // ── 3. Construction ──
    try {
      var ss3 = SpreadsheetApp.openById("1ViXXv5P8jSgx5heBqEP419ZkSR77C3OsflK0xpHMoi8");
      var sh3 = ss3.getSheetByName("Collect Data");
      results.push({
        spreadsheet: "Construction",
        tab: "Collect Data",
        label: "Construction Reports",
        rows: sh3 ? sh3.getLastRow() : 0,
        cols: sh3 ? sh3.getLastColumn() : 0
      });
    } catch(e3) {
      results.push({spreadsheet: "Construction", tab: "ERROR", label: e3.message, rows: -1, cols: 0});
    }
    
    // ── 4. Refuel ──
    try {
      var ss4 = SpreadsheetApp.openById("1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM");
      var tabs4 = [
        {name: "Plan refuel", label: "Refuel Plans"},
        {name: "Refueled", label: "Refueled Records"}
      ];
      for (var k = 0; k < tabs4.length; k++) {
        var sh4 = ss4.getSheetByName(tabs4[k].name);
        results.push({
          spreadsheet: "Refuel",
          tab: tabs4[k].name,
          label: tabs4[k].label,
          rows: sh4 ? sh4.getLastRow() : 0,
          cols: sh4 ? sh4.getLastColumn() : 0
        });
      }
    } catch(e4) {
      results.push({spreadsheet: "Refuel", tab: "ERROR", label: e4.message, rows: -1, cols: 0});
    }
    
    // ── 5. Drive storage info (approximate from About) ──
    var driveInfo = {used: -1, total: -1};
    try {
      // DriveApp doesn't expose quota, but we note total file count as proxy
      driveInfo.note = "Drive quota requires Drive API v2 (not available via DriveApp). Use Google Admin console to check.";
    } catch(ed) {}
    
    // ── Summary ──
    var warnings = [];
    var criticals = [];
    for (var r = 0; r < results.length; r++) {
      if (results[r].rows > 40000) {
        criticals.push(results[r].spreadsheet + "/" + results[r].tab + ": " + results[r].rows + " rows");
      } else if (results[r].rows > 20000) {
        warnings.push(results[r].spreadsheet + "/" + results[r].tab + ": " + results[r].rows + " rows");
      }
    }
    
    var status = criticals.length > 0 ? "CRITICAL" : (warnings.length > 0 ? "WARNING" : "OK");
    
    return json({
      status: status,
      timestamp: Utilities.formatDate(new Date(), "Asia/Yangon", "dd/MM/yyyy HH:mm"),
      tabs: results,
      warnings: warnings,
      criticals: criticals,
      drive: driveInfo
    });
  } catch(err) {
    return json({status: "error", message: err.message});
  }
}

// ============================================================
// DIAGNOSE SITE CLEAR — Đọc formulas + values từ Site Down Clear Morning
// GET ?action=diagnose_site_clear
// ============================================================
function handleDiagnoseSiteClear_() {
  try {
    var ss = SpreadsheetApp.openById("1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow");
    var sheets = ss.getSheets();
    
    // Lấy danh sách tất cả tabs
    var sheetNames = [];
    for (var s = 0; s < sheets.length; s++) {
      sheetNames.push({name: sheets[s].getName(), gid: sheets[s].getSheetId()});
    }
    
    // Tìm tab theo GID hoặc theo tên chứa "Clear Morning"
    var sheet = null;
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === 582589665) { sheet = sheets[i]; break; }
    }
    if (!sheet) {
      for (var j = 0; j < sheets.length; j++) {
        var n = sheets[j].getName().toLowerCase();
        if (n.indexOf("clear morning") !== -1 || n.indexOf("clear") !== -1) { sheet = sheets[j]; break; }
      }
    }
    if (!sheet) return json({status: "not_found", message: "No tab matching GID 582589665 or name 'Clear Morning'", allSheets: sheetNames});

    var lastRow = sheet.getLastRow();
    var lastCol = sheet.getLastColumn();
    if (lastRow < 1 || lastCol < 1) return json({status: "ok", message: "Sheet empty", rows: 0, sheetName: sheet.getName(), gid: sheet.getSheetId(), allSheets: sheetNames});

    var values = sheet.getRange(1, 1, lastRow, lastCol).getValues();
    var formulas = sheet.getRange(1, 1, lastRow, lastCol).getFormulas();
    
    var result = [];
    var refErrors = 0;
    for (var r = 0; r < lastRow; r++) {
      var rowData = [];
      for (var c = 0; c < lastCol; c++) {
        var val = String(values[r][c]);
        var formula = formulas[r][c] || "";
        var hasRef = val.indexOf("#REF!") !== -1 || formula.indexOf("#REF!") !== -1;
        if (hasRef) refErrors++;
        rowData.push({
          cell: String.fromCharCode(65 + c) + (r + 1),
          value: val.substring(0, 200),
          formula: formula,
          hasRefError: hasRef
        });
      }
      result.push(rowData);
    }

    return json({
      status: "ok",
      sheetName: sheet.getName(),
      gid: sheet.getSheetId(),
      lastRow: lastRow,
      lastCol: lastCol,
      refErrors: refErrors,
      allSheets: sheetNames,
      data: result
    });
  } catch(err) {
    return json({status: "error", message: err.message});
  }
}

// ============================================================
// CLEAR SITE DOWN CLEAR MORNING — Xóa sạch nội dung tab GID 582589665
// Tab này KHÔNG thuộc Steel Lock Site Down v2 (đã xác nhận bởi Admin)
// GET ?action=clear_site_clear_morning
// ============================================================
function handleClearSiteClearMorning_() {
  try {
    var ss = SpreadsheetApp.openById("1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow");
    var sheets = ss.getSheets();
    var sheet = null;
    
    // Tìm theo GID
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === 582589665) { sheet = sheets[i]; break; }
    }
    // Fallback: tìm theo tên
    if (!sheet) {
      for (var j = 0; j < sheets.length; j++) {
        var n = sheets[j].getName().toLowerCase();
        if (n.indexOf("clear morning") !== -1 || (n.indexOf("site") !== -1 && n.indexOf("clear") !== -1)) { sheet = sheets[j]; break; }
      }
    }
    if (!sheet) {
      var names = [];
      for (var k = 0; k < sheets.length; k++) names.push(sheets[k].getName() + " (gid:" + sheets[k].getSheetId() + ")");
      return json({status: "error", message: "Tab not found. All tabs: " + names.join(", ")});
    }

    var lastRow = sheet.getLastRow();
    var lastCol = sheet.getLastColumn();
    if (lastRow < 2) return json({status: "ok", message: "Sheet already empty (only header)", rows: lastRow});

    // Xóa toàn bộ nội dung từ row 2 trở đi (giữ row 1 header)
    sheet.getRange(2, 1, lastRow - 1, lastCol).clearContent();

    return json({
      status: "ok",
      message: "Đã xóa sạch " + (lastRow - 1) + " dòng dữ liệu (giữ header row 1)",
      clearedRows: lastRow - 1,
      timestamp: Utilities.formatDate(new Date(), "Asia/Yangon", "dd/MM/yyyy HH:mm")
    });
  } catch(err) {
    return json({status: "error", message: err.message});
  }
}


// ============================================================
// 🧹 CLEANUP READ GROUP — Xóa dữ liệu cũ quá 45 ngày
// Trigger: ngày 16 hàng tháng lúc ~01:00-02:00 Myanmar
// ============================================================
/**
 * Dọn dẹp dữ liệu cũ quá 45 ngày trong tab "Read Group" và "Read Group Refule/Refuel".
 * Dữ liệu được chèn mới nhất ở trên (row 2), cũ nhất ở dưới cùng.
 * → Quét từ trên xuống, tìm dòng đầu tiên cũ hơn 45 ngày, xóa batch từ đó đến cuối.
 */
function cleanupReadGroupOldRows() {
  var SS_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8";
  var TABS = ["Read Group", "Read Group Refule", "Read Group Refuel"];
  var TZ = "Asia/Rangoon";
  var MAX_AGE_DAYS = 45;

  var now = new Date();
  var cutoffMs = now.getTime() - MAX_AGE_DAYS * 24 * 60 * 60 * 1000;
  var cutoffDate = new Date(cutoffMs);
  var cutoffStr = Utilities.formatDate(cutoffDate, TZ, "dd/MM/yyyy");

  Logger.log("🧹 Cleanup Read Group — Xóa dữ liệu cũ hơn " + MAX_AGE_DAYS + " ngày (trước " + cutoffStr + ")");

  var ss = SpreadsheetApp.openById(SS_ID);

  for (var t = 0; t < TABS.length; t++) {
    var tabName = TABS[t];
    var sheet = ss.getSheetByName(tabName);
    if (!sheet) continue;

    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) {
      Logger.log("  📋 " + tabName + ": Chỉ có header — bỏ qua");
      continue;
    }

    var dates = sheet.getRange(2, 1, lastRow - 1, 1).getValues();

    // Quét từ trên xuống (newest → oldest), tìm dòng đầu tiên cũ hơn cutoff
    var firstOldIdx = -1;
    for (var i = 0; i < dates.length; i++) {
      var cellVal = (dates[i][0] || "").toString().trim();
      if (!cellVal) continue;

      var parts = cellVal.match(/(\d{2})\/(\d{2})\/(\d{4})/);
      if (!parts) continue;

      var rowDate = new Date(parseInt(parts[3], 10), parseInt(parts[2], 10) - 1, parseInt(parts[1], 10));
      if (rowDate.getTime() < cutoffMs) {
        firstOldIdx = i;
        break;
      }
    }

    if (firstOldIdx >= 0) {
      var firstOldRow = firstOldIdx + 2; // +2: 0-indexed → 1-indexed + header row
      var deleteCount = lastRow - firstOldRow + 1;
      sheet.deleteRows(firstOldRow, deleteCount);
      Logger.log("  📋 " + tabName + ": Đã xóa " + deleteCount + " dòng cũ (row " + firstOldRow + "→" + lastRow + ") | Còn " + sheet.getLastRow() + " dòng");
    } else {
      Logger.log("  📋 " + tabName + ": Không có dữ liệu cũ (tất cả trong 45 ngày)");
    }
  }

  Logger.log("✅ Cleanup hoàn tất — " + Utilities.formatDate(now, TZ, "dd/MM/yyyy HH:mm"));
}

/**
 * Cài đặt trigger tự động dọn dẹp Read Group vào ngày 16 hàng tháng lúc ~01:00-02:00 Myanmar.
 * Chạy 1 lần để cài, sau đó trigger tự chạy hàng tháng.
 */
function setupReadGroupCleanupTrigger() {
  // Xóa trigger cũ nếu có
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "cleanupReadGroupOldRows") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Tạo trigger mới: ngày 16 hàng tháng, ~01:00-02:00 Myanmar
  ScriptApp.newTrigger("cleanupReadGroupOldRows")
    .timeBased()
    .onMonthDay(16)
    .atHour(1)
    .create();

  Logger.log("✅ Đã cài trigger dọn dẹp Read Group: ngày 16 hàng tháng lúc ~01:00-02:00 Myanmar");
}
