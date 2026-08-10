// ============================================================
// TNI Site Down Auto-Notification — v5 (STRICT SEPARATION)
// ============================================================
// HỆ THỐNG PHÂN LUỒNG ĐỘC LẬP 100% TRONG 1 GOOGLE APPS SCRIPT:
//
// 1. LUỒNG A1 / CỘT C (TIN 1 — Chi tiết Site Down):
//    - Đọc timestamp từ A1. So sánh riêng với TS_KEY_A1.
//    - Lấy dữ liệu chi tiết site từ Cột C để gửi Telegram.
//    - Ghi dữ liệu Cột A (qua doPost) CHỈ kích hoạt Luồng A1/Cột C.
//
// 2. LUỒNG AW7 (TIN 2 — Bảng SUMMARY):
//    - Đọc timestamp riêng từ ô AW7. So sánh riêng với TS_KEY_AW7.
//    - Lấy dữ liệu bảng từ AW7:AZ15 để gửi Telegram.
//    - Chạy hoàn toàn độc lập, TUYỆT ĐỐI KHÔNG can thiệp/ghi đè/dùng chung giờ với A1.
// ============================================================

// ── Telegram Bot Token ──────────────────────────────────────
const SD_BOT_TOKEN = PropertiesService.getScriptProperties().getProperty("SD_BOT_TOKEN") || "";

// ── Telegram Group Chat IDs ──────────────────────────────────
const SD_GROUPS = {
  T1:      "-1004215695747",  // TNI TEAM 1 PLAN - ALARM (Dawei)
  T2:      "-1004480845549",  // TNI TEAM 2 PLAN - ALARM (Myeik + Team5)
  T3:      "-1004369170658",  // TNI TEAM 3 PLAN - ALARM (Bokpyin)
  T4:      "-1004293741999",  // TNI TEAM 4 PLAN - ALARM (Kawthoung)
  CONTROL: "-5251698940",     // TNI TECHNICAL DEP CONTROL SITE
};

// ── Cá nhân nhận Tin 2 (DM) ────────────────────────────────
const SD_PERSONAL_IDS = [
  "6859790680",   // Ha Duc Phong
];

// ── Google Sheet Metadata ───────────────────────────────────
const SD_SHEET_ID  = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow";
const SD_SHEET_GID = "0";

// ── DEDUP KEYS RIÊNG BIỆT 100% (KHÔNG BAO GIỜ TRÙNG NHAU) ────
const TS_KEY_A1       = "SD_KEY_A1_INDEPENDENT_V5";  // Chìa khóa dedup riêng của A1/Col C
const TS_KEY_AW7      = "SD_KEY_AW7_INDEPENDENT_V5"; // Chìa khóa dedup riêng của AW7
const LAST_UPDATE_KEY = "SD_LAST_UPDATE_ID";          // Offset Telegram polling

// ── AW:AZ Column & Label Mappings ───────────────────────────
const AWAZ_COL = { T1: 0, T2: 1, T3: 2, T4: 3 };

const AWAZ_LABELS = [
  { emoji: "⚡", name: "Site down"   },
  { emoji: "🔴", name: "Cell down"   },
  { emoji: "⚙️", name: "DG Abnormal" },
  { emoji: "⏱️", name: "DG Run>16H"  },
  { emoji: "🔗", name: "Link down"   },
];

const TEAM_COLORS = { T1: "🟠", T2: "🔵", T3: "🟢", T4: "🟡" };


