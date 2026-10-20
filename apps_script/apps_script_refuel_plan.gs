// ============================================================
// SYSTEM: TNI Refuel Plan Collector & Reporter — Updated 10/07/2026 v2
// BotState: get_msg_id / set_msg_id → xóa tin cũ trước khi gửi mới
// Spreadsheet: https://docs.google.com/spreadsheets/d/1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM/edit
// Tabs: Refueled, Plan refuel, Team request, Telegram ID, Template
// Deploy: New deployment → Web App → Execute as Me → Anyone
// ============================================================

const PLAN_GROUP_ID    = "5469544739";   // ID group 9 TNI REQUEST REFUEL (đúng)
const PLAN_BOT_TOKEN = PropertiesService.getScriptProperties().getProperty("REFUEL_BOT_TOKEN") || "";
const PLAN_CHAT_ID     = "-5469544739";

const REFUEL_SS_ID     = "1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM";
function getRefuelSpreadsheet_() {
  return SpreadsheetApp.openById(REFUEL_SS_ID);
}

// ── Web App Entry Points ───────────────────────────────────────────────────

function doGetRefuelPlan_(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || "";
    if (action === "get_refuel_data") return getRefuelData();
    if (action === "audit_refuel") return handleAuditRefuel_();
    return jsonResp({ status: "ok", message: "TNI Refuel GAS running" });
  } catch (err) {
    return jsonResp({ status: "error", message: err.message });
  }
}

function handleAuditRefuel_() {
  try {
    const ss = getRefuelSpreadsheet_();
    const lpSheet = ss.getSheetByName("Lettel Progress");
    const lettelRows = [];
    let latestSubmit = "";
    let latestApproved = "";
    if (lpSheet && lpSheet.getLastRow() >= 2) {
      const vals = lpSheet.getRange(2, 1, lpSheet.getLastRow() - 1, 3).getDisplayValues();
      for (let i = 0; i < vals.length; i++) {
        const defId = String(vals[i][0] || "").trim();
        const subD  = String(vals[i][1] || "").trim();
        const appD  = String(vals[i][2] || "").trim();
        if (defId || subD || appD) {
          lettelRows.push({ row: i + 2, def: defId, submit_date: subD, approved_date: appD });
          if (i === 0 || !latestSubmit) latestSubmit = subD || latestSubmit;
          if (i === 0 || !latestApproved) latestApproved = appD || latestApproved;
        }
      }
    }
    const rawLast = PropertiesService.getScriptProperties().getProperty("AUDIT_REFUEL_LAST_COLLECT");
    let lastCollect = null;
    try { lastCollect = rawLast ? JSON.parse(rawLast) : null; } catch (ex) {}
    return jsonResp({
      status: "ok",
      supervisor_seat: "AUDITOR-3.1",
      monitored_seat: "BOT-REFUEL-9",
      latest_submit: latestSubmit,
      latest_approved: latestApproved,
      lettel_progress: lettelRows,
      last_collect: lastCollect,
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    return jsonResp({ status: "error", message: err.message });
  }
}

function doPostRefuelPlan_(e) {
  let body;
  try {
    body = (e.postData && e.postData.contents)
      ? JSON.parse(e.postData.contents)
      : (e.parameter || {});
  } catch (err) {
    return jsonResp({ status: "error", message: "Invalid JSON: " + err.message });
  }
  const action = body.action || "";
  try {
    if (action === "collect_message")       return collectMessage(body);
    if (action === "collect_photo")         return collectPhoto(body);
    if (action === "sync_image3_requests")  return syncMissingImage3Requests();
    if (action === "update_team1_partner_auto") return updateTeam1PartnerAuto();
    if (action === "log_read_group_refuel") return logReadGroupRefuel(body);
    if (action === "realtime_read")          return handleRealtimeRead(body);
    if (action === "clean_test_rows")        return cleanTestRows(body);
    if (action === "get_msg_id")            return getMsgId(body.key || "");
    if (action === "set_msg_id")            return setMsgId(body.key || "", body.msg_id || "");
    return jsonResp({ status: "error", message: "Unknown action: " + action });
  } catch (err) {
    return jsonResp({ status: "error", message: err.message });
  }
}

function handleRealtimeRead(body) {
  const sender   = String(body.sender    || "Unknown").trim();
  const senderId = String(body.sender_id || "").trim();
  const text     = String(body.text      || "").trim();
  return syncSenderToTelegramIdAndReadSheet(sender, senderId, text);
}

function cleanTestRows(body) {
  const ss = getRefuelSpreadsheet_();
  const planSheet = ss.getSheetByName("Plan refuel");
  let deletedPlan = 0;
  if (planSheet) {
    for (let r = 2; r <= 20; r++) {
      if (r > planSheet.getLastRow()) break;
      const val = String(planSheet.getRange(r, 8).getValue()).trim();
      if (val === "12345678" || val === "987654321") {
        planSheet.deleteRow(r);
        deletedPlan++;
        r--;
      }
    }
  }
  const readSheet = ss.getSheetByName("Read Group Refuel");
  let deletedRead = 0;
  if (readSheet) {
    for (let r = 2; r <= 15; r++) {
      if (r > readSheet.getLastRow()) break;
      const val = String(readSheet.getRange(r, 5).getValue()).trim();
      if (val === "12345") {
        readSheet.deleteRow(r);
        deletedRead++;
        r--;
      }
    }
  }
  return jsonResp({ status: "ok", deletedPlan: deletedPlan, deletedRead: deletedRead });
}

// ── Read Group Refuel: Ghi nhận lịch sử đọc tin Group 9 ────────────────────

function logReadGroupRefuel(body) {
  const ss = getRefuelSpreadsheet_();
  let sh = ss.getSheetByName("Read Group Refuel");
  if (!sh) {
    sh = ss.insertSheet("Read Group Refuel");
  }
  
  if (sh.getLastRow() < 1) {
    sh.getRange(1, 1, 1, 10).setValues([[
      "Date", "Time", "Team", "Name", "Telegram ID", "Status", "Trend 3Day", "Count 7Day", "Count Month", "Refuel Note"
    ]]);
    sh.getRange("A1:J1").setFontWeight("bold").setBackground("#D9E1F2");
    sh.setFrozenRows(1);
  }

  const records = body.records || [];
  if (!records.length) {
    return jsonResp({ status: "ok", count: 0 });
  }

  const rows = records.map(r => [
    r.date || "",
    r.time || "",
    r.team || "Group 9 Refuel",
    r.name || "",
    r.telegram_id || "",
    r.status || "Unread",
    "'" + (r.trend_3day || "0/0/0"),
    r.count_7day || 0,
    r.count_month || 0,
    r.note_msg || ""
  ]);

  // Chèn vào Dòng 2 (ngay dưới Header dòng 1) để luôn hiển thị dữ liệu mới nhất trên đầu
  sh.insertRowsBefore(2, rows.length);
  sh.getRange(2, 1, rows.length, 10).setValues(rows);

  return jsonResp({ status: "ok", count: rows.length });
}

// ── Auto-Sync Sender Telegram ID & Real-Time Read Logger ───────────────────

function syncSenderToTelegramIdAndReadSheet(sender, senderId, text) {
  if (!senderId || senderId === "0" || !sender) return jsonResp({ status: "skip", message: "No sender or ID" });
  try {
    const ss = getRefuelSpreadsheet_();
    const now = new Date();
    const dateStr = Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy");
    const timeStr = Utilities.formatDate(now, "Asia/Rangoon", "HH:mm");

    // 1. Tự động đồng bộ Telegram ID vào tab 'Telegram ID' nếu chưa có ID
    const teleSheet = ss.getSheetByName("Telegram ID");
    let matchedName = sender;
    let matchedTeam = "Group 9 Refuel";

    if (teleSheet) {
      const data = teleSheet.getDataRange().getValues();
      const cleanSender = String(sender).toLowerCase().replace(/[^a-z0-9]/g, "");

      for (let r = 1; r < data.length; r++) {
        const cellId = String(data[r][0]).trim();
        const cellName = String(data[r][5] || data[r][2]).trim();
        const cleanName = cellName.toLowerCase().replace(/[^a-z0-9]/g, "");

        if (cellId === String(senderId).trim()) {
          matchedName = cellName || sender;
          matchedTeam = String(data[r][12] || "Group 9 Refuel").trim();
          break;
        } else if (!cellId && cleanName && (cleanSender.includes(cleanName) || cleanName.includes(cleanSender))) {
          // Khớp tên nhưng chưa có ID -> Gán luôn ID vào Cột A!
          teleSheet.getRange(r + 1, 1).setValue(senderId);
          matchedName = cellName;
          matchedTeam = String(data[r][12] || "Group 9 Refuel").trim();
          Logger.log("[Auto-Sync] Assigned Telegram ID " + senderId + " to " + cellName);
          break;
        }
      }
    }

    // 2. Ghi nhận THỜI GIAN THỰC vào tab 'Read Group Refuel' ngay Dòng 2
    let readSheet = ss.getSheetByName("Read Group Refuel");
    if (!readSheet) {
      readSheet = ss.insertSheet("Read Group Refuel");
    }
    if (readSheet.getLastRow() < 1) {
      readSheet.getRange(1, 1, 1, 10).setValues([[
        "Date", "Time", "Team", "Name", "Telegram ID", "Status", "Trend 3Day", "Count 7Day", "Count Month", "Refuel Note"
      ]]);
      readSheet.getRange("A1:J1").setFontWeight("bold").setBackground("#D9E1F2");
      readSheet.setFrozenRows(1);
    }

    // Tính số lần tương tác/hoạt động thực tế trong 7 ngày và 30 ngày qua
    let count7d = 1;
    let count30d = 1;
    const lastRow = readSheet.getLastRow();
    if (lastRow > 1) {
      const checkRows = Math.min(lastRow - 1, 200);
      const recentVals = readSheet.getRange(2, 1, checkRows, 5).getValues();
      const oneDay = 24 * 60 * 60 * 1000;
      for (let i = 0; i < recentVals.length; i++) {
        const rId = String(recentVals[i][4]).trim();
        if (rId === String(senderId).trim()) {
          count30d++;
          const dVal = recentVals[i][0];
          let rDate = null;
          if (dVal instanceof Date) {
            rDate = dVal;
          } else if (typeof dVal === "string") {
            const parts = dVal.split("/");
            if (parts.length === 3) rDate = new Date(parts[2], parts[1] - 1, parts[0]);
          }
          if (rDate && (now.getTime() - rDate.getTime()) <= 7 * oneDay) {
            count7d++;
          }
        }
      }
    }

    const snippet = String(text || "").substring(0, 80).replace(/\n/g, " ");

    // Chèn dòng 2 để người mở sheet luôn thấy ngay tin mới nhất ở trên cùng
    readSheet.insertRowsBefore(2, 1);
    readSheet.getRange(2, 1, 1, 10).setValues([[
      dateStr,
      timeStr,
      matchedTeam || "Group 9 Refuel",
      matchedName || sender,
      senderId,
      "Read / Active",
      "'1/1/1",
      count7d,
      count30d,
      snippet
    ]]);

    return jsonResp({ status: "ok", message: "Recorded realtime read in row 2", sender: matchedName, time: timeStr });
  } catch (err) {
    Logger.log("[Auto-Sync Error] " + err.message);
    return jsonResp({ status: "error", message: err.message });
  }
}

// ── BotState: lưu/đọc message_id trong tab BotState ───────────────────────

function getBotStateSheet() {
  const ss = getRefuelSpreadsheet_();
  let sh = ss.getSheetByName("BotState");
  if (!sh) {
    sh = ss.insertSheet("BotState");
    sh.getRange(1, 1, 1, 2).setValues([["key", "msg_id"]]);
  }
  return sh;
}

function getMsgId(key) {
  const sh = getBotStateSheet();
  const data = sh.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]) === key) {
      return jsonResp({ status: "ok", key: key, msg_id: String(data[i][1]) });
    }
  }
  return jsonResp({ status: "ok", key: key, msg_id: "" });
}

