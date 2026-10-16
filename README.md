# ⚡ TNI Sale & Operations Portal

Enterprise Management Portal for Solar Energy, UPS Solutions & Field Operations.

---

## 🌐 Portal Navigation & Live Links

| Module | File | Direct Link | Description |
|---|---|---|---|
| **🛒 Sale & Inventory Portal** | `sale.html` | [Open Sale Portal](https://mon6879.github.io/tni-sale-portal/sale.html) | Quotations, Inventory, In/Out stock, Advance payments & RBAC Role-Based Access Control |
| **🚀 Operations Management** | `index.html` | [Open Operations Hub](https://mon6879.github.io/tni-sale-portal/index.html) | Work Orders, Daily Plans, Task Notes, Department Assignments & Construction Management |
| **📊 Executive BI Dashboard** | `executive_dashboard.html` | [Open Executive Dashboard](https://mon6879.github.io/tni-sale-portal/executive_dashboard.html) | High-level Executive Summary, Financial Overview, Real-time Station KPIs & BOD Reports |

---

## 🔒 Security & Access Control

- **Universal Password Gate**: All public-facing portals are protected by client-side SHA-256 password authentication.
- **Default System Password**: `TNI@2026`
- **Session Duration**: Active for 8 hours (480 minutes) per device.
- **30-Day Rotation**: Automatic prompt to update credentials every 30 days.
- **Zero-PII Compliance**: No personal phone numbers, emails, or sensitive internal credentials stored in public repositories.
- **Role-Based Access Control (RBAC)**:
  - 👑 **BOD (Admin)**: Full access to all 20 modules including financial metrics and profit margin calculations.
  - 💰 **Finance & Accounting**: Dedicated access to Statements, HO 17% quota, and Cost of Goods Sold (83%).
  - 🧑‍💼 **Sales**: Quotes, Solar presets, Stock availability, CRM, and Clients. Financial data is strictly locked.
  - 🚀 **Field Ops & Technical**: Site surveys, Handover acceptance, Site Down telemetry. Financial data is strictly locked.
  - 📦 **Warehouse**: Stock levels, Intake/Dispatch tracking, Advance requests. Financial data is strictly locked.
  - 🏪 **Authorized Dealers**: Wholesale pricing and Consignment ledger. Internal operations are strictly locked.

---

## 🌐 Language & Localization

- Full bilingual support (**Tiếng Việt** / **English**).
- Toggle anytime via the top-right header button (`🌐 VN / EN`).
- Dynamic real-time translation for all navigation items, tables, security matrix, and form inputs.

---

## 🛠️ Deployment & Hosting

- **Hosted on**: GitHub Pages & Vercel Serverless
- **Repository**: [MON6879/tni-sale-portal](https://github.com/MON6879/tni-sale-portal)
- **Live Base URL**: `https://mon6879.github.io/tni-sale-portal/`