// ============================================================
// WEB APP — doPost() (Xử lý dán Cột A — CHỈ GỌI LUỒNG COL C)
// ============================================================
// NOTE: renamed from doPost → private, to avoid conflict with apps_script_collector.gs master doPost
function doPost_siteDownStandalone_(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.tryLock(8000);
    const data = JSON.parse(e.postData.contents);

    if (data.update_id !== undefined && !data.action) {
      return handleTelegramWebhook_(data);
    }

    const action = data.action || "";

    if (action === "store_site_down") {
      const text  = (data.text || "").trim();
      const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
      const sheet = getSheetByGid(ss, SD_SHEET_GID);
      if (!sheet) return _json({ ok: false, msg: "Sheet not found" });

      const props   = PropertiesService.getScriptProperties();
      const relayTs = data.relay_ts || 0;

      // Clear & ghi dữ liệu mới vào Cột A
      const lastRow = Math.max(sheet.getLastRow(), 1);
      sheet.getRange(1, 1, lastRow, 1).clearContent();

      const lines = text.split("\n");
      if (lines.length > 0) {
        const values = lines.map(l => [l]);
        sheet.getRange(1, 1, values.length, 1).setValues(values);
      }
      Logger.log("[doPost] store_site_down — " + lines.length + " dòng ghi vào Col A | relay_ts=" + relayTs);

      // ✅ TÁCH BIỆT LUỒNG: Xóa chìa khóa A1 để Luồng A1/Col C BẮN TIN 1 NGAY LẬP TỨC
      props.deleteProperty(TS_KEY_A1);

      if (relayTs > 0) props.setProperty("SD_LAST_RELAY_TS", relayTs.toString());

      SpreadsheetApp.flush();
      Utilities.sleep(300);

      // ✅ CHỈ CHẠY LUỒNG A1 / COL C (Không đụng chạm gì tới Luồng AW7)
      var sentColC = false;
      try {
        sentColC = processSiteDownColC(sheet);
        Logger.log("[doPost] Luồng A1/Col C chạy xong. Kết quả: " + sentColC);
      } catch(errColC) {
        Logger.log("[doPost] ❌ Lỗi Luồng A1/Col C: " + errColC.message);
      }

      return _json({ 
        ok: true, 
        lines: lines.length,
        relay_ts: relayTs,
        sent_tin1: sentColC
      });
    }

    if (action === "get_note_b2b5") {
      const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
      const sheet = getSheetByGid(ss, SD_SHEET_GID);
      if (!sheet) return _json({ ok: false, msg: "Sheet not found" });
      const vals = sheet.getRange("B2:B5").getValues();
      const note = vals.map(r => (r[0] || "").toString().trim()).filter(v => v).join("\n");
      return ContentService.createTextOutput(note).setMimeType(ContentService.MimeType.TEXT);
    }

    if (action === "save_note_msgids") {
      const msgids = data.msgids || {};
      PropertiesService.getScriptProperties().setProperty("SD_NOTE_MSGIDS", JSON.stringify(msgids));
      return _json({ ok: true });
    }

    if (action === "get_note_msgids") {
      const raw    = PropertiesService.getScriptProperties().getProperty("SD_NOTE_MSGIDS") || "{}";
      const msgids = JSON.parse(raw);
      return _json({ ok: true, msgids: msgids });
    }

    return _json({ ok: false, msg: "Unknown action: " + action });

  } catch (err) {
    return _json({ ok: false, msg: err.message });
  }
}

// NOTE: renamed from doGet → private, to avoid conflict with apps_script_collector.gs master doGet
function doGet_siteDownStandalone_(e) {
  try {
    const action = (e.parameter && e.parameter.action) || "";

    if (action === "get_note_b2b5") {
      const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
      const sheet = getSheetByGid(ss, SD_SHEET_GID);
      if (!sheet) return ContentService.createTextOutput("").setMimeType(ContentService.MimeType.TEXT);
      const vals = sheet.getRange("B2:B5").getValues();
      const note = vals.map(r => (r[0] || "").toString().trim()).filter(v => v).join("\n");
      return ContentService.createTextOutput(note).setMimeType(ContentService.MimeType.TEXT);
    }

    if (action === "get_note_msgids") {
      const raw    = PropertiesService.getScriptProperties().getProperty("SD_NOTE_MSGIDS") || "{}";
      const msgids = JSON.parse(raw);
      return _json({ ok: true, msgids: msgids });
    }

    return _json({ ok: false, msg: "Unknown GET action: " + action });
  } catch (err) {
    return _json({ ok: false, msg: err.message });
  }
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}


