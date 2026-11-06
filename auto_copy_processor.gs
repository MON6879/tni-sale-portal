// ============================================================
// SYSTEM: Auto Copy & Delete Processor
// ============================================================
// Chức năng: 
//   - Đọc bảng cấu hình động tại Spreadsheet trung tâm
//   - Tự động chạy Copy-Paste 123 & Xóa hàng theo điều kiện
//   - Lịch chạy: Chạy tự động mỗi 15 phút (trong khung giờ làm việc)
// ============================================================

const CONFIG_SS_ID = "19RBlwehMC6BLoueaTEzsJHMx4puB0CTE5i5x79-uI6c";
const CONFIG_TAB_NAME = "Auto_Copy_Config";

// Bộ nhớ đệm (Cache) để tránh mở một file nhiều lần, giúp script chạy nhanh gấp 5-10 lần
const ssCache_ = {};
function getSpreadsheetCached_(id) {
  if (!id) return null;
  if (!ssCache_[id]) {
    ssCache_[id] = SpreadsheetApp.openById(id);
  }
  return ssCache_[id];
}

/**
 * Tạo tab cấu hình mẫu nếu chưa tồn tại
 * Chạy thủ công 1 lần để khởi tạo bảng cấu hình
 */
function initConfigTab() {
  try {
    const ss = getSpreadsheetCached_(CONFIG_SS_ID);
    let sheet = ss.getSheetByName(CONFIG_TAB_NAME);
    if (!sheet) {
      sheet = ss.insertSheet(CONFIG_TAB_NAME);
      const headers = [
        "Link dữ liệu nguồn (A)",
        "Tên sheet cần copy (B) [Ví dụ: Sheet1!A:AA]",
        "Cột điều kiện (C) [Ví dụ: A]",
        "Tên tìm kiếm điều kiện (D) [Ví dụ: New]",
        "Link cần dán (E)",
        "Sheet cần dán (F) [Ví dụ: Sheet2!A:H]",
        "Link cần xóa (G)",
        "Cột điều kiện xóa (H) [Ví dụ: Sheet2!A]",
        "Tên tìm kiếm điều kiện để xóa (I) [Ví dụ: Site OK]"
      ];
      sheet.appendRow(headers);
      sheet.getRange(1, 1, 1, 9).setFontWeight("bold")
           .setBackground("#D9E1F2").setHorizontalAlignment("center");
      sheet.setFrozenRows(1);
      
      // Định dạng độ rộng cột
      for (let i = 1; i <= 9; i++) {
        sheet.setColumnWidth(i, 200);
      }
      SpreadsheetApp.flush();
      Logger.log("✅ Đã tạo tab cấu hình '" + CONFIG_TAB_NAME + "' thành công.");
    } else {
      Logger.log("ℹ️ Tab cấu hình '" + CONFIG_TAB_NAME + "' đã tồn tại.");
    }
  } catch (e) {
    Logger.log("❌ Lỗi khi khởi tạo tab cấu hình: " + e.message);
  }
}

/**
 * HÀM CHẠY THỬ NGHIỆM THỦ CÔNG (Bỏ qua cổng thời gian)
 * Anh có thể chọn và chạy hàm này từ Apps Script Editor bất kỳ lúc nào để test hệ thống copy.
 */
function runAutoCopyProcessorManual() {
  Logger.log("🧪 Đang bắt đầu chạy thử nghiệm thủ công (Bỏ qua giới hạn khung giờ)...");
  runAutoCopyProcessor(true);
}



/**
 * Hàm kiểm tra nhanh nội dung các ô A3, A4 để phân tích lỗi công thức
 */
function runDebugTeam3Cells() {
  try {
    const ss = SpreadsheetApp.openById("1Z2E4gSGXpYbjexfZJGNDglACYB9Zn46VXuiO2GGSGqQ");
    const sh = ss.getSheetByName("3.1 Update Assign");
    if (!sh) {
      Logger.log("❌ Không tìm thấy sheet '3.1 Update Assign'");
      return;
    }
    Logger.log("🔍 [Debug Team 3]");
    Logger.log("A3 Value: " + sh.getRange("A3").getValue());
    Logger.log("A3 Formula: " + sh.getRange("A3").getFormula());
    Logger.log("A4 Value: " + sh.getRange("A4").getValue());
    Logger.log("A4 Formula: " + sh.getRange("A4").getFormula());
    Logger.log("G4 Value: " + sh.getRange("G4").getValue());
  } catch (e) {
    Logger.log("❌ Lỗi debug: " + e.message);
  }
}

/**
 * Hàm kiểm tra cấu trúc và dữ liệu của Team 4
 */
function runDebugTeam4() {
  try {
    const ss = SpreadsheetApp.openById("1s53UHIDF-T9P4EuNB8XoE9yTpoNmDyrQaEe_VJP6f9o");
    const sheets = ss.getSheets();
    for (let i = 0; i < sheets.length; i++) {
      const sh = sheets[i];
      Logger.log("=== Sheet: " + sh.getName() + " ===");
      Logger.log("Row 1: " + JSON.stringify(sh.getRange(1, 1, 1, 15).getValues()[0]));
      Logger.log("Row 2: " + JSON.stringify(sh.getRange(2, 1, 1, 15).getValues()[0]));
      Logger.log("Row 3: " + JSON.stringify(sh.getRange(3, 1, 1, 15).getValues()[0]));
      Logger.log("Row 4: " + JSON.stringify(sh.getRange(4, 1, 1, 15).getValues()[0]));
      Logger.log("Row 5: " + JSON.stringify(sh.getRange(5, 1, 1, 15).getValues()[0]));
    }
  } catch (e) {
    Logger.log("❌ Lỗi debug Team 4: " + e.message);
  }
}