function setMsgId(key, msgId) {
  const sh = getBotStateSheet();
  const data = sh.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]) === key) {
      sh.getRange(i + 1, 2).setValue(msgId);
      return jsonResp({ status: "ok", key: key, msg_id: msgId });
    }
  }
  // Thêm dòng mới nếu chưa có key
  sh.appendRow([key, msgId]);
  return jsonResp({ status: "ok", key: key, msg_id: msgId });
}


// ── Helper: generate next sequential DEF ID ────────────────────────────────

function nextDefId(sheet) {
  // Đếm số dòng dữ liệu (trừ header row 1)
  const lastRow = sheet.getLastRow();
  const count = lastRow < 1 ? 1 : lastRow; // count bao gồm header
  return "#" + String(count).padStart(5, "0");
}

// ── Helper: insert row at TOP (row 2, after header) ────────────────────────

function insertAtTop(sheet, rowData) {
  sheet.insertRowBefore(2);
  sheet.getRange(2, 1, 1, rowData.length).setValues([rowData]);
}

// ── Lettel Progress Tracker ────────────────────────────────────────────────

/**
 * Ghi ngày vào cột B (Plan) hoặc C (Refueled) của sheet 'Lettel Progress'
 * khi sender_id khớp với cột J trong sheet đó.
 * @param {string} senderId  Telegram ID của người gửi
 * @param {string} dateStr   Ngày dạng dd/MM/yyyy
 * @param {string} category  "PLAN" → ghi col B | "REFUELED" → ghi col C
 */
function updateLettelProgress(senderId, dateStr, category) {
  try {
    const ss        = getRefuelSpreadsheet_();
    const tmplSheet = ss.getSheetByName("Template");
    const lpSheet   = ss.getSheetByName("Lettel Progress");
    if (!tmplSheet || !lpSheet) return "";

    const lastRow = tmplSheet.getLastRow();
    const writeCol = (category === "PLAN" || category === "LETTER_SUBMIT") ? 2 : 3;

    let targetRow = -1;
    if (lastRow >= 2) {
      const colJ = tmplSheet.getRange(2, 10, lastRow - 1, 1).getValues();
      for (let i = 0; i < colJ.length; i++) {
        const cellId = String(colJ[i][0]).trim();
        if (cellId && cellId === String(senderId).trim()) {
          targetRow = i + 2;
          break;
        }
      }
    }

    // Fallback: Với LETTER_SUBMIT / LETTER_APPROVED, nếu senderId chưa khai báo trong Template col J,
    // luôn cập nhật vào dòng 2 (#00003 — dòng Letter chính) để không bao giờ bị rớt công văn
    if (targetRow === -1 && (category === "LETTER_SUBMIT" || category === "LETTER_APPROVED")) {
      targetRow = 2;
    }

    if (targetRow !== -1) {
      // Tự sinh DEF vào cột A nếu chưa có
      let defId = String(lpSheet.getRange(targetRow, 1).getValue()).trim();
      if (!defId) {
        defId = nextDefId(lpSheet);
        lpSheet.getRange(targetRow, 1).setValue(defId);
        Logger.log("[LettelProgress] Auto DEF=" + defId + " → row=" + targetRow);
      }

      lpSheet.getRange(targetRow, writeCol).setValue(dateStr);
      Logger.log("[LettelProgress] row=" + targetRow + " col=" + writeCol + " = " + dateStr + " (sender=" + senderId + ")");
      return defId;  // trả về DEF để caller đưa vào response
    }
  } catch(e) {
    Logger.log("[LettelProgress] Error: " + e.message);
  }
  return "";
}


// ── Message Collection & Parsing ───────────────────────────────────────────

function extractTeamName(text) {
  if (!text) return "";
  // Match team02, Team03, Team-2, Team 2, TEAM 1, Team 1 S1, Team 2 S1, team_4, Team X, Aung Naing Refuel Team 2, etc.
  const m = text.match(/(?:team|team\s*id|đội)[\s\-_]*(\d+)(?:\s*(s\d+))?/i);
  if (m) {
    const num = parseInt(m[1], 10);
    const sub = m[2] ? " " + m[2].toUpperCase() : "";
    return "Team " + num + sub;
  }
  const m2 = text.match(/(?:team|team\s*id|đội)[\s\-_]*([a-z0-9]+)/i);
  if (m2) {
    return "Team " + m2[1].trim().toUpperCase();
  }
  return "";
}

function extractDateVal(text, defaultDate) {
  if (!text) return defaultDate;
  // Match dd/mm/yyyy, d/m/yyyy, dd.mm.yyyy, d.m.yyyy, dd-mm-yyyy, d-m-yyyy
  const m = text.match(/(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})/);
  if (m) {
    const d = String(m[1]).padStart(2, "0");
    const month = String(m[2]).padStart(2, "0");
    const y = m[3];
    return d + "/" + month + "/" + y;
  }
  return defaultDate;
}

function extractFtName(text) {
  if (!text) return "";
  const colonIdx = text.indexOf(":");
  let ftRaw = colonIdx > -1 ? text.substring(colonIdx + 1).trim() : text.trim();
  let cleanName = ftRaw;
  const dateM = cleanName.match(/(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})/);
  if (dateM) {
    cleanName = cleanName.substring(0, dateM.index).trim();
  }
  const tniM = cleanName.match(/TNI\d{4}/i);
  if (tniM) {
    cleanName = cleanName.substring(0, tniM.index).trim();
  }
  return cleanName.replace(/[\s\-,:]+$/, "").trim();
}

