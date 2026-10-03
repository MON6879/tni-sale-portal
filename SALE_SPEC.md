# SALE_SPEC.md — Đặc tả nghiệp vụ Đoàn Tàu Sale (nguồn sự thật duy nhất)

> Quy trình bắt buộc: **sửa SPEC trước → sửa code → chạy bộ ca test**. Không code ngoài SPEC.
> Trạng thái: **v1.4** (03/10/2026) — gộp quyết định của chủ (MMK, báo cáo lên GROUP chỉ định) + rà soát 4 chuyên gia (2 vòng, gồm pre-mortem 'điều không lường được') + ghế thực thi/giám sát (mục 13) + sửa rule đúng chỗ (mục 14) + độ tin cậy/vận hành (mục 15) + bảo mật bổ sung (mục 16) + con người/ngôn ngữ (mục 17). Mục `[MẶC ĐỊNH]` là phương án tạm chọn, đổi bằng cách sửa file này.

## 0. Bảng Đã chốt / Chờ chốt
| Mục | Trạng thái |
|---|---|
| Ký gởi KHÔNG tính là bán; theo dõi lô; 1 tin tổng hợp/ngày (nằm trong báo cáo 17:30) | Đã chốt |
| Công nợ tiền chỉ phát sinh khi xác nhận nhận hàng (bán thường, không áp cho đại lý bán đứt) | Đã chốt |
| Đại lý = bán đứt; không nợ; không hoa hồng; chiết khấu nhập tay theo lô | Đã chốt |
| Ký gởi/lô giao NV bắt buộc serial; tối đa 60 ngày/lô | Đã chốt |
| Hàng trả & hàng hỏng do kho nhập; trả thì trừ hàng đang giữ của người giữ; hỏng thì theo dõi gởi bảo hành | Đã chốt |
| Ngôn ngữ: VI chính + EN, không Myanmar | Đã chốt |
| Sửa/xóa đơn: chủ đơn khi còn Nháp; sau đó chỉ admin | Đã chốt |
| Tiền tệ: **MMK**; lưu số thuần + cột `tien_te` (mặc định `MMK`) | Đã chốt |
| Báo cáo Sale **nhắn lên GROUP Telegram chỉ định** (không DM người giữ hàng) | Đã chốt |
| Group nhận báo cáo Sale: tên đặt ở `Cau Hinh.sale_report_group`, id lấy từ tab `List Group Telegram` | **Chờ chủ chỉ định group** (chưa chọn thì báo cáo bỏ qua, không đoán) |
| Tin nhóm: mỗi dòng song ngữ `VI/EN` ngắn, ≤1500 ký tự (mẫu ở mục 17) | [MẶC ĐỊNH] chờ chủ xác nhận |
| **Có nhân viên/người giữ hàng nào KHÔNG đọc được cả tiếng Việt lẫn tiếng Anh không?** (nếu có: thêm lớp Myanmar tối thiểu ~100 chuỗi cho màn nhân viên) | **Chờ chủ trả lời** — rủi ro lớn nhất chưa chốt |
| Cắt gọt phạm vi (MVP, mục 12): hoãn hash-chain/`DOI_MAY`/`GIA_HAN`/`SUA_SERIAL` sang sau; chạy thử (pilot) 2–4 tuần với 1 nhóm nhỏ | [MẶC ĐỊNH] chờ chủ xác nhận |

## 1. Nguồn dữ liệu
- Google Sheet Sale (`1s-V0owHlwub4qrCxTUvKmXp4PWZthzk5oKhi5m_wQBA`) là **SSOT**. Web chỉ là giao diện; `localStorage` chỉ lưu tùy chọn giao diện (ngôn ngữ), **không lưu phiên hay dữ liệu nghiệp vụ nhạy cảm**.
- Mọi ghi đi qua **một hàm ghi duy nhất** trong GAS: lock + `idem_key` + audit. Web, Telegram, train không tự ghi.
- `idem_key` bắt buộc; server lưu trong Sheet (không chỉ cache) và trả kết quả cũ khi gặp lại. Web sinh UUID khi mở form; Telegram dùng `chatId_messageId`.
- Giờ luôn do server, `Asia/Yangon`, `yyyy-MM-dd HH:mm:ss`. Không tin giờ client.
- Hệ số kinh doanh (ngưỡng CK, `max_hold_days`=60, ngưỡng tồn thấp, hạn nợ) nằm ở **tab `Cau Hinh`**; chỉ admin sửa, có audit.
- **Một Script ID/deployment duy nhất được GHI** (ID phụ chỉ đọc hoặc bỏ), có endpoint `version` cho Auditor so sánh.
- Migration: chỉ **thêm cột ở cuối**, idempotent, snapshot tab đã có dữ liệu trước, chốt schema cuối **một lần** rồi mới migration.

## 2. Giá trị lưu là MÃ ỔN ĐỊNH (không phụ thuộc ngôn ngữ)
Sheet/API lưu mã chữ hoa không dấu; web hiển thị bằng `t('status.<MA>')`. Đổi bản dịch không được làm hỏng dữ liệu.

| Mã đơn | VI | EN |
|---|---|---|
| `DRAFT` | Nháp | Draft |
| `QUOTE_SENT` | Đã gửi báo giá | Quotation sent |
| `RECEIPT_CONFIRMED` | Đã xác nhận nhận hàng | Delivery confirmed |
| `PAID` | Đã thanh toán đủ | Paid in full |

> Ghi chú triển khai: Phase 1a (@474/@475) đang lưu **nhãn tiếng Việt**; phải đổi sang mã ở Phase 1b trước khi có dữ liệu thật (bảng đơn hiện 0 dòng).