/**
 * Hàm xử lý chính: Quét cấu hình và thực thi Copy-Paste + Xóa dòng
 * @param {boolean} bypassTimeGate - Nếu là true, bỏ qua kiểm tra khung giờ làm việc
 */
function runAutoCopyProcessor(bypassTimeGate) {
  if (bypassTimeGate !== true && !isWithinCopyActiveWindows_()) {
    Logger.log("😴 Ngoài khung giờ hoạt động Copy (05:00-20:00 Myanmar) — Dừng tiến trình.");
    return;
  }

  // 🛡️ TẦNG 1: LOCK TOÀN CỤC CHỐNG CHẠY ĐỒNG THỜI (RACE CONDITION)
  const lock = LockService.getScriptLock();
  const hasLock = lock.tryLock(10000); // Chờ tối đa 10s để lấy lock
  if (!hasLock) {
    Logger.log("⚠️ Tiến trình Auto Copy khác đang chạy. Bỏ qua phiên này để chống xung đột/trùng lặp.");
    return;
  }

  try {
    Logger.log("🚀 Bắt đầu tiến trình Auto Copy & Delete...");
    
    // Tự động chạy quét gửi tin nhắn BOD assign trước khi tiến hành copy/xóa dữ liệu nguồn
    try {
      if (typeof checkBodAssign === "function") {
        Logger.log("🔄 Đang chạy quét gửi tin nhắn BOD assign trước khi copy...");
        checkBodAssign();
      }
    } catch (eBod) {
      Logger.log("⚠️ Cảnh báo chạy checkBodAssign trong copy processor: " + eBod.message);
    }

    const errorRows = []; // Thu thập các dòng lỗi để tổng hợp báo cáo
    let ssConfig;
    try {
      ssConfig = getSpreadsheetCached_(CONFIG_SS_ID);
    } catch (e) {
      Logger.log("❌ Không thể mở Spreadsheet cấu hình với ID: " + CONFIG_SS_ID + ". Lỗi: " + e.message);
      return;
    }

  const sheetConfig = ssConfig.getSheetByName(CONFIG_TAB_NAME);
  if (!sheetConfig) {
    Logger.log("❌ Không tìm thấy tab cấu hình: " + CONFIG_TAB_NAME + ". Hãy chạy initConfigTab() trước.");
    return;
  }

  const lastRow = sheetConfig.getLastRow();
  if (lastRow < 2) {
    Logger.log("ℹ️ Bảng cấu hình trống (không có dòng dữ liệu nào).");
    return;
  }

  // Đọc dữ liệu từ cột A đến J (cột 1 đến 10)
  const configRows = sheetConfig.getRange(2, 1, lastRow - 1, 10).getValues();
  Logger.log("Tìm thấy " + configRows.length + " dòng cấu hình cần xử lý.");

  for (let i = 0; i < configRows.length; i++) {
    const rowIdx = i + 2;
    const row = configRows[i];
    
    // .getValues() đã tự động đọc giá trị cuối cùng được tính toán bởi công thức Excel/Sheets
    const sourceLink    = String(row[0] || "").trim();
    const sourceSheet   = String(row[1] || "").trim();
    const sourceColCond = String(row[2] || "").trim();
    const sourceValCond = String(row[3] || "").trim();
    const targetLink    = String(row[4] || "").trim();
    const targetSheet   = String(row[5] || "").trim();
    const deleteLink    = String(row[6] || "").trim();
    const deleteColCond = String(row[7] || "").trim();
    const deleteValCond = String(row[8] || "").trim();
    const sortConfig    = String(row[9] || "").trim();

    Logger.log("--------------------------------------------------");
    Logger.log("Dòng cấu hình #" + rowIdx + ":");

    // ========================================================
    // PHẦN 1: XÓA HÀNG Ở SHEET KHÁC (theo cấu hình cột G, H, I)
    // ========================================================
    if (deleteLink && deleteColCond && deleteValCond) {
      try {
        const delSSId = extractSsId_(deleteLink);
        const delSS = getSpreadsheetCached_(delSSId);
        const delInfo = parseSheetAndRange_(deleteColCond);
        const delSh = getSheetSmart_(delSS, delInfo.sheetName);

        if (!delSh) {
          Logger.log("  ❌ Lỗi: Không tìm thấy sheet xóa: '" + delInfo.sheetName + "'");
        } else {
          const delColLetter = delInfo.rangeStr || "A";
          const delRangeInfo = parseColAndStartRow_(delColLetter);
          const delColNum = colLetterToNum_(delRangeInfo.colLetter);
          const delStartRow = delRangeInfo.startRow;
          const delLastRow = delSh.getLastRow();

          if (delLastRow >= delStartRow) {
            const numRowsToRead = delLastRow - delStartRow + 1;
            const delData = delSh.getRange(delStartRow, delColNum, numRowsToRead, 1).getValues();
            let deletedCount = 0;

            // 🚀 Gom các dòng cần xóa liên tiếp thành từng khối để xóa 1 lần duy nhất bằng deleteRows (Siêu tốc & chống Timeout)
            const blocks = [];
            let currentBlock = null;

            for (let r = numRowsToRead - 1; r >= 0; r--) {
              const cellVal = String(delData[r][0] || "").trim().toLowerCase();
              if (cellVal === deleteValCond.toLowerCase()) {
                const rowNum = r + delStartRow;
                if (!currentBlock) {
                  currentBlock = { startRow: rowNum, count: 1 };
                } else if (currentBlock.startRow === rowNum + 1) {
                  currentBlock.startRow = rowNum;
                  currentBlock.count++;
                } else {
                  blocks.push(currentBlock);
                  currentBlock = { startRow: rowNum, count: 1 };
                }
              } else {
                if (currentBlock) {
                  blocks.push(currentBlock);
                  currentBlock = null;
                }
              }
            }
            if (currentBlock) {
              blocks.push(currentBlock);
            }

            // Xóa từng khối từ dưới lên trên (nhanh gấp 100 lần, không bao giờ bị timeout)
            for (let b = 0; b < blocks.length; b++) {
              try {
                delSh.deleteRows(blocks[b].startRow, blocks[b].count);
                deletedCount += blocks[b].count;
              } catch (delErr) {
                Logger.log("  ⚠️ Lỗi khi xóa khối dòng từ " + blocks[b].startRow + " (số lượng " + blocks[b].count + "): " + delErr.message);
              }
            }
            Logger.log("  🗑️ Đã xóa thành công: " + deletedCount + " dòng có '" + deleteValCond + "' tại '" + delSh.getName() + "' cột " + delColLetter);
          }
        }
      } catch (err) {
        Logger.log("  ❌ Lỗi xử lý Xóa dòng #" + rowIdx + ": " + err.message);
      }
    }

    // ========================================================
    // PHẦN 2: COPY - PASTE 123 (Nếu có đủ cấu hình)
    // ========================================================
    if (sourceLink && sourceSheet && sourceColCond && sourceValCond && targetSheet) {
      try {
        const srcSSId = extractSsId_(sourceLink);
        const srcSS = getSpreadsheetCached_(srcSSId);
        const srcInfo = parseSheetAndRange_(sourceSheet);
        const srcSh = getSheetSmart_(srcSS, srcInfo.sheetName);

        if (!srcSh) {
          Logger.log("  ❌ Lỗi: Không tìm thấy sheet nguồn: '" + srcInfo.sheetName + "'");
        } else {
          const tgtSSId = targetLink ? extractSsId_(targetLink) : srcSSId;
          const tgtSS = getSpreadsheetCached_(tgtSSId);
          const tgtInfo = parseSheetAndRange_(targetSheet);
          const tgtSh = getSheetSmart_(tgtSS, tgtInfo.sheetName);

          if (!tgtSh) {
            Logger.log("  ❌ Lỗi: Không tìm thấy sheet đích: '" + tgtInfo.sheetName + "'");
          } else {
            const srcLastRow = srcSh.getLastRow();
            
            // 1. Xác định cột dán ở sheet đích và dòng dán bắt đầu
            let targetStartCol = 1;
            let targetStartRow = 1;
            let targetHasRow = false;
            if (tgtInfo.rangeStr) {
              const tgtRangeInfo = parseColAndStartRow_(tgtInfo.rangeStr);
              targetStartCol = colLetterToNum_(tgtRangeInfo.colLetter);
              targetStartRow = tgtRangeInfo.startRow;
              targetHasRow = tgtRangeInfo.hasRow;
            }

            // 2. Lấy dòng bắt đầu quét điều kiện của cột điều kiện và dải ô nguồn
            const condRangeInfo = parseColAndStartRow_(sourceColCond);
            let condColNum = colLetterToNum_(condRangeInfo.colLetter);
            // Đảm bảo cột điều kiện nằm trong giới hạn của sheet nguồn
            condColNum = Math.min(condColNum, srcSh.getMaxColumns());
            
            let srcStartRow = 1;
            let srcHasRow = false;
            if (srcInfo.rangeStr) {
              const srcRangeInfo = parseColAndStartRow_(srcInfo.rangeStr);
              srcStartRow = srcRangeInfo.startRow;
              srcHasRow = srcRangeInfo.hasRow;
            }

            // Đồng bộ dòng bắt đầu quét nếu cấu hình nguồn là cột dạng A:A (không có số dòng)
            // nhưng cấu hình đích có dạng C4:H (bắt đầu từ dòng 4) để tránh copy nhầm tiêu đề.
            let condStartRow = condRangeInfo.startRow;
            if (!condRangeInfo.hasRow && targetHasRow) {
              condStartRow = targetStartRow;
            }
            if (!srcHasRow && targetHasRow) {
              srcStartRow = targetStartRow;
            }

            const finalStartRow = Math.max(srcStartRow, condStartRow);

            if (srcLastRow >= finalStartRow) {
              const numCondRows = srcLastRow - finalStartRow + 1;
              const condData = srcSh.getRange(finalStartRow, condColNum, numCondRows, 1).getValues();
              
              // Xác định khoảng cột cần copy
              let startCol = 1;
              let endCol = 27; // mặc định A:AA
              if (srcInfo.rangeStr) {
                const rangeCols = parseRangeCols_(srcInfo.rangeStr);
                startCol = rangeCols.start;
                endCol = rangeCols.end;
              }
              // Đảm bảo cột copy nằm trong giới hạn của sheet nguồn
              const srcMaxCols = srcSh.getMaxColumns();
              startCol = Math.min(startCol, srcMaxCols);
              endCol = Math.min(endCol, srcMaxCols);
              const numCols = endCol - startCol + 1;
              const tgtMaxCols = tgtSh.getMaxColumns();
              const neededTgtCols = targetStartCol + numCols - 1;
              if (neededTgtCols > tgtMaxCols) {
                tgtSh.insertColumnsAfter(tgtMaxCols, neededTgtCols - tgtMaxCols);
                Logger.log("  ➕ Đã tự động chèn thêm " + (neededTgtCols - tgtMaxCols) + " cột cho sheet đích.");
              }

              // 🛡️ TẦNG 2: BỘ LỌC CHỐNG DÁN TRÙNG Ở ĐÍCH (PRE-PASTE DEDUPLICATION GUARD)
              const existingSignatures = new Set();
              const tgtLastRow = tgtSh.getLastRow();
              if (tgtLastRow >= targetStartRow) {
                const tgtNumRows = tgtLastRow - targetStartRow + 1;
                const tgtExistingData = tgtSh.getRange(targetStartRow, targetStartCol, tgtNumRows, numCols).getValues();
                for (let tr = 0; tr < tgtExistingData.length; tr++) {
                  const sig = tgtExistingData[tr].map(function(v) {
                    return String(v !== null && v !== undefined ? v : "").trim().toLowerCase();
                  }).join("|||");
                  if (sig.replace(/\|/g, "") !== "") {
                    existingSignatures.add(sig);
                  }
                }
              }

              let copiedCount = 0;
              const rowsToAppend = [];
              for (let r = 0; r < condData.length; r++) {
                if (String(condData[r][0]).trim() === sourceValCond) {
                  const srcRowNum = r + finalStartRow;
                  let rowValues;
                  let hasCircularError = false;
                  
                  try {
                    rowValues = srcSh.getRange(srcRowNum, startCol, 1, numCols).getValues();
                    const flatVals = rowValues[0];
                    for (let v = 0; v < flatVals.length; v++) {
                      const vStr = String(flatVals[v]).trim();
                      if (
                        vStr.indexOf("#REF") !== -1 || 
                        vStr.indexOf("#CIRC") !== -1 || 
                        vStr.indexOf("#VALUE") !== -1 || 
                        vStr.indexOf("#DIV/0") !== -1 || 
                        vStr.indexOf("#NAME") !== -1 || 
                        vStr.indexOf("#N/A") !== -1 || 
                        vStr === "Error"
                      ) {
                        hasCircularError = true;
                        break;
                      }
                    }
                  } catch (readErr) {
                    hasCircularError = true;
                    rowValues = null;
                    Logger.log("  ⚠️ Lỗi đọc dữ liệu dòng " + srcRowNum + " (có thể do Circular Reference): " + readErr.message);
                  }
                  
                  if (hasCircularError) {
                    const errMsg = "⚠️ Lỗi vòng lặp/công thức tại sheet '" + srcInfo.sheetName + "' dòng " + srcRowNum + " (Cấu hình dòng #" + rowIdx + ")";
                    errorRows.push(errMsg);
                    Logger.log("  ❌ " + errMsg);
                    continue;
                  }

                  // 🛡️ GHẾ AUDITOR-OIL-9.8: Nếu cấu hình copy tới cột AB (endCol >= 28) mà cột AA có dữ liệu nhưng cột AB trống -> Chặn copy dòng thiếu AB và báo lỗi
                  if (startCol <= 27 && endCol >= 28 && rowValues && rowValues[0]) {
                    const aaIdx = 27 - startCol;
                    const abIdx = 28 - startCol;
                    const aaVal = String(rowValues[0][aaIdx] !== null && rowValues[0][aaIdx] !== undefined ? rowValues[0][aaIdx] : "").trim();
                    const abVal = String(rowValues[0][abIdx] !== null && rowValues[0][abIdx] !== undefined ? rowValues[0][abIdx] : "").trim();
                    if (aaVal !== "" && aaVal.toLowerCase().indexOf("closed time") === -1 && (abVal === "" || abVal === "0")) {
                      const errAbMsg = "⚠️ Sheet '" + srcInfo.sheetName + "' dòng " + srcRowNum + ": Có dữ liệu Cột AA (" + aaVal + ") nhưng thiếu Cột AB (Team) — nghi do hàm QUERY xung đột Text/Số!";
                      errorRows.push(errAbMsg);
                      Logger.log("  🚨 " + errAbMsg);
                      continue;
                    }
                  }

                  // 🛡️ Kiểm tra chống trùng lặp: Nếu dòng này đã có ở sheet đích -> Bỏ qua 100%
                  const rowSig = rowValues[0].map(function(v) {
                    return String(v !== null && v !== undefined ? v : "").trim().toLowerCase();
                  }).join("|||");
                  
                  if (existingSignatures.has(rowSig)) {
                    Logger.log("  ⏭️ Bỏ qua dòng nguồn " + srcRowNum + " vì dữ liệu đã tồn tại ở sheet đích (chống trùng lặp/Double).");
                    continue;
                  }
                  
                  existingSignatures.add(rowSig);
                  rowsToAppend.push(rowValues[0]);
                  copiedCount++;
                }
              }

              if (rowsToAppend.length > 0) {
                const tgtNextRow = findNextEmptyRowInCol_(tgtSh, targetStartCol, targetStartRow);
                const maxRows = tgtSh.getMaxRows();
                const neededRows = tgtNextRow + rowsToAppend.length - 1;
                if (neededRows > maxRows) {
                  tgtSh.insertRowsAfter(maxRows, neededRows - maxRows);
                }
                tgtSh.getRange(tgtNextRow, targetStartCol, rowsToAppend.length, numCols).setValues(rowsToAppend);
                SpreadsheetApp.flush(); // ⚡ Ép Google Cloud tính toán lại toàn bộ công thức ngay lập tức!
                Logger.log("  ✅ Đã copy hàng loạt " + rowsToAppend.length + " dòng sang sheet đích từ dòng " + tgtNextRow + " (liền kề, không tạo khoảng trống)");
              }
              Logger.log("  📊 Hoàn thành copy: " + copiedCount + " dòng.");
              
              // Tự động sắp xếp (Sort A:Z) sheet đích sau khi hoàn thành nếu được cấu hình
              if (sortConfig) {
                sortSheetByConfig_(tgtSS, sortConfig);
              }
            }
          }
        }
      } catch (err) {
        Logger.log("  ❌ Lỗi xử lý Copy-Paste dòng #" + rowIdx + ": " + err.message);
      }
    }

  } // end for configRows

  Logger.log("🏁 Hoàn thành toàn bộ tiến trình Auto Copy & Delete.");

  // Gửi báo cáo tổng hợp lỗi nếu có
  if (errorRows.length > 0) {
    const summaryMsg = "⚠️ AUTO COPY BÁO CÁO LỖI\n" +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      errorRows.join("\n") +
      "\n━━━━━━━━━━━━━━━━━━━━\n" +
      "🔧 Vui lòng kiểm tra và chỉnh sửa công thức ở các dòng trên.";
    Logger.log("📨 Tổng hợp lỗi:\n" + summaryMsg);
    // Ghi lỗi vào Script Properties để có thể truy xuất sau
    const props = PropertiesService.getScriptProperties();
    props.setProperty("LAST_COPY_ERRORS", summaryMsg);
    props.setProperty("LAST_COPY_ERROR_TIME", new Date().toISOString());
  }

  // 🛡️ GHẾ GIÁM SÁT CỘT AB (AUDITOR-OIL-9.8): Kiểm tra nếu có dữ liệu Cột AA mà Cột AB trống -> Báo Telegram ngay
  try {
    auditOilCloseWoColAB_(false);
  } catch (eAuditAb) {
    Logger.log("⚠️ Lỗi chạy auditOilCloseWoColAB_: " + eAuditAb.message);
  }
  } finally {
    lock.releaseLock();
  }
}

