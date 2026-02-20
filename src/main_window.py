"""Main application window."""

import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QInputDialog,
    QLabel, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QColor, QPalette
from PyQt6.QtGui import QShortcut

from .editor import MarkdownEditor
from .preview import PreviewWidget


# ── App-level QSS ─────────────────────────────────────────────────────────────

_LIGHT_QSS = """
QMainWindow, QWidget#root {
    background: #f4f2ef;
}
QMenuBar {
    background: #ece9e4;
    border-bottom: 1px solid #d4d0ca;
    spacing: 0px;
    padding: 2px 6px;
    font-size: 13px;
    color: #2a2520;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 11px;
    border-radius: 5px;
    color: #2a2520;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background: #d8d4ce;
}
QMenu {
    background: #faf9f7;
    border: 1px solid #ccc8c2;
    border-radius: 10px;
    padding: 6px 4px;
    font-size: 13px;
    color: #1e1e1e;
}
QMenu::item {
    padding: 7px 30px 7px 18px;
    border-radius: 5px;
    color: #1e1e1e;
}
QMenu::item:selected {
    background: #2563eb;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #b0aca6;
}
QMenu::separator {
    height: 1px;
    background: #e4e0da;
    margin: 4px 12px;
}
QMenu::indicator {
    width: 16px; height: 16px;
    margin-left: 6px;
}
QStatusBar {
    background: #e8e4e0;
    border-top: 1px solid #d0ccc6;
    font-size: 11px;
    color: #7a7570;
    padding: 0px 10px;
    min-height: 20px;
}
QStatusBar QLabel { color: #7a7570; font-size: 11px; }
QStatusBar QFrame { color: #c0bcb6; }
QStatusBar::item { border: none; }
QSplitter::handle:horizontal {
    background: #d4d0ca;
    width: 1px;
}
QToolTip {
    background: #2a2520;
    color: #e8e4dc;
    border: none;
    border-radius: 5px;
    padding: 4px 9px;
    font-size: 12px;
}
"""

_DARK_QSS = """
QMainWindow, QWidget#root {
    background: #181612;
}
QMenuBar {
    background: #1e1b17;
    border-bottom: 1px solid #2a2722;
    spacing: 0px;
    padding: 2px 6px;
    font-size: 13px;
    color: #b8b0a5;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 11px;
    border-radius: 5px;
    color: #b8b0a5;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background: #2a2520;
}
QMenu {
    background: #242018;
    border: 1px solid #353028;
    border-radius: 10px;
    padding: 6px 4px;
    font-size: 13px;
    color: #c8c0b5;
}
QMenu::item {
    padding: 7px 30px 7px 18px;
    border-radius: 5px;
    color: #c8c0b5;
}
QMenu::item:selected {
    background: #2563eb;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #504840;
}
QMenu::separator {
    height: 1px;
    background: #2e2a24;
    margin: 4px 12px;
}
QMenu::indicator {
    width: 16px; height: 16px;
    margin-left: 6px;
}
QStatusBar {
    background: #1a1714;
    border-top: 1px solid #2a2722;
    font-size: 11px;
    color: #5a5450;
    padding: 0px 10px;
    min-height: 20px;
}
QStatusBar QLabel { color: #5a5450; font-size: 11px; }
QStatusBar QFrame { color: #302c28; }
QStatusBar::item { border: none; }
QSplitter::handle:horizontal {
    background: #2a2722;
    width: 1px;
}
QToolTip {
    background: #2a2520;
    color: #e8e4dc;
    border: none;
    border-radius: 5px;
    padding: 4px 9px;
    font-size: 12px;
}
"""