function collectMessage(body) {
  const groupId  = String(body.group_id  || "").trim();
  const text     = String(body.text      || "").trim();
  const sender   = String(body.sender    || "Unknown").trim();
  const senderId = String(body.sender_id || "").trim();

  if (groupId !== PLAN_GROUP_ID && groupId !== "-" + PLAN_GROUP_ID) {
    return jsonResp({ status: "skip", message: "Group ID not matched: " + groupId });
  }
  if (!text) return jsonResp({ status: "skip", message: "Empty message" });

  // ── Auto-Sync Sender Telegram ID & Read Status in Real-Time ──
  syncSenderToTelegramIdAndReadSheet(sender, senderId, text);

  const textLower = text.toLowerCase();
  const ss  = getRefuelSpreadsheet_();
  const now = new Date();
  const today   = Utilities.formatDate(now, "Asia/Rangoon", "dd/MM/yyyy");
  const timeStr = Utilities.formatDate(now, "Asia/Rangoon", "HH:mm");

  const hasSite = /\btni0*(\d{1,4})\b/i.test(text);
  const explicitCat = String(body.category || "").trim().toUpperCase();

  // ==================== 0. FT FOLLOW MONITOR ====================
  const isFtMonitor = explicitCat === "FT_MONITOR" || (
    (/^\s*(?:name\s+of\s+ft\s+staff\s+member\s+accompanying\s+to\s+supervise|follow\s*monit[eo]r)\b/i.test(text)) && hasSite
  );
  if (isFtMonitor) {
    let sheet = ss.getSheetByName("FT follow monitor");
    if (!sheet) {
      sheet = ss.insertSheet("FT follow monitor");
      sheet.appendRow(["DEF", "Date", "FT Name", "Site ID", "Refuel Qty", "Timestamp", "Sender Name", "Sender ID"]);
      sheet.getRange("A1:H1").setFontWeight("bold").setBackground("#D9E1F2");
    }

    const dateVal = extractDateVal(text, today);
    const ftName  = extractFtName(text);

    const entries = parseSitesAndQty(text, false);
    if (entries.length === 0) return jsonResp({ status: "skip", message: "No sites parsed in FT Monitor" });

    const firstDefId = "#" + String(sheet.getLastRow() + entries.length - 1).padStart(5, "0");
    entries.reverse().forEach(function(en) {
      const defId = nextDefId(sheet);
      const row = [
        defId,    // A: DEF
        dateVal,  // B: Date
        ftName,   // C: FT Name
        en.site,  // D: Site ID
        en.qty,   // E: Refuel Qty
        now,      // F: Timestamp
        sender,   // G: Sender Name
        senderId  // H: Sender ID
      ];
      insertAtTop(sheet, row);
    });

    Logger.log("[Collect] FT_MONITOR → FT follow monitor sheet, " + entries.length + " sites, first DEF=" + firstDefId);
    return jsonResp({ status: "ok", category: "FT_MONITOR", sites: entries.length, def: firstDefId, time: today + " " + timeStr });
  }

  // ==================== 1. REFUELED (DG Type) ====================
  const refueledStart = (
    /^\s*(?:dg\s*type|tni0*\d{1,4}\b.*dg\s*type)\b/i.test(text) ||
    /^\s*(?:\d+[\.\:\-\)]\s*)?date\s*[=:]/i.test(text) ||
    /^\s*(?:\d+[\.\:\-\)]\s*)?(?:mytel\s*)?(?:site|dg)\s*id\b/i.test(text) ||
    /^\s*tni0*\d{1,4}\b/i.test(text) ||
    /^\s*(?:refuel(?:ed)?|báo\s*cáo\s*đổ\s*dầu)\b/i.test(text)
  );
  const refueledMetrics = (
    textLower.includes("actual filled") || textLower.includes("csu reading") ||
    textLower.includes("running hour") || textLower.includes("level %") ||
    textLower.includes("fuel level") || textLower.includes("fuel liter")
  );
  const refueledKeywords = (
    textLower.includes("dg type") || textLower.includes("actual filled") ||
    textLower.includes("fuel filling team") || textLower.includes("power mode")
  );
  const isRefueled = explicitCat === "REFUELED" || (
    hasSite && refueledMetrics && (refueledStart || (textLower.includes("before") && textLower.includes("after"))) && refueledKeywords
  );
  if (isRefueled) {
    const sheet = ss.getSheetByName("Refueled");
    if (!sheet) return jsonResp({ status: "error", message: "Sheet 'Refueled' not found" });

    const p = parseRefueledText(text);
    const filledNum = parseFloat(p.filled) || 0;
    const priceNum  = parseFloat(p.price)  || 0;
    const totalVal  = filledNum && priceNum ? filledNum * priceNum : "";
    const defId     = nextDefId(sheet);

    const row = [
      defId,            // A: DEF (#00001)
      p.date || today,  // B: Date
      p.dgId,           // C: DG ID
      p.siteId,         // D: Site ID
      p.team,           // E: Team
      p.rh,             // F: DG Running Hour
      p.kwh,            // G: DG KWH Hour
      p.beforeLvl,      // H: Before Fuel Level %
      p.beforeCsu,      // I: Before CSU Reading(L)
      p.beforeCm,       // J: Before Fuel Liter/cm (cm reading)
      p.afterLvl,       // K: After Fuel Level %
      p.afterCsu,       // L: After CSU Reading(L)
      p.afterCm,        // M: After Fuel Liter/cm (cm reading)
      p.filled,         // N: Actual Filled Qty(L)
      p.price,          // O: Partner Price per Liter (MMK)
      totalVal,         // P: Total Amount (MMK)
      now,              // Q: Timestamp (metadata)
      sender,           // R: Sender Name (metadata)
      senderId          // S: Sender ID (metadata)
    ];

    insertAtTop(sheet, row);
    Logger.log("[Collect] REFUELED → Refueled sheet, DEF=" + defId);

    // Cập nhật Lettel Progress col C (Date Letter approved)
    updateLettelProgress(senderId, today, "REFUELED");

    return jsonResp({ status: "ok", category: "REFUELED", site: p.siteId, qty: p.filled, def: defId, time: today + " " + timeStr });
  }

  // ==================== 2. PLAN ====================
  const isPlan = explicitCat === "PLAN" || (
    (/^\s*(?:plan\s*refuel|team[\s_\-]*0*[1-4](\s*s\d+)?\s*plan(\s*refuel)?)\b/i.test(text)) && hasSite
  );
  if (isPlan) {
    const sheet = ss.getSheetByName("Plan refuel");
    if (!sheet) return jsonResp({ status: "error", message: "Sheet 'Plan refuel' not found" });

    const dateVal = extractDateVal(text, today);
    const teamVal = extractTeamName(text);

    const entries = parseSitesAndQty(text, true);
    if (entries.length === 0) return jsonResp({ status: "skip", message: "No sites parsed in Plan" });

    // Ghi từng dòng lên đầu (mỗi site 1 dòng, site đầu tiên sẽ ở row 2 sau khi xong)
    const firstDefId = "#" + String(sheet.getLastRow() + entries.length - 1).padStart(5, "0");
    entries.reverse().forEach(function(en) {
      const defId = nextDefId(sheet);
      const row = [
        defId,    // A: DEF
        dateVal,  // B: Date Plan
        teamVal,  // C: Name Team Plan
        en.site,  // D: Name Site
        en.qty,   // E: Plan will refuel
        now,      // F: Timestamp (metadata)
        sender,   // G: Sender Name (metadata)
        senderId  // H: Sender ID (metadata)
      ];
      insertAtTop(sheet, row);
    });

    Logger.log("[Collect] PLAN → Plan refuel sheet, " + entries.length + " sites, first DEF=" + firstDefId);

    // Cập nhật Lettel Progress col B (Date Letter Submit)
    updateLettelProgress(senderId, today, "PLAN");

    return jsonResp({ status: "ok", category: "PLAN", sites: entries.length, def: firstDefId, time: today + " " + timeStr });
  }

  // ==================== 3. REQUEST ====================
  const isRequest = explicitCat === "REQUEST" || (
    (/^\s*(?:request\s*refuel|team[\s_\-]*0*[1-4](\s*s\d+)?\s*request(\s*refuel)?)\b/i.test(text)) && hasSite
  );
  if (isRequest) {
    const sheet = ss.getSheetByName("Team request");
    if (!sheet) return jsonResp({ status: "error", message: "Sheet 'Team request' not found" });

    const dateVal = extractDateVal(text, today);
    const teamVal = extractTeamName(text);

    const entries = parseSitesAndQty(text, false);
    if (entries.length === 0) return jsonResp({ status: "skip", message: "No sites parsed in Request" });

    const firstDefId = "#" + String(sheet.getLastRow() + entries.length - 1).padStart(5, "0");
    entries.reverse().forEach(function(en) {
      const defId = nextDefId(sheet);
      const row = [
        defId,    // A: DEF
        dateVal,  // B: Date sent request
        timeStr,  // C: Time
        teamVal,  // D: Name Team
        en.site,  // E: Name Site
        en.qty,   // F: Order litter
        now,      // G: Timestamp (metadata)
        sender,   // H: Sender Name (metadata)
        senderId  // I: Sender ID (metadata)
      ];
      insertAtTop(sheet, row);
    });

    Logger.log("[Collect] REQUEST → Team request sheet, " + entries.length + " sites, first DEF=" + firstDefId);
    return jsonResp({ status: "ok", category: "REQUEST", sites: entries.length, def: firstDefId, time: today + " " + timeStr });
  }

  // ==================== 4. LETTER SUBMIT & 5. LETTER APPROVED ====================
  const hasSubmitLine = /(?:^|\n)\s*(?:[•\-\*]\s*)?(?:letter\s*submit(?:ted)?|submit(?:ted)?\s*letter)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})?/i.test(text);
  const hasApproveLine = /(?:^|\n)\s*(?:[•\-\*]\s*)?(?:approve(?:d)?\s*letter|letter\s*approve(?:d)?|government\s+approve(?:d)?)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})?/i.test(text);

  const isLetterSubmit = explicitCat === "LETTER_SUBMIT" || (hasSubmitLine && !hasApproveLine);
  const isLetterApproved = explicitCat === "LETTER_APPROVED" || hasApproveLine;

  if (isLetterSubmit || isLetterApproved) {
    let defId = "";
    let dateVal = extractDateVal(text, today);

    if (hasSubmitLine && hasApproveLine) {
      // Nếu người dùng gửi gộp cả 2 dòng Submit Letter và Approved Letter trong cùng 1 tin nhắn
      const mSub = text.match(/(?:letter\s*submit(?:ted)?|submit(?:ted)?\s*letter)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})/i);
      const mApp = text.match(/(?:approve(?:d)?\s*letter|letter\s*approve(?:d)?|government\s+approve(?:d)?)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})/i);
      const subDate = mSub ? extractDateVal(mSub[1], today) : dateVal;
      const appDate = mApp ? extractDateVal(mApp[1], today) : dateVal;
      defId = updateLettelProgress(senderId, subDate, "LETTER_SUBMIT");
      defId = updateLettelProgress(senderId, appDate, "LETTER_APPROVED") || defId;
      dateVal = appDate;
    } else if (isLetterApproved) {
      const mApp = text.match(/(?:approve(?:d)?\s*letter|letter\s*approve(?:d)?|government\s+approve(?:d)?)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})/i);
      if (mApp) dateVal = extractDateVal(mApp[1], today);
      defId = updateLettelProgress(senderId, dateVal, "LETTER_APPROVED");
      Logger.log("[Collect] LETTER_APPROVED → Lettel Progress col C, date=" + dateVal + " def=" + defId);
    } else {
      const mSub = text.match(/(?:letter\s*submit(?:ted)?|submit(?:ted)?\s*letter)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})/i);
      if (mSub) dateVal = extractDateVal(mSub[1], today);
      defId = updateLettelProgress(senderId, dateVal, "LETTER_SUBMIT");
      Logger.log("[Collect] LETTER_SUBMIT → Lettel Progress col B, date=" + dateVal + " def=" + defId);
    }

    const finalCat = isLetterApproved ? "LETTER_APPROVED" : "LETTER_SUBMIT";
    try {
      PropertiesService.getScriptProperties().setProperty("AUDIT_REFUEL_LAST_COLLECT", JSON.stringify({
        category: finalCat,
        sender: sender,
        sender_id: senderId,
        date: dateVal,
        def: defId,
        time: today + " " + timeStr,
        ts: new Date().toISOString()
      }));
    } catch (eProp) {}

    return jsonResp({ status: "ok", category: finalCat, date: dateVal, def: defId, time: today + " " + timeStr });
  }

  return jsonResp({ status: "skip", message: "No matching keyword" });
}