/**
 * 🛡️ GHẾ AUDITOR-OIL-9.8: Giám sát Cột AA/AB trên bảng 2.1 Control Oil and water coolant at Team
 * Nếu bất kỳ dòng nào trên tab 'Input Close WO DG paste 123' hoặc 'Update Close WO'
 * có dữ liệu ở Cột AA (Closed Time) nhưng Cột AB (Team) bị trống (hoặc bằng 0 / lỗi công thức),
 * lập tức gửi cảnh báo Telegram về Admin DM (6859790680) để kiểm tra hàm (ví dụ lỗi QUERY xung đột Text và Số).
 */
function auditOilCloseWoColAB_(forceNotify) {
  const OIL_SS_ID = "1EmECb3aPXMRxSyUzhV6wKU2oDq_32Ga-lwpwmkcHdh0";
  const ADMIN_CHAT_ID = "6859790680";
  const ss = getSpreadsheetCached_(OIL_SS_ID);
  if (!ss) return { status: "error", message: "Cannot open Oil & Coolant Spreadsheet" };

  const tabsToCheck = [
    { name: "Input Close WO DG paste 123", gid: "1378310796", startRow: 1 },
    { name: "Update Close WO",             gid: "1508195088", startRow: 3 }
  ];

  const missingDetails = [];
  const sigParts = [];

  for (let t = 0; t < tabsToCheck.length; t++) {
    const tabCfg = tabsToCheck[t];
    const sh = getSheetSmart_(ss, tabCfg.name);
    if (!sh) continue;
    const lastRow = sh.getLastRow();
    if (lastRow < tabCfg.startRow) continue;

    const numRows = lastRow - tabCfg.startRow + 1;
    const vals = sh.getRange(tabCfg.startRow, 1, numRows, 28).getDisplayValues();
    const tabIssues = [];

    for (let r = 0; r < vals.length; r++) {
      const rowNum = tabCfg.startRow + r;
      const row = vals[r];
      const woCode = String(row[18] || "").trim(); // Cột S
      const staff  = String(row[22] || "").trim(); // Cột W
      const aaVal  = String(row[26] || "").trim(); // Cột AA (Closed Time)
      const abVal  = String(row[27] || "").trim(); // Cột AB (Team)

      // Bỏ qua nếu AA trống hoặc là tiêu đề
      if (aaVal === "" || aaVal.toLowerCase().indexOf("closed time") !== -1) continue;

      const isAbInvalid = (
        abVal === "" ||
        abVal === "0" ||
        abVal.indexOf("#") === 0 ||
        abVal.toLowerCase() === "error"
      );

      if (isAbInvalid) {
        tabIssues.push("   • Dòng " + rowNum + ": AA=\"" + aaVal + "\" | AB=\"" + (abVal || "TRỐNG") + "\" | WO: " + (woCode || "N/A") + (staff ? " (" + staff + ")" : ""));
        sigParts.push(tabCfg.name + ":R" + rowNum + ":" + (woCode || aaVal));
      }
    }

    if (tabIssues.length > 0) {
      missingDetails.push("📌 Tab [" + tabCfg.name + "] (" + tabIssues.length + " dòng thiếu AB):\n" + tabIssues.slice(0, 15).join("\n") + (tabIssues.length > 15 ? "\n   ... (còn " + (tabIssues.length - 15) + " dòng khác)" : ""));
    }
  }

  const props = PropertiesService.getScriptProperties();
  const todayStr = Utilities.formatDate(new Date(), "Asia/Rangoon", "yyyyMMdd");
  const nowStr = Utilities.formatDate(new Date(), "Asia/Rangoon", "dd/MM/yyyy HH:mm:ss");

  if (missingDetails.length === 0) {
    props.deleteProperty("OIL_AB_AUDIT_LAST_SIG");
    return { status: "ok", missingCount: 0, timestamp: nowStr };
  }

  const currentSig = todayStr + "|" + sigParts.join(",");
  const lastSig = props.getProperty("OIL_AB_AUDIT_LAST_SIG") || "";

  let sentTelegram = false;
  if (forceNotify === true || currentSig !== lastSig) {
    const token = (props.getProperty("SEND_BOT_TOKEN") || props.getProperty("PLAN_BOT_TOKEN") || "").trim();
    if (token) {
      const msgLines = [
        "🚨 [GHẾ AUDITOR-OIL-9.8] CẢNH BÁO THIẾU CỘT AB (TEAM) KHI CỘT AA CÓ DỮ LIỆU",
        "━━━━━━━━━━━━━━━━━━━━",
        "⏰ Thời điểm phát hiện: " + nowStr + " (MMT)",
        "📂 Bảng tính: 2.1 Control Oil and water coolant at Team",
        "",
        missingDetails.join("\n\n"),
        "",
        "⚠️ Nguyên nhân cần kiểm tra:",
        "1. Hàm QUERY Google Sheet bị xung đột kiểu dữ liệu Text và Số (ví dụ XLOOKUP trả về số 0 trộn lẫn với chữ T1/T2 làm QUERY ẩn giá trị cột AB).",
        "2. Dòng dữ liệu bên Input Close WO DG paste 123 bị lệch dòng 1 (B1 vs A2) hoặc copy thiếu cột AB.",
        "🔗 Link kiểm tra: https://docs.google.com/spreadsheets/d/" + OIL_SS_ID + "/edit#gid=1508195088"
      ];
      try {
        const resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/sendMessage", {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify({
            chat_id: ADMIN_CHAT_ID,
            text: msgLines.join("\n")
          }),
          muteHttpExceptions: true
        });
        if (resp.getResponseCode() === 200) {
          sentTelegram = true;
          props.setProperty("OIL_AB_AUDIT_LAST_SIG", currentSig);
        }
      } catch (tgErr) {
        Logger.log("❌ Lỗi gửi Telegram auditOilCloseWoColAB_: " + tgErr.message);
      }
    }
  }

  return {
    status: "alert",
    missingCount: sigParts.length,
    sentTelegram: sentTelegram,
    signature: currentSig,
    details: missingDetails,
    timestamp: nowStr
  };
}

