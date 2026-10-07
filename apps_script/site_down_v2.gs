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
const SD_BOT_TOKEN = PropertiesService.getScriptProperties().getProperty("SD_BOT_TOKEN") || PropertiesService.getScriptProperties().getProperty("SEND_BOT_TOKEN") || "";

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
  { emoji: "⚡", name: "Site down"                },
  { emoji: "🔴", name: "Cell down"                },
  { emoji: "⚙️", name: "DG Abnormal"              },
  { emoji: "⏱️", name: "DG Run>16H"               },
  { emoji: "🔗", name: "Link down"                },
  { emoji: "🌡️", name: "Battery Temperature High" },
  { emoji: "💨", name: "Smoke"                    },
  { emoji: "🚪", name: "DOOR"                     },
];

const TEAM_COLORS = { T1: "🟠", T2: "🔵", T3: "🟢", T4: "🟡" };


/**
 * 🤖 Xử lý Webhook Telegram Update (Bot 10 Construction, Callbacks, Commands)
 */
function handleTelegramWebhook_(data) {
  try {
    const updateId = data.update_id;
    if (updateId) {
      const cache = CacheService.getScriptCache();
      const cacheKey = "TG_UPD_" + updateId;
      if (cache.get(cacheKey)) {
        Logger.log("[handleTelegramWebhook_] 🛡️ Bỏ qua update_id trùng lặp: " + updateId);
        return ContentService.createTextOutput(JSON.stringify({ ok: true, status: "dedup_skipped" })).setMimeType(ContentService.MimeType.JSON);
      }
      cache.put(cacheKey, "1", 600); // Khóa trùng 10 phút (600s)
    }

    if (typeof processTelegramUpdate === "function") {
      processTelegramUpdate(data);
    }
  } catch (ex) {
    Logger.log("[handleTelegramWebhook_] Lỗi xử lý update: " + ex.message);
  }
  return ContentService.createTextOutput(JSON.stringify({ ok: true, status: "processed" })).setMimeType(ContentService.MimeType.JSON);
}