// ── Text Parsers ───────────────────────────────────────────────────────────

function parseRefueledText(text) {
  function search(pat, defaultVal) {
    const m = text.match(pat);
    return m ? m[1].trim() : (defaultVal || "");
  }

  // Parse ngày DD/MM/YYYY → JavaScript Date (tránh parse kiểu MM/DD/YYYY)
  let dateVal = "";
  const dateRaw = search(/Date\s*[=:]\s*(\d{1,2}\/\d{1,2}\/\d{4})/i);
  if (dateRaw) {
    const parts = dateRaw.split("/");
    if (parts.length === 3) {
      // Chuyển DD/MM/YYYY → Date object đúng
      dateVal = new Date(parseInt(parts[2],10), parseInt(parts[1],10)-1, parseInt(parts[0],10));
    } else {
      dateVal = dateRaw;
    }
  }

  const dgId    = search(/(?:DG\s*ID|site\s*ID)\s+([^\r\n]+)/i);
  let siteId = "";
  if (dgId) {
    const sm = dgId.match(/TNI\d{4}/i);
    if (sm) siteId = sm[0].toUpperCase();
  }
  if (!siteId) {
    const smAll = text.match(/TNI\d{4}/i);
    if (smAll) siteId = smAll[0].toUpperCase();
  }

  let teamVal = search(/Team\s*(\d+)/i);
  if (teamVal) teamVal = "Team " + parseInt(teamVal, 10);

  const rh  = search(/Running\s*Hour[s]?\s*-?\s*(\d+)/i);
  const kwh = search(/KWH?\s*Hour[s]?\s*-?\s*(\d+)/i);

  const bm = text.match(/Before([\s\S]*?)(?:After|$)/i);
  const beforePart = bm ? bm[1] : "";
  let beforeCsu = (beforePart.match(/CSU\s*Reading\s*\(L\)\s*-?\s*(\d+)/i) || [])[1] || "";
  let beforeLvl = (beforePart.match(/Level\s*%\s*-?\s*(\d+)/i) || [])[1] || "";
  let beforeCmMatch = beforePart.match(/Liter\/cm[\s\S]*?-\s*\((\d+)\)/i);
  let beforeCm  = beforeCmMatch ? beforeCmMatch[1] : ((beforePart.match(/Liter\/cm[^\r\n]*?(\d+)/i) || [])[1] || "");

  const am = text.match(/After([\s\S]*?)(?:Emergency|Note|Mention|$)/i);
  const afterPart = am ? am[1] : "";
  let afterCsu = (afterPart.match(/CSU\s*Reading\s*\(L\)\s*-?\s*(\d+)/i) || [])[1] || "";
  let afterLvl = (afterPart.match(/Level\s*%\s*-?\s*(\d+)/i) || [])[1] || "";
  let afterCmMatch = afterPart.match(/Liter\/cm[\s\S]*?-\s*\((\d+)\)/i);
  let afterCm  = afterCmMatch ? afterCmMatch[1] : ((afterPart.match(/Liter\/cm[^\r\n]*?(\d+)/i) || [])[1] || "");

  const filled = search(/Actual\s*Filled\s*Qty\s*\(L\)\s*-?\s*(\d+)/i);
  let price = search(/1Liter\s*price\s*=\s*(\d+)/i);
  if (!price) price = search(/Partner\s*price\s*[=:]\s*(\d+)/i);

  return { date: dateVal, dgId: dgId, siteId: siteId, team: teamVal,
           rh: rh, kwh: kwh,
           beforeCsu: beforeCsu, beforeLvl: beforeLvl, beforeCm: beforeCm,
           afterCsu: afterCsu, afterLvl: afterLvl, afterCm: afterCm,
           filled: filled, price: price };
}