/**
 * Thiết lập lịch chạy tự động mỗi 15 phút (chỉ chạy trong khung giờ làm việc)
 */
function setupAutoCopyEvery15MinutesTrigger() {
  // Xóa các trigger cũ cùng tên để tránh trùng lặp
  const triggers = ScriptApp.getProjectTriggers();
  for (const t of triggers) {
    if (t.getHandlerFunction() === "runAutoCopyProcessor") {
      ScriptApp.deleteTrigger(t);
    }
  }

  // Tạo trigger mới chạy mỗi 15 phút
  ScriptApp.newTrigger("runAutoCopyProcessor")
           .timeBased()
           .everyMinutes(15)
           .create();
  
  Logger.log("⏰ Đã thiết lập trigger chạy tự động mỗi 15 phút cho tác vụ Copy.");
}

/**
 * Xem báo cáo lỗi lần chạy Auto Copy cuối cùng
 * Chạy thủ công từ Apps Script Editor để xem có lỗi gì không
 */
function getLastCopyErrors() {
  const props = PropertiesService.getScriptProperties();
  const errors = props.getProperty("LAST_COPY_ERRORS");
  const errorTime = props.getProperty("LAST_COPY_ERROR_TIME");
  if (errors) {
    Logger.log("🕐 Thời điểm lỗi: " + (errorTime || "N/A"));
    Logger.log(errors);
  } else {
    Logger.log("✅ Không có lỗi nào từ lần chạy cuối cùng.");
  }
}



