# BACKUP CONTEXT — 12/09/2026 (Phiên bản v800)
# THIẾT LẬP NGUYÊN TẮC: ĐỌC LẠI RULE TRƯỚC KHI PHÚC TRA & PHÚC TRA TOÀN DIỆN SAU KHI SỬA TRÁNH NHẦM HAY QUÊN (MINDSET RULE #7)

---

## 1. BỐI CẢNH & YÊU CẦU NGƯỜI DÙNG
- **Yêu cầu Người Dùng**: *"và thêm vào rule sau khi sửa gì là phải phúc tra lại toàn bộ tránh nhầm hay quên và đọc lại Rule trước khi phúc tra"*
- **Mục tiêu**: Đóng băng kỷ luật tư duy kỹ thuật tuyệt đối cho mọi phiên AI: Sau khi sửa bất kỳ thành phần nào, AI BẮT BUỘC phải:
  1. Đọc lại toàn bộ quy tắc cốt lõi trong `AGENTS.md` trước khi tiến hành phúc tra (để đối chiếu không vi phạm/bỏ sót quy định nào).
  2. Thực hiện đầy đủ 5 bước phúc tra toàn diện (Cú pháp/Logic, Tri-Repo Parity, Phụ thuộc 2 đầu, Git sống, Bằng chứng live thực tế) để loại bỏ 100% nguy cơ nhầm lẫn hoặc bỏ quên.

---

## 2. NỘI DUNG ĐÃ GHI NHẬN VÀO `AGENTS.md` (MINDSET ITEM 7)
Đã bổ sung vào mục `# 🧠 STRICT MINDSET RULE: KỶ LUẬT TƯ DUY AI MẪN CÁN, TỈ MỈ & LOGIC CHẮC CHẮN`:

> **7. Đọc Lại Rule Trước Khi Phúc Tra & Phúc Tra Toàn Diện Sau Khi Sửa Tránh Nhầm Hay Quên (Mandatory Rule Review & Full-Scope Post-Edit Verification Policy)**:
> - **ĐỌC LẠI RULE TRƯỚC KHI PHÚC TRA (Review Rules Before Verification)**: Trước khi tiến hành bước phúc tra hoặc kết luận bất kỳ tác vụ nào, AI BẮT BUỘC phải đọc lại toàn bộ các quy tắc liên quan trong `AGENTS.md` (Single Train, Repo Isolation, Khóa Thép Site Down, Template 2 dòng, Dedup, Rule phòng ngừa mới...) để rà soát đối chiếu xem giải pháp vừa sửa có vô tình vi phạm hoặc bỏ quên bất kỳ quy định nào không!
> - **PHÚC TRA TOÀN DIỆN SAU KHI SỬA TRÁNH NHẦM HAY QUÊN (Full-Scope End-to-End Cross-Verification)**: Sau MỌI lần chỉnh sửa code, cấu hình, lịch trình hoặc dữ liệu, AI BẮT BUỘC phải thực hiện đủ 5 bước phúc tra:
>   ① **Phúc tra Cú Pháp & Logic Code**: Chạy test import (`python -c "import ..."`) và validate cú pháp file, bảo đảm 0 lỗi biên dịch/runtime cơ bản.
>   ② **Phúc tra Đồng Bộ 3 Repositories (Tri-Repo Parity)**: Dùng công cụ so sánh đối chiếu (`fc` / `Compare-Object`) đảm bảo file đã được đồng bộ 100% qua cả 3 repos (`Task and WO`, `tni-search`, `tni-sitedown`), TUYỆT ĐỐI CẤM chỉ sửa 1 repo mà quên 2 repo còn lại!
>   ③ **Phúc tra Hai Đầu Phụ Thuộc (Upstream & Downstream Dependencies)**: Rà soát ai gọi hàm này, hàm này trả dữ liệu cho ai, kiểm tra các tính năng lân cận để bảo đảm ZERO tác dụng phụ (Zero Side-Effects).
>   ④ **Phúc tra Trạng Thái Git Sống**: Kiểm tra `git status` trên toàn bộ 3 repos và root, bảo đảm không sót bất kỳ file uncommitted hay untracked nào.
>   ⑤ **Phúc tra Bằng Chứng Live Thực Tế**: Kiểm tra HTTP 200, message_id thực tế hoặc log phản hồi thực trước khi bàn giao.
>   - **TUYỆT ĐỐI CẤM** nói "đã sửa xong", "hoàn thành" hay báo "ĐÃ LƯU ĐI" khi chưa hoàn tất đầy đủ 5 bước phúc tra trên!

---

## 3. BẢNG PHÂN BỔ SỐ GHẾ HỆ THỐNG & TRẠNG THÁI TRIỂN KHAI
| Ghế Phân Hệ | File | Version / Trạng Thái | Mô Tả Thay Đổi |
| :--- | :--- | :--- | :--- |
| **CORE-RULES** | `AGENTS.md` (x3 repos) | **v800** ✅ | Bổ sung Mindset Rule #7: Đọc lại Rule trước khi phúc tra & phúc tra 5 bước toàn diện |
| **DISCIPLINE** | Toàn bộ các phiên AI | **v800** ✅ | Bắt buộc đối chiếu Rule + 5 bước phúc tra trước khi báo "ĐÃ LƯU ĐI" |
| **DOCS-HISTORY** | `history/backup_context_20260912_v800.md` | **v800** ✅ | Lưu vết bối cảnh và chuẩn hóa quy trình phúc tra |
