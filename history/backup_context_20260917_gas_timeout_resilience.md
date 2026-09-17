# Snapshot Lịch Sử: Khắc Phục Sự Cố Timeout / Ngủ Google Apps Script Backend (Version @438 & Rule PM-28)

- Thời gian: 17/09/2026 09:30 MMT
- Ghế: GAS-OPS-1 (QLTC_GAS @438), AUDITOR-9.1 (system_auditor.py)
- Rule: RULE PM-28 (GAS Cold-Start Resilience & Ultra-Fast Ping Keepalive Policy)

## 1. Bối Cảnh Sự Cố
Cảnh báo đỏ từ system_auditor.py lúc 08:58:38 MMT:
- TNI Main GAS Backend: Timeout / Ngủ: HTTPSConnectionPool
- BI Portal Backend (Plan Dep): Timeout / Ngủ: HTTPSConnectionPool

## 2. Nguyên Nhân Gốc (PM-1)
- QLTC_GAS thiếu endpoint ping/get_general tức thì, rơi vào nhánh default mở toàn bộ Spreadsheet khổng lồ gây nghẽn.
- system_auditor.py có timeout=12s quá chặt và 0 retry, trong khi Google V8 cold start mất 12-16s.

## 3. Khắc Phục (PM-2)
- Thêm endpoint ping và get_general tức thì (<50ms) trên apps_script_collector.gs, deploy Version @438.
- Nâng timeout=20s và 2-attempt retry buffer trên audit_gas_backends().
- Thêm RULE PM-28 vào AGENTS.md đồng bộ 4 repos.

## 4. Phúc Tra Thực Tế (HTTP 200 / PASS 100%)
- TNI Main GAS Backend (@438 SSOT): PASS (7.64s)
- Standalone Site Down GAS Backend (@83 SSOT): PASS (13.65s)
- BI Portal Backend (Plan Dep): PASS (19.37s)
- Attendance GAS Backend (@72 SSOT): PASS (11.15s)