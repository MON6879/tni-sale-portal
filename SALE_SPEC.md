# SALE_SPEC.md — Đặc tả nghiệp vụ Đoàn Tàu Sale (nguồn sự thật duy nhất)

> Quy trình bắt buộc: **sửa SPEC trước → sửa code → chạy lại bộ ca test**. Không code ngoài SPEC.
> Trạng thái: **v1 — DRAFT chờ duyệt** (03/10/2026). Mục ghi `[MẶC ĐỊNH]` là phương án tôi tự chọn vì người dùng chưa trả lời; đổi được bằng cách sửa file này.

## 1. Nguồn dữ liệu
- Google Sheet Sale (`1s-V0owHlwub4qrCxTUvKmXp4PWZthzk5oKhi5m_wQBA`) là **SSOT**. Web chỉ là giao diện, `localStorage` chỉ là cache đọc.
- Mọi ghi đi qua **một hàm ghi duy nhất** trong GAS (lock + `idem_key` + audit). Web, Telegram, train không tự ghi.
- Mỗi dòng có `id` (UUID) và `idem_key`. Giờ luôn `Asia/Yangon`, định dạng `yyyy-MM-dd HH:mm:ss`.
- Hệ số kinh doanh (83% / 17%, số ngày hạn nợ, ngưỡng tồn thấp) nằm ở **tab Cấu hình**, không hardcode trong code.

## 2. Vòng đời đơn bán (trạng thái)
`Nháp` → `Đã gửi báo giá` → `Đã xác nhận nhận hàng` → `Đã thanh toán đủ`

| Quy tắc | Nội dung |
|---|---|
| Sửa / xóa đơn | **Người tạo đơn tự sửa/xóa đơn của mình khi đơn còn `Nháp`** (chưa gửi báo giá cho khách). Từ `Đã gửi báo giá` trở đi: khóa; chỉ `admin` được sửa, mọi lần sửa/xóa ghi vào tab `Sale Audit`. *(người dùng chốt)* |
| Công nợ | Phát sinh **khi xác nhận nhận hàng** (`Đã xác nhận nhận hàng`), không phải lúc xuất kho. *(người dùng chốt)* |
| Thanh toán từng phần | [MẶC ĐỊNH] Có. Ghi cột `da_thu`; `con_no = tong_tien - da_thu`. |
| Hạn nợ | [MẶC ĐỊNH] 30 ngày, đặt ở tab Cấu hình. Quá hạn thì cảnh báo trong báo cáo ngày. |
| Ai xác nhận thu tiền | [MẶC ĐỊNH] `finance` và `admin`. |

## 3. Tồn kho
- `Tồn khả dụng = Nhập − Bán lẻ − Bán đứt đại lý − Ký gởi/giao NV đang giữ + Trả/Bảo hành nhập lại`.
- **Hàng ký gởi KHÔNG tính là đã bán** *(người dùng chốt)*: trừ khỏi tồn khả dụng, hiện riêng "Đang ký gởi". Chỉ thành doanh thu khi bán ra thật.
- [MẶC ĐỊNH] Serial bắt buộc với sản phẩm có serial, **duy nhất toàn hệ thống**, một serial chỉ ở một nơi tại một thời điểm (kho / lô ký gởi / đã bán). **Không cho tồn âm.**

## 4. Đại lý phân phối = BÁN ĐỨT *(người dùng chốt 03/10)*
- Phân phối cho đại lý là **bán đứt**: trừ kho và ghi doanh thu **ngay** khi ghi đơn. Không ký gởi, không theo dõi sau bán.
- Chỉ liên hệ lại đại lý khi **bảo hành**: mỗi đơn đại lý lưu `serial`, `ngay_ban`, liên hệ đại lý, `han_bao_hanh`; tra serial ra đại lý + ngày bán + hạn BH.
- **Không có hoa hồng và không có hạn nợ cho kênh đại lý** [MẶC ĐỊNH]. `CK%` = chiết khấu giá (giá đại lý = giá niêm yết × (1 − CK%)), lưu `gia_ap_dung` trên dòng đơn, đổi bảng giá không làm đổi đơn cũ. *(chờ chủ xác nhận: CK% là chiết khấu giá? có đại lý nào trả chậm không? Nếu có thì giữ `da_thu/con_no` cho đại lý đó.)*
- Hoa hồng (`hoa_hong`, ô nhập tay mỗi đơn) chỉ còn dùng cho đơn khác nếu cần; người xem: người tạo đơn, `finance`, `admin`; không gửi vào nhóm Telegram.
- Vai trò `dealer`: chỉ xem hàng đã mua của chính mình và tạo yêu cầu bảo hành; không thấy giá vốn, đại lý khác, tồn kho.
- Tab `Phan Phoi` và `Dai Ly` tách rõ: `Dai Ly` = danh bạ; `Phan Phoi` = đơn bán đứt. Bỏ `ngay_gui`/trạng thái đang giữ khỏi phân phối.

