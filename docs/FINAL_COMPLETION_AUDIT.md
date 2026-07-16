# Final Completion Audit

_Updated after the completion increment. Branch: `claude/zenith-erp-scope-reduction-lxjtoi`._

Classification legend: **COMPLETE** · **PARTIAL** · **MISSING** · **BROKEN** ·
**HIDDEN** (built back-end, no UI yet, not shown) · **WIN-VERIFY**
(needs a Windows runner to confirm).

## How the audit was run

- `python -m compileall zenith` — passes.
- `pytest` under `QT_QPA_PLATFORM=offscreen` — **62 tests pass**.
- App shell built in offscreen mode for all five profiles; every sidebar page
  constructed and navigated without error.
- Searched for placeholder markers (`coming soon`, `NotImplementedError`,
  "This module is enabled…", mock data) — none rendered to users; unfinished
  modules are simply not registered in the sidebar.

## Feature status

| Area | Status | Notes |
|------|--------|-------|
| Five-profile architecture | COMPLETE | Data-driven registry; forbidden profiles proven absent by tests |
| Setup wizard (profile↔license) | COMPLETE | Enforces match; builds LTR/RTL |
| Login | PARTIAL | Real auth, loading state, i18n; Caps-Lock indicator best-effort |
| Main shell / sidebar / top bar | COMPLETE | Profile-driven, collapsible, responsive |
| **Additive migrations** | COMPLETE | ALTER TABLE ADD COLUMN for missing cols + pre-migration backup; not full Alembic |
| **Global Business Identity** | COMPLETE | Bilingual identity model + service + Settings→Business tab + logo mgmt; used in shell title/sidebar |
| **Business logo management** | COMPLETE | Validated, copied into managed dir, survives original deletion, in backups |
| Products (list + create) | COMPLETE | Profile-aware fields; numeric inputs fixed |
| **Duplicate-product prevention** | COMPLETE | Similar-item check; variants (strength/form) allowed; override path |
| **Product reuse / stock model** | COMPLETE | Stock only via transactions; repeated purchase reuses master (Paracetamol test) |
| **New Purchase page** | PARTIAL | Product search, create-product inline, add lines, approve→stock; no discounts/tax/attachments UI yet |
| **New Sale / POS page** | PARTIAL | Product search, add lines, cash/credit, paid; no barcode-scanner/hold/multi-pay UI yet |
| **Weighted-average cost & profit** | PARTIAL | Real current-WAC COGS + profit card; historical-at-sale WAC is future work |
| Pharmacy batch + **FEFO** | PARTIAL | Batch stock + FEFO suggestion + expired-sale block (service+tests); batch UI on purchase/sale pending |
| Customers / Suppliers | COMPLETE | List + create, wired |
| Inventory transfer/adjust | PARTIAL | Services complete + tested; dedicated screens pending |
| Sales list / Stock balance / Audit | COMPLETE | Live data pages |
| License page | COMPLETE | Status, import, copy request, transfer |
| Backup / Restore | COMPLETE | Create/verify/restore, profile-guarded |
| Users list | PARTIAL | List; add/edit/reset UI pending (service auth exists) |
| **Numeric inputs** | COMPLETE | CurrencyInput/QuantityInput with min widths; applied to product/purchase/sale forms |
| Bilingual (en/fa) + RTL | COMPLETE | 344 keys, parity + non-empty asserted |
| Returns (sales/purchase) | MISSING | Not built |
| Printing (A4/A5/58/80mm) | MISSING | Templates not built |
| Reports suite | PARTIAL | Dashboard metrics + profit; full report screens pending |
| Finance screens (receipts/payments/expenses) | HIDDEN | Models exist; screens pending |
| Windows build / installer | WIN-VERIFY | Spec + Inno script + CI provided; artifacts not yet produced on Windows |

## Honest headline

The product is a **substantially more complete, tested foundation** than the
previous iteration — the biggest correctness/honesty gaps (create_all-only
schema, fake zero profit, no business identity, no purchase/sale UI, overlapping
numeric fields, duplicate products) are now closed and covered by tests. It is
**not yet a finished commercial release**: returns, printing, the full reports
suite, several finance/admin screens, batch UI on transactions, and a
produced-and-verified Windows installer remain. These are tracked in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