## 3. Vòng đời đơn theo KÊNH
| Kênh (`kenh`) | Vòng đời | Doanh thu | Nợ tiền |
|---|---|---|---|
| `retail` (bán lẻ) | DRAFT → QUOTE_SENT → RECEIPT_CONFIRMED → PAID | khi RECEIPT_CONFIRMED | Có, từ lúc xác nhận nhận hàng; thu từng phần; hạn `due_days` (30) |
| `dealer_outright` (đại lý bán đứt) | ghi đơn là xong (không vòng đời nợ) | ngay khi ghi đơn | **Không** |
| `consignment_sale` (bán từ lô ký gởi) | như `retail` | khi đơn đạt RECEIPT_CONFIRMED | như `retail` |
| `staff_sale` (bán từ lô NV) | như `retail` | khi đơn đạt RECEIPT_CONFIRMED | như `retail`; tiền thu hộ NV nộp: `[MẶC ĐỊNH]` theo dõi bằng `da_thu` |

- Sửa/xóa đơn: chủ đơn tự sửa/xóa khi `DRAFT`; từ `QUOTE_SENT` trở đi chỉ `admin`, bắt buộc có lý do, mọi lần ghi `Sale Audit`. Xóa = đánh dấu (soft delete), vẫn giữ vết.
- Đơn đại lý (bán đứt): sửa/xóa chỉ `admin`; sai thì dùng **đơn đảo** (`HUY_BAN`), không xóa dòng.
- Hủy đơn sau xác nhận / hàng trả sau bán: chỉ `admin` duyệt; sinh sự kiện đảo, doanh thu điều chỉnh bằng dòng điều chỉnh, serial về trạng thái trước (kho hoặc lô).
- Người thu tiền: `finance`, `admin`.
- `DRAFT`/`QUOTE_SENT` chỉ **giữ chỗ serial 24 giờ** (cấu hình); sự kiện bán (`BAN`) chỉ ghi khi đơn đạt `RECEIPT_CONFIRMED` (bán thường) hoặc ngay khi ghi đơn (đại lý bán đứt).

## 4. Hai khái niệm "nợ" — tách bạch
- **Receivables (Công nợ tiền khách)**: tiền khách còn phải trả sau `RECEIPT_CONFIRMED`.
- **Custody liability (Trách nhiệm hàng người giữ)**: số hàng/serial người giữ (NV, người ký gởi) còn giữ, chưa bán/chưa trả.
- Đại lý bán đứt: không có cả hai.

## 5. Serial — máy trạng thái duy nhất
Mỗi serial có **đúng 1 trạng thái hiện tại** (tab `Serial`: serial, sku, trạng thái, nơi giữ, `lo_id`, `don_id`, ngày). Serial duy nhất toàn hệ thống, chuẩn hóa (trim, upper, bỏ ký tự lạ, chống công thức Sheet).

| Mã | VI | EN |
|---|---|---|
| `IN_STOCK` | Trong kho | In stock |
| `PENDING_ACCEPT` | Chờ nhận (kho đã giao, người giữ chưa xác nhận) | Pending accept |
| `RESERVED` | Giữ chỗ (đơn Nháp/báo giá, tối đa 24 giờ) | Reserved |
| `HELD` | Đang giữ (ký gởi/giao NV) — đã xác nhận nhận | Held (custody) |
| `SOLD` | Đã bán | Sold |
| `DEFECTIVE` | Hỏng | Defective |
| `IN_REPAIR` | Gởi bảo hành | In warranty repair |
| `REPAIRED` | Đã bảo hành/Đổi | Repaired / Replaced |
| `LOST` | Mất/Thất thoát (admin xác nhận) | Lost |

| Chuyển | Điều kiện | Ai |
|---|---|---|
| (mới) → `IN_STOCK` | Nhập kho, serial chưa tồn tại | warehouse |
| `IN_STOCK` → `PENDING_ACCEPT` | Giao lô cho người giữ hợp lệ | warehouse/admin |
| `PENDING_ACCEPT` → `HELD` | Người nhận **xác nhận** (nút "Nhận"); quá 48 giờ chưa nhận → cảnh báo admin, **không tự xác nhận hộ** | người nhận |
| `PENDING_ACCEPT` → `IN_STOCK` | Người nhận từ chối hoặc admin hủy giao | người nhận/admin |
| `IN_STOCK` → `RESERVED` → `IN_STOCK`/`SOLD` | Giữ chỗ khi tạo đơn; job tự giải phóng khi quá 24 giờ | hệ thống |
| `HELD` → `SOLD` | Có đơn thật, serial thuộc lô của chính người bán | người giữ |
| `IN_STOCK` → `SOLD` | Bán lẻ/đại lý có đơn | sales/admin |
| `HELD` → `IN_STOCK` | Trả (TRA), kho nhập; người giữ xác nhận hoặc admin duyệt | warehouse |
| `SOLD` → `IN_STOCK` | Hàng trả sau bán: có đơn gốc, trong hạn, admin duyệt | warehouse + admin |
| `IN_STOCK`/`HELD`/`SOLD` → `DEFECTIVE` | Kho nhập hỏng, ghi nguồn, bắt buộc ảnh/biên bản | warehouse |
| `DEFECTIVE` → `IN_REPAIR` → `REPAIRED` → `IN_STOCK` | Theo dõi ngày gởi/nhận, nơi nhận | warehouse/tech |
| `HELD` → `LOST` | NV nghỉ việc không trả được | admin |
| Mọi cặp khác | **Từ chối** | — |

- Mỗi chuyển là compare-and-set trong lock: kèm `trang_thai_cu` mong đợi, `idem_key`, người ghi, giờ MMT; sai trạng thái → lỗi rõ ràng. Mọi chuyển ghi 1 dòng vào nhật ký sự kiện (append-only).
- Sự kiện: `GIAO`, `BAN`, `TRA`, `HU`, `GUI_BH`, `NHAN_BH`, `DOI_MAY`, `HUY_BAN`, `CHUYEN_LO`, `SUA_SERIAL`, `GIA_HAN`, `MAT`.
- **Tồn khả dụng = số serial `IN_STOCK`** (đếm trực tiếp, không cộng trừ tay). Hàng ký gởi/giao NV hiện riêng "Đang giữ"; hàng hỏng/bảo hành hiện riêng, không vào tồn khả dụng.