// ============================================================
// MAIN TRIGGER — checkAndSend() (CHẠY 2 LUỒNG ĐỘC LẬP TÁCH BIỆT)
// ============================================================
function checkAndSend(isWebhookCall) {
  const now    = new Date();
  const mytime = Utilities.formatDate(now, "Asia/Rangoon", "H:mm");
  const hour   = parseInt(Utilities.formatDate(now, "Asia/Rangoon", "H"), 10);
  const minute = parseInt(Utilities.formatDate(now, "Asia/Rangoon", "m"), 10);

  const props = PropertiesService.getScriptProperties();

  // ── 1. Reset đệm độc lập vào 03:30 AM đầu ngày ─────────────────────────
  const todayStr = Utilities.formatDate(now, "Asia/Rangoon", "yyyyMMdd");
  const lastDay  = props.getProperty("SD_LAST_RUN_DATE") || "";
  if (todayStr !== lastDay) {
    props.setProperty("SD_LAST_RUN_DATE", todayStr);
    props.deleteProperty(TS_KEY_A1);
    props.deleteProperty(TS_KEY_AW7);
    Logger.log("🌅 NGÀY MỚI (" + todayStr + ") — Đã reset chìa khóa A1 & AW7!");
  }

  // ── 2. Kiểm tra khung giờ hoạt động (03:30 - 22:30 Myanmar) ────────────
  if (isWebhookCall !== true) {
    if (hour < 3 || hour > 22) return { sent_tin1: false, sent_tin2: false };
    if (hour === 3 && minute < 30) return { sent_tin1: false, sent_tin2: false };
    if (hour === 22 && minute > 30) return { sent_tin1: false, sent_tin2: false };

    const thisMinute = Utilities.formatDate(now, "Asia/Rangoon", "yyyyMMddHHmm");
    const lastDoneMinute = props.getProperty("SD_LAST_DONE_MINUTE") || "";
    if (thisMinute === lastDoneMinute) {
      return { sent_tin1: false, sent_tin2: false };
    }
    props.setProperty("SD_LAST_DONE_MINUTE", thisMinute);

    // Kích hoạt cào GitHub ở mốc 5 phút
    if (minute % 5 === 0) {
      const cycleSlot = Utilities.formatDate(now, "Asia/Rangoon", "yyyyMMddHH") + (minute < 30 ? "_00" : "_30");
      const lastSlot  = props.getProperty("SD_DISPATCH_SLOT") || "";

      let count = parseInt(props.getProperty("SD_DISPATCH_COUNT") || "0", 10);
      if (cycleSlot !== lastSlot) {
        count = 0;
        props.setProperty("SD_DISPATCH_SLOT", cycleSlot);
        props.setProperty("SD_DISPATCH_COUNT", "0");
      }

      const lastSentSlot   = props.getProperty("SD_LAST_SENT_SLOT") || "";
      const lastDispatchTs = parseInt(props.getProperty("SD_LAST_DISPATCH_TS") || "0", 10);
      const minSinceDisp   = (Date.now() - lastDispatchTs) / 60000;

      if (lastSentSlot !== cycleSlot && count < 3 && (lastDispatchTs === 0 || minSinceDisp >= 3)) {
        Logger.log("⏰ " + mytime + " Myanmar → Ép GitHub dispatch relay");
        triggerBotlookupRelay();
        props.setProperty("SD_DISPATCH_COUNT", (count + 1).toString());
      }
    }
  }

  // ── 3. Mở Google Sheet và THỰC THI 2 LUỒNG TRONG 2 KHỐI TRY/CATCH TÁCH BIỆT ──
  const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
  const sheet = getSheetByGid(ss, SD_SHEET_GID);
  if (!sheet) return { sent_tin1: false, sent_tin2: false };

  var r1 = false;
  var r2 = false;

  // 🔹 LUỒNG 1: DÀNH RIÊNG CHO A1 / CỘT C (TIN 1)
  try {
    r1 = processSiteDownColC(sheet);
  } catch(e1) {
    Logger.log("❌ Lỗi Luồng 1 (A1/Col C): " + e1.message);
  }

  // 🔹 LUỒNG 2: DÀNH RIÊNG CHO AW7 (TIN 2 SUMMARY)
  // Nếu Tin 1 vừa phát (r1 = true), ép Tin 2 phát lại ngay phía dưới để Tin 2 LUÔN NẰM Ở ĐÁY CHAT DƯỚI TIN 1
  try {
    r2 = processSummaryAwAz(sheet, r1 === true);
  } catch(e2) {
    Logger.log("❌ Lỗi Luồng 2 (AW7 Summary): " + e2.message);
  }

  return { sent_tin1: r1, sent_tin2: r2 };
}