function parseSitesAndQty(text, isPlan) {
  const results = [];
  // pat1: matches TNIxxxx followed by separator (space, colon, comma, plus, equals, hyphen) and quantity
  // Thêm = và - vào separator để parse đúng TNI0385=220L, TNI0213 - 660L
  const pat1 = /TNI(\d{4}(?:_\d+)?)(?:\([^)]*\))?[\s:,+=\-]+(\d+)\s*[Ll]?\b(?!\s*\/)/gi;
  let m;
  const matchedSites = {};

  while ((m = pat1.exec(text)) !== null) {
    const siteCode = "TNI" + m[1];
    const qty = parseInt(m[2], 10);
    results.push({ site: siteCode, qty: qty });
    matchedSites[siteCode.toUpperCase()] = true;
  }

  if (isPlan) {
    // pat2: matches any remaining TNIxxxx or TNIxxxx_01 (defaults to 440)
    const pat2 = /TNI(\d{4}(?:_\d+)?)/gi;
    while ((m = pat2.exec(text)) !== null) {
      const siteCode = "TNI" + m[1];
      if (!matchedSites[siteCode.toUpperCase()]) {
        results.push({ site: siteCode, qty: 440 });
        matchedSites[siteCode.toUpperCase()] = true;
      }
    }
  }

  // Dedup theo site
  const seen = {};
  results.forEach(function(r) {
    const s = r.site.toUpperCase();
    if (!seen[s] || r.qty > seen[s]) seen[s] = r.qty;
  });
  return Object.keys(seen).sort().map(function(s) { return { site: s, qty: seen[s] }; });
}

// ── JSON Helper ────────────────────────────────────────────────────────────

function jsonResp(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}


// ── Need Refuel: đọc cột R của sheet Refueled ──────────────────────────────

function getRefuelData() {
  const ss    = SpreadsheetApp.openById("1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM");
  const sheet = ss.getSheetByName("Need Refuel");
  if (!sheet) return jsonResp({ status: "error", message: "Sheet 'Need Refuel' not found" });

  // Đọc chính xác 4 ô Y2:Y5 (Column Y = 25) của sheet Need Refuel
  const values = sheet.getRange(2, 25, 4, 1).getValues();
  const data   = [];
  for (let i = 0; i < values.length; i++) {
    const val = String(values[i][0] || "").trim();
    if (val) data.push(val);
  }
  return jsonResp({ status: "ok", data: data });
}


// ============================================================
// PHOTO COLLECTION — Cột T, U, V, W, X, Y, Z, AA
// ============================================================
//
// Layout cột trong sheet Refueled (1-indexed):
//   T  = 20  : QI4 Code      — 3 ký tự cuối KeyPhoto ngày hôm nay
//   U  = 21  : QI4 Match     — MATCH / NEAR / NO
//   V  = 22  : Lng (Photo)   — GPS longitude từ EXIF ảnh
//   W  = 23  : Lat (Photo)   — GPS latitude từ EXIF ảnh
//   X  = 24  : Lng (Real)    — User tự điền thủ công
//   Y  = 25  : Lat (Real)    — User tự điền thủ công
//   Z  = 26  : Distance (m)  — Haversine tự tính khi user điền X/Y
//   AA = 27  : Photo Auth    — ORIGINAL / EDITED / SUSPECT

const COL_T  = 20;
const COL_U  = 21;
const COL_V  = 22;
const COL_W  = 23;
const COL_X  = 24;
const COL_Y  = 25;
const COL_Z  = 26;
const COL_AA = 27;


/**
 * collectPhoto: nhận payload từ Python bot (refuel_photo_collector.py),
 * tìm row trong sheet Refueled khớp sender_id + ngày hôm nay,
 * rồi ghi các cột T, U, V, W, AA.
 */
function collectPhoto(body) {
  const ss    = getRefuelSpreadsheet_();
  const sheet = ss.getSheetByName("Refueled");
  if (!sheet) return jsonResp({ status: "error", message: "Sheet 'Refueled' not found" });

  const senderId   = String(body.sender_id   || "").trim();
  const senderName = String(body.sender_name || "").trim();
  const dateStr    = String(body.date        || "").trim();   // dd/MM/yyyy
  const siteCode   = String(body.site_code   || "").trim().toUpperCase(); // TNIxxxx hoặc TNIxxxx_01
  const fileId     = String(body.file_id     || "").trim();
  const caption    = String(body.caption     || "").trim();
  const latPhoto   = (body.lat_photo !== undefined && body.lat_photo !== null)
                     ? Number(body.lat_photo) : null;
  const lngPhoto   = (body.lng_photo !== undefined && body.lng_photo !== null)
                     ? Number(body.lng_photo) : null;
  const auth       = String(body.auth || "SUSPECT").trim().toUpperCase();

  if (!senderId) return jsonResp({ status: "error", message: "Missing sender_id" });

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return jsonResp({ status: "skip", message: "Refueled sheet empty" });

  const numRows   = lastRow - 1;
  const dateCol   = sheet.getRange(2, 2,  numRows, 1).getValues();  // col B: Date
  const dgIdCol   = sheet.getRange(2, 3,  numRows, 1).getValues();  // col C: DG ID
  const senderCol = sheet.getRange(2, 19, numRows, 1).getValues();  // col S: sender_id

  let targetRow = -1;
  let dgId      = "";

  // 1. Ưu tiên: Tìm theo siteCode và ngày hôm nay
  if (siteCode) {
    const cleanSiteCode = siteCode.replace(/_01$/, "").replace(/_1$/, "");
    for (let i = 0; i < numRows; i++) {
      const rowDate = String(dateCol[i][0] || "").trim();
      const rowDg   = String(dgIdCol[i][0] || "").trim().toUpperCase();
      const cleanRowDg = rowDg.replace(/_01$/, "").replace(/_1$/, "");
      
      if (rowDate === dateStr && cleanRowDg === cleanSiteCode) {
        targetRow = i + 2;
        dgId      = rowDg;
        break;
      }
    }
  }

  // 2. Thử tìm theo sender_id + ngày hôm nay (nếu không khớp siteCode)
  if (targetRow === -1) {
    for (let i = 0; i < numRows; i++) {
      const rowDate   = String(dateCol[i][0]   || "").trim();
      const rowSender = String(senderCol[i][0] || "").trim();
      if (rowSender === senderId && rowDate === dateStr) {
        targetRow = i + 2;
        dgId      = String(dgIdCol[i][0] || "").trim().toUpperCase();
        break;
      }
    }
  }

  // 3. Fallback: tìm row đầu tiên có ngày hôm nay mà cột Lng (Photo) chưa điền
  if (targetRow === -1) {
    for (let i = 0; i < numRows; i++) {
      const rowDate = String(dateCol[i][0] || "").trim();
      const rowV    = sheet.getRange(i + 2, COL_V).getValue();
      if (rowDate === dateStr && !rowV) {
        targetRow = i + 2;
        dgId      = String(dgIdCol[i][0] || "").trim().toUpperCase();
        break;
      }
    }
  }

  // Nếu vẫn không tìm thấy → thêm dòng mới
  if (targetRow === -1) {
    const now     = new Date();
    const defId   = nextDefId(sheet);
    const newRow  = [
      defId, dateStr, siteCode, "", "", "", "", "", "", "",  // A–J (Cột C ghi siteCode)
      "", "", "", "", "", "", now, senderName, senderId // K–S
    ];
    insertAtTop(sheet, newRow);
    targetRow = 2;
    dgId      = siteCode;
    Logger.log("[collectPhoto] New row inserted: DEF=" + defId);
  }

  // ── Ghi các cột V, W, AA (Bỏ qua cột T, U) ──
  sheet.getRange(targetRow, COL_V).setValue(lngPhoto !== null ? lngPhoto : "");
  sheet.getRange(targetRow, COL_W).setValue(latPhoto !== null ? latPhoto : "");
  sheet.getRange(targetRow, COL_AA).setValue(auth);

  // Lưu file_id vào note của cell AA để tra cứu sau
  if (fileId) {
    const note = sheet.getRange(targetRow, COL_AA).getNote() || "";
    if (!note.includes(fileId)) {
      sheet.getRange(targetRow, COL_AA).setNote((note ? note + "\n" : "") + fileId);
    }
  }

  Logger.log("[collectPhoto] row=" + targetRow + " DG=" + dgId +
             " V=" + lngPhoto + " W=" + latPhoto + " AA=" + auth);

  return jsonResp({
    status: "ok",
    row:    targetRow,
    dg_id:  dgId,
    auth:   auth,
    lat:    latPhoto,
    lng:    lngPhoto
  });
}


/**
 * haversineMeters: tính khoảng cách Haversine giữa 2 điểm GPS, đơn vị mét.
 * @param {number} lat1  Vĩ độ điểm 1 (Photo)
 * @param {number} lon1  Kinh độ điểm 1 (Photo)
 * @param {number} lat2  Vĩ độ điểm 2 (Real)
 * @param {number} lon2  Kinh độ điểm 2 (Real)
 * @returns {number} Khoảng cách tính bằng mét
 */