## 6. Đại lý phân phối = BÁN ĐỨT
- Trừ kho và ghi doanh thu **ngay** khi ghi đơn; không ký gởi, không theo dõi sau bán.
- Chiết khấu **nhập tay theo lô** (`ck_lo`), validate `0 ≤ ck_lo ≤ ck_max` (cấu hình, theo SKU/vai trò); vượt ngưỡng cần admin duyệt. Lưu `gia_ap_dung` trên dòng, đổi bảng giá không làm đổi đơn cũ.
- Mỗi đơn đại lý lưu `serial`, `ngay_ban`, liên hệ đại lý, `han_bao_hanh` (= ngày bán + số tháng BH theo SKU, cấu hình). Tra serial ra đại lý + ngày bán + hạn BH.
- Tab `Dai Ly` = danh bạ; `Phan Phoi` = đơn bán đứt (bỏ `ngay_gui`/trạng thái giữ).
- Vai trò `dealer`: đăng nhập riêng (whitelist), chỉ xem hàng đã mua của chính mình (lọc server theo session), tạo yêu cầu bảo hành; rate-limit chống dò serial.
- Hoa hồng: chỉ khi có ô `hoa_hong` nhập tay ở đơn không phải đại lý bán đứt; lưu **tab riêng**, chỉ người tạo đơn, `finance`, `admin` đọc; không gửi vào nhóm Telegram. Thuật ngữ "% nộp Tổng Cty", "Tạm ứng" giữ ở bảng thuật ngữ nhưng chưa dùng trong luồng mới.

## 7. Ký gởi & lô giao nhân viên (trọng tâm)
- Người giữ: người nhận ký gởi hoặc **từng nhân viên sale**. Hàng chưa bán, công ty còn sở hữu.
- Mô hình: `Lo Giao` (lo_id, holder_type = consignee|staff, holder_id, ngay_giao, nguoi_giao, trang_thai), `Lo Giao Chi Tiet` (mỗi serial 1 dòng, SL=1), `Lo Giao Su Kien` (nhật ký bất biến). Không sửa số trực tiếp; số liệu tính từ nhật ký.
- `còn giữ = giao − đã bán − đã trả − hỏng/BH − mất`, không âm. `BAN`/`TRA` không vượt `còn giữ`; serial bán phải đang nằm trong lô của chính người bán; TRA chỉ nhận serial đang ở lô của người đó.
- **Hạn 60 ngày tính theo từng serial** (ngày giao). Cảnh báo ngày 53 và quá hạn; quá hạn: **khóa `BAN` mới** của serial đó và chặn giao thêm cho người đó cho tới khi admin gia hạn (có lý do, ghi audit) hoặc kho nhận trả.
- Hàng trả: kho nhập (`TRA`), người giữ xác nhận hoặc admin duyệt → `còn giữ` −1, serial về `IN_STOCK`. Hàng hỏng: kho nhập (`HU`), `còn giữ` giảm, theo dõi bảo hành (mục 5).
- Chuyển nhầm người/lô: sự kiện `CHUYEN_LO` (người giao + người nhận đều xác nhận). Nhập nhầm serial: chỉ `admin` sửa qua `SUA_SERIAL` có lý do (serial cũ→mới), không sửa đè.
- **NV nghỉ việc**: không đặt `inactive` nếu còn lô giữ (phải trả hoặc chuyển lô, admin duyệt); khi `inactive` hủy session ngay, gỡ liên kết Telegram; serial không trả được → `LOST` do admin xác nhận. Báo cáo ngày liệt kê lô thuộc người `inactive`.
- Đổi máy bảo hành (`DOI_MAY`): serial cũ → `DEFECTIVE`/thu hồi, serial mới → `SOLD` cho cùng khách/đại lý, kế thừa hạn BH còn lại; lấy máy mới từ kho.

## 8. Báo cáo & kiểm soát
| Báo cáo | Nội dung | Gửi | Ai xem |
|---|---|---|---|
| **Báo cáo ngày: Tồn & Bán hàng** | Bán trong ngày theo 4 kênh (SL, doanh thu), tồn khả dụng theo SKU, tồn thấp, nợ quá hạn (chỉ kênh có nợ), tổng hợp ký gởi/NV (giao/bán/trả/còn giữ/ngày giữ lâu nhất), lô còn 7 ngày & quá 60 ngày, hàng hỏng/đang BH, người `inactive` còn giữ, kết quả đối soát | 1 lần/ngày **17:30 MMT**; bỏ nhịp 11:30; chạy trong `train_5min.yml` | Group Sale chỉ định: **chỉ SL/tồn/hạn, không giá vốn/lợi nhuận/CK/hoa hồng**; số tiền MMK doanh thu tổng được phép, chi tiết giá vốn/LN → DM `finance/admin` |
| Mục "Người giữ hàng" trong báo cáo ngày | Bảng theo người giữ: giao / bán / trả / còn giữ / hạn / số ngày còn lại (không tiền) | cùng slot 17:30, **cùng 1 tin trên group chỉ định** | Thành viên group; web "Lô của tôi" vẫn chỉ cho chính người đó |

- Dedup theo slot `SALE_SLOT_yyyyMMdd_HHmm` (PropertiesService), ghi **sau khi gửi thành công**.
- **Đối soát tự động hằng ngày** (cùng 17:30): Nhập = `IN_STOCK`+`HELD`+`SOLD`+`DEFECTIVE/IN_REPAIR/REPAIRED`+`LOST` (không cộng trừ tay); mọi serial đúng 1 trạng thái; mọi `SOLD` có đơn; mọi lô `Đóng` có giao = bán + trả; số "còn giữ" trên web = tính lại từ nhật ký. Lệch → báo admin, **không tự sửa**.
- **Kiểm kê hằng tháng**: người giữ xác nhận danh sách đang giữ trên web; chênh lệch ghi sự kiện điều chỉnh có lý do.
- Cảnh báo: lô gần/quá 60 ngày, serial `DEFECTIVE/IN_REPAIR` quá N ngày, đơn `DRAFT` quá 3 ngày, tồn dưới ngưỡng.