// ============================================================
// LUỒNG 1 — XỬ LÝ A1 / CỘT C (TIN 1 — Chi tiết Site Down)
// Độc lập 100% — Chỉ đọc mốc giờ A1 & ghi chìa khóa TS_KEY_A1
// ============================================================
function processSiteDownColC(sheet) {
  const storeKey = parseA1Timestamp(sheet);
  if (!storeKey) {
    Logger.log("[Luồng A1] Không tìm thấy timestamp hợp lệ trong A1");
    return false;
  }

  const props   = PropertiesService.getScriptProperties();
  const lastKey = props.getProperty(TS_KEY_A1) || "";

  if (storeKey === lastKey) {
    Logger.log("[Luồng A1] Timestamp A1 không đổi (" + storeKey.substring(0, 30) + ") → Bỏ qua Luồng 1");
    return false;
  }

  // ✅ ĐỘC LẬP: Lưu ngay khóa A1
  props.setProperty(TS_KEY_A1, storeKey);
  Logger.log("[Luồng A1] 🆕 Timestamp A1 thay đổi: " + storeKey + " → Đang gửi Tin 1...");

  const lastRow = sheet.getLastRow();
  if (lastRow < 1) return false;

  const colC = sheet.getRange(1, 3, lastRow, 1).getValues().flat().map(v => (v || "").toString().trim());

  function isTeamSummaryLine(l) {
    return /Team\s*0?[1-4][\s\—\-]*:\s*Total\s+Site\s+down/i.test(l);
  }

  // Gửi nhóm CONTROL
  const controlId = SD_GROUPS["CONTROL"];
  if (controlId) {
    try {
      const header = [colC[0]||"", colC[1]||"", colC[2]||""].filter(l => l.length > 0);
      const rawSites = colC.slice(9).filter(l => l.length > 0 && l !== "..." && !isTeamSummaryLine(l));

      const teamDefs = [
        { key: "T1", regex: /Team\s*0?1\b|Dawei|DW\b/i,                         label: "🟠 Team 1 Dawei" },
        { key: "T2", regex: /Team\s*0?2\b|Myeik|MK\b/i,                         label: "🔵 Team 2 Myeik" },
        { key: "T3", regex: /Team\s*0?3\b|Bokpyin|Bok\s*pyin|Bok\s*Pyin|BP\b/i,    label: "🟢 Team 3 Bokpyin" },
        { key: "T4", regex: /Team\s*0?4\b|Kawthoung|KT\b/i,                      label: "🟡 Team 4 Kawthoung" },
      ];

      const teamBlocks = { T1: [], T2: [], T3: [], T4: [] };
      let currentTeam = null;

      for (const line of rawSites) {
        let matched = false;
        for (const td of teamDefs) {
          if (/^Team\s*/i.test(line.trim()) && td.regex.test(line)) {
            currentTeam = td.key;
            matched = true;
            break;
          }
        }
        if (matched) continue;

        let lineTeam = currentTeam;
        if (/\|\s*🟠?\s*T1\b/i.test(line)) lineTeam = "T1";
        else if (/\|\s*🔵?\s*T2\b/i.test(line)) lineTeam = "T2";
        else if (/\|\s*🟢?\s*T3\b/i.test(line)) lineTeam = "T3";
        else if (/\|\s*🟡?\s*T4\b/i.test(line)) lineTeam = "T4";

        if (lineTeam && teamBlocks[lineTeam]) {
          if (/^_{5,}$/.test(line.trim())) continue;
          teamBlocks[lineTeam].push(line);
        }
      }

      const bodyLines = [];
      for (const td of teamDefs) {
        bodyLines.push("");
        bodyLines.push(td.label);
        bodyLines.push("__________________________");
        
        const lines = teamBlocks[td.key];
        while (lines.length > 0 && !lines[0].trim()) lines.shift();
        while (lines.length > 0 && !lines[lines.length - 1].trim()) lines.pop();

        if (lines.length > 0) {
          bodyLines.push(...lines);
        } else {
          bodyLines.push("✅ No incident");
        }
      }

      const msg = [...header, ...bodyLines].join("\n");
      if (msg) {
        sendOrEditTelegramPre(controlId, addKeywordIcons(colorizeTeams(msg)), "TIN1_CONTROL", "[Tin1][CONTROL]");
      }
    } catch (e) {
      Logger.log("[Luồng A1][CONTROL] ❌ " + e.message);
    }
  }

  // Phân loại site theo 4 Teams (T1, T2, T3, T4)
  const teamCells = { T1: colC[3]||"", T2: colC[4]||"", T3: colC[5]||"", T4: colC[6]||"" };
  const teams = ["T1", "T2", "T3", "T4"];
  const allC10 = colC.slice(9).filter(l => l.length > 0 && l !== "...");

  for (const team of teams) {
    if (!teamCells[team]) {
      const n = team[1];
      const found = allC10.find(l => new RegExp("Team\\s+" + n + "\\s*:\\s*Total\\s+Site\\s+down", "i").test(l));
      if (found) teamCells[team] = found;
    }
  }

  const siteOnly  = allC10.filter(l => !isTeamSummaryLine(l));
  const teamSites = { T1: [], T2: [], T3: [], T4: [] };

  for (const line of siteOnly) {
    const fields = line.split("|");
    if (fields.length < 2) continue;
    const teamField = fields[1].trim().toUpperCase();
    for (const team of teams) {
      const tn  = team.slice(1);
      const idx = teamField.indexOf("T" + tn);
      if (idx < 0) continue;
      const afterChar = teamField[idx + 1 + tn.length];
      if (!afterChar || !/\d/.test(afterChar)) {
        teamSites[team].push(line);
        break;
      }
    }
  }

  // Gửi sang 4 nhóm Team
  for (const team of teams) {
    try {
      const chatId = SD_GROUPS[team];
      if (!chatId || String(chatId).trim() === String(controlId).trim()) continue;
      const summary = teamCells[team];
      const sites   = teamSites[team];
      if (sites.length > 0) {
        const parts = summary ? [summary, ...sites] : [...sites];
        sendOrEditTelegramPre(chatId, addKeywordIcons(colorizeTeams(parts.join("\n"))), "TIN1_" + team, "[Tin1][" + team + "]");
      } else if (summary) {
        sendOrEditTelegramPre(chatId, addKeywordIcons(colorizeTeams(summary)), "TIN1_" + team, "[Tin1][" + team + "]");
      }
    } catch (e) {
      Logger.log("[Luồng A1][" + team + "] ❌ " + e.message);
    }
  }

  const now = new Date();
  const sentSlot = Utilities.formatDate(now, "Asia/Rangoon", "yyyyMMddHH") + (now.getMinutes() < 30 ? "_00" : "_30");
  props.setProperty("SD_LAST_SENT_SLOT", sentSlot);
  Logger.log("[Luồng A1] ✅ Hoàn tất gửi Tin 1!");
  return true;
}