function haversineMeters(lat1, lon1, lat2, lon2) {
  const R  = 6371000;  // Bán kính Trái Đất (mét)
  const f1 = lat1 * Math.PI / 180;
  const f2 = lat2 * Math.PI / 180;
  const df = (lat2 - lat1) * Math.PI / 180;
  const dl = (lon2 - lon1) * Math.PI / 180;
  const a  = Math.sin(df / 2) * Math.sin(df / 2)
             + Math.cos(f1) * Math.cos(f2)
             * Math.sin(dl / 2) * Math.sin(dl / 2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}


/**
 * onEditRefuelPhoto: trigger tự động tính cột Z (khoảng cách mét)
 * khi user điền cột X (Lng Real) hoặc Y (Lat Real).
 * Cần cài bằng setupOnEditTrigger().
 */
function onEditRefuelPhoto(e) {
  if (!e) return;
  const sheet = e.source.getActiveSheet();
  if (!sheet || sheet.getName() !== "Refueled") return;

  const col = e.range.getColumn();
  const row = e.range.getRow();

  if (row < 2) return;
  if (col !== COL_X && col !== COL_Y) return;

  const lngPhoto = parseFloat(sheet.getRange(row, COL_V).getValue());
  const latPhoto = parseFloat(sheet.getRange(row, COL_W).getValue());
  const lngReal  = parseFloat(sheet.getRange(row, COL_X).getValue());
  const latReal  = parseFloat(sheet.getRange(row, COL_Y).getValue());

  // Cần cả 4 giá trị hợp lệ mới tính
  if (isNaN(lngPhoto) || isNaN(latPhoto) || isNaN(lngReal) || isNaN(latReal)) {
    sheet.getRange(row, COL_Z).setValue("");
    return;
  }

  const dist = haversineMeters(latPhoto, lngPhoto, latReal, lngReal);
  sheet.getRange(row, COL_Z).setValue(Math.round(dist));  // làm tròn tới mét
  Logger.log("[onEditRefuelPhoto] row=" + row + " dist=" + Math.round(dist) + "m");
}


/**
 * setupRefuelPhotoHeaders: thiết lập tiêu đề cột T → AA trong sheet Refueled.
 * Chạy 1 lần từ Apps Script Editor để khởi tạo.
 */
function setupRefuelPhotoHeaders() {
  const ss    = getRefuelSpreadsheet_();
  const sheet = ss.getSheetByName("Refueled");
  if (!sheet) { Logger.log("❌ Sheet 'Refueled' not found"); return; }

  const headers = [[
    "QI4 Code",    // T
    "QI4 Match",   // U
    "Lng (Photo)", // V
    "Lat (Photo)", // W
    "Lng (Real)",  // X  ← user điền
    "Lat (Real)",  // Y  ← user điền
    "Distance (m)",// Z  ← auto Haversine
    "Photo Auth"   // AA
  ]];
  sheet.getRange(1, COL_T, 1, 8).setValues(headers);

  // Header màu xanh
  const hdr = sheet.getRange(1, COL_T, 1, 8);
  hdr.setBackground("#1a73e8");
  hdr.setFontColor("#ffffff");
  hdr.setFontWeight("bold");

  // Cột X, Y (user fill) → nền vàng nhạt
  const maxR = sheet.getMaxRows();
  sheet.getRange(2, COL_X, maxR - 1, 2).setBackground("#fff9c4");

  // Cột Z, AA (auto) → nền xanh lá nhạt
  sheet.getRange(2, COL_Z, maxR - 1, 2).setBackground("#e8f5e9");

  Logger.log("✅ Headers T→AA đã thiết lập trong sheet Refueled.");
}


/**
 * setupOnEditTrigger: cài trigger onEdit cho onEditRefuelPhoto.
 * Chạy 1 lần từ Apps Script Editor.
 */
function setupOnEditTrigger() {
  const existing = ScriptApp.getProjectTriggers();
  for (let i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === "onEditRefuelPhoto") {
      ScriptApp.deleteTrigger(existing[i]);
    }
  }
  ScriptApp.newTrigger("onEditRefuelPhoto")
    .forSpreadsheet(getRefuelSpreadsheet_())
    .onEdit()
    .create();
  Logger.log("✅ onEditRefuelPhoto trigger installed.");
}

// ============================================================
// HỆ THỐNG CẬP NHẬT TỰ ĐỘNG: TAB "Request Partner Auto"
// Ghế Quản Trị: GAS-OPS-1 (QLTC_GAS)
// Ghế Giám Sát: AUDITOR-9.1 (Admin DM: 6859790680)
// Lịch chạy: 01:16 sáng & 13:16 chiều (MMT) theo nhịp toa tàu 5 phút
// ============================================================

const PARTNER_AUTO_TAB_NAME = "Request Partner Auto";
const PARTNER_AUTO_ADMIN_CHAT_ID = "6859790680";

/**
 * Gửi cảnh báo lỗi và mất đồng bộ về DM Admin (Ghế AUDITOR-9.1)
 */
function notifyAuditorPartnerAuto_(alertText) {
  try {
    const token = typeof PLAN_BOT_TOKEN !== "undefined" ? PLAN_BOT_TOKEN : "";
    const payload = {
      chat_id: PARTNER_AUTO_ADMIN_CHAT_ID,
      text: "🚨 [AUDITOR-9.1] CẢNH BÁO REFUEL PARTNER AUTO:\n" + alertText
    };
    UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/sendMessage", {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log("notifyAuditorPartnerAuto_ error: " + e.message);
  }
}

/**
 * Hàm cập nhật dữ liệu bảng Request Partner Auto
 * - Việc 1: Nếu Y4:Y300 <> "-" thì xóa hàng tương ứng theo cột V4:W300 (clearContent)
 * - Việc 2: Nếu cột V có bôi màu cam (#ff9900) thì:
 *           + Dán 123 ngày hôm nay vào V tương ứng
 *           + Xóa bôi màu cam (mất bôi cam)
 *           + Copy tương ứng hàng của cột Q dán vào W (paste 123)
 * - Ghế Giám Sát AUDITOR-9.1 kiểm tra tính toàn vẹn và báo lỗi về Admin DM
 *
 * @param {boolean} forceSend Bỏ qua kiểm tra giờ/cờ khi chạy thủ công
 */