## 9. Ngôn ngữ & định dạng
- Web: **VI mặc định + EN**, nút chuyển, nhớ lựa chọn, `<html lang>` đổi theo ngôn ngữ; không Myanmar. Một từ điển `t(key)` cho web + GAS + Python; nhãn tab qua `t()`. Tên tab Sheet là hằng số (không dịch).
- Thông báo lỗi server: `{ok:false, code:'ERR_*', params:{...}, msg_vi, msg_en}`; web dịch theo `code`. Mã: `ERR_UNAUTHORIZED`, `ERR_FORBIDDEN`, `ERR_STOCK_NEGATIVE`, `ERR_SERIAL_DUP`, `ERR_SERIAL_REQUIRED`, `ERR_ORDER_LOCKED`, `ERR_HOLD_EXCEEDED`, `ERR_LOT_EXPIRED`, `ERR_DUPLICATE`, `ERR_STATE_MISMATCH`, `ERR_SELF_APPROVE`.
- Tiền: **MMK**; lưu số thuần + cột `tien_te` (`MMK` mặc định); hiển thị `fmtMoney(v,cur,lang)` (VI `1.234.567 MMK`, EN `1,234,567 MMK`). Bỏ ký hiệu `₫`/VND khỏi giao diện và tin nhắn. Phần trăm lưu dấu chấm. Ngày hiển thị VI `dd/MM/yyyy`, EN `yyyy-MM-dd`.
- Chọn **một chính tả** "ký gởi" xuyên suốt.
- Thuật ngữ chuẩn:

| VI | EN |
|---|---|
| Tồn kho / Tồn khả dụng | Stock / Available stock |
| Công nợ tiền khách | Receivables |
| Trách nhiệm hàng người giữ | Custody liability |
| Đại lý | Dealer |
| Bán đứt | Outright sale |
| Ký gởi | Consignment |
| Lô giữ hàng / Người giữ hàng | Custody lot / Custodian |
| Giao nhân viên | Staff issue |
| Hàng trả | Return |
| Hàng hỏng | Defective goods |
| Gởi bảo hành | Sent for warranty repair |
| Đã bảo hành/Đổi | Repaired / Replaced |
| Chiết khấu theo lô | Per-lot discount |
| Giá áp dụng | Applied price |
| Hạn giữ tối đa | Max holding period |
| Hạn bảo hành | Warranty expiry |
| Hoa hồng | Commission |
| % nộp Tổng Cty | HQ remittance % |
| Tạm ứng | Advance |
| Nhập kho | Stock-in |

- Mẫu dòng trong tin group (2 dòng): `📦 {holder} — Lot {lo_id}: holding {n}, due {yyyy-MM-dd} ({d} days left)` / `📦 {holder} — Lô {lo_id}: còn giữ {n}, hạn {dd/MM/yyyy} (còn {d} ngày)`. Mã SKU, serial, số lô giữ nguyên.

## 10. Phân quyền & bảo mật (tiên quyết trước khi mở tính năng nhạy cảm)
- `admin`, `finance`: thấy giá vốn/lợi nhuận/CK/hoa hồng. `sales`, `warehouse`, `tech`, `dealer`: **không**; lọc theo whitelist cột theo vai trò **ở server**.
- **`holder_id` không nhận từ client**: server lấy từ session (email → staff_id). API "Lô của tôi" không có tham số holder; xem người khác chỉ qua action riêng có kiểm vai trò. Sales A gọi lô của B → 403.
- **Tách quyền (4 mắt)**: người giao ≠ người xác nhận nhận; người nhập TRA/HU ≠ người bị trừ; người duyệt ≠ người tạo; kho nhập TRA/HU ở trạng thái `Chờ xác nhận` cho tới khi người giữ xác nhận hoặc admin/finance duyệt; server từ chối khi actor trùng và ghi audit cả lần bị chặn.
- **Nhật ký bất biến thật**: chỉ append bằng 1 hàm GAS, range protected, hash chain (`SHA256(prev_hash + dòng)`), snapshot hằng ngày sang bản chỉ-đọc, job đối soát phát hiện đứt chuỗi. Sửa sai = sự kiện bù trừ (`REVERSAL`).
- Hành động nhạy cảm (hủy đơn đã xác nhận, gia hạn, sửa serial, điều chỉnh, sửa Cấu hình): chỉ `admin` + PIN kiểm phía server.
- **Đăng nhập thật**: Google Sign-In (ID token verify phía server: aud, exp, email_verified) → session ngắn hạn 8–12 giờ, kiểm trạng thái nhân viên ở **mỗi request**; Vercel làm cổng, gọi GAS kèm key + HMAC. Rate-limit: login/PIN 5 lần/15 phút, ghi 20/phút/session, fail-closed.
- **Telegram**: báo cáo gửi lên **group chỉ định** (id lấy từ `List Group Telegram` theo tên ở `Cau Hinh.sale_report_group`; thiếu/không khớp → bỏ qua và báo lỗi cho admin qua DM, KHÔNG đoán group). Tin group không chứa giá vốn/LN/CK/hoa hồng. Webhook thu thập có secret; thu thập chỉ nhận từ group nằm trong `List Group Telegram`. (Liên kết `telegram_id` cho DM cá nhân là tùy chọn, không bắt buộc.)
- Chưa xong đăng nhập thật thì **không phát hành** module lô/nợ/giá vốn lên web.