// ============================================================
// LUỒNG 2 — XỬ LÝ AW7 (TIN 2 — Bảng SUMMARY)
// Độc lập 100% — Chỉ đọc mốc giờ ô AW7 & ghi chìa khóa TS_KEY_AW7
// ============================================================
function processSummaryAwAz(sheet) {
  const rawTs = sheet.getRange("AW7").getValue().toString().trim();
  if (!rawTs) {
    Logger.log("[Luồng AW7] Ô AW7 rỗng — Bỏ qua Luồng 2");
    return false;
  }

  // ✅ ĐỘC LẬP 100%: Chỉ đọc mốc giờ riêng của ô AW7
  const tsKey = parseAW7Timestamp(sheet) || formatTsHeader(rawTs);

  const props  = PropertiesService.getScriptProperties();
  const lastTs = props.getProperty(TS_KEY_AW7) || "";

  if (tsKey === lastTs) {
    Logger.log("[Luồng AW7] Timestamp AW7 không đổi (" + tsKey + ") → Bỏ qua Luồng 2");
    return false;
  }

  // ✅ ĐỘC LẬP: Lưu ngay khóa AW7
  props.setProperty(TS_KEY_AW7, tsKey);
  Logger.log("[Luồng AW7] 🆕 Timestamp AW7 thay đổi: " + tsKey + " → Đang gửi Tin 2 (SUMMARY)...");

  const awaz  = readAwAz(sheet);
  const teams = ["T1", "T2", "T3", "T4"];

  // Gửi sang 4 nhóm Team
  for (const team of teams) {
    try {
      const chatId = SD_GROUPS[team];
      if (!chatId) continue;
      const colIdx = AWAZ_COL[team];
      if (colIdx === undefined) continue;
      const msg = buildAwAzTeamMessage(team, tsKey, awaz, colIdx);
      sendOrEditTelegram(chatId, msg, "TIN2_" + team, "[Tin2][" + team + "]");
    } catch (err) {
      Logger.log("[Luồng AW7][" + team + "] ❌ " + err.message);
    }
  }

  // Gửi nhóm CONTROL
  const controlId = SD_GROUPS["CONTROL"];
  if (controlId) {
    try {
      const msg = buildAwAzControlMessage(tsKey, awaz);
      sendOrEditTelegram(controlId, msg, "TIN2_CONTROL", "[Tin2][CONTROL]");
    } catch(e) {
      Logger.log("[Luồng AW7][CONTROL] ❌ " + e.message);
    }
  }

  // Gửi DM cá nhân
  for (const pid of SD_PERSONAL_IDS) {
    try {
      sendOrEditTelegram(pid, buildAwAzControlMessage(tsKey, awaz), "TIN2_P_" + pid, "[Tin2][DM]");
    } catch(e) {}
    Utilities.sleep(200);
  }

  Logger.log("[Luồng AW7] ✅ Hoàn tất gửi Tin 2 SUMMARY!");
  return true;
}


// ============================================================
// HELPER PARSERS & UTILITIES
// ============================================================
function parseA1Timestamp(sheet) {
  const maxRow = Math.min(sheet.getLastRow(), 50);
  if (maxRow < 1) return null;
  const vals = sheet.getRange(1, 1, maxRow, 1).getValues().flat();

  for (const cellVal of vals) {
    const raw = (cellVal || "").toString();
    const m1 = raw.match(/(\d{2}\/\d{2}\/\d{4}[\s\-T]+\d{2}:\d{2}:\d{2})/);
    if (m1) return m1[1].replace(/[\-T]/g, " ").trim();
    const m2 = raw.match(/(\d{2}\/\d{2}\/\d{4}[\s\-T]+\d{2}:\d{2})/);
    if (m2) return m2[1].replace(/[\-T]/g, " ").trim();
  }

  const textHead = vals.map(v => v.toString().trim()).filter(v => v.length > 0).slice(0, 5).join(" ");
  if (textHead) {
    const nowStr = Utilities.formatDate(new Date(), "Asia/Rangoon", "dd/MM/yyyy HH:mm");
    return "RAW_" + nowStr + "_" + textHead.substring(0, 40).replace(/[^a-zA-Z0-9]/g, "");
  }
  return null;
}