// ============================================================
// WEB APP — doPost() (Xử lý dán Cột A — CHỈ GỌI LUỒNG COL C)
// ============================================================
function doPost(e) {
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

      // ✅ GHI ĐÈ TRỰC TIẾP (Atomic Overwrite) — KHÔNG clearContent trước để tránh công thức FILTER bị giật về #N/A
      const lastRow = Math.max(sheet.getLastRow(), 1);
      const lines = text.split("\n");
      if (lines.length > 0) {
        const values = lines.map(l => [l]);
        sheet.getRange(1, 1, values.length, 1).setValues(values);
        // Chỉ xóa các dòng thừa bên dưới nếu dữ liệu mới ngắn hơn dữ liệu cũ
        if (lastRow > values.length) {
          sheet.getRange(values.length + 1, 1, lastRow - values.length, 1).clearContent();
        }
      }
      Logger.log("[doPost] store_site_down — " + lines.length + " dòng ghi vào Col A (Atomic Overwrite) | relay_ts=" + relayTs);

      // ✅ MỞ KHÓA LUỒNG 1: Xóa chìa khóa A1 để dữ liệu Cột A vừa dán luôn được gửi Tin 1
      props.deleteProperty(TS_KEY_A1);
      // 🛑 TUYỆT ĐỐI KHÔNG XÓA TS_KEY_AW7: Luồng 2 (AW7 Summary) chỉ gửi khi ô AW7 thực sự có mốc giờ MỚI!

      if (relayTs > 0) props.setProperty("SD_LAST_RELAY_TS", relayTs.toString());

      SpreadsheetApp.flush();
      try { lock.releaseLock(); } catch(eLock) {} // ✅ Nhả lock ngay

      Utilities.sleep(5000); // ⏱️ Chờ đúng 5s + flush để Google Sheets hoàn tất 100% tính toán đồng bộ công thức Cột C
      SpreadsheetApp.flush();

      // ✅ THỰC THI GỬI:
      // Luồng 1 (Cột C): Dành riêng cho dữ liệu trạm sập chi tiết của đợt cào mới vừa dán vào Cột A
      var sentColC = false;
      try {
        sentColC = processSiteDownColC(sheet, true);
        Logger.log("[doPost] Luồng 1 (Cột C) gửi xong: " + sentColC);
      } catch(errColC) {
        Logger.log("[doPost] ❌ Lỗi Luồng 1 (Cột C): " + errColC.message);
      }

      // 🛑 KHÔNG GỌI processSummaryAwAz Ở ĐÂY:
      // Luồng cào Cột A (store_site_down) CHỈ GỬI DUY NHẤT Cột C (Tin 1) + kích hoạt Bot 2D ETA.
      // Bảng AW7 độc lập, tuyệt đối không gửi chen vào đợt cào Cột A để tránh gửi tin cũ và lệch thời gian!

      return _json({ 
        ok: true, 
        lines: lines.length,
        relay_ts: relayTs,
        sent_tin1: sentColC
      });
    }

    if (action === "process_aw_az") {
      const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
      const sheet = getSheetByGid(ss, SD_SHEET_GID);
      if (!sheet) return _json({ ok: false, msg: "Sheet not found" });
      const force = data.force === true;
      const sent2 = processSummaryAwAz(sheet, force);
      return _json({ ok: true, sent_tin2: sent2 });
    }

    if (action === "send_site_down_now") {
      const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
      const sheet = getSheetByGid(ss, SD_SHEET_GID);
      if (!sheet) return _json({ ok: false, msg: "Sheet not found" });
      const props = PropertiesService.getScriptProperties();
      props.deleteProperty(TS_KEY_A1);
      SpreadsheetApp.flush();
      try { lock.releaseLock(); } catch(eLock) {}
      const sent1 = processSiteDownColC(sheet, true);
      const sent2 = processSummaryAwAz(sheet, false);
      return _json({ ok: true, sent_tin1: sent1, sent_tin2: sent2 });
    }

    if (action === "trigger_bot2d_eta") {
      const skipDelay = data.skip_delay === true;
      const ok = triggerBot2dEta_(skipDelay);
      return _json({ ok: ok, action: "trigger_bot2d_eta" });
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

function doGet(e) {
  try {
    const action = (e.parameter && e.parameter.action) || "";

    // ── Admin Audit: Kiểm tra / Gán SD_BOT_TOKEN & Dọn dẹp Trigger cũ ──
    if (action === "admin_audit_sitedown") {
      const props = PropertiesService.getScriptProperties();
      const sdTokenOld = props.getProperty("SD_BOT_TOKEN") || "";
      const sendToken = props.getProperty("SEND_BOT_TOKEN") || "";
      
      // Tự động gán SD_BOT_TOKEN nếu chưa có hoặc rỗng
      if (!sdTokenOld) {
        props.setProperty("SD_BOT_TOKEN", "8647102342:AAGwI95-xeyFfJZusOOrIPVBER-z6taZHZI");
      }
      const sdTokenNew = props.getProperty("SD_BOT_TOKEN") || "";

      // Dọn dẹp tất cả trigger checkAndSend & checkAndSend_1min cũ (nếu có)
      const deletedTriggers = [];
      const allTriggers = ScriptApp.getProjectTriggers();
      for (let i = 0; i < allTriggers.length; i++) {
        const handlerName = allTriggers[i].getHandlerFunction();
        if (handlerName === "checkAndSend" || handlerName === "checkAndSend_1min") {
          deletedTriggers.push(handlerName);
          ScriptApp.deleteTrigger(allTriggers[i]);
        }
      }

      const remainingTriggers = ScriptApp.getProjectTriggers().map(t => t.getHandlerFunction());

      return _json({
        ok: true,
        sd_bot_token_before: sdTokenOld ? sdTokenOld.substring(0, 15) + "..." : "EMPTY (NOT SET)",
        sd_bot_token_active: sdTokenNew ? sdTokenNew.substring(0, 15) + "..." : "EMPTY",
        send_bot_token_active: sendToken ? sendToken.substring(0, 15) + "..." : "EMPTY",
        deleted_legacy_triggers: deletedTriggers,
        remaining_triggers: remainingTriggers
      });
    }

    if (action === "teardown_gas_train") {
      teardownGasTrain1min();
      const remaining = ScriptApp.getProjectTriggers().map(t => t.getHandlerFunction());
      return _json({ ok: true, action: "teardown_gas_train", remaining_triggers: remaining });
    }

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

    // ── Kích hoạt / Kiểm tra GAS 1-Minute Train ──────────────────────────
    if (action === "setup_gas_train_1min") {
      const deleted = [];
      ScriptApp.getProjectTriggers().forEach(t => {
        const fn = t.getHandlerFunction();
        if (fn === "checkAndSend_1min" || fn === "checkAndSend") {
          ScriptApp.deleteTrigger(t);
          deleted.push(fn);
        }
      });
      ScriptApp.newTrigger("checkAndSend_1min")
        .timeBased()
        .everyMinutes(1)
        .create();
      const remaining = ScriptApp.getProjectTriggers().map(t => t.getHandlerFunction());
      return _json({ ok: true, action: "setup_gas_train_1min", deleted: deleted, triggers: remaining, msg: "GAS 1-min train active!" });
    }

    if (action === "status_gas_train") {
      const triggers = ScriptApp.getProjectTriggers().map(t => ({ fn: t.getHandlerFunction(), type: t.getTriggerSource().toString() }));
      const has1min = triggers.some(t => t.fn === "checkAndSend_1min");
      return _json({ ok: true, triggers: triggers, has_1min_train: has1min });
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

  // ── 1. Reset đệm Cột A vào 03:30 AM đầu ngày ─────────────────────────
  const todayStr = Utilities.formatDate(now, "Asia/Rangoon", "yyyyMMdd");
  const lastDay  = props.getProperty("SD_LAST_RUN_DATE") || "";
  if (todayStr !== lastDay) {
    props.setProperty("SD_LAST_RUN_DATE", todayStr);
    props.deleteProperty(TS_KEY_A1);
    // 🛑 TUYỆT ĐỐI KHÔNG XÓA TS_KEY_AW7: AW7 độc lập 100%, chỉ cập nhật khi ô AW7 có mốc giờ mới!
    Logger.log("🌅 NGÀY MỚI (" + todayStr + ") — Đã reset chìa khóa A1!");
    // ✅ PM-59 FIX RC-2: Sweep dọn tin cũ TẤT CẢ 5 nhóm khi ngày mới bắt đầu.
    // Tin hôm qua >48h Bot API không xóa được → phải chủ động dọn trước khi gửi tin sáng mới.
    try {
      var sweepKeys = ["TIN1_T1","TIN1_T2","TIN1_T3","TIN1_T4","TIN1_CONTROL","TIN2_T1","TIN2_T2","TIN2_T3","TIN2_T4","TIN2_CONTROL","TIN2_CONTROL_SD_ONLY"];
      var sweepChats = { TIN1_T1: SD_GROUPS["T1"], TIN1_T2: SD_GROUPS["T2"], TIN1_T3: SD_GROUPS["T3"], TIN1_T4: SD_GROUPS["T4"], TIN1_CONTROL: SD_GROUPS["CONTROL"], TIN2_T1: SD_GROUPS["T1"], TIN2_T2: SD_GROUPS["T2"], TIN2_T3: SD_GROUPS["T3"], TIN2_T4: SD_GROUPS["T4"], TIN2_CONTROL: SD_GROUPS["CONTROL"], TIN2_CONTROL_SD_ONLY: SD_GROUPS["CONTROL"] };
      for (var sk = 0; sk < sweepKeys.length; sk++) {
        var sKey = sweepKeys[sk];
        var sChatId = sweepChats[sKey];
        if (sChatId) {
          deleteOldMessages_(sChatId, sKey);
          Logger.log("🧹 Daily sweep: xóa tin cũ key=" + sKey + " chat=" + sChatId);
        }
      }
    } catch(sweepErr) {
      Logger.log("⚠️ Daily sweep lỗi (bỏ qua, tiếp tục gửi tin mới): " + sweepErr.message);
    }
  }

  // ── 2. Kiểm tra khung giờ hoạt động (03:30 - 22:30 Myanmar) ────────────
  if (isWebhookCall !== true) {
    if (hour < 3 || hour > 22) return { sent_tin1: false, sent_tin2: false };
    if (hour === 3 && minute < 30) return { sent_tin1: false, sent_tin2: false };
    if (hour === 22 && minute > 30) return { sent_tin1: false, sent_tin2: false };
    // ✅ v660: Bỏ SD_LAST_DONE_MINUTE throttle — Trigger 1 phút đã bị xóa, không còn nguy cơ chạy đè
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
  // CHỈ GỬI khi timestamp AW7 thay đổi, dữ liệu mới và có sự cố thực tế. Không ép gửi lại tin cũ.
  try {
    r2 = processSummaryAwAz(sheet);
  } catch(e2) {
    Logger.log("❌ Lỗi Luồng 2 (AW7 Summary): " + e2.message);
  }

  return { sent_tin1: r1, sent_tin2: r2 };
}


// ============================================================
// LUỒNG 1 — XỬ LÝ A1 / CỘT C (TIN 1 — Chi tiết Site Down)
// Độc lập 100% — Chỉ đọc mốc giờ A1 & ghi chìa khóa TS_KEY_A1
// ============================================================
function processSiteDownColC(sheet, isDirectPush) {
  const storeKey = parseA1Timestamp(sheet);
  if (!storeKey) {
    Logger.log("[Luồng A1] Không tìm thấy timestamp hợp lệ trong A1");
    return false;
  }

  const props   = PropertiesService.getScriptProperties();
  const lastKey = props.getProperty(TS_KEY_A1) || "";


  // 🛑 DEDUP: Nếu timestamp A1 không đổi → bỏ qua (đã gửi rồi)
  // Logic đúng: storeKey mới ≠ lastKey → GỬI NGAY. Không cần freshness check.
  if (storeKey === lastKey && !isDirectPush) {
    Logger.log("[Luồng A1] Timestamp A1 không đổi (" + storeKey.substring(0, 30) + ") → Bỏ qua Luồng 1");
    return false;
  }

  // ✅ Timestamp mới → gửi ngay lập tức (không giới hạn thời gian)
  Logger.log("[Luồng A1] 🆕 Timestamp mới: " + storeKey + " (cũ: " + lastKey.substring(0,30) + ") → Gửi ngay!");

  // ✅ v660: Lưu ngay khóa A1 — Sheet ổn định, chỉ cần so timestamp cũ/mới
  props.setProperty(TS_KEY_A1, storeKey);
  Logger.log("[Luồng A1] 🆕 Timestamp A1 thay đổi: " + storeKey + " (isDirectPush=" + !!isDirectPush + ") → Đang gửi Tin 1...");

  const lastRow = sheet.getLastRow();
  if (lastRow < 1) return false;

  let colC = sheet.getRange(1, 3, lastRow, 1).getValues().flat().map(v => (v || "").toString().trim());

  // ✅ Header chuẩn: C1 và C2
  const header = [colC[0] || "", colC[1] || ""].filter(l => l.length > 0);
  
  // ✅ Danh sách trạm: Từ C10 trở đi
  const rawSites = colC.slice(9).filter(l => l.length > 0 && l !== "..." && !/^Team\s*0?[1-4]/i.test(l));

  const teamDefs = [
    { key: "T1", label: "🟠 Team 1" },
    { key: "T2", label: "🔵 Team 2" },
    { key: "T3", label: "🟢 Team 3" },
    { key: "T4", label: "🟡 Team 4" },
  ];

  const teamSites = { T1: [], T2: [], T3: [], T4: [] };

  for (const line of rawSites) {
    const fields = line.split("|");
    if (fields.length < 2) continue;
    const teamField = fields[1].trim().toUpperCase();
    for (const td of teamDefs) {
      const tn = td.key.slice(1);
      const reg = new RegExp("(?:^|[^A-Z0-9])T0?" + tn + "(?:$|[^A-Z0-9]|\\s*S\\d)", "i");
      if (reg.test(teamField) || new RegExp("Team\\s*0?" + tn + "\\b", "i").test(teamField)) {
        teamSites[td.key].push(line);
        break;
      }
    }
  }

  const teamHeaderMap = {
    T1: colC[3] || "🟠 Team 1",
    T2: colC[4] || "🔵 Team 2",
    T3: colC[5] || "🟢 Team 3",
    T4: colC[6] || "🟡 Team 4",
  };

  // 1. Gửi nhóm CONTROL (Header C1:C2 + C10:C liên tục, không tách bảng Team, chỉ gắn icon màu)
  const controlId = SD_GROUPS["CONTROL"];
  if (controlId) {
    try {
      const colorizedSites = rawSites.map(l => colorizeTeams(l));
      const msg = [...header, "", ...colorizedSites].join("\n");
      if (msg) {
        sendOrEditTelegramPre(controlId, msg, "TIN1_CONTROL", "[Tin1][CONTROL]");
      }
    } catch (e) {
      Logger.log("[Luồng A1][CONTROL] ❌ " + e.message);
    }
  }

  // 2. Gửi sang 4 nhóm Team (Nguyên bản: C4..C7 + C10:C phân theo Team)
  for (const td of teamDefs) {
    try {
      const chatId = SD_GROUPS[td.key];
      if (!chatId || String(chatId).trim() === String(controlId).trim()) continue;
      const summary = teamHeaderMap[td.key];
      const sites   = teamSites[td.key];
      if (sites.length > 0) {
        const parts = summary ? [summary, ...sites] : [...sites];
        sendOrEditTelegramPre(chatId, addKeywordIcons(colorizeTeams(parts.join("\n"))), "TIN1_" + td.key, "[Tin1][" + td.key + "]");
      } else if (summary) {
        sendOrEditTelegramPre(chatId, addKeywordIcons(colorizeTeams(summary)), "TIN1_" + td.key, "[Tin1][" + td.key + "]");
      }
    } catch (e) {
      Logger.log("[Luồng A1][" + td.key + "] ❌ " + e.message);
    }
  }

  const now = new Date();
  const sentSlot = Utilities.formatDate(now, "Asia/Rangoon", "yyyyMMddHH") + (now.getMinutes() < 30 ? "_00" : "_30");
  props.setProperty("SD_LAST_SENT_SLOT", sentSlot);
  Logger.log("[Luồng A1] ✅ Hoàn tất gửi Tin 1!");

  // ⏱️ LIÊN KẾT BOT 5T -> BOT 2D: Đợi đúng 30 giây rồi kích hoạt Bot 2D phát tin ETA Update
  triggerBot2dEta_();

  return true;
}

/**
 * ⏱️ LIÊN KẾT BOT 5T -> BOT 2D:
 * Sau khi Bot 5T gửi xong tin Site Down vào các nhóm, đợi đúng 30 giây
 * rồi kích hoạt Bot 2D (2. TNI Auto Report Daily) phát bản tin ETA Update ngay lập tức.
 */
function triggerBot2dEta_(skipDelay) {
  if (!skipDelay) {
    Logger.log("⏳ Bot 5T đã gửi xong Tin 1. Bắt đầu đếm đúng 30 giây để kích hoạt Bot 2D (ETA Update)...");
    Utilities.sleep(30000);
  } else {
    Logger.log("⚡ Kích hoạt Bot 2D ngay lập tức (skipDelay=true)...");
  }
  try {
    const url = "https://tni-bot.vercel.app/api/search_bot?action=send_eta_reminders";
    const resp = UrlFetchApp.fetch(url, {
      method: "get",
      muteHttpExceptions: true
    });
    Logger.log("✅ Kích hoạt Bot 2D (ETA Update) thành công: HTTP " + resp.getResponseCode() + " | " + resp.getContentText().substring(0, 120));
    return true;
  } catch(e) {
    Logger.log("❌ Lỗi kích hoạt Bot 2D qua Webhook: " + e.message);
    return false;
  }
}


// ============================================================
// LUỒNG 2 — XỬ LÝ AW7 (TIN 2 — Bảng SUMMARY)
// Độc lập 100% — Chỉ đọc mốc giờ ô AW7 & ghi chìa khóa TS_KEY_AW7
// ✅ Restore logic d9f8bfd: đọc thẳng AW7, không wrapper, không freshness/A1 guard
// ============================================================
function processSummaryAwAz(sheet, isDirectPush) {
  const rawVal = sheet.getRange("AW7").getValue();
  Logger.log("[Luồng AW7] rawVal type=" + typeof rawVal + " | instanceof Date=" + (rawVal instanceof Date) + " | raw=" + String(rawVal).substring(0, 60));

  let rawTs;
  if (rawVal instanceof Date) {
    rawTs = Utilities.formatDate(rawVal, "Asia/Rangoon", "dd/MM/yyyy HH:mm");
  } else {
    rawTs = String(rawVal).trim();
  }

  if (!rawTs) {
    Logger.log("[Luồng AW7] Ô AW7 rỗng — Bỏ qua Luồng 2");
    return false;
  }

  const m = rawTs.match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
  const tsKey = m ? m[1] : rawTs.substring(0, 16).trim();

  if (!tsKey) {
    Logger.log("[Luồng AW7] Không bóc tách được timestamp từ AW7 — Bỏ qua Luồng 2");
    return false;
  }

  const props  = PropertiesService.getScriptProperties();
  const lastTs = props.getProperty(TS_KEY_AW7) || "";

  // 🛑 DEDUP KHÓA MỐC GIỜ THUẦN TÚY (RULE PM-83):
  // Bản tin Site Down mới CHỈ xuất hiện khi mốc giờ ô AW7 thay đổi (tsKey !== lastTs).
  // Tuyệt đối KHÔNG so sánh chuỗi nội dung vì công thức tự tính số giờ trạm sập (Duration)
  // sẽ tự động nhảy số sau mỗi 6-10 phút (vd: 0.7h -> 1.6h) làm gửi lại bản tin cũ liên tục!
  Logger.log("[Luồng AW7] tsKey=[" + tsKey + "] lastTs=[" + lastTs + "] match=" + (tsKey === lastTs));

  if (tsKey === lastTs && !isDirectPush) {
    Logger.log("[Luồng AW7] Mốc giờ AW7 chưa đổi (" + tsKey + ") → Chặn 100%, bỏ qua Luồng 2");
    return false;
  }

  // ✅ Mốc giờ mới → gửi ngay!
  Logger.log("[Luồng AW7] 🆕 AW7 có mốc giờ mới: " + tsKey + " (cũ: " + lastTs + ") → Gửi ngay!");

  // ✅ Đọc trực tiếp bảng AW:AZ và gửi nguyên vẹn 100% thông tin có trong ô (thêm Icon)
  let awaz = readAwAz(sheet);

  // ✅ ĐỘC LẬP: Lưu ngay khóa mốc giờ AW7
  props.setProperty(TS_KEY_AW7, tsKey);
  Logger.log("[Luồng AW7] 🆕 Đã lưu khóa TS_KEY_AW7: " + tsKey + " → Đang xử lý Tin 2 (SUMMARY)...");

  const teams = ["T1", "T2", "T3", "T4"];
  let sentCount = 0;

  // Gửi sang 4 nhóm Team (Gửi nguyên vẹn 100% nội dung ô kèm Icon)
  for (const team of teams) {
    try {
      const chatId = SD_GROUPS[team];
      if (!chatId) continue;
      const colIdx = AWAZ_COL[team];
      if (colIdx === undefined) continue;
      const msg = buildAwAzTeamMessage(team, tsKey, awaz, colIdx);
      if (!msg) continue;
      sendOrEditTelegram(chatId, msg, "TIN2_" + team, "[Tin2][" + team + "]");
      sentCount++;
    } catch (err) {
      Logger.log("[Luồng AW7][" + team + "] ❌ " + err.message);
    }
  }

  // Gửi nhóm CONTROL (Tổng hợp cả 4 Team nguyên vẹn 100%)
  const controlId = SD_GROUPS["CONTROL"];
  if (controlId) {
    try {
      const msg = buildAwAzControlMessage(tsKey, awaz);
      if (msg) {
        sendOrEditTelegram(controlId, msg, "TIN2_CONTROL", "[Tin2][CONTROL]");
      }
    } catch(e) {
      Logger.log("[Luồng AW7][CONTROL] ❌ " + e.message);
    }

    // 🔹 TIN THỨ 2 DÀNH RIÊNG CHO GROUP CONTROL: CHỈ TỔNG HỢP SITE DOWN (T1 -> SUB 1 -> T2 -> SUB 2...)
    try {
      Utilities.sleep(500); // Khoảng đệm nhẹ chống rate limit của Telegram
      const sdOnlyMsg = buildSiteDownOnlyControlMessage(tsKey, awaz, sheet);
      if (sdOnlyMsg) {
        sendOrEditTelegram(controlId, sdOnlyMsg, "TIN2_CONTROL_SD_ONLY", "[Tin2][CONTROL_SD_ONLY]");
      }
    } catch(eSd) {
      Logger.log("[Luồng AW7][CONTROL_SD_ONLY] ❌ " + eSd.message);
    }
  }

  // Gửi DM cá nhân
  const ctrlMsg = buildAwAzControlMessage(tsKey, awaz);
  if (ctrlMsg) {
    for (const pid of SD_PERSONAL_IDS) {
      try {
        sendOrEditTelegram(pid, ctrlMsg, "TIN2_P_" + pid, "[Tin2][DM]");
      } catch(e) {}
      Utilities.sleep(200);
    }
  }

  Logger.log("[Luồng AW7] ✅ Hoàn tất xử lý Tin 2 SUMMARY (Đã gửi " + sentCount + " nhóm)!");
  return sentCount > 0;
}


// ============================================================
// HELPER PARSERS & UTILITIES
// ============================================================

/**
 * 🛡️ FRESHNESS CHECK: Kiểm tra timestamp dữ liệu có quá cũ không
 * Nếu dữ liệu cách hiện tại > maxMinutes phút → return false (quá cũ, bỏ qua)
 * @param {string} tsStr - Timestamp dạng "dd/MM/yyyy HH:mm" hoặc "dd/MM/yyyy HH:mm:ss"
 * @param {number} maxMinutes - Số phút tối đa cho phép (mặc định 30)
 * @returns {boolean} true = còn tươi, false = quá cũ
 */
function isDataFresh_(tsStr, maxMinutes) {
  if (!tsStr) return true; // Không parse được → cho qua (fallback an toàn)
  maxMinutes = maxMinutes || 30;

  // Bóc tách dd/MM/yyyy HH:mm(:ss)
  var m = tsStr.match(/(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return true; // Không parse được (VD: RAW_...) → cho qua

  // Interpret timestamp as Myanmar time (UTC+6:30 = +390 phút)
  var myanmarOffsetMs = 390 * 60 * 1000;
  var dataUtcMs = Date.UTC(
    parseInt(m[3], 10),           // year
    parseInt(m[2], 10) - 1,       // month (0-indexed)
    parseInt(m[1], 10),           // day
    parseInt(m[4], 10),           // hour
    parseInt(m[5], 10),           // minute
    m[6] ? parseInt(m[6], 10) : 0 // second
  ) - myanmarOffsetMs;

  var nowUtcMs = new Date().getTime();
  var diffMin = (nowUtcMs - dataUtcMs) / 60000;

  Logger.log("[isDataFresh_] Data: " + tsStr + " | Now MMT: " + Utilities.formatDate(new Date(), "Asia/Rangoon", "dd/MM/yyyy HH:mm") + " | Diff: " + diffMin.toFixed(1) + " min | Fresh: " + (diffMin <= maxMinutes));

  return diffMin <= maxMinutes;
}

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
  // 1. Thử đọc AW7 (Cell down / Site down)
  try {
    const rawVal7 = sheet.getRange("AW7").getValue();
    const raw7 = (rawVal7 instanceof Date)
      ? Utilities.formatDate(rawVal7, "Asia/Rangoon", "dd/MM/yyyy HH:mm")
      : (rawVal7 || "").toString();
    const m1 = raw7.match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
    if (m1) return m1[1].trim();
  } catch(e) {}

  // 2. Thử đọc AW6 (Site down header nếu có)
  try {
    const rawVal6 = sheet.getRange("AW6").getValue();
    const raw6 = (rawVal6 instanceof Date)
      ? Utilities.formatDate(rawVal6, "Asia/Rangoon", "dd/MM/yyyy HH:mm")
      : (rawVal6 || "").toString();
    const m2 = raw6.match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
    if (m2) return m2[1].trim();
  } catch(e) {}

  return null;
}

/**
 * ⏱️ Chuyển chuỗi timestamp "dd/MM/yyyy HH:mm" thành số phút để so sánh thời gian chính xác
 */
function parseTsToMinutes_(tsStr) {
  if (!tsStr) return 0;
  const m = tsStr.match(/(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})/);
  if (!m) return 0;
  const day   = parseInt(m[1], 10);
  const month = parseInt(m[2], 10) - 1;
  const year  = parseInt(m[3], 10);
  const hour  = parseInt(m[4], 10);
  const min   = parseInt(m[5], 10);
  return Math.floor(Date.UTC(year, month, day, hour, min) / 60000);
}

/**
 * ⚡ Định dạng danh sách nhân viên trong phần Site down xuống hàng theo từng người cho dễ nhìn
 */
function formatSiteDownStaffLines_(bodyRaw) {
  if (!bodyRaw) return "";
  var m = bodyRaw.match(/^(.*?\s*=\s*\/?[0-9]+\s*=\s*)(.*)$/);
  if (!m) return bodyRaw;
  var head = m[1].trim();
  var rest = m[2].trim();
  if (rest === "/0" || rest === "0" || !rest) {
    return head + " 0";
  }
  var parts = rest.split(/\s+-\s+(?:\/)?/);
  var out = [head];
  for (var i = 0; i < parts.length; i++) {
    var sp = parts[i].trim().replace(/^\/+/, "");
    if (sp) {
      out.push("• " + sp);
    }
  }
  return out.join("\n");
}

function readAwAz(sheet) {
  // ✅ Mở rộng dải ô AW7:AZ16 (10 dòng từ dòng 7 đến dòng 16)
  return sheet.getRange(7, 49, 10, 4).getValues();
}

function buildAwAzTeamMessage(teamKey, ts, awaz, colIdx) {
  const label   = "Team " + teamKey.replace("T", "");
  const numRows = awaz.length;
  const lines   = [];
  lines.push("📊 <b>SUMMARY — " + label + "</b>");
  lines.push("📅 " + escHtml(ts));
  lines.push("━".repeat(26));

  for (let r = 0; r < numRows; r++) {
    const txt = ((awaz[r] || [])[colIdx] || "").toString().trim();
    if (!txt || txt === "..." || txt === "null" || txt === "undefined" || txt === "-" || txt === "0") continue;
    const cleanRaw = txt.replace(/[*_`]/g, "");
    if (r < AWAZ_LABELS.length) {
      const labelDef = AWAZ_LABELS[r];
      const labelName = labelDef.name;
      const prefixRegex = new RegExp("^" + labelName.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&") + "\\s*:\\s*", "i");
      let bodyRaw = cleanRaw.replace(prefixRegex, "").trim();
      // Xuống hàng theo từng tên nhân viên trong phần Site down cho dễ nhìn
      if (r === 0 || labelName === "Site down") {
        bodyRaw = formatSiteDownStaffLines_(bodyRaw);
      }
      // Tách | Battery Temperature High / Smoke / DOOR thành dòng riêng + icon
      bodyRaw = bodyRaw.replace(/\|\s*Battery Temperature High:/gi, "\n🌡️ Battery Temperature High:");
      bodyRaw = bodyRaw.replace(/\|\s*Smoke:/gi, "\n💨 Smoke:");
      bodyRaw = bodyRaw.replace(/\|\s*DOOR:/gi, "\n🚪 DOOR:");
      lines.push(labelDef.emoji + " <b>" + escHtml(labelName) + ":</b> " + escHtml(bodyRaw));
    } else {
      const lm = cleanRaw.match(/^([^:]+):\s*(.*)$/);
      if (lm) {
        const lb = lm[1].trim();
        const body = lm[2].trim();
        lines.push("📌 <b>" + escHtml(lb) + ":</b> " + escHtml(body));
      } else {
        lines.push("📌 " + escHtml(cleanRaw));
      }
    }
  }
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
    const teamLines = [];
    for (let r = 0; r < numRows; r++) {
      const txt = ((awaz[r] || [])[t.col] || "").toString().trim();
      if (!txt || txt === "..." || txt === "null" || txt === "undefined" || txt === "-" || txt === "0") continue;
      const cleanRaw = txt.replace(/[*_`]/g, "");
      if (r < AWAZ_LABELS.length) {
        const labelDef = AWAZ_LABELS[r];
        const labelName = labelDef.name;
        const prefixRegex = new RegExp("^" + labelName.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&") + "\\s*:\\s*", "i");
        let bodyRaw = cleanRaw.replace(prefixRegex, "").trim();
        // Xuống hàng theo từng tên nhân viên trong phần Site down cho dễ nhìn
        if (r === 0 || labelName === "Site down") {
          bodyRaw = formatSiteDownStaffLines_(bodyRaw);
        }
        // Tách | Battery Temperature High / Smoke / DOOR thành dòng riêng + icon
        bodyRaw = bodyRaw.replace(/\|\s*Battery Temperature High:/gi, "\n🌡️ Battery Temperature High:");
        bodyRaw = bodyRaw.replace(/\|\s*Smoke:/gi, "\n💨 Smoke:");
        bodyRaw = bodyRaw.replace(/\|\s*DOOR:/gi, "\n🚪 DOOR:");
        teamLines.push(labelDef.emoji + " <b>" + escHtml(labelName) + ":</b> " + escHtml(bodyRaw));
      } else {
        const lm = cleanRaw.match(/^([^:]+):\s*(.*)$/);
        if (lm) {
          const lb = lm[1].trim();
          const body = lm[2].trim();
          teamLines.push("📌 <b>" + escHtml(lb) + ":</b> " + escHtml(body));
        } else {
          teamLines.push("📌 " + escHtml(cleanRaw));
        }
      }
    }
    if (teamLines.length > 0) {
      lines.push("");
      lines.push(t.emoji + " <b>" + t.label + "</b>");
      lines.push("─".repeat(20));
      lines.push(...teamLines);
    }
  }
  return lines.join("\n");
}

/**
 * 🗺️ Quét bảng trạm Site Down từ C10:C để tạo bảng ánh xạ nhân sự -> Sub-team
 * Ví dụ: "aung la pyae oo" -> "T1 S1", "si thu ye htun" -> "T2 S1"
 */
function getStaffSubteamMap_(sheet) {
  const map = {};
  if (!sheet) return map;
  try {
    const lastRow = sheet.getLastRow();
    if (lastRow >= 10) {
      const vals = sheet.getRange(10, 3, lastRow - 9, 1).getValues();
      for (let i = 0; i < vals.length; i++) {
        const line = String(vals[i][0] || "").trim();
        if (!line || line === "..." || line.toLowerCase().startsWith("team")) continue;
        const parts = line.split("|").map(p => p.trim());
        if (parts.length >= 7) {
          const teamCol = parts[1].toUpperCase();
          const ftName  = parts[6];
          if (ftName && teamCol) {
            map[ftName.toLowerCase()] = teamCol;
          }
        }
      }
    }
  } catch(e) {
    Logger.log("[getStaffSubteamMap_] Lỗi: " + e.message);
  }
  return map;
}

/**
 * ⚡ Xây dựng bản tin chuyên biệt CHỈ TỔNG HỢP SITE DOWN cho Group Control
 * Phân chia theo: Team 1 Dawei -> Sub Team 1 -> Team 2 Myeik -> Sub Team 2 -> Team 3 Bokpyin -> Sub Team 3 -> Team 4 Kawthoung
 * Dưới mỗi Team: Tên nhân viên: nội dung trạm, xuống hàng từng người
 */
function buildSiteDownOnlyControlMessage(ts, awaz, sheet) {
  try {
    const lines = [];
    lines.push("📊 <b>SUMMARY — SITE DOWN ALL TEAMS</b>");
    lines.push("📅 " + escHtml(ts));
    lines.push("━".repeat(26));

    // Bảng ánh xạ nhân viên -> Sub-team từ C10:C
    const subMap = getStaffSubteamMap_(sheet);

    // Fallback định sẵn nếu C10:C chưa kịp tải
    const knownSubs = {
      "aung la pyae oo": "T1 S1",
      "si thu ye htun":  "T2 S1",
      "aye min soe":     "T2 S1",
      "min paing oo":    "T2 S1",
      "tin naing lin":   "T3 S1"
    };

    const teamConfigs = [
      { col: 0, key: "T1", label: "Team 1 Dawei",     emoji: "🟠", subKey: "T1 S1", subLabel: "Sub Team 1" },
      { col: 1, key: "T2", label: "Team 2 Myeik",     emoji: "🔵", subKey: "T2 S1", subLabel: "Sub Team 2" },
      { col: 2, key: "T3", label: "Team 3 Bokpyin",   emoji: "🟢", subKey: "T3 S1", subLabel: "Sub Team 3" },
      { col: 3, key: "T4", label: "Team 4 Kawthoung", emoji: "🟡", subKey: "",      subLabel: "" }
    ];

    for (let i = 0; i < teamConfigs.length; i++) {
      const cfg = teamConfigs[i];
      const rawTxt = ((awaz[0] || [])[cfg.col] || "").toString().trim();
      const clean = rawTxt.replace(/[*_`]/g, "");

      const m = clean.match(/^(?:Site down\s*:\s*)?(.*?\s*=\s*\/?[0-9]+\s*=\s*)(.*)$/i);
      const rest = m ? m[2].trim() : "";

      const teamItems = [];
      const subItems  = [];

      if (rest && rest !== "/0" && rest !== "0") {
        const parts = rest.split(/\s+-\s+(?:\/)?/);
        for (let j = 0; j < parts.length; j++) {
          const p = parts[j].trim().replace(/^\/+/, "");
          if (!p) continue;
          const colonIdx = p.indexOf(":");
          if (colonIdx !== -1) {
            const staffName = p.substring(0, colonIdx).trim().toLowerCase();
            const mappedTeam = subMap[staffName] || knownSubs[staffName] || "";
            if (mappedTeam.indexOf("S1") !== -1 || mappedTeam.indexOf("SUB") !== -1) {
              subItems.push("• " + p);
            } else {
              teamItems.push("• " + p);
            }
          } else {
            teamItems.push("• " + p);
          }
        }
      }

      // 1. Team chính
      const cntTeam = teamItems.reduce((acc, it) => acc + (it.match(/TNI\d{4}/g) || []).length, 0);
      lines.push("");
      lines.push(cfg.emoji + " <b>" + cfg.label + "</b>");
      if (teamItems.length > 0) {
        lines.push("⚡ <b>Site down:</b> = /" + cntTeam + " =");
        lines.push(...teamItems);
      } else {
        lines.push("⚡ <b>Site down:</b> 0");
      }

      // 2. Sub-team (nếu có cấu hình Sub-team)
      if (cfg.subLabel) {
        const cntSub = subItems.reduce((acc, it) => acc + (it.match(/TNI\d{4}/g) || []).length, 0);
        lines.push("");
        lines.push(cfg.emoji + " <b>" + cfg.subLabel + "</b>");
        if (subItems.length > 0) {
          lines.push("⚡ <b>Site down:</b> = /" + cntSub + " =");
          lines.push(...subItems);
        } else {
          lines.push("⚡ <b>Site down:</b> 0");
        }
      }
    }

    return lines.join("\n");
  } catch(err) {
    Logger.log("[buildSiteDownOnlyControlMessage] ❌ Lỗi: " + err.message);
    return "";
  }
}

// ✅ v660: isTimestampFresh_ đã bị loại bỏ — Sheet ổn định, chỉ cần so timestamp A1/AW7 cũ vs mới là đủ.


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

// 🛡️ HÀM KIỂM TRA NỘI DUNG RỖNG: Đảm bảo có nội dung trước khi gửi Telegram
function isValidMessageContent_(text) {
  if (!text) return false;
  var s = text.toString().trim();
  if (!s || s === "..." || s === "null" || s === "undefined") return false;
  return s.length >= 5;
}

function sendOrEditTelegram(chatId, text, msgKey, tag) {
  if (!isValidMessageContent_(text)) {
    Logger.log("[sendOrEditTelegram] ⚠️ Nội dung rỗng hoặc không có sự cố thực tế → BỎ QUA KHÔNG GỬI (" + tag + ")");
    return;
  }
  deleteOldMessages_(chatId, msgKey);
  Utilities.sleep(200);
  const props  = PropertiesService.getScriptProperties();
  const idKey  = "SD_MSGID_" + msgKey;
  const newIds = sendTelegramCollectIds_(chatId, text, tag);
  const currentUnremoved = getSavedMsgIds_(msgKey);
  const combinedIds = Array.from(new Set([...currentUnremoved, ...newIds]));
  props.setProperty(idKey, JSON.stringify(combinedIds));
}

function sendOrEditTelegramPre(chatId, plainContent, msgKey, tag) {
  if (!isValidMessageContent_(plainContent)) {
    Logger.log("[sendOrEditTelegramPre] ⚠️ Nội dung rỗng hoặc không có sự cố thực tế → BỎ QUA KHÔNG GỬI (" + tag + ")");
    return;
  }
  const props  = PropertiesService.getScriptProperties();
  const idKey  = "SD_MSGID_" + msgKey;
  
  // ✅ Xóa tin cũ của chính luồng này và gửi tin mới xuống cuối nhóm để luôn nổi bật
  deleteOldMessages_(chatId, msgKey);
  Utilities.sleep(200);
  const newIds = sendTelegramPreCollectIds_(chatId, plainContent, tag);
  const currentUnremoved = getSavedMsgIds_(msgKey);
  const combinedIds = Array.from(new Set([...currentUnremoved, ...newIds]));
  props.setProperty(idKey, JSON.stringify(combinedIds));
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
      if (res.ok && res.result && res.result.message_id) {
        ids.push(res.result.message_id);
      } else {
        Logger.log(tag + " ⚠️ HTML send fail: " + (res.description || "error") + " -> retry plain text");
        const resp2 = UrlFetchApp.fetch(url, {
          method: "post", contentType: "application/json",
          payload: JSON.stringify({ chat_id: chatId, text: chunk }),
          muteHttpExceptions: true,
        });
        const res2 = JSON.parse(resp2.getContentText());
        if (res2.ok && res2.result && res2.result.message_id) ids.push(res2.result.message_id);
      }
    } catch(e) {
      Logger.log(tag + " ❌ sendTelegramCollectIds_ error: " + e.message);
    }
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
      if (res.ok && res.result && res.result.message_id) {
        ids.push(res.result.message_id);
      } else {
        Logger.log(tag + " ⚠️ <pre> send fail: " + (res.description || "error") + " -> retry plain text");
        const resp2 = UrlFetchApp.fetch(url, {
          method: "post", contentType: "application/json",
          payload: JSON.stringify({ chat_id: chatId, text: chunk }),
          muteHttpExceptions: true,
        });
        const res2 = JSON.parse(resp2.getContentText());
        if (res2.ok && res2.result && res2.result.message_id) ids.push(res2.result.message_id);
      }
    } catch(e) {
      Logger.log(tag + " ❌ sendTelegramPreCollectIds_ error: " + e.message);
    }
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
  if (!messageId) return false;
  // ✅ PM-59 FIX: Chỉ dùng SD_BOT_TOKEN chính thức. TUYỆT ĐỐI CẤM hardcode token backup cũ.
  var token = SD_BOT_TOKEN;
  if (!token) {
    Logger.log("[deleteTelegramMsgBot_] ❌ SD_BOT_TOKEN rỗng — không thể xóa msg_id=" + messageId);
    return false;
  }
  try {
    var resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/deleteMessage", {
      method: "post", contentType: "application/json",
      payload: JSON.stringify({ chat_id: chatId, message_id: messageId }),
      muteHttpExceptions: true,
    });
    var res = JSON.parse(resp.getContentText());
    if (res.ok === true) {
      Logger.log("[deleteTelegramMsgBot_] 🗑️ Xóa thành công msg_id=" + messageId + " khỏi " + chatId);
      return true;
    }
    if (res.description && res.description.indexOf("message to delete not found") >= 0) {
      Logger.log("[deleteTelegramMsgBot_] ℹ️ msg_id=" + messageId + " đã được xóa trước đó (not found)");
      return true;
    }
    if (res.description && (res.description.indexOf("can't be deleted") >= 0 || res.description.indexOf("message_id_invalid") >= 0)) {
      Logger.log("[deleteTelegramMsgBot_] ⏳ msg_id=" + messageId + " quá 48h hoặc invalid → bỏ qua: " + res.description);
      return true; // Coi là "done" để dọn khỏi Properties, tránh loop mãi
    }
    Logger.log("[deleteTelegramMsgBot_] ⚠️ Xóa thất bại msg_id=" + messageId + ": " + (res.description || JSON.stringify(res)));
    return false;
  } catch(e) {
    Logger.log("[deleteTelegramMsgBot_] ❌ Exception xóa msg_id=" + messageId + ": " + e.message);
    return false;
  }
}

function deleteOldMessages_(chatId, msgKey) {
  const remainingIds = [];
  try {
    const oldIds = getSavedMsgIds_(msgKey);
    for (let i = 0; i < oldIds.length; i++) {
      const mid = oldIds[i];
      const ok = deleteTelegramMsgBot_(chatId, mid);
      if (!ok) {
        remainingIds.push(mid);
      }
    }
  } catch(e) {
    Logger.log("[deleteOldMessages_] ⚠️ Lỗi xóa tin cũ (" + msgKey + "): " + e.message);
  }

  try {
    const idKey = "SD_MSGID_" + msgKey;
    if (remainingIds.length === 0) {
      PropertiesService.getScriptProperties().deleteProperty(idKey);
    } else {
      PropertiesService.getScriptProperties().setProperty(idKey, JSON.stringify(remainingIds.slice(-10)));
      Logger.log("[deleteOldMessages_] ⚠️ Còn " + remainingIds.length + " msg_id chưa xóa được, lưu lại để retry lần sau: " + JSON.stringify(remainingIds));
    }
  } catch(e) {}
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
  s = s.replace(/(?:^|\n|\s*)>(?:\s*)(Link down:)/gi, "\n🔗 Link down:");
  s = s.replace(/(?:^|\n|\s*)>(?:\s*)(Duty:)/gi, "\n🕒 Duty:");
  s = s.replace(/\|\s*(DG Abnormal:)/gi, "\n⚙️ DG Abnormal:");
  s = s.replace(/\|\s*(Link down:)/gi, "\n🔗 Link down:");
  s = s.replace(/\|\s*(Cell down:)/gi, "\n🔴 Cell down:");
  s = s.replace(/\|\s*(Duty:)/gi, "\n🕒 Duty:");
  s = s.replace(/(?:^|\s)(Duty:)/gi, "\n🕒 Duty:");

  s = s.replace(/(?:(?:^|\n|\s*)>|\|)\s*(DG Run>16H:)\s*([^\n\|]*)/gi, function(match, keyword, dataStr) {
     let c = dataStr.replace(/[*_]/g, "").trim();
     let icon = (c && c !== "0" && c !== "-" && c.toLowerCase() !== "none") ? "❌" : "✅";
     return "\n" + icon + " " + keyword + " " + dataStr;
  });

  // Battery Temperature High, Smoke, DOOR — xuống hàng + icon riêng
  s = s.replace(/(?:(?:^|\n|\s*)>|\|)\s*(Battery Temperature High:)/gi, "\n🌡️ Battery Temperature High:");
  s = s.replace(/(?:(?:^|\n|\s*)>|\|)\s*(Smoke:)/gi, "\n💨 Smoke:");
  s = s.replace(/(?:(?:^|\n|\s*)>|\|)\s*(DOOR:)/gi, "\n🚪 DOOR:");

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
    // 1. Dispatch DUY NHẤT 1 LẦN to MON6879/tni-sitedown-relay botlookup_relay.yml
    UrlFetchApp.fetch("https://api.github.com/repos/MON6879/tni-sitedown-relay/actions/workflows/botlookup_relay.yml/dispatches", {
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
// GAS 1-MINUTE TRAIN — ĐẦU TÀU GAS ĐẾM THỜI GIAN (03:30–22:00)
// Chạy hoàn toàn độc lập trên Google Servers, không liên quan GitHub Actions.
// Phụ trách: Luồng AW7 Summary (Tin 2) — phát hiện thay đổi và gửi ngay.
// ============================================================

/**
 * ⏱️ Wrapper 1 phút — được gọi bởi GAS time-driven trigger.
 * Kiểm tra khung giờ 03:30–22:00 Myanmar trước khi chạy checkAndSend().
 */
function checkAndSend_1min() {
  const now    = new Date();
  const hour   = parseInt(Utilities.formatDate(now, "Asia/Rangoon", "H"),  10);
  const minute = parseInt(Utilities.formatDate(now, "Asia/Rangoon", "m"),  10);

  // Khung giờ hoạt động 03:30 – 22:00 Myanmar
  const afterStart  = (hour > 3) || (hour === 3 && minute >= 30);
  const beforeEnd   = (hour < 22) || (hour === 22 && minute === 0);
  if (!afterStart || !beforeEnd) {
    Logger.log("[1min-train] 🌙 Ngoài khung giờ 03:30–22:00 MMT (" + hour + ":" + (minute < 10 ? "0" : "") + minute + ") — Bỏ qua.");
    return;
  }

  Logger.log("[1min-train] ⏱️ " + Utilities.formatDate(now, "Asia/Rangoon", "HH:mm:ss") + " MMT — Chạy checkAndSend()...");
  try {
    const result = checkAndSend(false);
    Logger.log("[1min-train] ✅ Kết quả: sent_tin1=" + result.sent_tin1 + " sent_tin2=" + result.sent_tin2);
  } catch(ex) {
    Logger.log("[1min-train] ❌ Lỗi: " + ex.message);
  }
}

/**
 * 🔧 Đặt GAS 1-Minute Trigger cho checkAndSend_1min().
 * Chạy 1 lần duy nhất để thiết lập. Tự động dọn trigger cũ trước khi tạo mới.
 * CÁCH CHẠY: Mở GAS Editor → chọn hàm setupGasTrain1min → Run.
 */
function setupGasTrain1min() {
  // 1. Xóa tất cả trigger cũ của checkAndSend_1min và checkAndSend (legacy)
  const deleted = [];
  ScriptApp.getProjectTriggers().forEach(t => {
    const fn = t.getHandlerFunction();
    if (fn === "checkAndSend_1min" || fn === "checkAndSend") {
      ScriptApp.deleteTrigger(t);
      deleted.push(fn);
    }
  });
  Logger.log("[setupGasTrain1min] 🗑️ Đã xóa " + deleted.length + " trigger cũ: " + deleted.join(", "));

  // 2. Tạo trigger mới: mỗi 1 phút
  ScriptApp.newTrigger("checkAndSend_1min")
    .timeBased()
    .everyMinutes(1)
    .create();

  // 3. Xác nhận
  const remaining = ScriptApp.getProjectTriggers().map(t => t.getHandlerFunction());
  Logger.log("[setupGasTrain1min] ✅ GAS 1-Minute Train đã được tạo! Triggers hiện tại: " + remaining.join(", "));
  Logger.log("[setupGasTrain1min] ⏰ checkAndSend_1min() sẽ chạy mỗi 1 phút, 03:30–22:00 MMT, hoàn toàn độc lập GitHub Actions.");
}

/**
 * 🔧 Dọn sạch GAS 1-Minute Trigger (khi cần tắt tạm).
 */
function teardownGasTrain1min() {
  const deleted = [];
  ScriptApp.getProjectTriggers().forEach(t => {
    const fn = t.getHandlerFunction();
    if (fn === "checkAndSend_1min" || fn === "checkAndSend") {
      ScriptApp.deleteTrigger(t);
      deleted.push(fn);
    }
  });
  Logger.log("[teardownGasTrain1min] 🛑 Đã xóa " + deleted.length + " trigger: " + deleted.join(", "));
}

// ============================================================
// TIỆN ÍCH CHẠY THỬ
// ============================================================

// 🧪 CHẠY THỬ ĐỘC LẬP 2 LUỒNG
function testSendNow() {
  const props = PropertiesService.getScriptProperties();
  props.deleteProperty(TS_KEY_A1);
  const ss    = SpreadsheetApp.openById(SD_SHEET_ID);
  const sheet = getSheetByGid(ss, SD_SHEET_GID);
  if (!sheet) return;
  processSiteDownColC(sheet);
  processSummaryAwAz(sheet);
}

// 🧪 Test 1-min wrapper độc lập
function testCheckAndSend1min() {
  checkAndSend_1min();
}