## 11. Tiêu chí nghiệm thu
1. Không token → 401 ở mọi action; sales gọi API thẳng không thấy giá vốn/LN/CK/hoa hồng/SĐT.
2. Ghi từ web và Telegram ra cùng schema; gửi lại cùng `idem_key` không tạo dòng trùng.
3. **Bộ ca test tay (khoảng 19 ca) khớp 100% với tab Tổng Hợp**:
   1. Nhập 3 serial → tồn 3. 2. Bán lẻ 1 → tồn 2, doanh thu +1 (khi xác nhận). 3. Bán đại lý (CK nhập tay) → tồn 1, `gia_ap_dung` đúng, tra serial ra đại lý + hạn BH. 4. Giao serial còn lại cho NV A (A xác nhận) → tồn 0, A còn giữ 1. 5. Giao lại cho NV B → chặn. 6. B bán serial của A → chặn. 7. A bán → doanh thu +1, còn giữ 0, lô đóng. 8. Gửi cùng `idem_key` hai lần → 1 dòng. 9. Hai request đồng thời bán cùng serial → 1 thành công, 1 từ chối. 10. Giao serial không tồn tại/đã bán → chặn. 11. Nhập trùng serial → chặn. 12. Kho nhập TRA (có xác nhận) → serial về kho, còn giữ −1. 13. Kho nhập hỏng → tồn không tăng, chuỗi BH đúng. 14. Hủy đơn Nháp không phát sinh doanh thu; sau gửi báo giá chỉ admin. 15. Hàng trả sau bán → doanh thu điều chỉnh, serial về kho. 16. NV nghỉ việc → thu hồi toàn lô, không BAN mới. 17. Lô ngày 53 cảnh báo; ngày 61 chặn BAN/giao thêm. 18. Sales gọi API trực tiếp → không thấy giá vốn; NV A không xem lô B. 19. Đối soát 0 lệch; cố tình sửa tay 1 ô → báo lệch.
   - Bảo mật thêm: kho tự duyệt trả khống → chặn; người giao tự xác nhận → chặn; NV `inactive` gọi API → 401; tin group không chứa serial đầy đủ/tên khách/SĐT/giá vốn.
4. Mỗi báo cáo đúng giờ, đúng một lần.
5. Không còn token/PIN/hash trong source; không còn `undefined`/`NaN` trên giao diện.
6. **Tiêu chí "xong"**: chạy hết ca test Critical/High; đối soát tự động ra 0 lệch trong 7 ngày liên tiếp; chạy song song 1–2 tuần với sổ tay trước khi cắt bản cũ.

## 12. Thứ tự thực thi (chốt schema một lần)
1. **Phase 0** — SPEC v1.4 (file này), chủ duyệt; trả lời câu hỏi Myanmar và xác nhận các mục `[MẶC ĐỊNH]` ở mục 0. *Dừng nếu chưa chốt.*
2. **Phase 1a** (xong, @474/@475/@476/@477) — trạng thái đơn, `idem_key`, sửa/xóa theo chủ đơn, tab `Cau Hinh`, tiền MMK.
3. **Phase 1b (MVP)** — tiên quyết, theo thứ tự: ① khóa quyền Sheet + snapshot + runbook (mục 15–16); ② bot Sale riêng + `SALE_API_KEY`/`SESSION_SECRET`/`SALE_COLLECT_SECRET` + HMAC Vercel→GAS + đăng nhập thật; ③ đổi trạng thái đơn sang **mã**; ④ chuẩn hóa serial + cột văn bản thuần; ⑤ hàm ghi duy nhất có `txn_id` PENDING/APPLIED + lock ngắn; ⑥ tab `Serial`, `Lo Giao`, `Lo Giao Chi Tiet`, `Lo Giao Su Kien`. *Dừng nếu fault-injection F1–F5 chưa đạt.*
4. **Phase 2** — chuyển trạng thái serial, công thức tồn, `Tong Hop`, chạy 19 ca test + F1–F14 trên bản copy. *Dừng nếu đối soát còn lệch.*
5. **Phase 2.5 — PILOT 2–4 tuần** với 1 nhóm nhỏ, chạy song song sổ tay; KPI: đơn nhập đúng hạn ≥ 90%, sai lệch kiểm kê ≤ 0,5%, báo cáo đúng giờ ≥ 95%. *Dừng/điều chỉnh nếu không đạt.*
6. **Phase 3** — giao diện: "Lô của tôi" + danh sách "Việc cần làm", form bán, bảo hành theo serial, kho nhập trả/hỏng, hàng đợi offline; một file `sale.html` chính; i18n `t()`; Guide For Staff.
7. **Phase 4** — đối soát tự động (`SENTINEL-SALE-RECON`), cảnh báo, báo cáo 17:30, kiểm kê hằng tháng; sau đó mới thêm hash-chain HMAC, `DOI_MAY`, `GIA_HAN`, `SUA_SERIAL` nếu có nhu cầu thật.

## 13. Ghế THỰC THI & ghế GIÁM SÁT Sale (mỗi ghế một việc, đúng chỗ)
| Loại | Mã ghế | Phạm vi duy nhất | Không được làm |
|---|---|---|---|
| Thực thi | `WEB-SALE-16` | `tni-search/sale.html` (+ bản sao `tni_sale.html` đến khi gộp): giao diện, `t()` VI/EN, "Lô của tôi" | Tự tính tồn/nợ; tự ghi Sheet; giữ token |
| Thực thi | `GAS-SALE-16` | `QLTC_GAS/sale_backend.gs` (Script `1rvgW…`, **một deployment ghi duy nhất**): **hàm ghi duy nhất**, máy trạng thái serial, RBAC cột, audit hash chain | Sửa chéo GAS khác; ghi ngoài hàm ghi duy nhất |
| Thực thi | `BOT-SALE-16` | Bot Telegram **riêng của Sale** (token mới, không dùng chung Site Down): thu thập đơn từ group trong `List Group Telegram`; gửi báo cáo lên group chỉ định | Gửi DM cá nhân dữ liệu lô; dùng token của Site Down |
| Thực thi | `TRAIN-SALE-1730` | Toa Sale trong `train_5min.yml` → `sale_summary_report.py`, **1 lần 17:30 MMT**, dedup `SALE_SLOT_yyyyMMdd_1730` | Workflow/cron riêng; chạy 11:30; đọc Telegram thay vì Sheet |
| Giám sát | `SENTINEL-SALE-RECON` (mới) | Đối soát hằng ngày: Nhập = tổng trạng thái serial; mọi serial đúng 1 trạng thái; mọi `SOLD` có đơn; kiểm hash chain `Sale Audit`/`Lo Giao Su Kien`; lô ≥53 ngày/quá 60 ngày; người `inactive` còn giữ; serial hỏng/bảo hành quá N ngày; tồn âm | Tự sửa dữ liệu (chỉ báo) |
| Giám sát | `AUDITOR-9.1` (sẵn có) | Sức khỏe: webhook bot Sale, 2 GAS ID cùng version, Sheet đọc được, báo cáo 17:30 đã gửi đúng 1 lần | — |
| Kênh báo lỗi | `AUDITOR-DM` | DM Admin cho mọi cảnh báo đỏ của ghế giám sát | Spam vào group chung |