function parseAW7Timestamp(sheet) {
  const raw = sheet.getRange("AW7").getValue().toString();
  const m1 = raw.match(/Site\s*down[^:]*:\s*(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/i);
  if (m1) return m1[1].trim();
  const m2 = raw.match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
  if (m2) return m2[1].trim();
  return null;
}

function readAwAz(sheet) {
  return sheet.getRange(7, 49, 9, 4).getValues();
}

function buildAwAzTeamMessage(teamKey, ts, awaz, colIdx) {
  const label   = "Team " + teamKey.replace("T", "");
  const numRows = awaz.length;
  const lines   = [];
  lines.push("📊 <b>SUMMARY — " + label + "</b>");
  lines.push("📅 " + escHtml(ts));
  lines.push("━".repeat(26));

  let hasData = false;
  for (let r = 0; r < numRows; r++) {
    const txt = ((awaz[r] || [])[colIdx] || "").toString().trim();
    if (!txt || txt === "0") continue;
    const clean = escHtml(txt.replace(/[*_`]/g, ""));
    if (r < AWAZ_LABELS.length) {
      lines.push(AWAZ_LABELS[r].emoji + " <b>" + AWAZ_LABELS[r].name + ":</b> " + clean);
    } else {
      const lm = txt.match(/^([^:]+):/);
      const lb = lm ? lm[1].replace(/[*_`]/g, "").trim() : "Row " + (r + 1);
      lines.push("📌 <b>" + escHtml(lb) + ":</b> " + clean);
    }
    hasData = true;
  }
  if (!hasData) lines.push("✅ No incident");
  return lines.join("\n");
}

function buildAwAzControlMessage(ts, awaz) {
  const teamDefs = [
    { key: "T1", label: "Team 1 Dawei",     emoji: "🟠", col: 0 },
    { key: "T2", label: "Team 2 Myeik",     emoji: "🔵", col: 1 },
    { key: "T3", label: "Team 3 Bokpyin",   emoji: "🟢", col: 2 },
    { key: "T4", label: "Team 4 Kawthoung", emoji: "🟡", col: 3 },
  ];
  const numRows = awaz.length;
  const lines   = [];
  lines.push("📊 <b>SUMMARY — ALL TEAMS</b>");
  lines.push("📅 " + escHtml(ts));
  lines.push("━".repeat(26));

  for (const t of teamDefs) {
    lines.push("");
    lines.push(t.emoji + " <b>" + t.label + "</b>");
    lines.push("─".repeat(20));
    let hasData = false;
    for (let r = 0; r < numRows; r++) {
      const txt = ((awaz[r] || [])[t.col] || "").toString().trim();
      if (!txt || txt === "0") continue;
      const clean = escHtml(txt.replace(/[*_`]/g, ""));
      if (r < AWAZ_LABELS.length) {
        lines.push(AWAZ_LABELS[r].emoji + " <b>" + AWAZ_LABELS[r].name + ":</b> " + clean);
      } else {
        const lm = txt.match(/^([^:]+):/);
        const lb = lm ? lm[1].replace(/[*_`]/g, "").trim() : "Row " + (r + 1);
        lines.push("📌 <b>" + escHtml(lb) + ":</b> " + clean);
      }
      hasData = true;
    }
    if (!hasData) lines.push("✅ No incident");
  }
  return lines.join("\n");
}


// ============================================================
// TELEGRAM BOT API HELPERS (IN-PLACE EDITING & DELETE)
// ============================================================
function splitMessage(text, maxLen) {
  if (!text) return [""];
  if (text.length <= maxLen) return [text];
  const chunks = [];
  const lines = text.split("\n");
  let cur = "";
  for (const line of lines) {
    if ((cur + "\n" + line).length > maxLen) {
      if (cur) chunks.push(cur.trim());
      cur = line;
    } else {
      cur = cur ? cur + "\n" + line : line;
    }
  }
  if (cur) chunks.push(cur.trim());
  return chunks;
}

function sendOrEditTelegram(chatId, text, msgKey, tag) {
  deleteOldMessages_(chatId, msgKey);
  Utilities.sleep(200);
  const props  = PropertiesService.getScriptProperties();
  const idKey  = "SD_MSGID_" + msgKey;
  const newIds = sendTelegramCollectIds_(chatId, text, tag);
  props.setProperty(idKey, JSON.stringify(newIds));
}

function sendOrEditTelegramPre(chatId, plainContent, msgKey, tag) {
  // ✅ Xóa tin cũ và bắn tin mới xuống ĐÁY CHAT TELEGRAM theo định dạng HTML đẹp mắt (KHÔNG dùng thẻ <pre> ô xám code)
  deleteOldMessages_(chatId, msgKey);
  Utilities.sleep(200);
  const props  = PropertiesService.getScriptProperties();
  const idKey  = "SD_MSGID_" + msgKey;
  const newIds = sendTelegramCollectIds_(chatId, plainContent, tag);
  props.setProperty(idKey, JSON.stringify(newIds));
}

function editTelegramMsg_(chatId, messageId, text, parseMode, tag) {
  try {
    const resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + SD_BOT_TOKEN + "/editMessageText", {
      method:             "post",
      contentType:        "application/json",
      payload:            JSON.stringify({ chat_id: chatId, message_id: messageId, text: text, parse_mode: parseMode || "HTML" }),
      muteHttpExceptions: true,
    });
    const res = JSON.parse(resp.getContentText());
    return res.ok === true || (!!res.description && res.description.indexOf("message is not modified") >= 0);
  } catch(e) {
    return false;
  }
}

