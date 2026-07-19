"""Branded document rendering.

Renders official documents (sales invoice A4, thermal receipts 80mm/58mm) as
self-contained HTML using the saved **business identity** -- logo, bilingual
name, phone, address, registration/tax numbers, footer and terms. The HTML is
printable via Qt (QTextDocument) and exportable to PDF, and is fully testable
headless: tests assert the identity, lines, totals and text direction appear.

Never renders sample data: every renderer takes a real posted document id.
"""

from __future__ import annotations

import html as html_mod
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from zenith.core.exceptions import NotFound
from zenith.db.models import Sale, Product, Customer, BusinessSettings, User
from zenith.services.business_identity import BusinessIdentityService
from zenith.ui import i18n


@dataclass
class RenderedDocument:
    html: str
    title: str
    paper: str  # "a4" | "80mm" | "58mm"


def _esc(value) -> str:
    return html_mod.escape("" if value is None else str(value))


def _money(value) -> str:
    return f"{Decimal(str(value or 0)):,.2f}"


def _identity_block(session: Session, locale: str) -> tuple[str, dict]:
    """Header HTML for the business identity + raw fields for footers."""
    svc = BusinessIdentityService(session)
    ident = svc.get_identity()
    settings = session.scalar(select(BusinessSettings).limit(1))
    logo_html = ""
    if ident.logo_path and Path(ident.logo_path).exists():
        logo_html = f'<img src="{_esc(ident.logo_path)}" style="max-height:64px;max-width:120px;" />'
    name = ident.name(locale)
    lines = [f"<div class='biz-name'>{_esc(name)}</div>"]
    if ident.slogan:
        lines.append(f"<div class='muted'>{_esc(ident.slogan)}</div>")
    contact_bits = [b for b in (ident.phone, ident.phone_secondary, ident.email) if b]
    if contact_bits:
        lines.append(f"<div class='muted'>{_esc(' · '.join(contact_bits))}</div>")
    addr = ident.address(locale)
    if addr:
        lines.append(f"<div class='muted'>{_esc(addr)}</div>")
    reg_bits = []
    if ident.registration_no:
        reg_bits.append(f"Reg: {ident.registration_no}")
    if ident.tax_no:
        reg_bits.append(f"Tax: {ident.tax_no}")
    if reg_bits:
        lines.append(f"<div class='muted'>{_esc(' · '.join(reg_bits))}</div>")
    header = (
        "<table class='head'><tr>"
        f"<td class='logo'>{logo_html}</td>"
        f"<td class='ident'>{''.join(lines)}</td>"
        "</tr></table>"
    )
    footers = {
        "footer": (settings.invoice_footer_fa if locale.startswith("fa") else settings.invoice_footer_en) or "",
        "terms": (settings.terms_fa if locale.startswith("fa") else settings.terms_en) or "",
        "currency": ident.currency,
    }
    return header, footers


def _base_css(paper: str, rtl: bool) -> str:
    direction = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    if paper == "a4":
        width = "190mm"; font = "12px"
    elif paper == "80mm":
        width = "72mm"; font = "11px"
    else:  # 58mm
        width = "50mm"; font = "10px"
    return f"""
    body {{ direction: {direction}; text-align: {align}; font-family: 'Segoe UI','Vazirmatn',Tahoma,sans-serif;
            font-size: {font}; width: {width}; margin: 0 auto; color: #111; }}
    .head {{ width: 100%; border-bottom: 1px solid #444; padding-bottom: 6px; margin-bottom: 8px; }}
    .biz-name {{ font-size: 1.35em; font-weight: bold; }}
    .muted {{ color: #444; font-size: 0.92em; }}
    table.items {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
    table.items th {{ border-bottom: 1px solid #444; padding: 3px 4px; text-align: {align}; }}
    table.items td {{ border-bottom: 1px dotted #999; padding: 3px 4px; }}
    .totals {{ margin-top: 8px; width: 100%; }}
    .totals td {{ padding: 2px 4px; }}
    .totals .grand {{ font-weight: bold; font-size: 1.15em; border-top: 1px solid #444; }}
    .docmeta {{ margin: 6px 0; }}
    .foot {{ border-top: 1px solid #444; margin-top: 10px; padding-top: 6px; font-size: 0.9em; color:#333; }}
    """


