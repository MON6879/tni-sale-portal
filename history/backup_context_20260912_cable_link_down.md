# Backup Context: Phan he Bot 15 TNI CABLE — Cable Link Down Report (:16 / :46 MMT)

**Ngay thuc hien:** 12/09/2026  
**Nguoi yeu cau:** User  
**Muc tieu:**
1. Thu thap du lieu truc tiep 100% tu Google Sheet SSOT: Spreadsheet Cable Collect Database +MDG (1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y), tab Link down now (GID 263097982), Cot C (tu dong 2 tro di).
2. Dung Bot 15 TNI CABLE (@TNI_CABLE_BOT, Token 8758104446:AAH3o7lMCxBXn70ThAXweH1DddmRkJrgwWo).
3. Gui vao Telegram Group: 8 TNI CABLE BROKEN SOS (Chat ID -5531350787).
4. Chu ky: Moi 30 phut mot lan, lech gio hop ly sau Site Down (:06/:36), chon moc :16 va :46 MMT (dung 10 phut sau Site Down, 5 phut sau ETA :11/:41).
5. Co che xoa tin cu: Tin nao xoa tin nay truoc khi gui tin moi thong qua delete_old_helper.py voi key CABLE_LINK_DOWN_REPORT.
6. Ngon ngu: 100% tieng Anh theo chuan STRICT ENGLISH-ONLY BOT RESPONSE POLICY.
7. Dinh dang cham mau theo Team chuan Site Down (T1 va T1S1 cung mau):
   - T1 / T1 S1 / T1s1: 🟠 (Orange)
   - T2 / T2 S1 / T2s1: 🔵 (Blue)
   - T3 / T3 S1 / T3s1: 🟢 (Green)
   - T4 / T4 S1 / T4s1: 🟡 (Yellow)
   - Header moi link: {emoji} <b>Link #{idx} | {tag}:</b>
   - Noi dung trong o: tu dong thay the ma Team thanh {emoji}{Team}, ngan ngat dong 🔗 link down va Plz note.
   - Escape HTML dac biet (&lt;, &gt;, &amp;) tranh loi parse entities Telegram.
8. Khoa doan tau tuan tu: Tich hop Toa Cable Link Down truc tiep vao train_5min.yml, chay tuan tu tren 1 may ao runner duy nhat (MON6879/tni-sitedown-relay), tuyet doi khong tach workflow rieng.

---

## 1. Kich Ban Thuc Thi (cable_link_down_report.py)
- Vi tri: Task and WO, tni-sitedown, tni-search.
- Ham chinh:
  - fetch_link_down_items(): Doc CSV song tu Google Sheet.
  - get_team_info(team_raw, text_val): Xac dinh emoji va tag team.
  - colorize_team_in_text(text): Gan cham mau theo chuan Site Down va format text.
  - build_telegram_message(items): Xay dung noi dung 100% tieng Anh.
  - send_telegram_report(text): Gui tin qua Bot API Bot 15.
  - delete_old_messages_bot(token, cid, gas_url, key): Xoa tin cu qua delete_old_helper.py.
  - save_msgids(gas_url, key, msgids): Luu message_id moi vao GAS PropertiesService.

---

## 2. Ket Qua Kiem Thu Live
- Kiem thu xoa tin cu: Message ID 39 da duoc xoa sach khoi nhom (-5531350787).
- Kiem thu gui tin moi: Message ID 40 da gui thanh cong voi day du cham mau T3 (🟢) va T2s1 (🔵).
- Kiem thu luu ID: Message ID 40 da luu vao GAS PropertiesService thanh cong.