function sendTelegramCollectIds_(chatId, text, tag) {
  const url    = "https://api.telegram.org/bot" + SD_BOT_TOKEN + "/sendMessage";
  const chunks = splitMessage(text, 4000);
  const ids    = [];
  chunks.forEach((chunk, i) => {
    try {
      const resp = UrlFetchApp.fetch(url, {
        method: "post", contentType: "application/json",
        payload: JSON.stringify({ chat_id: chatId, text: chunk, parse_mode: "HTML" }),
        muteHttpExceptions: true,
      });
      const res = JSON.parse(resp.getContentText());
      if (res.ok && res.result && res.result.message_id) ids.push(res.result.message_id);
    } catch(e) {}
  });
  return ids;
}

function sendTelegramPreCollectIds_(chatId, plainContent, tag) {
  const url     = "https://api.telegram.org/bot" + SD_BOT_TOKEN + "/sendMessage";
  const escaped = escHtml(plainContent);
  const chunks  = splitMessage(escaped, 3800);
  const ids     = [];
  chunks.forEach((chunk, i) => {
    try {
      const resp = UrlFetchApp.fetch(url, {
        method: "post", contentType: "application/json",
        payload: JSON.stringify({ chat_id: chatId, text: "<pre>" + chunk + "</pre>", parse_mode: "HTML" }),
        muteHttpExceptions: true,
      });
      const res = JSON.parse(resp.getContentText());
      if (res.ok && res.result && res.result.message_id) ids.push(res.result.message_id);
    } catch(e) {}
    if (i < chunks.length - 1) Utilities.sleep(200);
  });
  return ids;
}

function getSavedMsgIds_(msgKey) {
  const val = PropertiesService.getScriptProperties().getProperty("SD_MSGID_" + msgKey) || "";
  if (!val) return [];
  try {
    const arr = JSON.parse(val);
    if (Array.isArray(arr)) return arr;
  } catch(e) {}
  return [];
}

function deleteTelegramMsgBot_(chatId, messageId) {
  try {
    const resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + SD_BOT_TOKEN + "/deleteMessage", {
      method: "post", contentType: "application/json",
      payload: JSON.stringify({ chat_id: chatId, message_id: messageId }),
      muteHttpExceptions: true,
    });
    const res = JSON.parse(resp.getContentText());
    return res.ok === true || (res.description && res.description.indexOf("message to delete not found") >= 0);
  } catch(e) { return false; }
}

function deleteOldMessages_(chatId, msgKey) {
  const oldIds = getSavedMsgIds_(msgKey);
  for (let i = 0; i < oldIds.length; i++) {
    deleteTelegramMsgBot_(chatId, oldIds[i]);
    if (i < oldIds.length - 1) Utilities.sleep(100);
  }
  PropertiesService.getScriptProperties().deleteProperty("SD_MSGID_" + msgKey);
}