_ORG  = "TypeDown"
_APP  = "TypeDown"
_RECENT_MAX = 12


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._file: str | None = None
        self._modified = False
        self._dark = False
        self._preview_on = True
        self._focus = False
        self._line_numbers_on = True

        self._settings = QSettings(_ORG, _APP)

        self._build_ui()
        self._build_menus()
        self._build_statusbar()
        self._restore_state()
        self._apply_theme()

        # Window-level shortcut so Ctrl+Shift+F works even when the menu bar
        # is hidden in focus mode (menu actions go dead when their bar hides).
        QShortcut(QKeySequence("Ctrl+Shift+F"), self).activated.connect(self.toggle_focus)

        self.setWindowTitle("TypeDown")
        self.resize(1280, 820)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(1)

        self._editor = MarkdownEditor()
        self._editor.content_changed.connect(self._on_content_changed)
        self._editor.cursorPositionChanged.connect(self._update_cursor)

        self._preview = PreviewWidget()

        self._splitter.addWidget(self._editor)
        self._splitter.addWidget(self._preview)
        self._splitter.setSizes([500, 680])

        layout.addWidget(self._splitter)

    def _build_menus(self):
        mb = self.menuBar()

        # ── File ──
        file_menu = mb.addMenu("&File")
        self._act(file_menu, "&New",            self.new_file,          "Ctrl+N")
        self._act(file_menu, "&Open…",          self.open_file_dialog,  "Ctrl+O")
        file_menu.addSeparator()
        self._save_act = self._act(file_menu, "&Save",   self.save_file,   "Ctrl+S")
        self._act(file_menu, "Save &As…",               self.save_file_as,"Ctrl+Shift+S")
        file_menu.addSeparator()
        export = file_menu.addMenu("&Export")
        self._act(export, "Export as &HTML…",   self.export_html,       "Ctrl+E")
        self._act(export, "Export as &PDF…",    self.export_pdf,        "Ctrl+Shift+E")
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("Recent &Files")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        self._act(file_menu, "&Quit",            self.close,             "Ctrl+Q")

        # ── Edit ──
        edit_menu = mb.addMenu("&Edit")
        self._act(edit_menu, "&Undo",            self._editor.undo,      "Ctrl+Z")
        self._act(edit_menu, "&Redo",            self._editor.redo,      "Ctrl+Y")
        edit_menu.addSeparator()
        self._act(edit_menu, "Cu&t",             self._editor.cut,       "Ctrl+X")
        self._act(edit_menu, "&Copy",            self._editor.copy,      "Ctrl+C")
        self._act(edit_menu, "&Paste",           self._editor.paste,     "Ctrl+V")
        self._act(edit_menu, "Select &All",      self._editor.selectAll, "Ctrl+A")
        edit_menu.addSeparator()
        self._act(edit_menu, "&Find…",           self._find,             "Ctrl+F")
        self._act(edit_menu, "Find &Next",       self._find_next,        "F3")

        # ── Format ──
        fmt_menu = mb.addMenu("F&ormat")
        self._act(fmt_menu, "&Bold",             self._editor.insert_bold,         "Ctrl+B")
        self._act(fmt_menu, "&Italic",           self._editor.insert_italic,       "Ctrl+I")
        self._act(fmt_menu, "&Strikethrough",    self._editor.insert_strikethrough,"Ctrl+Shift+X")
        fmt_menu.addSeparator()
        self._act(fmt_menu, "Inline &Code",      self._editor.insert_code,         "Ctrl+`")
        self._act(fmt_menu, "Code &Block",       self._editor.insert_code_block,   "Ctrl+Shift+`")
        fmt_menu.addSeparator()
        self._act(fmt_menu, "Insert &Link",      self._editor.insert_link,         "Ctrl+K")
        self._act(fmt_menu, "Insert I&mage",     self._editor.insert_image)
        self._act(fmt_menu, "Insert &Table",     self._editor.insert_table)
        fmt_menu.addSeparator()
        h_menu = fmt_menu.addMenu("&Headings")
        for n in range(1, 7):
            self._act(h_menu, f"Heading &{n}",
                      lambda _checked=False, level=n: self._editor.insert_heading(level),
                      f"Ctrl+{n}")
        fmt_menu.addSeparator()
        self._act(fmt_menu, "&Blockquote",       self._editor.insert_blockquote,   "Ctrl+Shift+Q")
        self._act(fmt_menu, "&Ordered List",     self._editor.insert_ordered_list, "Ctrl+Shift+O")
        self._act(fmt_menu, "&Unordered List",   self._editor.insert_unordered_list,"Ctrl+Shift+U")
        self._act(fmt_menu, "Horizontal &Rule",  self._editor.insert_hr)

        # ── View ──
        view_menu = mb.addMenu("&View")
        self._preview_act = self._act(
            view_menu, "Show &Preview", self.toggle_preview,
            "Ctrl+Shift+P", checkable=True, checked=True,
        )
        self._focus_act = self._act(
            view_menu, "&Focus Mode", self.toggle_focus,
            "Ctrl+Shift+F", checkable=True,
        )
        self._linenum_act = self._act(
            view_menu, "Show &Line Numbers", self.toggle_line_numbers,
            checkable=True, checked=True,
        )
        view_menu.addSeparator()
        self._dark_act = self._act(
            view_menu, "&Dark Theme", self.toggle_theme,
            "Ctrl+Shift+D", checkable=True,
        )
        view_menu.addSeparator()
        self._act(view_menu, "Toggle &Fullscreen", self.toggle_fullscreen, "F11")

        # ── Help ──
        help_menu = mb.addMenu("&Help")
        self._act(help_menu, "&Markdown Cheatsheet", self._show_cheatsheet)
        help_menu.addSeparator()
        self._act(help_menu, "&About TypeDown",       self._show_about)

    def _act(self, menu, title, slot=None, shortcut=None,
             checkable=False, checked=False) -> QAction:
        a = QAction(title, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
        if slot:
            a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_statusbar(self):
        sb = self.statusBar()

        self._words_lbl  = QLabel("0 words")
        self._chars_lbl  = QLabel("0 chars")
        self._cursor_lbl = QLabel("Ln 1, Col 1")
        self._file_lbl   = QLabel()

        sep = lambda: self._vline()

        sb.addWidget(self._words_lbl)
        sb.addWidget(sep())
        sb.addWidget(self._chars_lbl)
        sb.addPermanentWidget(self._file_lbl)
        sb.addPermanentWidget(sep())
        sb.addPermanentWidget(self._cursor_lbl)

    @staticmethod
    def _vline():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        f.setMaximumHeight(14)
        return f

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(_DARK_QSS if self._dark else _LIGHT_QSS)
        self._editor.set_dark(self._dark)
        self._preview.set_dark(self._dark)
        self._preview.render_markdown(self._editor.toPlainText())
        if hasattr(self, "_dark_act"):
            self._dark_act.setChecked(self._dark)

    # ── State persistence ─────────────────────────────────────────────────────

    def _restore_state(self):
        self._dark = self._settings.value("dark", False, type=bool)
        geom = self._settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        split = self._settings.value("splitter")
        if split:
            self._splitter.restoreState(split)

    def closeEvent(self, event):
        if not self._confirm_discard():
            event.ignore()
            return
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("splitter", self._splitter.saveState())
        self._settings.setValue("dark", self._dark)
        event.accept()

    # ── File operations ───────────────────────────────────────────────────────

    def new_file(self):
        if not self._confirm_discard():
            return
        self._editor.clear()
        self._file = None
        self._modified = False
        self._refresh_title()
        self._preview.render_markdown("")
        self._update_counts("")

    def open_file_dialog(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "Markdown (*.md *.markdown *.txt);;All Files (*)",
        )
        if path:
            self.open_file(Path(path))

    def open_file(self, path: Path):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", f"Could not read file:\n{exc}")
            return
        self._editor.setPlainText(text)
        self._file = str(path)
        self._modified = False
        self._refresh_title()
        self._preview.render_markdown(text)
        self._update_counts(text)
        self._add_recent(str(path))

    def save_file(self):
        if self._file:
            self._write(self._file)
        else:
            self.save_file_as()

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save File As", "",
            "Markdown (*.md);;Text (*.txt);;All Files (*)",
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".md"
        self._write(path)
        self._file = path
        self._add_recent(path)
        self._refresh_title()

    def _write(self, path: str):
        try:
            Path(path).write_text(self._editor.toPlainText(), encoding="utf-8")
            self._modified = False
            self._refresh_title()
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n{exc}")

    def export_html(self):
        default = (Path(self._file).stem + ".html") if self._file else "document.html"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export HTML", default,
            "HTML (*.html *.htm);;All Files (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self._preview.get_full_html(), encoding="utf-8")
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def export_pdf(self):
        default = (Path(self._file).stem + ".pdf") if self._file else "document.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", default,
            "PDF (*.pdf);;All Files (*)",
        )
        if not path:
            return
        self._preview.print_to_pdf(path)
        # Show confirmation after a short delay (print is async)
        QTimer.singleShot(1500, lambda: QMessageBox.information(
            self, "PDF Export", f"PDF saved to:\n{path}"
        ))

    def _confirm_discard(self) -> bool:
        if not self._modified:
            return True
        name = Path(self._file).name if self._file else "Untitled"
        btn = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"\u201c{name}\u201d has unsaved changes.\nSave before closing?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if btn == QMessageBox.StandardButton.Save:
            self.save_file()
            return not self._modified   # False if save was cancelled
        return btn == QMessageBox.StandardButton.Discard

    # ── View actions ──────────────────────────────────────────────────────────

    def toggle_preview(self):
        self._preview_on = not self._preview_on
        self._preview.setVisible(self._preview_on)
        self._preview_act.setChecked(self._preview_on)

    def toggle_focus(self):
        self._focus = not self._focus
        self.menuBar().setVisible(not self._focus)
        self.statusBar().setVisible(not self._focus)
        if self._focus:
            self._preview.setVisible(False)
        else:
            self._preview.setVisible(self._preview_on)
        self._focus_act.setChecked(self._focus)

    def toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme()

    def toggle_line_numbers(self):
        self._line_numbers_on = not self._line_numbers_on
        self._editor.set_line_numbers(self._line_numbers_on)
        self._linenum_act.setChecked(self._line_numbers_on)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ── Live updates ──────────────────────────────────────────────────────────

    def _on_content_changed(self, text: str):
        if not self._modified:
            self._modified = True
            self._refresh_title()
        self._preview.render_markdown(text)
        self._update_counts(text)

    def _update_counts(self, text: str):
        words = len(text.split()) if text.strip() else 0
        self._words_lbl.setText(f"{words:,} {'word' if words == 1 else 'words'}")
        self._chars_lbl.setText(f"{len(text):,} chars")

    def _update_cursor(self):
        cur = self._editor.textCursor()
        self._cursor_lbl.setText(f"Ln {cur.blockNumber()+1}, Col {cur.columnNumber()+1}")

    def _refresh_title(self):
        dot = " ●" if self._modified else ""
        name = Path(self._file).name if self._file else "Untitled"
        self.setWindowTitle(f"{name}{dot} — TypeDown")
        self._file_lbl.setText(self._file or "")

    # ── Find ──────────────────────────────────────────────────────────────────

    def _find(self):
        text, ok = QInputDialog.getText(self, "Find", "Search for:")
        if ok and text:
            self._last_search = text
            if not self._editor.find(text):
                self._wrap_find(text)

    def _find_next(self):
        if hasattr(self, "_last_search") and self._last_search:
            if not self._editor.find(self._last_search):
                self._wrap_find(self._last_search)

    def _wrap_find(self, text: str):
        cur = self._editor.textCursor()
        cur.movePosition(cur.MoveOperation.Start)
        self._editor.setTextCursor(cur)
        if not self._editor.find(text):
            QMessageBox.information(self, "Find", f'"{text}" not found.')

    # ── Recent files ──────────────────────────────────────────────────────────

    def _add_recent(self, path: str):
        recent = self._settings.value("recent", []) or []
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:_RECENT_MAX]
        self._settings.setValue("recent", recent)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recent", []) or []
        existing = [p for p in recent if Path(p).exists()]
        if not existing:
            a = QAction("(No recent files)", self)
            a.setEnabled(False)
            self._recent_menu.addAction(a)
            return
        for path in existing:
            name = Path(path).name
            a = QAction(name, self)
            a.setToolTip(path)
            a.triggered.connect(lambda _checked=False, p=path: self.open_file(Path(p)))
            self._recent_menu.addAction(a)
        self._recent_menu.addSeparator()
        self._act(self._recent_menu, "Clear Recent Files", self._clear_recent)

    def _clear_recent(self):
        self._settings.setValue("recent", [])
        self._rebuild_recent_menu()

    # ── Help ──────────────────────────────────────────────────────────────────

    def _show_cheatsheet(self):
        cheat = (
            "# Markdown Cheatsheet\n\n"
            "## Text Formatting\n\n"
            "**Bold** — `**text**` or `__text__`\n\n"
            "*Italic* — `*text*` or `_text_`\n\n"
            "~~Strikethrough~~ — `~~text~~`\n\n"
            "`Inline code` — `` `code` ``\n\n"
            "## Headings\n\n"
            "`# H1`  `## H2`  `### H3`  `#### H4`\n\n"
            "## Lists\n\n"
            "- Unordered: `- item` or `* item`\n"
            "- Ordered: `1. item`\n"
            "- Task: `- [ ] todo` / `- [x] done`\n\n"
            "## Links & Images\n\n"
            "`[link text](url)`\n\n"
            "`![alt text](image.png)`\n\n"
            "## Blockquote\n\n"
            "`> quoted text`\n\n"
            "## Code Block\n\n"
            "````\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
            "````\n\n"
            "## Table\n\n"
            "```\n"
            "| Col 1 | Col 2 |\n"
            "| ----- | ----- |\n"
            "| A     | B     |\n"
            "```\n\n"
            "## Horizontal Rule\n\n"
            "`---` or `***`\n\n"
            "## Footnote\n\n"
            "`text[^1]`  `[^1]: footnote content`\n"
        )
        win = QMainWindow(self)
        win.setWindowTitle("Markdown Cheatsheet")
        win.resize(700, 600)
        editor = MarkdownEditor()
        editor.setPlainText(cheat)
        editor.setReadOnly(True)
        editor.set_dark(self._dark)
        win.setCentralWidget(editor)
        win.show()

    def _show_about(self):
        QMessageBox.about(
            self, "About TypeDown",
            "<h2 style='margin-bottom:4px'>TypeDown</h2>"
            "<p style='color:#666;margin-top:0'>A beautiful markdown editor for Linux</p>"
            "<p>Version 1.0</p>"
            "<p>Built with PyQt6, python-markdown, and Pygments.</p>"
        )