// ============================================================
// HELPERS
// ============================================================

function extractSsId_(link) {
  if (!link) return "";
  const match = link.match(/\/d\/([a-zA-Z0-9_-]+)/);
  return match ? match[1] : link;
}

function getSheetSmart_(ss, targetName) {
  if (!ss || !targetName) return null;
  targetName = String(targetName).trim();
  
  // 1. Tìm chính xác
  let sheet = ss.getSheetByName(targetName);
  if (sheet) return sheet;
  
  // 2. Tìm không phân biệt chữ hoa/thường và chuẩn hóa khoảng trắng thừa
  const cleanTarget = targetName.toLowerCase().replace(/\s+/g, " ");
  const allSheets = ss.getSheets();
  for (let i = 0; i < allSheets.length; i++) {
    const sh = allSheets[i];
    const cleanShName = sh.getName().toLowerCase().replace(/\s+/g, " ");
    if (cleanShName === cleanTarget) {
      return sh;
    }
  }
  
  // 3. Tìm tương đối không tính khoảng cách
  const cleanTargetNoSpace = targetName.toLowerCase().replace(/\s+/g, "");
  for (let i = 0; i < allSheets.length; i++) {
    const sh = allSheets[i];
    const cleanShName = sh.getName().toLowerCase().replace(/\s+/g, "");
    if (cleanShName === cleanTargetNoSpace) {
      return sh;
    }
  }
  return null;
}

