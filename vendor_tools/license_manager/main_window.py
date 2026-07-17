"""Zenith License Manager main window (owner-only)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QPlainTextEdit, QTabWidget, QScrollArea, QFrame, QCheckBox,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QDialogButtonBox,
)

from zenith.licensing.model import LicenseType, SignedLicense
from zenith.licensing.request import MachineRequest, RequestError
from zenith.profiles import ProfileCode, get_profile
from zenith.profiles import modules as M

from vendor_tools.license_manager import i18n
from vendor_tools.license_manager.models.db import session_scope
from vendor_tools.license_manager.services import generator, history, backup as vbackup
from vendor_tools.license_manager.services.keystore import KeyStoreError, BadPassphrase
from vendor_tools.license_manager.services.owner_auth import OwnerAuthService

from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton, GhostButton

_PROFILE_NAMES = {
    "GENERAL_STORE": "General Store", "SUPERMARKET": "Supermarket", "WHOLESALE": "Wholesale",
    "PHARMACY": "Pharmacy", "WAREHOUSE": "Warehouse",
}


def _ltr(widget):
    """Force LTR for cryptographic / path fields, even in RTL mode."""
    widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    return widget


def _section(title: str) -> tuple[QFrame, QGridLayout]:
    frame = QFrame(); frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    head = QLabel(title); head.setProperty("role", "h2")
    lay.addWidget(head)
    grid = QGridLayout(); grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1)
    lay.addLayout(grid)
    return frame, grid


class MainWindow(QMainWindow):
    def __init__(self, state, controller=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.controller = controller
        self.tr = i18n.tr
        self._last_result: generator.GenerationResult | None = None
        self.setWindowTitle(self.tr("app.name"))
        self.setMinimumSize(1024, 720)

        central = QWidget(); central.setObjectName("Root")
        root = QVBoxLayout(central)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._generate_tab(), self.tr("tab.generate"))
        self.tabs.addTab(self._history_tab(), self.tr("tab.history"))
        self.tabs.addTab(self._bundle_tab(), self.tr("tab.bundle"))
        self.tabs.addTab(self._security_tab(), self.tr("tab.security"))
        root.addWidget(self.tabs)
        self.setCentralWidget(central)

    # ==================================================================
    # Generate tab
    # ==================================================================
    def _generate_tab(self) -> QWidget:
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget(); host.setObjectName("Root")
        lay = QVBoxLayout(host)

        # customer
        cust, g = _section(self.tr("gen.customer"))
        self.f_customer = QLineEdit(); self.f_business = QLineEdit()
        self.f_phone = QLineEdit(); self.f_email = QLineEdit()
        self.f_address = QLineEdit(); self.f_custid = QLineEdit()
        g.addWidget(QLabel(self.tr("gen.customer_name")), 0, 0); g.addWidget(self.f_customer, 0, 1)
        g.addWidget(QLabel(self.tr("gen.business_name")), 0, 2); g.addWidget(self.f_business, 0, 3)
        g.addWidget(QLabel(self.tr("gen.phone")), 1, 0); g.addWidget(_ltr(self.f_phone), 1, 1)
        g.addWidget(QLabel(self.tr("gen.email")), 1, 2); g.addWidget(_ltr(self.f_email), 1, 3)
        g.addWidget(QLabel(self.tr("gen.address")), 2, 0); g.addWidget(self.f_address, 2, 1, 1, 3)
        lay.addWidget(cust)

        # machine
        mach, g = _section(self.tr("gen.machine"))
        self.f_fingerprint = _ltr(QLineEdit()); self.f_fingerprint.setMinimumWidth(420)
        self.f_fingerprint.textChanged.connect(self._update_fp_status)
        self.fp_status = QLabel("")
        paste = SecondaryButton(self.tr("gen.paste_request")); paste.clicked.connect(self._paste_request)
        imp = SecondaryButton(self.tr("gen.import_request")); imp.clicked.connect(self._import_request)
        g.addWidget(QLabel(self.tr("gen.fingerprint")), 0, 0); g.addWidget(self.f_fingerprint, 0, 1, 1, 3)
        g.addWidget(self.fp_status, 1, 1, 1, 3)
        row = QHBoxLayout(); row.addWidget(paste); row.addWidget(imp); row.addStretch(1)
        g.addLayout(row, 2, 0, 1, 4)
        lay.addWidget(mach)

        # profile + type + validity + limits
        cfg, g = _section(self.tr("gen.validity"))
        self.f_profile = QComboBox()
        for c in [p.value for p in ProfileCode]:
            self.f_profile.addItem(_PROFILE_NAMES[c], c)
        self.f_profile.currentIndexChanged.connect(self._on_profile_changed)
        self.f_type = QComboBox()
        self.f_type.addItem(self.tr("gen.type.demo"), "DEMO")
        self.f_type.addItem(self.tr("gen.type.full"), "FULL")
        self.f_type.currentIndexChanged.connect(self._on_type_changed)
        self.f_full_mode = QComboBox()
        self.f_full_mode.addItem(self.tr("gen.subscription"), "sub")
        self.f_full_mode.addItem(self.tr("gen.perpetual"), "perp")
        self.f_full_mode.setEnabled(False)
        self.f_full_mode.currentIndexChanged.connect(self._sync_validity)
        self.f_duration = QSpinBox(); self.f_duration.setRange(1, 3650); self.f_duration.setValue(30)
        self.f_duration.setMinimumWidth(120)
        self.f_users = QSpinBox(); self.f_users.setRange(1, 9999); self.f_users.setValue(3); self.f_users.setMinimumWidth(120)
        self.f_branches = QSpinBox(); self.f_branches.setRange(1, 9999); self.f_branches.setValue(1); self.f_branches.setMinimumWidth(120)

        g.addWidget(QLabel(self.tr("gen.profile")), 0, 0); g.addWidget(self.f_profile, 0, 1)
        g.addWidget(QLabel(self.tr("gen.type")), 0, 2); g.addWidget(self.f_type, 0, 3)
        g.addWidget(QLabel(self.tr("gen.full_mode")), 1, 0); g.addWidget(self.f_full_mode, 1, 1)
        g.addWidget(QLabel(self.tr("gen.duration_days")), 1, 2); g.addWidget(self.f_duration, 1, 3)
        # duration presets
        presets = QHBoxLayout()
        for d in (7, 15, 30, 60, 90):
            b = GhostButton(str(d)); b.setFixedWidth(48)
            b.clicked.connect(lambda _c=False, days=d: self.f_duration.setValue(days))
            presets.addWidget(b)
        presets.addStretch(1)
        g.addLayout(presets, 2, 1, 1, 3)
        g.addWidget(QLabel(self.tr("gen.max_users")), 3, 0); g.addWidget(self.f_users, 3, 1)
        g.addWidget(QLabel(self.tr("gen.max_branches")), 3, 2); g.addWidget(self.f_branches, 3, 3)
        self.expiry_label = QLabel(""); self.expiry_label.setProperty("role", "muted")
        g.addWidget(self.expiry_label, 4, 1, 1, 3)
        lay.addWidget(cfg)

        # modules
        mod, g = _section(self.tr("gen.modules"))
        hint = QLabel(self.tr("gen.modules_hint")); hint.setProperty("role", "muted")
        g.addWidget(hint, 0, 0, 1, 4)
        self.module_checks: dict[str, QCheckBox] = {}
        self._module_host = QGridLayout()
        g.addLayout(self._module_host, 1, 0, 1, 4)
        lay.addWidget(mod)
        self._rebuild_modules()

        # generate + verification + output
        gen_btn = PrimaryButton(self.tr("gen.generate")); gen_btn.clicked.connect(self._generate)
        lay.addWidget(gen_btn)

        self.verify_panel = QLabel(""); self.verify_panel.setWordWrap(True)
        self.verify_panel.setVisible(False)
        lay.addWidget(self.verify_panel)

        self.key_output = _ltr(QPlainTextEdit()); self.key_output.setReadOnly(True)
        self.key_output.setMaximumHeight(90); self.key_output.setVisible(False)
        self.key_output.setPlaceholderText("ZBE1....")
        lay.addWidget(QLabel(self.tr("gen.activation_key")))
        lay.addWidget(self.key_output)

        out = QHBoxLayout()
        self.btn_copy = SecondaryButton(self.tr("gen.copy_key")); self.btn_copy.clicked.connect(self._copy_key)
        self.btn_savekey = SecondaryButton(self.tr("gen.save_key")); self.btn_savekey.clicked.connect(self._save_key)
        self.btn_savelic = SecondaryButton(self.tr("gen.save_license")); self.btn_savelic.clicked.connect(self._save_license)
        self.btn_txt = SecondaryButton(self.tr("gen.export_txt")); self.btn_txt.clicked.connect(self._export_txt)
        self.btn_verify = SecondaryButton(self.tr("gen.verify_again")); self.btn_verify.clicked.connect(self._verify_again)
        for b in (self.btn_copy, self.btn_savekey, self.btn_savelic, self.btn_txt, self.btn_verify):
            b.setEnabled(False); out.addWidget(b)
        out.addStretch(1)
        lay.addLayout(out)
        lay.addStretch(1)

        self._on_type_changed(); self._sync_validity(); self._update_fp_status()
        scroll.setWidget(host)
        return scroll

    def _rebuild_modules(self):
        # clear
        while self._module_host.count():
            item = self._module_host.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.module_checks.clear()
        prof = get_profile(self.f_profile.currentData())
        mods = [k for k in prof.enabled_modules]
        for i, key in enumerate(mods):
            mod = M.MODULE_CATALOG.get(key)
            label = key if mod is None else key.split(".")[-1].replace("_", " ").title()
            cb = QCheckBox(label); cb.setChecked(True)
            self.module_checks[key] = cb
            self._module_host.addWidget(cb, i // 3, i % 3)

    def _on_profile_changed(self, *_):
        self._rebuild_modules()

    def _on_type_changed(self, *_):
        is_full = self.f_type.currentData() == "FULL"
        self.f_full_mode.setEnabled(is_full)
        self._sync_validity()

    def _sync_validity(self, *_):
        is_full = self.f_type.currentData() == "FULL"
        perpetual = is_full and self.f_full_mode.currentData() == "perp"
        self.f_duration.setEnabled(not perpetual)
        if perpetual:
            self.expiry_label.setText(self.tr("gen.perpetual"))
        else:
            exp = date.today() + timedelta(days=self.f_duration.value())
            self.expiry_label.setText(f"{self.tr('gen.expiry')}: {exp.isoformat()}")

    def _update_fp_status(self, *_):
        fp = self.f_fingerprint.text().strip().lower()
        n = len(fp)
        valid = n == 64 and all(c in "0123456789abcdef" for c in fp)
        self.fp_status.setText(self.tr("gen.fp_length", n=n) + " — " +
                               (self.tr("gen.fp_valid") if valid else self.tr("gen.fp_invalid")))
        self.fp_status.setProperty("badge", "success" if valid else "danger")
        self.fp_status.style().unpolish(self.fp_status); self.fp_status.style().polish(self.fp_status)

    # -- request import --------------------------------------------------
    def _apply_request(self, req: MachineRequest):
        self.f_fingerprint.setText(req.machine_fingerprint)
        idx = self.f_profile.findData(req.profile_code)
        if idx >= 0:
            self.f_profile.setCurrentIndex(idx)
        if req.business_name and not self.f_business.text():
            self.f_business.setText(req.business_name)

    def _paste_request(self):
        text, _ = _text_input(self, self.tr("gen.paste_request"))
        if not text:
            return
        try:
            req = MachineRequest.from_code(text.strip())
            req.validate()
            self._apply_request(req)
        except RequestError as exc:
            QMessageBox.warning(self, self.tr("err.generic"), str(exc))

    def _import_request(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("gen.import_request"), "", "Zenith Request (*.zreq)")
        if not path:
            return
        try:
            req = MachineRequest.from_file_json(Path(path).read_text(encoding="utf-8"))
            req.validate()
            self._apply_request(req)
        except RequestError as exc:
            QMessageBox.warning(self, self.tr("err.generic"), str(exc))

    # -- generate --------------------------------------------------------
    def _collect_input(self) -> generator.LicenseInput:
        selected = [k for k, cb in self.module_checks.items() if cb.isChecked()]
        prof = get_profile(self.f_profile.currentData())
        # empty list => all modules for the profile (don't store a full list needlessly)
        modules = [] if set(selected) == set(prof.enabled_modules) else selected
        is_full = self.f_type.currentData() == "FULL"
        perpetual = is_full and self.f_full_mode.currentData() == "perp"
        return generator.LicenseInput(
            profile_code=self.f_profile.currentData(),
            machine_fingerprint=self.f_fingerprint.text().strip().lower(),
            license_type=self.f_type.currentData(),
            perpetual=perpetual,
            duration_days=None if perpetual else self.f_duration.value(),
            max_users=self.f_users.value(), max_branches=self.f_branches.value(),
            enabled_modules=modules,
            customer_name=self.f_customer.text().strip(), business_name=self.f_business.text().strip(),
            customer_id=self.f_custid.text().strip(), phone=self.f_phone.text().strip(),
            email=self.f_email.text().strip(), address=self.f_address.text().strip(),
        )

    def _require_unlocked(self) -> bool:
        if not self.state.is_unlocked:
            QMessageBox.warning(self, self.tr("err.generic"), self.tr("err.no_key"))
            return False
        return True

    def _generate(self):
        if not self._require_unlocked():
            return
        try:
            inp = self._collect_input()
            with session_scope(self.state.db) as s:
                res = generator.generate(s, self.state.keystore, self.state.passphrase, inp,
                                         owner=self.state.owner_name)
                self._last_result = res
                self._show_result(res)
        except (generator.GenerationError, KeyStoreError, BadPassphrase) as exc:
            QMessageBox.warning(self, self.tr("err.generic"), str(exc))

    def _show_result(self, res: generator.GenerationResult):
        lic = res.signed.payload
        self.key_output.setPlainText(res.activation_key)   # full, never truncated
        self.key_output.setVisible(True)
        v = res.verification
        lines = [
            (f"✔ {self.tr('gen.sig_valid')}" if v.ok else f"✗ {v.reason_key}"),
            f"✔ {self.tr('gen.machine_matched')}",
            f"✔ {self.tr('gen.profile_matched')}: {lic.profile_code}",
            f"{self.tr('gen.type')}: {lic.license_type}",
            f"{self.tr('gen.start_date')}: {lic.start_date}",
            f"{self.tr('gen.expiry')}: {lic.expiry_date or self.tr('gen.perpetual')}",
            f"{self.tr('gen.max_users')}: {lic.max_users}",
            f"{self.tr('gen.max_branches')}: {lic.max_branches}",
            f"{self.tr('gen.license_id')}: {lic.license_id}",
        ]
        self.verify_panel.setText("   ".join(lines))
        self.verify_panel.setProperty("badge", "success" if v.ok else "danger")
        self.verify_panel.style().unpolish(self.verify_panel); self.verify_panel.style().polish(self.verify_panel)
        self.verify_panel.setVisible(True)
        for b in (self.btn_copy, self.btn_savekey, self.btn_savelic, self.btn_txt, self.btn_verify):
            b.setEnabled(True)
        self._refresh_history()

    def _copy_key(self):
        if self._last_result:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._last_result.activation_key)

    def _save_key(self):
        if not self._last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("gen.save_key"), "activation.txt", "Text (*.txt)")
        if path:
            Path(path).write_text(self._last_result.activation_key, encoding="utf-8")

    def _save_license(self):
        if not self._last_result:
            return
        default = f"{self._last_result.record.profile_code}.zlic"
        path, _ = QFileDialog.getSaveFileName(self, self.tr("gen.save_license"), default, "Zenith License (*.zlic)")
        if path:
            Path(path).write_text(self._last_result.signed.to_file_json(), encoding="utf-8")

    def _export_txt(self):
        if not self._last_result:
            return
        lic = self._last_result.signed.payload
        path, _ = QFileDialog.getSaveFileName(self, self.tr("gen.export_txt"), f"{lic.license_id}.txt", "Text (*.txt)")
        if path:
            Path(path).write_text(json.dumps(lic.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _verify_again(self):
        if self._last_result:
            self._show_result(self._last_result)

    # ==================================================================
    # History tab
    # ==================================================================
    def _history_tab(self) -> QWidget:
        host = QWidget(); host.setObjectName("Root")
        lay = QVBoxLayout(host)
        bar = QHBoxLayout()
        self.h_search = QLineEdit(); self.h_search.setPlaceholderText(self.tr("hist.search"))
        self.h_search.textChanged.connect(self._refresh_history)
        self.h_profile = QComboBox(); self.h_profile.addItem(self.tr("hist.filter_profile"), None)
        for c in [p.value for p in ProfileCode]:
            self.h_profile.addItem(_PROFILE_NAMES[c], c)
        self.h_profile.currentIndexChanged.connect(self._refresh_history)
        self.h_status = QComboBox(); self.h_status.addItem(self.tr("hist.filter_status"), None)
        for st in ("active", "expired", "replaced", "revoked_local", "test"):
            self.h_status.addItem(st, st)
        self.h_status.currentIndexChanged.connect(self._refresh_history)
        bar.addWidget(self.h_search, 1); bar.addWidget(self.h_profile); bar.addWidget(self.h_status)
        lay.addLayout(bar)

        self.h_table = QTableWidget(0, 7)
        self.h_table.setHorizontalHeaderLabels([
            self.tr("hist.col.created"), self.tr("hist.col.customer"), self.tr("hist.col.business"),
            self.tr("hist.col.profile"), self.tr("hist.col.type"), self.tr("hist.col.expiry"),
            self.tr("hist.col.status")])
        self.h_table.verticalHeader().setVisible(False)
        self.h_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.h_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.h_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.h_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.h_table, 1)

        actions = QHBoxLayout()
        for text, fn in [("hist.copy_key", self._h_copy), ("hist.export", self._h_export),
                         ("hist.renew", self._h_renew), ("hist.replace", self._h_replace),
                         ("hist.duplicate", self._h_duplicate)]:
            b = SecondaryButton(self.tr(text)); b.clicked.connect(fn); actions.addWidget(b)
        actions.addStretch(1)
        lay.addLayout(actions)
        self._refresh_history()
        return host

    def _refresh_history(self, *_):
        if not hasattr(self, "h_table"):
            return
        with session_scope(self.state.db) as s:
            history.refresh_statuses(s)
            rows = history.search(
                s, term=self.h_search.text(), profile=self.h_profile.currentData(),
                status=self.h_status.currentData())
            data = [(r.license_id, r.created_at.strftime("%Y-%m-%d"), r.customer_name, r.business_name,
                     r.profile_code, r.license_type, r.expiry_date or "∞", r.status) for r in rows]
        self.h_table.setRowCount(0)
        for r, row in enumerate(data):
            self.h_table.insertRow(r)
            lic_id = row[0]
            for c, val in enumerate(row[1:]):
                item = QTableWidgetItem(str(val))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, lic_id)
                self.h_table.setItem(r, c, item)

    def _selected_license_id(self):
        row = self.h_table.currentRow()
        if row < 0:
            return None
        item = self.h_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _h_copy(self):
        lid = self._selected_license_id()
        if not lid:
            return QMessageBox.information(self, self.tr("app.name"), self.tr("err.pick_license"))
        with session_scope(self.state.db) as s:
            rec = history.get(s, lid)
            key = rec.activation_key if rec else ""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(key)

    def _h_export(self):
        lid = self._selected_license_id()
        if not lid:
            return
        with session_scope(self.state.db) as s:
            rec = history.get(s, lid)
            key = rec.activation_key
            profile = rec.profile_code
        signed = SignedLicense.from_key(key)
        path, _ = QFileDialog.getSaveFileName(self, self.tr("hist.export"), f"{profile}.zlic", "Zenith License (*.zlic)")
        if path:
            Path(path).write_text(signed.to_file_json(), encoding="utf-8")

    def _h_renew(self):
        self._renew_or_replace(replace=False)

    def _h_replace(self):
        self._renew_or_replace(replace=True)

    def _h_duplicate(self):
        lid = self._selected_license_id()
        if not lid:
            return
        with session_scope(self.state.db) as s:
            rec = history.get(s, lid)
            self.f_fingerprint.setText(rec.machine_fingerprint)
            idx = self.f_profile.findData(rec.profile_code)
            if idx >= 0:
                self.f_profile.setCurrentIndex(idx)
            self.f_customer.setText(rec.customer_name); self.f_business.setText(rec.business_name)
            self.f_users.setValue(rec.max_users); self.f_branches.setValue(rec.max_branches)
        self.tabs.setCurrentIndex(0)

    def _renew_or_replace(self, replace: bool):
        if not self._require_unlocked():
            return
        lid = self._selected_license_id()
        if not lid:
            return QMessageBox.information(self, self.tr("app.name"), self.tr("err.pick_license"))
        reason = ""
        if replace:
            reason, ok = _text_input(self, self.tr("hist.reason"))
            if not ok or not reason.strip():
                return QMessageBox.warning(self, self.tr("err.generic"), self.tr("err.reason_required"))
        try:
            with session_scope(self.state.db) as s:
                old = history.get(s, lid)
                inp = generator.LicenseInput(
                    profile_code=old.profile_code, machine_fingerprint=old.machine_fingerprint,
                    license_type=old.license_type, duration_days=30,
                    max_users=old.max_users, max_branches=old.max_branches,
                    customer_name=old.customer_name, business_name=old.business_name)
                if replace:
                    res = generator.replace(s, self.state.keystore, self.state.passphrase, lid, inp,
                                            reason=reason, owner=self.state.owner_name)
                else:
                    res = generator.renew(s, self.state.keystore, self.state.passphrase, lid, inp,
                                          owner=self.state.owner_name)
            self._last_result = res
            self.tabs.setCurrentIndex(0)
            self._show_result(res)
        except (generator.GenerationError, KeyStoreError) as exc:
            QMessageBox.warning(self, self.tr("err.generic"), str(exc))

    # ==================================================================
    # Bundle tab
    # ==================================================================
    def _bundle_tab(self) -> QWidget:
        host = QWidget(); host.setObjectName("Root")
        lay = QVBoxLayout(host)
        title = QLabel(self.tr("bundle.title")); title.setProperty("role", "h2"); title.setWordWrap(True)
        lay.addWidget(title)
        card, g = _section(self.tr("tab.bundle"))
        self.b_fingerprint = _ltr(QLineEdit()); self.b_fingerprint.setMinimumWidth(420)
        self.b_days = QSpinBox(); self.b_days.setRange(1, 3650); self.b_days.setValue(30); self.b_days.setMinimumWidth(120)
        self.b_users = QSpinBox(); self.b_users.setRange(1, 9999); self.b_users.setValue(3); self.b_users.setMinimumWidth(120)
        self.b_branches = QSpinBox(); self.b_branches.setRange(1, 9999); self.b_branches.setValue(1); self.b_branches.setMinimumWidth(120)
        g.addWidget(QLabel(self.tr("bundle.fingerprint")), 0, 0); g.addWidget(self.b_fingerprint, 0, 1, 1, 3)
        g.addWidget(QLabel(self.tr("bundle.days")), 1, 0); g.addWidget(self.b_days, 1, 1)
        g.addWidget(QLabel(self.tr("gen.max_users")), 1, 2); g.addWidget(self.b_users, 1, 3)
        g.addWidget(QLabel(self.tr("gen.max_branches")), 2, 0); g.addWidget(self.b_branches, 2, 1)
        lay.addWidget(card)
        btn = PrimaryButton(self.tr("bundle.generate")); btn.clicked.connect(self._generate_bundle)
        lay.addWidget(btn)
        self.b_result = QLabel(""); self.b_result.setWordWrap(True)
        lay.addWidget(self.b_result)
        lay.addStretch(1)
        return host

    def _generate_bundle(self):
        if not self._require_unlocked():
            return
        folder = QFileDialog.getExistingDirectory(self, self.tr("bundle.export_folder"))
        if not folder:
            return
        try:
            with session_scope(self.state.db) as s:
                results = generator.generate_test_bundle(
                    s, self.state.keystore, self.state.passphrase,
                    machine_fingerprint=self.b_fingerprint.text().strip().lower(),
                    duration_days=self.b_days.value(), max_users=self.b_users.value(),
                    max_branches=self.b_branches.value(), owner=self.state.owner_name)
                out = Path(folder) / "Profile-Test-Licenses"
                out.mkdir(parents=True, exist_ok=True)
                summary = []
                for code, res in results.items():
                    (out / f"{code}.zlic").write_text(res.signed.to_file_json(), encoding="utf-8")
                    summary.append(f"{code}: {res.record.license_id}")
                (out / "SUMMARY.txt").write_text("\n".join(summary), encoding="utf-8")
            self.b_result.setText(self.tr("bundle.done", n=len(results)) + "\n" + str(out))
            self.b_result.setProperty("badge", "success")
            self.b_result.style().unpolish(self.b_result); self.b_result.style().polish(self.b_result)
            self._refresh_history()
        except (generator.GenerationError, KeyStoreError) as exc:
            QMessageBox.warning(self, self.tr("err.generic"), str(exc))

    # ==================================================================
    # Security tab
    # ==================================================================
    def _security_tab(self) -> QWidget:
        host = QWidget(); host.setObjectName("Root")
        lay = QVBoxLayout(host)
        status = QLabel(("✔ " + self.tr("sec.key_status")) if self.state.is_unlocked else self.tr("sec.locked_msg"))
        status.setProperty("badge", "success" if self.state.is_unlocked else "warning")
        lay.addWidget(status)
        for text, fn in [("sec.lock", self._lock), ("sec.change_passphrase", self._change_passphrase),
                         ("sec.backup_key", self._backup_key), ("sec.backup_all", self._backup_all)]:
            b = SecondaryButton(self.tr(text)); b.clicked.connect(fn)
            lay.addWidget(b)
        lay.addStretch(1)
        return host

    def _lock(self):
        self.state.lock()
        QMessageBox.information(self, self.tr("app.name"), self.tr("sec.locked_msg"))
        if self.controller:
            self.close()
            self.controller.run()

    def _change_passphrase(self):
        old, ok1 = _text_input(self, self.tr("login.passphrase"), password=True)
        if not ok1:
            return
        new, ok2 = _text_input(self, self.tr("sec.change_passphrase"), password=True)
        if not ok2:
            return
        try:
            self.state.keystore.change_passphrase(old, new)
            self.state.passphrase = new
            QMessageBox.information(self, self.tr("app.name"), self.tr("common.ok"))
        except (KeyStoreError, BadPassphrase) as exc:
            QMessageBox.warning(self, self.tr("err.generic"), str(exc))

    def _backup_key(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr("sec.backup_key"), "signing_key.enc.bak", "Encrypted Key (*.enc *.bak)")
        if path:
            self.state.keystore.export_backup(path)
            QMessageBox.information(self, self.tr("app.name"), self.tr("gen.saved", path=path))

    def _backup_all(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("sec.backup_all"))
        if folder:
            info = vbackup.create_backup(Path(folder))
            QMessageBox.information(self, self.tr("app.name"), self.tr("gen.saved", path=str(info.path)))


# --------------------------------------------------------------------------
def _text_input(parent, title: str, password: bool = False):
    """Simple modal text prompt returning (text, ok)."""
    dlg = QDialog(parent); dlg.setWindowTitle(title); dlg.setMinimumWidth(420)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(title))
    edit = QLineEdit()
    edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    if password:
        edit.setEchoMode(QLineEdit.EchoMode.Password)
    lay.addWidget(edit)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    ok = dlg.exec() == QDialog.DialogCode.Accepted
    return (edit.text(), ok)