def render_sale_invoice(session: Session, sale_id: int, *, paper: str = "a4",
                        locale: str | None = None) -> RenderedDocument:
    """Render a posted sale as a branded invoice/receipt."""
    locale = locale or i18n.get_translator().locale
    rtl = locale in i18n.RTL_LOCALES
    trans = i18n.Translator(locale)  # locale-scoped so labels honor the passed locale
    tr = trans.tr

    sale = session.get(Sale, sale_id)
    if sale is None:
        raise NotFound(message_key="error.not_found")

    header, extras = _identity_block(session, locale)
    currency = extras["currency"]

    customer = session.get(Customer, sale.customer_id) if sale.customer_id else None
    user = session.get(User, sale.user_id) if sale.user_id else None

    meta = (
        f"<div class='docmeta'>"
        f"<b>{_esc(tr('sales.col.invoice'))}:</b> {_esc(sale.invoice_no)} &nbsp; "
        f"<b>{_esc(tr('common.date'))}:</b> {_esc(sale.date.isoformat())}<br>"
        f"<b>{_esc(tr('sales.col.customer'))}:</b> "
        f"{_esc(customer.name if customer else tr('sale.walk_in'))}"
        + (f" &nbsp; <b>{_esc(tr('common.phone'))}:</b> {_esc(customer.phone)}" if customer and customer.phone else "")
        + (f"<br><b>{_esc(tr('login.username'))}:</b> {_esc(user.full_name or user.username)}" if user else "")
        + "</div>"
    )

    rows = []
    for i, line in enumerate(sale.lines, start=1):
        product = session.get(Product, line.product_id)
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{_esc(product.name if product else line.product_id)}</td>"
            f"<td>{_money(line.quantity)}</td>"
            f"<td>{_money(line.unit_price)}</td>"
            f"<td>{_money(line.line_total)}</td>"
            "</tr>"
        )
    items = (
        "<table class='items'><thead><tr>"
        f"<th>#</th><th>{_esc(tr('products.col.name'))}</th>"
        f"<th>{_esc(tr('common.quantity'))}</th><th>{_esc(tr('common.price'))}</th>"
        f"<th>{_esc(tr('common.total'))}</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    remaining = (sale.total or Decimal("0")) - (sale.paid or Decimal("0"))
    # For a credit/partial sale to a registered (non-cash) customer, show the
    # account movement: previous balance -> this invoice's credit -> new balance.
    show_account = customer is not None and not customer.is_cash_customer and (
        sale.sale_type == "credit" or (sale.new_balance or Decimal("0")) != (sale.previous_balance or Decimal("0"))
    )
    account_rows = ""
    if show_account:
        account_rows = (
            f"<tr><td>{_esc(tr('customers.previous_balance'))}</td>"
            f"<td>{_money(sale.previous_balance)} {currency}</td></tr>"
            f"<tr class='grand'><td>{_esc(tr('customers.new_balance'))}</td>"
            f"<td>{_money(sale.new_balance)} {currency}</td></tr>"
        )
    totals = (
        "<table class='totals'>"
        f"<tr><td>{_esc(tr('common.total'))}</td><td>{_money(sale.subtotal)} {currency}</td></tr>"
        + (f"<tr><td>{_esc(tr('common.discount'))}</td><td>{_money(sale.discount)} {currency}</td></tr>"
           if sale.discount else "")
        + f"<tr class='grand'><td>{_esc(tr('purchase.grand_total'))}</td><td>{_money(sale.total)} {currency}</td></tr>"
        f"<tr><td>{_esc(tr('sale.paid'))}</td><td>{_money(sale.paid)} {currency}</td></tr>"
        f"<tr><td>{_esc(tr('sale.invoice_remaining'))}</td><td>{_money(remaining)} {currency}</td></tr>"
        + account_rows
        + "</table>"
    )

    foot_parts = []
    if extras["footer"]:
        foot_parts.append(f"<div>{_esc(extras['footer'])}</div>")
    if extras["terms"]:
        foot_parts.append(f"<div class='muted'>{_esc(extras['terms'])}</div>")
    foot = f"<div class='foot'>{''.join(foot_parts)}</div>" if foot_parts else ""

    html_doc = (
        f"<html><head><meta charset='utf-8'><style>{_base_css(paper, rtl)}</style></head>"
        f"<body>{header}{meta}{items}{totals}{foot}</body></html>"
    )
    return RenderedDocument(html=html_doc, title=f"{sale.invoice_no}", paper=paper)


def _voucher(session: Session, *, title_key: str, doc_no: str, day, party_label: str,
             party_name: str, amount, account_name: str, reference: str, note: str,
             paper: str, locale: str | None) -> RenderedDocument:
    """Shared branded voucher for receipts, supplier payments and expenses."""
    locale = locale or i18n.get_translator().locale
    rtl = locale in i18n.RTL_LOCALES
    trans = i18n.Translator(locale)  # locale-scoped so labels honor the passed locale
    tr = trans.tr
    header, extras = _identity_block(session, locale)
    currency = extras["currency"]

    rows = [
        (tr("common.date"), _esc(day.isoformat() if hasattr(day, "isoformat") else day)),
        (party_label, _esc(party_name)),
        (tr("finance.account"), _esc(account_name)),
        (tr("finance.reference"), _esc(reference or "-")),
    ]
    body_rows = "".join(
        f"<tr><td class='muted'>{label}</td><td>{value}</td></tr>" for label, value in rows
    )
    amount_html = (
        f"<table class='totals'><tr class='grand'>"
        f"<td>{_esc(tr('common.amount'))}</td><td>{_money(amount)} {currency}</td></tr></table>"
    )
    note_html = f"<div class='muted'>{_esc(note)}</div>" if note else ""
    foot = ""
    if extras["footer"]:
        foot = f"<div class='foot'>{_esc(extras['footer'])}</div>"

    html_doc = (
        f"<html><head><meta charset='utf-8'><style>{_base_css(paper, rtl)}</style></head><body>"
        f"{header}"
        f"<div class='docmeta'><b>{_esc(tr(title_key))}</b> &nbsp; "
        f"<b>{_esc(tr('finance.voucher_no'))}:</b> {_esc(doc_no)}</div>"
        f"<table class='items'>{body_rows}</table>{amount_html}{note_html}{foot}"
        f"</body></html>"
    )
    return RenderedDocument(html=html_doc, title=doc_no, paper=paper)


def render_customer_receipt(session: Session, payment_id: int, *, paper: str = "a4",
                            locale: str | None = None) -> RenderedDocument:
    from zenith.db.models import Payment, Customer, Account as Acc
    p = session.get(Payment, payment_id)
    if p is None:
        raise NotFound(message_key="error.not_found")
    tr = i18n.get_translator().tr
    cust = session.get(Customer, p.party_id) if p.party_id else None
    acc = session.get(Acc, p.account_id) if p.account_id else None
    return _voucher(session, title_key="finance.receipt_voucher", doc_no=p.ref_no, day=p.date,
                    party_label=tr("license.customer"), party_name=cust.name if cust else "-",
                    amount=p.amount, account_name=acc.name if acc else "-",
                    reference=p.reference, note=p.note, paper=paper, locale=locale)


def render_supplier_payment(session: Session, payment_id: int, *, paper: str = "a4",
                            locale: str | None = None) -> RenderedDocument:
    from zenith.db.models import Payment, Supplier, Account as Acc
    p = session.get(Payment, payment_id)
    if p is None:
        raise NotFound(message_key="error.not_found")
    tr = i18n.get_translator().tr
    sup = session.get(Supplier, p.party_id) if p.party_id else None
    acc = session.get(Acc, p.account_id) if p.account_id else None
    return _voucher(session, title_key="finance.payment_voucher", doc_no=p.ref_no, day=p.date,
                    party_label=tr("module.suppliers"), party_name=sup.name if sup else "-",
                    amount=p.amount, account_name=acc.name if acc else "-",
                    reference=p.reference, note=p.note, paper=paper, locale=locale)


def render_expense_voucher(session: Session, expense_id: int, *, paper: str = "a4",
                           locale: str | None = None) -> RenderedDocument:
    from zenith.db.models import Expense, ExpenseCategory, Account as Acc
    e = session.get(Expense, expense_id)
    if e is None:
        raise NotFound(message_key="error.not_found")
    tr = i18n.get_translator().tr
    cat = session.get(ExpenseCategory, e.category_id) if e.category_id else None
    acc = session.get(Acc, e.account_id) if e.account_id else None
    return _voucher(session, title_key="finance.expense_voucher", doc_no=e.voucher_no, day=e.date,
                    party_label=tr("module.expenses"), party_name=cat.name if cat else "-",
                    amount=e.amount, account_name=acc.name if acc else "-",
                    reference=e.reference, note=e.description, paper=paper, locale=locale)


def render_customer_statement(session: Session, customer_id: int, *, start=None, end=None,
                              paper: str = "a4", locale: str | None = None) -> RenderedDocument:
    """Render a branded customer account statement with a running balance."""
    from zenith.services import customer_ledger
    locale = locale or i18n.get_translator().locale
    rtl = locale in i18n.RTL_LOCALES
    tr = i18n.Translator(locale).tr

    customer = session.get(Customer, customer_id)
    if customer is None:
        raise NotFound(message_key="error.not_found")
    header, extras = _identity_block(session, locale)
    currency = extras["currency"]
    st = customer_ledger.statement(session, customer_id, start=start, end=end)

    meta_bits = [f"<b>{_esc(tr('license.customer'))}:</b> {_esc(customer.name)}"]
    if customer.phone:
        meta_bits.append(f"<b>{_esc(tr('common.phone'))}:</b> {_esc(customer.phone)}")
    if start or end:
        rng = f"{start.isoformat() if start else ''} - {end.isoformat() if end else ''}"
        meta_bits.append(f"<b>{_esc(tr('reports.period'))}:</b> {_esc(rng)}")
    meta = (
        f"<div class='docmeta'><b>{_esc(tr('customers.statement'))}</b><br>"
        + " &nbsp; ".join(meta_bits) + "</div>"
    )

    rows = [
        "<tr><td colspan='4'>" + _esc(tr("customers.opening_balance"))
        + f"</td><td>{_money(st.opening)} {currency}</td></tr>"
    ]
    for ln in st.lines:
        day = ln.at.date().isoformat() if hasattr(ln.at, "date") else _esc(ln.at)
        rows.append(
            "<tr>"
            f"<td>{_esc(day)}</td>"
            f"<td>{_esc(ln.ref_no or '-')}</td>"
            f"<td>{_esc(ln.description or ln.entry_type)}</td>"
            f"<td>{_money(ln.debit) if ln.debit else ''}"
            f"{('  -' + _money(ln.credit)) if ln.credit else ''}</td>"
            f"<td>{_money(ln.balance)} {currency}</td>"
            "</tr>"
        )
    items = (
        "<table class='items'><thead><tr>"
        f"<th>{_esc(tr('common.date'))}</th><th>{_esc(tr('finance.reference'))}</th>"
        f"<th>{_esc(tr('common.description'))}</th><th>{_esc(tr('common.amount'))}</th>"
        f"<th>{_esc(tr('customers.col.balance'))}</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    totals = (
        "<table class='totals'>"
        f"<tr><td>{_esc(tr('customers.total_purchases'))}</td><td>{_money(st.total_debit)} {currency}</td></tr>"
        f"<tr><td>{_esc(tr('customers.total_payments'))}</td><td>{_money(st.total_credit)} {currency}</td></tr>"
        f"<tr class='grand'><td>{_esc(tr('customers.closing_balance'))}</td>"
        f"<td>{_money(st.closing)} {currency}</td></tr>"
        "</table>"
    )
    foot = f"<div class='foot'>{_esc(extras['footer'])}</div>" if extras["footer"] else ""
    html_doc = (
        f"<html><head><meta charset='utf-8'><style>{_base_css(paper, rtl)}</style></head>"
        f"<body>{header}{meta}{items}{totals}{foot}</body></html>"
    )
    return RenderedDocument(html=html_doc, title=f"{customer.name} statement", paper=paper)


def export_pdf(doc: RenderedDocument, out_path: str | Path) -> Path:
    """Export a rendered document to PDF via QTextDocument (works offscreen)."""
    from PyQt6.QtGui import QTextDocument, QPageSize, QPageLayout
    from PyQt6.QtPrintSupport import QPrinter
    from PyQt6.QtCore import QMarginsF, QSizeF

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(out_path))
    if doc.paper == "a4":
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    else:
        width_mm = 80 if doc.paper == "80mm" else 58
        printer.setPageSize(QPageSize(QSizeF(width_mm, 297), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(5, 5, 5, 5), QPageLayout.Unit.Millimeter)

    text_doc = QTextDocument()
    text_doc.setHtml(doc.html)
    text_doc.print(printer)
    return out_path