function parseSheetAndRange_(sheetStr) {
  if (!sheetStr) return { sheetName: "", rangeStr: "" };
  sheetStr = String(sheetStr).trim();
  const idx = sheetStr.indexOf("!");
  if (idx === -1) return { sheetName: sheetStr.replace(/['"]/g, "").trim(), rangeStr: "" };
  return {
    sheetName: sheetStr.substring(0, idx).replace(/['"]/g, "").trim(),
    rangeStr: sheetStr.substring(idx + 1).trim()
  };
}

function colLetterToNum_(letter) {
  if (!letter) return 1;
  letter = String(letter).trim();
  // Nếu chứa dấu chấm than ! (VD: "Sheet1!A:A"), chỉ lấy phần range sau !
  if (letter.indexOf("!") !== -1) {
    letter = letter.split("!")[1].trim();
  }
  // Nếu chứa dấu hai chấm (VD: "A:A" hoặc "A:AA"), chỉ lấy phần cột đầu tiên
  if (letter.indexOf(":") !== -1) {
    letter = letter.split(":")[0].trim();
  }
  // Nếu là số hoặc chuỗi số (VD: 1 hoặc "1")
  if (!isNaN(letter) && letter !== "") {
    return parseInt(letter, 10);
  }
  letter = letter.toUpperCase().replace(/[^A-Z]/g, "");
  let column = 0;
  for (let i = 0; i < letter.length; i++) {
    column = column * 26 + (letter.charCodeAt(i) - 64);
  }
  return column || 1;
}

function parseRangeCols_(rangeStr) {
  if (!rangeStr) return { start: 1, end: 27 };
  const parts = rangeStr.split(":");
  if (parts.length < 2) return { start: 1, end: 27 };
  return {
    start: colLetterToNum_(parts[0]),
    end: colLetterToNum_(parts[1])
  };
}

function findNextEmptyRowInCol_(sheet, columnIdx, startRow) {
  startRow = startRow || 1;
  const maxRows = sheet.getMaxRows();
  if (maxRows < startRow) return startRow;
  
  const numRowsToRead = maxRows - startRow + 1;
  const values = sheet.getRange(startRow, columnIdx, numRowsToRead, 1).getValues();
  
  // 🔍 Quét TUẦN TỰ TỪ TRÊN XUỐNG DƯỚI (Top-Down) để tìm dòng trống LIỀN KỀ ĐẦU TIÊN
  for (let i = 0; i < values.length; i++) {
    const val = values[i][0];
    const s = (val === null || val === undefined) ? "" : String(val).trim();
    if (s === "") {
      return i + startRow; // Trả về ngay ô trống liền kề đầu tiên (không bao giờ để trống hàng)
    }
  }
  return maxRows + 1;
}

function sortSheetByConfig_(ss, sortConfig) {
  if (!ss || !sortConfig) return;
  try {
    const info = parseSheetAndRange_(sortConfig);
    const sheet = getSheetSmart_(ss, info.sheetName);
    if (!sheet) {
      Logger.log("  ❌ Lỗi sort: Không tìm thấy sheet '" + info.sheetName + "'");
      return;
    }

    const lastRow = sheet.getLastRow();
    const lastCol = sheet.getLastColumn();
    const frozenRows = sheet.getFrozenRows();
    const defaultStartRow = frozenRows > 0 ? frozenRows + 1 : 2;

    const sortInfo = parseSortConfigRange_(info.rangeStr, defaultStartRow);
    let startRow = sortInfo.startRow;
    const colLetter = sortInfo.colLetter;
    const colIdx = colLetterToNum_(colLetter);

    // 🛡️ BẢO VỆ TIÊU ĐỀ: Nếu dòng startRow chứa chữ tiêu đề -> Tự động bắt đầu sort từ dòng tiếp theo
    if (startRow <= lastRow) {
      const checkRowVals = sheet.getRange(startRow, 1, 1, lastCol).getValues()[0];
      for (let h = 0; h < checkRowVals.length; h++) {
        const hStr = String(checkRowVals[h] || "").toLowerCase();
        if (
          hStr.indexOf("date assign") !== -1 ||
          hStr.indexOf("detailed content") !== -1 ||
          hStr.indexOf("target date") !== -1 ||
          hStr.indexOf("group assign") !== -1 ||
          hStr.indexOf("dep assign") !== -1 ||
          hStr.indexOf("backoffice receive") !== -1 ||
          hStr.indexOf("your task") !== -1 && hStr.indexOf("assign") !== -1
        ) {
          Logger.log("  🛡️ Phát hiện dòng " + startRow + " là Tiêu đề (Header) -> Bắt đầu sort từ dòng " + (startRow + 1));
          startRow = startRow + 1;
          break;
        }
      }
    }

    let actualLastRow = startRow;
    const colValues = sheet.getRange(1, colIdx, lastRow, 1).getValues();
    for (let r = lastRow - 1; r >= 0; r--) {
      const val = String(colValues[r][0]).trim();
      if (val !== "" && val !== "null" && val !== "undefined" && val !== "-") {
        actualLastRow = r + 1;
        break;
      }
    }

    if (actualLastRow === startRow && colIdx !== 1) {
      const col1Values = sheet.getRange(1, 1, lastRow, 1).getValues();
      for (let r = lastRow - 1; r >= 0; r--) {
        const val = String(col1Values[r][0]).trim();
        if (val !== "" && val !== "null" && val !== "undefined" && val !== "-") {
          actualLastRow = r + 1;
          break;
        }
      }
    }

    if (actualLastRow <= startRow) {
      Logger.log("  ℹ️ Sheet '" + info.sheetName + "' không có dữ liệu thực tế nào để sắp xếp.");
      return;
    }

    const range = sheet.getRange(startRow, 1, actualLastRow - startRow + 1, lastCol);
    const data        = range.getValues();
    const formulas    = range.getFormulas();
    const backgrounds = range.getBackgrounds();
    const fontWeights = range.getFontWeights();

    const rows = [];
    for (let r = 0; r < data.length; r++) {
      rows.push({
        values:   data[r],
        formulas: formulas[r],
        bg:       backgrounds[r],
        fw:       fontWeights[r]
      });
    }

    rows.sort(function(a, b) {
      const valA = a.values[colIdx - 1];
      const valB = b.values[colIdx - 1];

      const isAEmpty = (valA === "" || valA === null || valA === undefined || String(valA).trim() === "-");
      const isBEmpty = (valB === "" || valB === null || valB === undefined || String(valB).trim() === "-");

      if (isAEmpty && isBEmpty) return 0;
      if (isAEmpty) return 1;
      if (isBEmpty) return -1;

      if (valA < valB) return -1;
      if (valA > valB) return 1;
      return 0;
    });

    const sortedValues     = rows.map(r => r.values);
    const sortedFormulas   = rows.map(r => r.formulas);
    const sortedBackgrounds = rows.map(r => r.bg);
    const sortedFontWeights = rows.map(r => r.fw);

    // Quét các dòng phía trên dòng startRow để xem cột nào chứa công thức mảng (ARRAYFORMULA ở dòng tiêu đề)
    const formulaCols = {};
    if (startRow > 1 && lastCol > 0) {
      try {
        const upperFormulas = sheet.getRange(1, 1, startRow - 1, lastCol).getFormulas();
        for (let c = 0; c < lastCol; c++) {
          for (let rUpper = 0; rUpper < upperFormulas.length; rUpper++) {
            if (upperFormulas[rUpper][c] !== "") {
              formulaCols[c] = true;
              break;
            }
          }
        }
      } catch (eFormula) {
        Logger.log("  ⚠️ Cảnh báo đọc công thức hàng trên khi sort: " + eFormula.message);
      }
    }

    // Ghi đè dữ liệu sau khi sort theo từng cột (bảo vệ cột có ARRAYFORMULA)
    const numRows = sortedValues.length;
    for (let c = 0; c < lastCol; c++) {
      const colRange = sheet.getRange(startRow, c + 1, numRows, 1);
      
      // Sắp xếp định dạng nền và font chữ (không ảnh hưởng đến công thức mảng)
      const colBackgrounds = sortedBackgrounds.map(row => [row[c]]);
      const colFontWeights = sortedFontWeights.map(row => [row[c]]);
      try {
        colRange.setBackgrounds(colBackgrounds);
        colRange.setFontWeights(colFontWeights);
      } catch (eFormat) {
        // Bỏ qua lỗi định dạng nếu có
      }

      if (formulaCols[c]) {
        // Cột này được kiểm soát bởi ARRAYFORMULA phía trên -> KHÔNG ghi đè giá trị hoặc công thức để tránh lỗi #REF!
        continue;
      }

      // Trộn lẫn giá trị và công thức để ghi đè trong 1 lần setValues duy nhất,
      // tránh việc setFormulas ghi đè các ô giá trị tĩnh thành rỗng.
      const mixedValues = [];
      for (let r = 0; r < numRows; r++) {
        const formula = sortedFormulas[r][c];
        if (formula && formula.indexOf("=") === 0) {
          mixedValues.push([formula]);
        } else {
          mixedValues.push([sortedValues[r][c]]);
        }
      }

      try {
        colRange.setValues(mixedValues);
      } catch (valErr) {
        // Nếu bị lỗi Validation ở cột này (ví dụ cột có Dropdown nghiêm ngặt), ta thử ghi từng ô
        for (let r = 0; r < numRows; r++) {
          const cell = sheet.getRange(startRow + r, c + 1);
          try {
            cell.setValue(mixedValues[r][0]);
          } catch (cellValErr) {
            try {
              cell.setValue("");
            } catch (cellValErr2) {
              // Bỏ qua ô bị Validation chặn không cho sửa
            }
          }
        }
      }
    }

    Logger.log("  📶 Đã tự động sắp xếp (Sort A:Z) sheet '" + info.sheetName + "' theo cột " + colLetter + " (Từ dòng " + startRow + " đến dòng " + actualLastRow + ")");
  } catch (err) {
    Logger.log("  ❌ Lỗi khi tự động sắp xếp sheet: " + err.message);
  }
}

function parseSortConfigRange_(rangeStr, defaultStartRow) {
  if (!rangeStr) return { colLetter: "A", startRow: defaultStartRow };
  let colLetter = "A";
  let startRow = defaultStartRow;
  let firstPart = rangeStr.indexOf(":") !== -1 ? rangeStr.split(":")[0] : rangeStr;
  firstPart = firstPart.trim();
  const rowMatch = firstPart.match(/\d+/);
  if (rowMatch) {
    startRow = parseInt(rowMatch[0], 10);
  }
  const colMatch = firstPart.match(/[a-zA-Z]+/);
  if (colMatch) {
    colLetter = colMatch[0];
  }
  return { colLetter: colLetter, startRow: startRow };
}

function isWithinCopyActiveWindows_() {
  const now = new Date();
  const hour = parseInt(Utilities.formatDate(now, "Asia/Rangoon", "H"), 10);
  const minute = parseInt(Utilities.formatDate(now, "Asia/Rangoon", "m"), 10);
  
  // Khung giờ hoạt động: 05:00 - 20:00
  if (hour >= 5 && hour < 20) return true;
  if (hour === 20 && minute === 0) return true;
  
  return false;
}

function parseColAndStartRow_(rangeStr) {
  if (!rangeStr) return { colLetter: "A", startRow: 1, hasRow: false };
  
  let colLetter = "A";
  let startRow = 1;
  let hasRow = false;
  
  // Loại bỏ phần tên sheet phía trước dấu chấm than ! nếu có (VD: "3.1 Update Assign!A4:A" -> "A4:A")
  let rangeOnly = rangeStr;
  if (rangeStr.indexOf("!") !== -1) {
    rangeOnly = rangeStr.split("!")[1].trim();
  }
  
  // Lấy phần trước dấu hai chấm nếu có (VD: "A4:A" -> "A4")
  let firstPart = rangeOnly.indexOf(":") !== -1 ? rangeOnly.split(":")[0] : rangeOnly;
  firstPart = firstPart.trim();
  
  // Trích xuất số dòng bắt đầu (VD: "A4" -> 4)
  const rowMatch = firstPart.match(/\d+/);
  if (rowMatch) {
    startRow = parseInt(rowMatch[0], 10);
    hasRow = true;
  }
  
  // Trích xuất chữ cái cột (VD: "A4" -> "A")
  const colMatch = firstPart.match(/[a-zA-Z]+/);
  if (colMatch) {
    colLetter = colMatch[0];
  }
  
  return { colLetter: colLetter, startRow: startRow, hasRow: hasRow };
}
