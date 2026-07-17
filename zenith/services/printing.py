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
    tr = lambda k, **p: i18n.get_translator().tr(k, **p)  # noqa: E731

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
    totals = (
        "<table class='totals'>"
        f"<tr><td>{_esc(tr('common.total'))}</td><td>{_money(sale.subtotal)} {currency}</td></tr>"
        + (f"<tr><td>{_esc(tr('common.discount'))}</td><td>{_money(sale.discount)} {currency}</td></tr>"
           if sale.discount else "")
        + f"<tr class='grand'><td>{_esc(tr('purchase.grand_total'))}</td><td>{_money(sale.total)} {currency}</td></tr>"
        f"<tr><td>{_esc(tr('sale.paid'))}</td><td>{_money(sale.paid)} {currency}</td></tr>"
        f"<tr><td>{_esc(tr('customers.col.balance'))}</td><td>{_money(remaining)} {currency}</td></tr>"
        "</table>"
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