function runPartnerAutoRefuelUpdate(forceSend) {
  const isForce = (forceSend === true);
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    Logger.log("⚠️ Không thể lấy lock runPartnerAutoRefuelUpdate. Bỏ qua lượt này.");
    return { status: "busy", message: "Script lock busy" };
  }

  let sheet = null;
  try {
    const ss = getRefuelSpreadsheet_();
    if (!ss) {
      throw new Error("Không thể mở Spreadsheet Refuel: " + REFUEL_SS_ID);
    }
    sheet = ss.getSheetByName(PARTNER_AUTO_TAB_NAME);
    if (!sheet) {
      throw new Error("Không tìm thấy tab '" + PARTNER_AUTO_TAB_NAME + "' trong Spreadsheet Refuel");
    }

    // Phạm vi xử lý: Row 7 đến Row 325 (dữ liệu thực tế từ dòng 7, tránh đụng header dòng 4-6)
    const START_ROW = 7;
    const END_ROW = 325;
    const NUM_ROWS = END_ROW - START_ROW + 1; // 319

    // Đọc từ Cột Q (17) đến Cột Y (25) — 9 cột: Q, R, S, T, U, V, W, X, Y
    // Cột Y (25) là công thức tự tính — CHỈ ĐỌC giá trị Y để xét điều kiện xóa V:W, TUYỆT ĐỐI KHÔNG GHI/XÓA CỘT Y!
    // Index tương ứng trong mảng 0-indexed:
    // Q = 0 (Col 17)
    // S = 2 (Col 19)
    // V = 5 (Col 22)
    // W = 6 (Col 23)
    // X = 7 (Col 24)
    // Y = 8 (Col 25)
    const COL_Q_IDX = 0;
    const COL_S_IDX = 2;
    const COL_V_IDX = 5;
    const COL_W_IDX = 6;
    const COL_X_IDX = 7;
    const COL_Y_IDX = 8;

    const EXCLUDED_X_LIST = ["DG destroy", "DG Note use", "DG Error", "Not have DG", "Site destroy"];

    const rangeData = sheet.getRange(START_ROW, 17, NUM_ROWS, 9); // Q:Y (chỉ đọc)
    const values = rangeData.getValues();

    // Đọc màu nền của Cột V (Col 22)
    const rangeColV = sheet.getRange(START_ROW, 22, NUM_ROWS, 1);
    const backgroundsV = rangeColV.getBackgrounds();

    let clearedCount = 0;
    let activatedCount = 0;
    const today = new Date();

    // ── TÁC VỤ 1 (XÓA V:W): Nếu Y7:Y325 <> "-" thì xóa hàng tương ứng theo cột V:W (clearContent) ──
    // Tuyệt đối KHÔNG đụng vào cột Y (vì Y đã có công thức =IF(V="","-",...) tự trả về "-" khi V trống hoặc nhận ngày mới)
    for (let i = 0; i < NUM_ROWS; i++) {
      const sheetRow = START_ROW + i;
      const yVal = String(values[i][COL_Y_IDX] || "").trim();
      const vVal = values[i][COL_V_IDX];
      const wVal = values[i][COL_W_IDX];

      if (yVal !== "" && yVal !== "-") {
        if ((vVal !== "" && vVal !== null) || (wVal !== "" && wVal !== null)) {
          sheet.getRange(sheetRow, 22, 1, 2).clearContent();
          clearedCount++;
          values[i][COL_V_IDX] = "";
          values[i][COL_W_IDX] = "";
        }
      }
    }

    // ── TÁC VỤ 2 (CẬP NHẬT V:W): Nếu cột V có bôi màu cam (#ff9900 thủ công hoặc do Conditional Formatting) thì:
    //   - Dán 123 ngày hôm nay vào V
    //   - Xóa bôi màu cam (mất bôi cam)
    //   - Copy tương ứng hàng của cột Q dán vào W
    for (let i = 0; i < NUM_ROWS; i++) {
      const sheetRow = START_ROW + i;
      const bg = String(backgroundsV[i][0] || "").toLowerCase().trim();
      const sVal = values[i][COL_S_IDX];
      const vVal = values[i][COL_V_IDX];
      const xVal = String(values[i][COL_X_IDX] || "").trim();

      // Kiểm tra màu cam Cột V:
      // 1) Màu cam thủ công (#ff9900, #f6b26b, #e69138, orange)
      // 2) Màu cam từ Conditional Formatting: S=1, V đang rỗng (bao gồm dòng vừa xóa V cũ ở Tác vụ 1), và X không thuộc nhóm DG lỗi/hủy
      const isManualOrange = (bg === "#ff9900" || bg === "#f6b26b" || bg === "#e69138" || bg === "orange");
      const isConditionalOrange = (String(sVal) === "1" && (vVal === "" || vVal === null) && EXCLUDED_X_LIST.indexOf(xVal) === -1);

      if (isManualOrange || isConditionalOrange) {
        const qVal = values[i][COL_Q_IDX];

        // 1. Dán ngày hôm nay vào V (đối tượng Date để Google Sheets tự format dd/mm/yyyy)
        sheet.getRange(sheetRow, 22).setValue(today);

        // 2. Xóa bôi cam thủ công của ô V nếu có
        sheet.getRange(sheetRow, 22).setBackground(null);

        // 3. Copy giá trị của Q dán vào W (dán 123 - paste value)
        sheet.getRange(sheetRow, 23).setValue(qVal);

        activatedCount++;
        values[i][COL_V_IDX] = today;
        values[i][COL_W_IDX] = qVal;
        backgroundsV[i][0] = null;
      }
    }

    SpreadsheetApp.flush();

    // ── GHẾ GIÁM SÁT AUDITOR-9.1: Kiểm tra tính toàn vẹn và độ đồng bộ sau cập nhật ──
    const verifyBackgrounds = sheet.getRange(START_ROW, 22, NUM_ROWS, 1).getBackgrounds();
    const verifyValues = sheet.getRange(START_ROW, 17, NUM_ROWS, 8).getValues(); // Q:X
    let remainingOrange = 0;
    for (let i = 0; i < NUM_ROWS; i++) {
      const bg = String(verifyBackgrounds[i][0] || "").toLowerCase().trim();
      const sVal = verifyValues[i][COL_S_IDX];
      const vVal = verifyValues[i][COL_V_IDX];
      const xVal = String(verifyValues[i][COL_X_IDX] || "").trim();

      const isManual = (bg === "#ff9900" || bg === "#f6b26b" || bg === "#e69138" || bg === "orange");
      const isCF = (String(sVal) === "1" && (vVal === "" || vVal === null) && EXCLUDED_X_LIST.indexOf(xVal) === -1);
      if (isManual || isCF) {
        remainingOrange++;
      }
    }

    if (remainingOrange > 0) {
      const alertMsg = "⚠️ Phát hiện mất đồng bộ: Vẫn còn " + remainingOrange + " ô màu cam chưa được xử lý tại Cột V tab '" + PARTNER_AUTO_TAB_NAME + "'!";
      notifyAuditorPartnerAuto_(alertMsg);
      Logger.log(alertMsg);
    } else {
      Logger.log("✅ [AUDITOR-9.1] Kiểm tra hoàn tất: 0 ô màu cam còn sót lại.");
    }

    Logger.log("✅ Cập nhật thành công 'Request Partner Auto': Đã xóa " + clearedCount + " dòng V:W (Y<>'-'), kích hoạt " + activatedCount + " dòng V:W mới (cột Y giữ nguyên công thức).");
    return {
      status: "ok",
      cleared: clearedCount,
      activated: activatedCount,
      remainingOrange: remainingOrange
    };

  } catch (err) {
    const errorMsg = "❌ Lỗi thực thi runPartnerAutoRefuelUpdate: " + err.message + "\nStack: " + (err.stack || "");
    Logger.log(errorMsg);
    notifyAuditorPartnerAuto_(errorMsg);
    return { status: "error", message: err.message };
  } finally {
    lock.releaseLock();
  }
}

/**
 * Kiểm tra mốc giờ theo nhịp toa tàu (01:16 & 13:16 MMT)
 * Gọi tự động mỗi 5 phút từ dispatchTrain5Min()
 */
function checkPartnerAutoSchedule_() {
  try {
    const now = new Date();
    // Tính giờ Myanmar (UTC+6:30)
    const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
    const mmtTotalMin = (utcMin + 390) % 1440;
    const h = Math.floor(mmtTotalMin / 60);
    const m = mmtTotalMin % 60;

    // Cửa sổ nhịp :16 (dung sai :13 đến :19 MMT theo chuẩn đoàn tàu 5 phút)
    const isSlot0116 = (h === 1 && m >= 13 && m <= 19);
    const isSlot1316 = (h === 13 && m >= 13 && m <= 19);

    if (!isSlot0116 && !isSlot1316) {
      return; // Không phải khung giờ
    }

    const slotName = isSlot0116 ? "0116" : "1316";
    const todayStr = Utilities.formatDate(now, "Asia/Yangon", "yyyyMMdd");
    const dedupKey = "PARTNER_AUTO_DONE_" + todayStr + "_" + slotName;

    const props = PropertiesService.getScriptProperties();
    if (props.getProperty(dedupKey) === "done") {
      return; // Đã chạy cho slot này hôm nay
    }

    Logger.log("⏰ Nhịp " + h + ":" + (m < 10 ? "0" + m : m) + " MMT (Slot " + slotName + ") → Bắt đầu cập nhật Request Partner Auto...");
    const result = runPartnerAutoRefuelUpdate(false);

    if (result && result.status === "ok") {
      props.setProperty(dedupKey, "done");
      Logger.log("✅ Đã ghi nhận cờ hoàn tất: " + dedupKey);
    }
  } catch (e) {
    Logger.log("checkPartnerAutoSchedule_ error: " + e.message);
    notifyAuditorPartnerAuto_("Lỗi tại checkPartnerAutoSchedule_: " + e.message);
  }
}

/**
 * Hàm kích hoạt chạy thử nghiệm thủ công bất kỳ lúc nào từ Apps Script Editor
 */
function runPartnerAutoRefuelUpdateManual() {
  Logger.log("🧪 Đang chạy thử nghiệm thủ công runPartnerAutoRefuelUpdate (bỏ qua cổng giờ)...");
  return runPartnerAutoRefuelUpdate(true);
}

/**
 * Đồng bộ các trạm còn thiếu từ Hình 3 (Report 1 Daily Report) vào sheet 'Team request'.
 * Tự động kiểm tra trùng theo mã trạm / máy phát (idempotent), chỉ chèn các trạm chưa có.
 * Chèn vào dòng 2 (ngay dưới header row 1) theo đúng quy tắc hệ thống.
 */