function colorizeTeams(text) {
  if (!text) return "";
  let s = text;
  s = s.replace(/\|\s*(T[1-4])(\s+S\w*)?\s*\|/gi, (match, team, sub) => {
    const emoji = TEAM_COLORS[team.toUpperCase()] || "";
    return "| " + emoji + team + (sub || "") + " |";
  });
  s = s.replace(/(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?Team\s*1(?:\s*[\—\-]?\s*Dawei)?(\s*:)?/gi, (match, colon) => {
    return "🟠 Team 1 Dawei" + (colon || "");
  });
  s = s.replace(/(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?Team\s*2(?:\s*[\—\-]?\s*Myeik)?(\s*:)?/gi, (match, colon) => {
    return "🔵 Team 2 Myeik" + (colon || "");
  });
  s = s.replace(/(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?Team\s*3(?:\s*[\—\-]?\s*Bokpyin)?(\s*:)?/gi, (match, colon) => {
    return "🟢 Team 3 Bokpyin" + (colon || "");
  });
  s = s.replace(/(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?Team\s*4(?:\s*[\—\-]?\s*Kawthoung)?(\s*:)?/gi, (match, colon) => {
    return "🟡 Team 4 Kawthoung" + (colon || "");
  });
  return s;
}

function formatTsHeader(ts) {
  if (!ts) return "";
  const match = ts.match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
  if (match) return match[1];
  return ts.length > 30 ? ts.substring(0, 30) : ts;
}

function addKeywordIcons(text) {
  if (!text) return "";
  let s = text;
  s = s.replace(/(?:^|\n|\s*)(Dont\s+Forget)/gi, "\n🔥 Dont Forget");
  s = s.replace(/(?:^|\n|\s*)>(?:\s*)(Cell down:)/gi, "\n🔴 Cell down:");
  s = s.replace(/(?:^|\n|\s*)>(?:\s*)(DG Abnormal:)/gi, "\n⚙️ DG Abnormal:");
  s = s.replace(/(?:^|\n|\s*)>(?:\s*)(Duty:)/gi, "\n🕒 Duty:");
  s = s.replace(/\|\s*(DG Abnormal:)/gi, "\n⚙️ DG Abnormal:");
  s = s.replace(/\|\s*(Cell down:)/gi, "\n🔴 Cell down:");
  s = s.replace(/\|\s*(Duty:)/gi, "\n🕒 Duty:");
  s = s.replace(/(?:^|\s)(Duty:)/gi, "\n🕒 Duty:");

  s = s.replace(/(?:(?:^|\n|\s*)>|\|)\s*(Link down:)\s*([^\n\|]*)/gi, function(match, keyword, dataStr) {
     let c = dataStr.replace(/[*_`]/g, "").trim();
     return "\n🔗 " + keyword + " " + c;
  });

  s = s.replace(/(?:(?:^|\n|\s*)>|\|)\s*(DG Run>16H:)\s*([^\n\|]*)/gi, function(match, keyword, dataStr) {
     let c = dataStr.replace(/[*_]/g, "").trim();
     let icon = (c && c !== "0" && c !== "-" && c.toLowerCase() !== "none") ? "❌" : "✅";
     return "\n" + icon + " " + keyword + " " + dataStr;
  });

  s = s.replace(/(?:🔥\s*)+Dont\s+Forget/gi, "🔥 Dont Forget");
  s = s.replace(/(?:🕒\s*)+Duty:/gi, "🕒 Duty:");
  return s.trim();
}

function escHtml(str) {
  return (str || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function getSheetByGid(ss, gid) {
  for (const s of ss.getSheets()) {
    if (s.getSheetId().toString() === gid.toString()) return s;
  }
  return null;
}

function triggerBotlookupRelay() {
  const props = PropertiesService.getScriptProperties();
  const pat   = props.getProperty("GITHUB_PAT") || "";
  if (!pat) return;
  try {
    UrlFetchApp.fetch("https://api.github.com/repos/phonghdpxd-cmd/tni-bot/actions/workflows/botlookup_relay.yml/dispatches", {
      method: "post",
      headers: { "Authorization": "token " + pat, "Accept": "application/vnd.github.v3+json" },
      contentType: "application/json",
      payload: JSON.stringify({ ref: "main", inputs: { skip_delay: "1" } }),
      muteHttpExceptions: true,
    });
    props.setProperty("SD_LAST_DISPATCH_TS", Date.now().toString());
  } catch(e) {}
}


// ============================================================
// TIỆN ÍCH CHẠY THỬ & ĐẶT TRIGGER
// ============================================================
function setupSdTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === "checkAndSend")
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("checkAndSend").timeBased().everyMinutes(1).create();
  Logger.log("✅ Trigger checkAndSend() mỗi 1 phút đã cài đặt.");
}

// 🧪 CHẠY THỬ ĐỘC LẬP 2 LUỒNG
function testSendNow() {
  const props = PropertiesService.getScriptProperties();
  props.deleteProperty(TS_KEY_A1);
  props.deleteProperty(TS_KEY_AW7);
  const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
  const sheet = getSheetByGid(ss, SD_SHEET_GID);
  if (!sheet) return;
  processSiteDownColC(sheet);
  processSummaryAwAz(sheet);
}
