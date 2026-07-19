"""Print preview dialog.

Shows the real rendered document (never sample data), lets the user switch paper
size (A4 / 80mm / 58mm), print to a physical printer, or export a PDF.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QTextBrowser, QFileDialog, QMessageBox,
)

from zenith.db.base import session_scope
from zenith.services.printing import (
    render_sale_invoice, render_customer_receipt, render_supplier_payment,
    render_expense_voucher, render_customer_statement, export_pdf,
)
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.common import Toast

PAPERS = [("a4", "print.paper.a4"), ("80mm", "print.paper.80mm"), ("58mm", "print.paper.58mm")]

_VOUCHER_RENDERERS = {
    "receipt": render_customer_receipt,
    "supplier_payment": render_supplier_payment,
    "expense": render_expense_voucher,
}


class SalePrintPreviewDialog(QDialog):
    def __init__(self, ctx, sale_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.sale_id = sale_id
        self._doc = None
        self.setWindowTitle(ctx.tr("print.preview"))
        self.setMinimumSize(680, 640)

        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.paper = QComboBox()
        for key, tr_key in PAPERS:
            self.paper.addItem(ctx.tr(tr_key), key)
        self.paper.currentIndexChanged.connect(lambda _i: self._render())
        bar.addWidget(self.paper)
        bar.addStretch(1)
        pdf_btn = SecondaryButton(ctx.tr("print.pdf"))
        pdf_btn.clicked.connect(self._export_pdf)
        bar.addWidget(pdf_btn)
        print_btn = PrimaryButton(ctx.tr("print.print"))
        print_btn.clicked.connect(self._print)
        bar.addWidget(print_btn)
        close_btn = SecondaryButton(ctx.tr("common.close"))
        close_btn.clicked.connect(self.reject)
        bar.addWidget(close_btn)
        lay.addLayout(bar)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        lay.addWidget(self.view, 1)
        self._render()

    def _render(self):
        paper = self.paper.currentData() or "a4"
        try:
            with session_scope(self.ctx.db) as s:
                self._doc = render_sale_invoice(s, self.sale_id, paper=paper, locale=self.ctx.locale)
            self.view.setHtml(self._doc.html)
        except Exception as exc:  # pragma: no cover - GUI error path
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))

    def _export_pdf(self):
        if not self._doc:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.ctx.tr("print.pdf"), f"{self._doc.title}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            out = export_pdf(self._doc, Path(path))
            Toast.show_message(self, self.ctx.tr("print.exported", path=out.name), "success")
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))

    def _print(self):  # pragma: no cover - needs a physical printer
        if not self._doc:
            return
        try:
            from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
            from PyQt6.QtGui import QTextDocument

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dlg = QPrintDialog(printer, self)
            if dlg.exec():
                text_doc = QTextDocument()
                text_doc.setHtml(self._doc.html)
                text_doc.print(printer)
        except Exception as exc:
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))


class VoucherPreviewDialog(SalePrintPreviewDialog):
    """Print preview for finance vouchers (receipt / supplier payment / expense)."""

    def __init__(self, ctx, kind: str, doc_id: int, parent=None):
        self._kind = kind
        super().__init__(ctx, doc_id, parent)

    def _render(self):
        paper = self.paper.currentData() or "a4"
        renderer = _VOUCHER_RENDERERS[self._kind]
        try:
            with session_scope(self.ctx.db) as s:
                self._doc = renderer(s, self.sale_id, paper=paper, locale=self.ctx.locale)
            self.view.setHtml(self._doc.html)
        except Exception as exc:  # pragma: no cover - GUI error path
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))


class StatementPreviewDialog(SalePrintPreviewDialog):
    """Print preview for a customer's branded account statement."""

    def __init__(self, ctx, customer_id: int, *, start=None, end=None, parent=None):
        self._start = start
        self._end = end
        super().__init__(ctx, customer_id, parent)

    def _render(self):
        paper = self.paper.currentData() or "a4"
        try:
            with session_scope(self.ctx.db) as s:
                self._doc = render_customer_statement(
                    s, self.sale_id, start=self._start, end=self._end,
                    paper=paper, locale=self.ctx.locale)
            self.view.setHtml(self._doc.html)
        except Exception as exc:  # pragma: no cover - GUI error path
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))
