// =====================================================================
// TNI Search Bot — GAS Backend (Standalone)
// Repo: MON6879/TNI-DONE
// Tách riêng khỏi GAS của các service khác (Refuel, SiteDown...)
// Spreadsheet: https://docs.google.com/spreadsheets/d/1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8
// =====================================================================

const SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8";
const LOG_SHEET_NAME  = "Search Log";       // Tab ghi log tìm kiếm
const DAILY_SHEET_NAME = "Daily Report";    // Tab lưu daily report
const CHAT_REG_SHEET  = "Chat Registry";    // Tab đăng ký chat ID

// ── CORS Helper ────────────────────────────────────────────────────────
function corsResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── Entry Point ────────────────────────────────────────────────────────
function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const action = body.action || "";

    if (action === "log_search")     return handleLogSearch(body);
    if (action === "register_chat")  return handleRegisterChat(body);
    if (action === "register_user")  return handleRegisterUser(body);
    if (action === "submit_daily")   return handleSubmitDaily(body);
    if (action === "save_photo")     return handleSavePhoto(body);

    return corsResponse({ status: "error", message: "Unknown action: " + action });
  } catch (err) {
    return corsResponse({ status: "error", message: err.toString() });
  }
}

function doGet(e) {
  const action = (e.parameter && e.parameter.action) || "";

  if (action === "get_fields") return handleGetFields();

  return corsResponse({ status: "ok", service: "TNI Search Bot GAS", version: "1.0" });
}

// ── Action: log_search ─────────────────────────────────────────────────
// Ghi log mỗi lần user tìm kiếm TNI
function handleLogSearch(body) {
  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet   = ss.getSheetByName(LOG_SHEET_NAME);
    if (!sheet) {
      sheet = ss.insertSheet(LOG_SHEET_NAME);
      sheet.appendRow(["Timestamp", "User Name", "User ID", "Query"]);
    }
    const now = new Date();
    sheet.appendRow([
      Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy HH:mm:ss"),
      body.user_name || "",
      body.user_id   || "",
      body.query     || ""
    ]);
    return corsResponse({ status: "ok" });
  } catch (err) {
    return corsResponse({ status: "error", message: err.toString() });
  }
}

// ── Action: get_fields ─────────────────────────────────────────────────
// Lấy danh sách fields của Daily Report (row 1 của sheet Daily Report)
function handleGetFields() {
  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = ss.getSheetByName(DAILY_SHEET_NAME);
    if (!sheet) return corsResponse({ status: "ok", fields: ["Daily report", "Site", "Note"] });

    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const fields  = headers.filter(h => h && h.toString().trim() !== "");
    return corsResponse({ status: "ok", fields: fields });
  } catch (err) {
    return corsResponse({ status: "error", message: err.toString() });
  }
}

// ── Action: submit_daily ───────────────────────────────────────────────
// Lưu Daily Report vào sheet
function handleSubmitDaily(body) {
  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet   = ss.getSheetByName(DAILY_SHEET_NAME);
    if (!sheet) {
      sheet = ss.insertSheet(DAILY_SHEET_NAME);
    }
    const now  = new Date();
    const data = body.data || {};
    const row  = [
      Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy HH:mm:ss"),
      body.user_name || "",
      body.user_id   || "",
      JSON.stringify(data)
    ];
    sheet.appendRow(row);
    return corsResponse({ status: "ok", message: "Daily report saved" });
  } catch (err) {
    return corsResponse({ status: "error", message: err.toString() });
  }
}

// ── Action: save_photo ─────────────────────────────────────────────────
function handleSavePhoto(body) {
  // Placeholder — có thể mở rộng sau
  return corsResponse({ status: "ok", message: "Photo noted (no Drive save in this GAS)" });
}

// ── Action: register_chat / register_user ──────────────────────────────
function handleRegisterChat(body) {
  return _registerEntry("chat", body);
}

function handleRegisterUser(body) {
  return _registerEntry("user", body);
}

function _registerEntry(type, body) {
  try {
    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet   = ss.getSheetByName(CHAT_REG_SHEET);
    if (!sheet) {
      sheet = ss.insertSheet(CHAT_REG_SHEET);
      sheet.appendRow(["Type", "Chat ID", "Chat Title", "Chat Type", "Reg By", "User ID", "Timestamp"]);
    }
    const chatId = body.chat_id || "";
    // Kiểm tra duplicate
    const data   = sheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][1] == chatId) return corsResponse({ status: "duplicate" });
    }
    const now = new Date();
    sheet.appendRow([
      type,
      chatId,
      body.chat_title || "",
      body.chat_type  || "",
      body.reg_by     || "",
      body.user_id    || "",
      Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy HH:mm:ss")
    ]);
    return corsResponse({ status: "ok" });
  } catch (err) {
    return corsResponse({ status: "error", message: err.toString() });
  }
}


// ── Search Bot Keepalive (thay GitHub Actions) ─────────────────────────────
/**
 * Ping tni-done.vercel.app mỗi 5 phút để giữ webhook luôn active.
 * Setup: chạy setupSearchBotKeepalive() 1 lần để cài trigger tự động.
 */
function pingSearchBot() {
  try {
    UrlFetchApp.fetch("https://tni-done.vercel.app/api/search_bot", {
      method: "get",
      muteHttpExceptions: true,
      followRedirects: true,
    });
    Logger.log("[Keepalive] ✅ Pinged tni-done.vercel.app at " + new Date().toISOString());
  } catch (e) {
    Logger.log("[Keepalive] ⚠️ Ping failed: " + e.message);
  }
}

/** Chạy 1 lần để cài trigger pingSearchBot mỗi 5 phút */
function setupSearchBotKeepalive() {
  // Xóa trigger cũ nếu có
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === "pingSearchBot")
    .forEach(t => ScriptApp.deleteTrigger(t));
  // Tạo trigger mới mỗi 5 phút
  ScriptApp.newTrigger("pingSearchBot")
    .timeBased()
    .everyMinutes(5)
    .create();
  Logger.log("✅ Trigger pingSearchBot mỗi 5 phút đã cài đặt.");
}