## 5. Ký gởi & giao hàng cho nhân viên sale *(người dùng chốt 03/10: chú trọng)*
- Ký gởi áp dụng cho: điểm bán/khách ký gởi và **từng nhân viên sale** (mỗi NV là một người giữ lô, xử lý như ký gởi).
- Mỗi lô theo dõi: `ngay_gui`, người giữ, SKU, serial, SL **giao / đã bán / đã trả / còn giữ**, trạng thái.
- **Người giữ thấy lượng tồn và đã bán của chính mình; admin thấy tất cả; NV không thấy lô của người khác.**
- Công thức: `còn giữ = giao − đã bán − đã trả`; khi bán ra thật thì ghi đơn bán và trừ lô.
- **Mô hình "Lô giữ hàng"** (chuyên gia đề xuất, chờ chủ duyệt): 3 tab `Lo Giao` (tiêu đề: lo_id, holder_type = consignee|staff, holder_id, ngay_giao, nguoi_giao, trang_thai), `Lo Giao Chi Tiet` (lo_id, sku, serial, sl), `Lo Giao Su Kien` (nhật ký bất biến GIAO/BAN/TRA/HU_BAO_HANH, idem_key, người ghi, `don_ban_id` khi BAN). Không sửa số trực tiếp; mọi số tính từ nhật ký.
- Ràng buộc (kiểm tra trong lock): BAN/TRA không vượt `còn giữ`; serial bán phải đang nằm trong lô của chính người bán; giao serial đã giữ/đã bán bị chặn. BAN chỉ ghi khi gắn với đơn thật trong `Ban Hang` (đó mới là doanh thu).
- Cột `kenh` trên đơn: `retail | dealer_outright | consignment_sale | staff_sale`.
- Tin ký gởi hằng ngày nằm trong báo cáo ngày 17:30 (không gửi tin riêng); mỗi người giữ nhận DM phần của mình. Màn web "Lô của tôi": Giao / Đã bán / Còn giữ + nút Bán, Trả lại.
- **Chủ đã chốt 03/10/2026 21:10:**
  1. **Chiết khấu nhập tay theo lô** (ô input mỗi lô phân phối/giao), không dùng CK% cố định của danh bạ làm giá chính; lưu `ck_lo` + `gia_ap_dung` trên dòng.
  2. **Đại lý không trả chậm** → không có công nợ/hạn nợ cho đại lý.
  3. **Ký gởi bắt buộc có serial** (không hàng không serial).
  4. **Mỗi lô giữ tối đa 2 tháng** (60 ngày; cấu hình `max_hold_days`=60); cảnh báo khi còn 7 ngày và khi quá hạn trong báo cáo ngày.
  5. **Hàng trả lại do kho (`warehouse`) nhập**; khi nhập, **giảm trừ công nợ/trách nhiệm hàng của nhân viên hoặc người ký gởi** (còn giữ −SL; serial về `Trong kho`).
  6. **Hàng hỏng cũng do kho nhập** và **theo dõi gởi bảo hành**: trạng thái `Hỏng → Gởi bảo hành → Đã bảo hành/Đổi → Trong kho`, có ngày gởi, nơi nhận, ngày nhận lại; hàng hỏng không tính vào tồn khả dụng.


## 6. Báo cáo
| Báo cáo | Nội dung | Gửi | Ai xem |
|---|---|---|---|
| **Báo cáo ngày: Tồn & Bán hàng** *(người dùng chốt)* | Bán trong ngày (SL, doanh thu theo kênh lẻ/đại lý), tồn kho theo SKU, tồn thấp, nợ quá hạn, tổng hợp ký gởi | [MẶC ĐỊNH] 1 lần/ngày lúc **17:30 MMT**; bỏ nhịp 11:30 | Nhóm Telegram vận hành; lợi nhuận/giá vốn **chỉ** `finance/admin` (DM) |
| Cảnh báo | Tồn dưới ngưỡng, nợ quá hạn | Nằm trong báo cáo ngày | như trên |

Mỗi tin dedup theo slot (`SALE_SLOT_yyyyMMdd_HHmm`, lưu PropertiesService), gửi lại cùng slot không gửi trùng.

## 7. Ngôn ngữ
- **Web: tiếng Việt (chính, mặc định) + tiếng Anh**, nút chuyển, nhớ lựa chọn. **Không làm Myanmar.** *(người dùng chốt)*
- [MẶC ĐỊNH] Tin Telegram/báo cáo: tiếng Anh theo quy tắc báo cáo hiện hành của hệ thống.
- Một từ điển `t(key)` duy nhất cho web + GAS + python. Thuật ngữ chuẩn:

| VI | EN |
|---|---|
| Tồn kho | Stock |
| Công nợ | Receivables |
| Đại lý | Dealer |
| Ký gởi | Consignment |
| Bảo hành | Warranty |
| % nộp Tổng Cty | HQ remittance % |
| Hoa hồng | Commission |
| Tạm ứng | Advance |
| Nhập kho | Stock-in |

## 8. Phân quyền
- `admin`, `finance`: thấy giá vốn/lợi nhuận. `sales`, `warehouse`, `tech`, `dealer`: **không** thấy; lọc ở server, không chỉ ẩn ở giao diện.
- Đăng nhập thật (Google Sign-In → phiên ngắn hạn do server cấp). PIN chỉ là lớp xác nhận thứ hai, kiểm tra phía server.

## 9. Tiêu chí nghiệm thu chung
1. Không token → 401 ở mọi action; sales gọi API thẳng không thấy giá vốn/LN/SĐT.
2. Ghi từ web và từ Telegram ra cùng schema; Telegram gửi lại không tạo dòng trùng.
3. Bộ 10–15 ca test số tay (nhập/bán/ký gởi/trả/thanh toán từng phần) khớp 100% với tab Tổng Hợp.
4. Sửa/xóa đơn `Nháp` bởi chủ đơn thành công; đơn đã gửi báo giá bị chặn với người không phải admin.
5. Mỗi báo cáo trong mục 6 đúng giờ, đúng một lần.
6. Không còn token/PIN/hash trong source; không còn `undefined`/`NaN` trên giao diện.

## 10. Còn mở (cần người dùng xác nhận)
- Các mục `[MẶC ĐỊNH]` ở trên.
- Cấu trúc cột thật của tab `Nhap Hang`/`Ban Hang`/`Dai Ly`/`Ky Goi` (cần đọc dữ liệu sống trước khi thiết kế migration; backup trước khi đổi).