- `SENTINEL-SALE-RECON` chạy **bên trong** Toa Auditor 9.1 của đoàn tàu `train_5min.yml` (không tạo workflow/cron/trigger riêng — Single Train). Kết quả đối soát nằm ở mục cuối tin 17:30 và, khi lệch, cảnh báo đỏ về DM Admin.
- Mỗi ghế khai báo trong `system_map.md` (ma trận ghế giám sát) và có rule kiểm tự động ở `system_auditor.py` ở Phase 4.

## 14. Rule sai chỗ nào sửa đúng chỗ đó (đối chiếu 03/10/2026)
| File | Chỗ sai | Sửa |
|---|---|---|
| `AGENTS.md` (Single Train, mục 1) | "Toa Sale Summary (11:30 & 17:30 MMT)" | → "Toa Sale Summary (17:30 MMT)" |
| `train_5min.yml` (2 bản `Task and WO`, `tni-search`) | điều kiện `check_time_exact 11 30 \|\| 17 30` | → chỉ `17 30` |
| `sale_summary_report.py` (2 bản; **bản `tni-sitedown` không đụng, đang vi phạm cô lập repo — chờ mở khóa thép để xóa**) | `_in_slot` cho 11:30 và 17:30 | → chỉ 17:30 |
| `sale_backend.gs` | `fmtVnd_` in `₫` | → định dạng MMK |
| `system_map.md` ma trận ghế | `GAS-SALE-16` ghi `@465`, `BOT-SALE-16` dùng token `8647102342` chung Site Down; chưa có ghế giám sát Sale | → cập nhật phiên bản @474/@475; BOT-SALE-16 chuyển sang bot riêng (khi tạo); thêm `TRAIN-SALE-1730` và `SENTINEL-SALE-RECON` |
| `AGENTS.md` PM-70 | thiếu quy tắc tin lên group chỉ định và ghế | → thêm mục 6–7 |

## 15. Độ tin cậy & vận hành (từ pre-mortem logic + bán hàng)
- **Giao dịch nhiều tab (không có transaction)**: mỗi thao tác = 1 `txn_id`; ghi nhật ký sự kiện `PENDING` **trước**, rồi áp trạng thái (`Serial`, lô, đơn), rồi đánh dấu `APPLIED`; job phục hồi replay/hủy `PENDING` quá N phút. `Serial` là **chỉ mục dẫn xuất**, nhật ký là nguồn đúng, có hàm dựng lại.
- **Lock**: giữ ngắn (chỉ kiểm tra + ghi), CẤM gọi Telegram/UrlFetch trong lock; chờ ≤ 20–30 giây; hết thì trả `ERR_BUSY`, client retry cùng `idem_key`.
- **Quy mô**: ước lượng khối lượng/năm (serial, đơn, sự kiện) và ghi vào đây; đọc theo vùng/chỉ mục (serial→dòng, `idem_key`), không `getDataRange()` toàn tab mỗi request; archive nhật ký >90 ngày sang tab theo tháng; theo dõi số ô (< 70% của 10 triệu ô) và quota Apps Script (cảnh báo > 60%); nêu ngưỡng chuyển sang CSDL thật. *Các con số giới hạn nền tảng phải xác nhận lại với tài liệu chính thức trước khi chốt.*
- **Bảo vệ Sheet**: protected range cho tab Serial/Su Kien/Audit/Cau Hinh; ẩn tab thô; đọc cột **theo tên header** và dừng khi header lệch; Editor ≤ 2 người, 2FA; người khác xem qua web.
- **Kiểu dữ liệu**: cột serial định dạng văn bản thuần (`@`) **trước** khi ghi; MMK số nguyên; `timeZone` manifest = `Asia/Yangon`; hạn 60 ngày tính theo ngày lịch (cuối ngày MMT); test biên 23:59/00:00.
- **Phiên bản bản ghi**: mỗi bản ghi có `version`; client gửi `base_version`, cũ hơn → `ERR_STATE_MISMATCH` (chống cache cũ ghi đè). Cache web khóa theo `schema_version`.
- **Sao lưu / khôi phục / rollback**: snapshot hằng ngày sang file/thư mục khác chủ, giữ ≥ 30–90 ngày, bản `.xlsx` ngoài Google hằng tuần; RPO ≤ 24 giờ, RTO ≤ 4 giờ; **diễn tập khôi phục hằng tháng** (restore vào bản copy + chạy đối soát); migration chạy trên bản copy trước, có `migration_state` (resume được), rollback = bỏ qua cột mới + khôi phục snapshot.
- **Báo cáo 17:30**: chạy theo **cửa sổ** (17:30–18:30) thay vì khớp phút; slot ghi `SENDING` rồi `SENT` + `message_id`; Auditor báo nếu 18:30 chưa gửi; chia tin ≤ 3500 ký tự đánh số phần, xử lý `retry_after` (429), escape HTML; thiếu group chỉ định thì báo DM admin **mỗi ngày** (không im lặng bỏ).
- **Telegram chỉ tạo đơn `DRAFT`**; web là nguồn chính; số Myanmar/toàn góc chuyển về 0-9 trước khi phân tích; bot phản hồi xác nhận đã ghi gì; không xóa tin gốc trước khi ghi thành công.
- **Mạng yếu**: web có hàng đợi gửi lại (`Chờ đồng bộ`), khóa nút Lưu sau khi bấm.
- **Thu tiền thực tế mọi kênh**: ghi `da_thu` + phương thức cho cả kênh đại lý (nợ ngoại lệ phải admin duyệt); đối chiếu ngân hàng/ví hằng tuần với doanh thu.
- **Cảnh báo có chủ & hạn xử lý** (tránh nhiễu): mỗi cảnh báo ghi người xử lý + hạn; báo cáo "tuổi cảnh báo"; "Chờ xác nhận" > 48 giờ nhắc admin. Chính sách hàng `LOST` (khấu trừ/bồi hoàn) do chủ duyệt, ghi vào SPEC.
- **Con người vận hành**: `staff_id` bất biến (không dùng email làm khóa); checklist onboarding/offboarding; cấm dùng chung tài khoản; runbook 1 trang (deploy, rollback, khôi phục, xoay secret), 2 người có quyền owner GAS/Sheet/Vercel, diễn tập mỗi quý.
- **Fault-injection (thêm vào nghiệm thu, chạy trên bản copy)**: F1 lỗi sau ghi `Su Kien` trước cập nhật `Serial`; F2 lỗi giữa `Serial` và `Lo Giao Chi Tiet`; F3 giữ lock 31 giây → `ERR_BUSY` và retry ra đúng 1 kết quả; F4 retry sau khi cache hết hạn → không trùng; F5 serial `00123`, `1E5`, `=1+1`, `ab 12`, Unicode → chuẩn hóa/từ chối đúng; F6 sửa tay 1 ô nhật ký → báo lệch, không tự sửa; F7 hai deployment lệch version → Auditor báo đỏ; F8 lỗi ngay trước khi ghi slot rồi chạy lại → không gửi trùng; F9 báo cáo > 4096 ký tự và 429 → chia tin, đúng `retry_after`; F10 `base_version` cũ → `ERR_STATE_MISMATCH`; F11 request lúc 23:59:59/00:00:01 MMT; F12 restore snapshot rồi đối soát 0 lệch và đo RTO; F13 dừng migration giữa chừng rồi chạy lại → idempotent; F14 50.000 dòng giả trong `Su Kien`, đo thời gian bán < 5 giây.