function syncMissingImage3Requests() {
  const ss = getRefuelSpreadsheet_();
  const sheet = ss.getSheetByName("Team request");
  if (!sheet) return jsonResp({ status: "error", message: "Sheet 'Team request' not found" });

  // Danh sách 24 trạm từ Hình 3
  const img3List = [
    // Team 1
    { team: "Team 1", date: "01/08/2026", d: 1, m: 8, y: 2026, site: "TNI0018_1", qty: 440 },
    { team: "Team 1", date: "01/08/2026", d: 1, m: 8, y: 2026, site: "TNI0216_1", qty: 440 },
    { team: "Team 1", date: "01/08/2026", d: 1, m: 8, y: 2026, site: "TNI0321_1", qty: 220 },
    { team: "Team 1", date: "03/08/2026", d: 3, m: 8, y: 2026, site: "TNI0207_1", qty: 440 },
    { team: "Team 1", date: "09/08/2026", d: 9, m: 8, y: 2026, site: "TNI0334_1", qty: 440 },
    { team: "Team 1", date: "09/08/2026", d: 9, m: 8, y: 2026, site: "TNI0313_1", qty: 440 },
    { team: "Team 1", date: "10/08/2026", d: 10, m: 8, y: 2026, site: "TNI0314_1", qty: 440 },
    { team: "Team 1", date: "13/08/2026", d: 13, m: 8, y: 2026, site: "TNI0038_1", qty: 440 },
    { team: "Team 1", date: "14/08/2026", d: 14, m: 8, y: 2026, site: "TNI0046_1", qty: 440 },
    { team: "Team 1", date: "16/08/2026", d: 16, m: 8, y: 2026, site: "TNI0357_1", qty: 440 },
    { team: "Team 1", date: "29/08/2026", d: 29, m: 8, y: 2026, site: "TNI0394_1", qty: 660 },
    { team: "Team 1", date: "29/08/2026", d: 29, m: 8, y: 2026, site: "TNI0198_1", qty: 440 },
    // Team 2
    { team: "Team 2", date: "01/08/2026", d: 1, m: 8, y: 2026, site: "TNI0002_1", qty: 440 },
    { team: "Team 2", date: "03/08/2026", d: 3, m: 8, y: 2026, site: "TNI0088_1", qty: 440 },
    { team: "Team 2", date: "03/08/2026", d: 3, m: 8, y: 2026, site: "TNI0199_1", qty: 440 },
    { team: "Team 2", date: "14/08/2026", d: 14, m: 8, y: 2026, site: "TNI0248_1", qty: 440 },
    { team: "Team 2", date: "14/08/2026", d: 14, m: 8, y: 2026, site: "TNI0336_1", qty: 660 },
    // Team 3
    { team: "Team 3", date: "03/08/2026", d: 3, m: 8, y: 2026, site: "TNI0010_1", qty: 440 },
    // Team 4
    { team: "Team 4", date: "04/08/2026", d: 4, m: 8, y: 2026, site: "TNI0012_1", qty: 440 },
    { team: "Team 4", date: "04/08/2026", d: 4, m: 8, y: 2026, site: "TNI0120_1", qty: 440 },
    { team: "Team 4", date: "09/08/2026", d: 9, m: 8, y: 2026, site: "TNI0015_1", qty: 660 },
    { team: "Team 4", date: "09/08/2026", d: 9, m: 8, y: 2026, site: "TNI0015_2", qty: 440 },
    { team: "Team 4", date: "09/08/2026", d: 9, m: 8, y: 2026, site: "TNI0012_2", qty: 440 },
    { team: "Team 4", date: "14/08/2026", d: 14, m: 8, y: 2026, site: "TNI0392_1", qty: 440 }
  ];

  const lastRow = sheet.getLastRow();
  const existingSites = {};
  if (lastRow >= 2) {
    const siteVals = sheet.getRange(2, 5, lastRow - 1, 1).getValues();
    for (let i = 0; i < siteVals.length; i++) {
      const s = String(siteVals[i][0] || "").trim().toUpperCase();
      if (s) existingSites[s] = true;
    }
  }

  const toInsert = [];
  for (let i = 0; i < img3List.length; i++) {
    const it = img3List[i];
    if (!existingSites[it.site.toUpperCase()]) {
      toInsert.push(it);
    }
  }

  if (toInsert.length === 0) {
    return jsonResp({ status: "ok", message: "All Image 3 sites already present in Team request", inserted: 0 });
  }

  const now = new Date();
  const timeStr = Utilities.formatDate(now, "Asia/Yangon", "HH:mm");
  const insertedSites = [];

  // Chèn từng dòng lên đầu bảng (row 2), đảo chiều để giữ đúng thứ tự
  toInsert.reverse().forEach(function(it) {
    const defId = nextDefId(sheet);
    const dateObj = new Date(it.y, it.m - 1, it.d);
    const row = [
      defId,               // A: DEF
      dateObj,             // B: Date sent request
      timeStr,             // C: Time
      it.team,             // D: Name Team
      it.site,             // E: Name Site
      it.qty,              // F: Order litter
      now,                 // G: Timestamp
      "TNI",               // H: Sender Name
      "6859790680"         // I: Sender ID
    ];
    insertAtTop(sheet, row);
    insertedSites.push(it.site);
  });

  Logger.log("[Sync] Inserted " + toInsert.length + " missing Image 3 requests into Team request sheet.");
  return jsonResp({ status: "ok", message: "Inserted " + toInsert.length + " sites", inserted: toInsert.length, sites: insertedSites });
}

/**
 * Cập nhật Cột AB trong tab 'Request Partner Auto':
 * - Gán 'T1' cho đúng 16 trạm Team 1
 * - Gán 'T1 S1' cho đúng 10 trạm Team 1 S1
 * - Bảo toàn nguyên vẹn T2, T2 S1, T3, T3 S1, T4
 */
function updateTeam1PartnerAuto() {
  const ss = getRefuelSpreadsheet_();
  if (!ss) throw new Error("Không thể mở Spreadsheet Refuel: " + REFUEL_SS_ID);
  const sheet = ss.getSheetByName(PARTNER_AUTO_TAB_NAME);
  if (!sheet) throw new Error("Không tìm thấy tab '" + PARTNER_AUTO_TAB_NAME + "'");

  const t1Sites = [
    "TNI0035", "TNI0041", "TNI0051", "TNI0013", "TNI0038", "TNI0052",
    "TNI0198", "TNI0207", "TNI0210", "TNI0231", "TNI0272",
    "TNI0314", "TNI0321", "TNI0322", "TNI0328", "TNI0394"
  ];

  const t1S1Sites = [
    "TNI0148_01", "TNI0284", "TNI0351", "TNI0213", "TNI0220",
    "TNI0129", "TNI0185", "TNI0006", "TNI0153", "TNI0206"
  ];

  const startRow = 4;
  const lastRow = Math.max(sheet.getLastRow(), 300);
  const numRows = lastRow - startRow + 1;

  // Cột B: DG ID (col 2), Cột C: Site code (col 3), Cột AB: Team (col 28)
  const dgVals = sheet.getRange(startRow, 2, numRows, 2).getValues();
  const abRange = sheet.getRange(startRow, 28, numRows, 1);
  const abVals = abRange.getValues();

  let updatedT1 = 0;
  let updatedT1S1 = 0;
  let resetCount = 0;

  for (let i = 0; i < numRows; i++) {
    const dgId = String(dgVals[i][0] || "").trim().toUpperCase();
    const siteCode = String(dgVals[i][1] || "").trim().toUpperCase();
    const curAB = String(abVals[i][0] || "").trim();

    let isT1 = false;
    for (let j = 0; j < t1Sites.length; j++) {
      const s = t1Sites[j].toUpperCase();
      if (siteCode === s || dgId.indexOf(s) !== -1) {
        isT1 = true;
        break;
      }
    }

    let isT1S1 = false;
    if (!isT1) {
      for (let j = 0; j < t1S1Sites.length; j++) {
        const s = t1S1Sites[j].toUpperCase();
        if (siteCode === s || dgId.indexOf(s) !== -1) {
          isT1S1 = true;
          break;
        }
      }
    }

    if (isT1) {
      if (curAB !== "T1") {
        abVals[i][0] = "T1";
        updatedT1++;
      }
    } else if (isT1S1) {
      if (curAB !== "T1 S1") {
        abVals[i][0] = "T1 S1";
        updatedT1S1++;
      }
    } else {
      // Chỉ reset nếu là trạm ngoài danh sách mà mang nhãn T1 hoặc T1 S1 hoặc Team 1
      if (curAB === "T1" || curAB === "T1 S1" || curAB.toLowerCase() === "team 1") {
        abVals[i][0] = "0";
        resetCount++;
      }
    }
  }

  abRange.setValues(abVals);

  try {
    const af1Cell = sheet.getRange("AF1");
    const af1Val = String(af1Cell.getValue() || "").trim();
    if (af1Val !== "T1" && af1Val.indexOf("REF") !== -1) {
      af1Cell.setValue("T1");
    }
  } catch (eAF) {
    Logger.log("AF1 check error: " + eAF.message);
  }

  Logger.log("✅ updateTeam1PartnerAuto: T1=" + updatedT1 + ", T1 S1=" + updatedT1S1 + ", Reset=" + resetCount);
  return jsonResp({
    status: "ok",
    message: "Updated Team 1 and Team 1 S1 in Request Partner Auto",
    updatedT1: updatedT1,
    updatedT1S1: updatedT1S1,
    resetCount: resetCount
  });
}




