# SALE_SPEC.md — Đặc tả nghiệp vụ Đoàn Tàu Sale (nguồn sự thật duy nhất)

> Quy trình bắt buộc: **sửa SPEC trước → sửa code → chạy bộ ca test**. Không code ngoài SPEC.
> Trạng thái: **v1.3** (03/10/2026) — gộp quyết định của chủ (tiền tệ MMK, báo cáo lên GROUP chỉ định) + rà soát 4 chuyên gia (bán hàng, logic, bảo mật, song ngữ) + ghế thực thi/giám sát (mục 13) + sửa rule đúng chỗ (mục 14). Mục `[MẶC ĐỊNH]` là phương án tạm chọn, đổi bằng cách sửa file này.

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
| Tin nhóm theo template 2 dòng EN + VI | [MẶC ĐỊNH] chờ chủ xác nhận |

## 1. Nguồn dữ liệu
- Google Sheet Sale (`1s-V0owHlwub4qrCxTUvKmXp4PWZthzk5oKhi5m_wQBA`) là **SSOT**. Web chỉ là giao diện, `localStorage` chỉ là cache đọc.
- Mọi ghi đi qua **một hàm ghi duy nhất** trong GAS: lock + `idem_key` + audit. Web, Telegram, train không tự ghi.
- `idem_key` bắt buộc; server lưu trong Sheet (không chỉ cache) và trả kết quả cũ khi gặp lại. Web sinh UUID khi mở form; Telegram dùng `chatId_messageId`.
- Giờ luôn do server, `Asia/Yangon`, `yyyy-MM-dd HH:mm:ss`. Không tin giờ client.
- Hệ số kinh doanh (ngưỡng CK, `max_hold_days`=60, ngưỡng tồn thấp, hạn nợ) nằm ở **tab `Cau Hinh`**; chỉ admin sửa, có audit.
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
| `HELD` | Đang giữ (ký gởi/giao NV) | Held (custody) |
| `SOLD` | Đã bán | Sold |
| `DEFECTIVE` | Hỏng | Defective |
| `IN_REPAIR` | Gởi bảo hành | In warranty repair |
| `REPAIRED` | Đã bảo hành/Đổi | Repaired / Replaced |
| `LOST` | Mất/Thất thoát (admin xác nhận) | Lost |

| Chuyển | Điều kiện | Ai |
|---|---|---|
| (mới) → `IN_STOCK` | Nhập kho, serial chưa tồn tại | warehouse |
| `IN_STOCK` → `HELD` | Giao lô cho người giữ hợp lệ; **người nhận phải xác nhận** | warehouse/admin tạo; người nhận xác nhận |
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
   - Bảo mật thêm: kho tự duyệt trả khống → chặn; người giao tự xác nhận → chặn; NV `inactive` gọi API → 401; DM không chứa dòng người khác.
4. Mỗi báo cáo đúng giờ, đúng một lần.
5. Không còn token/PIN/hash trong source; không còn `undefined`/`NaN` trên giao diện.
6. **Tiêu chí "xong"**: chạy hết ca test Critical/High; đối soát tự động ra 0 lệch trong 7 ngày liên tiếp; chạy song song 1–2 tuần với sổ tay trước khi cắt bản cũ.

## 12. Thứ tự thực thi (chốt schema một lần)
1. **Phase 0** — SPEC v1.2 (file này), chủ duyệt; xác nhận 2 mục `[MẶC ĐỊNH]` ở mục 0.
2. **Phase 1a** (xong, @474/@475) — trạng thái đơn, `idem_key`, sửa/xóa theo chủ đơn, tab `Cau Hinh`.
3. **Phase 1b** — đổi trạng thái đơn sang **mã**; tab `Serial`, `Lo Giao`, `Lo Giao Chi Tiet`, `Lo Giao Su Kien`; hàm ghi duy nhất (lock + idem + audit hash chain); đăng nhập thật (cần `SALE_API_KEY`, `SESSION_SECRET`, `SALE_COLLECT_SECRET`, OAuth Client ID, đổi bot token); tách quyền 4 mắt. Đọc dữ liệu sống + backup + thử trên bản copy trước.
4. **Phase 2** — chuyển trạng thái serial, công thức tồn, `Tong Hop`, chạy 19 ca test.
5. **Phase 3** — giao diện: "Lô của tôi", form bán, bảo hành theo serial, kho nhập trả/hỏng; một file `sale.html` chính, bỏ bản lệch; i18n `t()`.
6. **Phase 4** — đối soát tự động, cảnh báo, báo cáo 17:30, DM liên kết Telegram, kiểm kê hằng tháng; chạy song song 1–2 tuần.

## 13. Ghế THỰC THI & ghế GIÁM SÁT Sale (mỗi ghế một việc, đúng chỗ)
| Loại | Mã ghế | Phạm vi duy nhất | Không được làm |
|---|---|---|---|
| Thực thi | `WEB-SALE-16` | `tni-search/sale.html` (+ bản sao `tni_sale.html` đến khi gộp): giao diện, `t()` VI/EN, "Lô của tôi" | Tự tính tồn/nợ; tự ghi Sheet; giữ token |
| Thực thi | `GAS-SALE-16` | `QLTC_GAS/sale_backend.gs` (Script `1rvgW…`, ID chính + ID phụ): **hàm ghi duy nhất**, máy trạng thái serial, RBAC cột, audit hash chain | Sửa chéo GAS khác; ghi ngoài hàm ghi duy nhất |
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