## 16. Bảo mật bổ sung (từ pre-mortem bảo mật)
- **Chống thông đồng** (kho + NV): ngưỡng/tuần/người cho `TRA`/`HU`/`LOST`; cặp (kho, NV) lặp > N lần → cảnh báo; `HU` bắt buộc ảnh có hash và **kỹ thuật xác nhận** (không chỉ kho); `HU`/`LOST`/`SUA_SERIAL`/`GIA_HAN` cần admin khác người liên quan; kiểm kê vật lý đột xuất do người thứ ba mỗi quý; điểm rủi ro theo người trong `SENTINEL-SALE-RECON`.
- **Group Telegram**: group riêng Sale, bật chặn forward/lưu nội dung; kiểm member định kỳ đối chiếu nhân viên active; tin **không** chứa serial đầy đủ (chỉ 4 số cuối), tên khách, SĐT, tiền chi tiết; dùng `staff_code` thay tên; bot không gửi khi số member tăng bất thường; offboarding gỡ khỏi group.
- **Giao thức HMAC Vercel→GAS**: GAS chỉ nhận request có `HMAC(secret, method|action|body_hash|ts|nonce|email|role)`; `ts` ± 120 giây; `nonce` lưu 5 phút chống replay (cache mất thì fail-closed cho ghi nhờ `idem_key` lưu Sheet); URL `/exec` không lộ trên client; theo dõi quota.
- **Phiên**: Google ID token chỉ dùng 1 lần đổi phiên (`exp` ≤ 5 phút + nonce); cookie `HttpOnly; Secure; SameSite=Strict`, sinh mới sau login, gắn hash UA, idle 30 phút, tối đa 8 giờ, đăng xuất hủy phía server (danh sách `revoked_at`); hành động nhạy cảm yêu cầu PIN + đăng nhập lại ≤ 15 phút; whitelist email.
- **Secret**: bot Sale riêng trước Phase 1b; xoay 2 khóa song song (current/previous); xoay 90 ngày và ngay khi người có quyền nghỉ; gitleaks trong CI; token cũ trong lịch sử git coi như chết sau khi thu hồi; 2FA cho Google/GitHub/Vercel/BotFather. (Token dùng chung với Site Down chỉ đổi khi có `UNLOCK STEEL`.)
- **Hash-chain nâng cấp** (sau MVP): kèm HMAC bằng khóa trong ScriptProperties; `onEdit` watcher ghi mọi sửa tay vào Audit + cảnh báo admin; khi chuỗi đứt: không tự sửa, admin đặt "mốc neo mới" có audit.
- **Serial nhạy cảm**: tra serial rate-limit 10/phút/user, serial không tồn tại và serial không thuộc người dùng trả cùng một thông báo (chống dò); bảo hành chỉ nhận serial `SOLD` của chính dealer/khách trong hạn.
- **Dữ liệu cá nhân**: chỉ lưu SĐT khi cần BH/nợ; che giữa trong UI trừ finance/admin/người tạo đơn; không đưa PII vào Telegram/log; thời hạn lưu và quyền xóa; tài liệu chính sách dữ liệu 1 trang. Cần hỏi pháp chế/luật sư địa phương về luật bảo vệ dữ liệu VN (Nghị định 13/2023/NĐ-CP) và Myanmar — SPEC không khẳng định điều khoản.
- **Export/log**: export chỉ admin/finance, có audit + watermark (email + giờ), giới hạn dòng/ngày, cột giá vốn cần PIN; CẤM log token/key/body đầy đủ/SĐT/giá vốn.
- **Kill-switch**: `kill_switch` (`ON`/`READ_ONLY`/`OFF`) trong **ScriptProperties** (không phụ thuộc Sheet có thể bị sửa), kiểm ở đầu cổng xác thực và hàm ghi; diễn tập định kỳ.
- **Incident response (≤ 15 phút)**: ① `READ_ONLY`; ② nghi lộ key → `OFF` + đổi `SALE_API_KEY`/`SESSION_SECRET` (đổi `SESSION_SECRET` hủy mọi phiên); ③ `deleteWebhook`/thu hồi token bot Sale (không phải Site Down); ④ gỡ người nghi ngờ khỏi staff, Editor Sheet, group. Rồi: snapshot + xuất version history + log; điều tra (hash/đối soát/onEdit); restore snapshot sạch; xoay secret (tạo mới → đặt vào GAS+Vercel → deploy → kiểm tra → revoke cũ); đối soát 0 lệch; tắt kill-switch từng bước; post-mortem → rule vào `AGENTS.md`. Diễn tập mỗi quý.
- **Rủi ro chấp nhận**: chủ Sheet/Script owner (2FA + snapshot); ≥ 2 người có quyền duyệt thông đồng (kiểm kê đột xuất + thống kê); chụp màn hình bởi người xem hợp lệ; phụ thuộc Google/Vercel/Telegram (backup ngoài).

## 17. Con người, ngôn ngữ & giao diện (từ pre-mortem song ngữ)
- **Serial**: chuẩn hóa NFKC, bỏ khoảng trắng/zero-width/dấu gạch, chữ hoa; quy tắc nhầm `O/0`, `I/l/1` **chỉ** áp khi SKU có định dạng serial xác định; ưu tiên quét mã vạch/QR; nhập hàng loạt có bước xem trước (IMEI kiểm Luhn nếu là điện thoại); từ chối chuỗi dạng khoa học (`E+`); sai thì gợi ý "Ý bạn là …"; hiển thị lại 4 số cuối để xác nhận.
- **So khớp theo ID** (`staff_id`, `dealer_id`, `sku`), không so tên; tên chuẩn hóa NFC khi ghi, thêm cột tìm kiếm bỏ dấu (`ten_chuan`); tìm kiếm chấp nhận "ký gởi/ký gửi".
- **Nhập số**: chuyển chữ số Myanmar `၀-၉` và toàn góc về `0-9`, bỏ dấu phân cách; **MMK và số lượng chỉ số nguyên**; phần trăm cho phép một dấu thập phân; hiển thị lại số đã hiểu để xác nhận.
- **Lỗi**: cấu trúc `{code, params, hint}`, mỗi lỗi 1 câu nguyên nhân + 1 câu việc cần làm + mã ngắn báo admin (VD `E-SER-02`), có VI và EN. Mẫu: `E-SER-02` VI "Serial {sn} đã ở nơi khác ({noi}). Kiểm tra lại số trên máy, hoặc báo admin." / EN "Serial {sn} is already at {noi}. Re-check the number on the unit or contact admin."; `E-STK-01` VI "Kho không đủ {sku}: cần {need}, còn {have}." / EN "Not enough {sku}: need {need}, have {have}."; `E-ACC-03` VI "Bạn chưa xác nhận nhận lô {lo_id}. Mở 'Lô của tôi' để xác nhận." / EN "You have not accepted lot {lo_id}. Open 'My lots' to accept."
- **Thuật ngữ dễ nhầm**: "Chờ nhận" (đã giao, chưa xác nhận) ≠ "Đang giữ" (đã nhận); "Trả kho (còn tốt)" ≠ "Báo hỏng"; nút khác màu, kèm mô tả 1 dòng; hộp xác nhận hiện lại số serial.
- **Danh mục SKU là nguồn duy nhất**: `sku`, `ten_vi`, `ten_en`, `ten_ngan` (≤ 20 ký tự cho tin); mọi kênh lấy từ đây.
- **Ngày trong tin**: `dd MMM yyyy` (VD `03 Oct 2026`); Sheet lưu ISO.
- **Đổi thuật ngữ**: khóa `t()` bất biến, chỉ sửa chữ hiển thị; mỗi thay đổi có `ver` và changelog; test tự động kiểm khóa; CẤM lọc/so sánh theo chữ hiển thị.
- **Hướng dẫn nhân viên**: Guide For Staff 1 trang/vai trò (ảnh nhiều, chữ ít), nút "?" trên màn hình, video 60 giây/tác vụ; đầu "Lô của tôi" có "Việc cần làm hôm nay". Tin group **không bao giờ là kênh duy nhất** cho việc phải làm.
- **Nếu không làm Myanmar**: dùng biểu tượng + màu + số cho trạng thái (✅ ⏳ ⚠️), nút có icon, hướng dẫn bằng ảnh, admin hỗ trợ trực tiếp giai đoạn đầu.
- **Mẫu tin group (~950 ký tự, mỗi dòng `VI/EN`, không bảng)**:
```
📊 SALE 17:30 | 03 Oct 2026
Bán/Sold: 6 | 24,500,000 MMK
Lẻ/Retail 3 · Đại lý/Dealer 2 · Ký gởi/Consign 1

📦 Tồn/Stock: P550 12 · P330 4 ⚠️ · P250 0 ❗
👤 Đang giữ/Holding
S07 Kyaw: còn/left 3 · hạn/due 20 Oct (17 ngày/days)
S12 Hla: còn/left 2 · hạn/due 08 Oct (5 ngày/days) ⚠️
S03 Min: còn/left 1 · QUÁ HẠN/OVERDUE 2 ngày/days ❗

⏳ Chờ nhận/Pending: S09 (30h)
🔧 Hỏng/Defect: 2 · BH/Repair: 1
💳 Nợ quá hạn/Overdue: 1
✅ Đối soát/Recon: OK
👉 Chi tiết/Details: web "Lô của tôi / My lots"
```
  Quá 1500 ký tự thì chỉ liệt kê 5 người giữ gần/quá hạn nhất rồi ghi "+N khác, xem web". Chỉ tổng doanh thu MMK, không giá vốn/LN/CK/hoa hồng.
