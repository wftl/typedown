"""Markdown editor widget with line numbers and smart editing."""

import re
from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QColor, QPainter, QFont, QTextCursor, QKeyEvent,
    QTextFormat, QTextCharFormat,
)
from .highlighter import MarkdownHighlighter


# ── QSS ──────────────────────────────────────────────────────────────────────

EDITOR_QSS_LIGHT = """
QPlainTextEdit {
    background-color: #fefefe;
    color: #1f1f1f;
    selection-background-color: #c8deff;
    selection-color: #111111;
    border: none;
}
"""

EDITOR_QSS_DARK = """
QPlainTextEdit {
    background-color: #1c1914;
    color: #d5d0c7;
    selection-background-color: #2d4a6b;
    selection-color: #e8e4dc;
    border: none;
}
"""

LINE_BG_LIGHT = QColor("#f5f3f0")
LINE_BG_DARK  = QColor("#201d19")
GUTTER_BG_LIGHT = QColor("#fefefe")   # same as editor — invisible seam
GUTTER_BG_DARK  = QColor("#1c1914")   # same as editor — invisible seam
GUTTER_FG_LIGHT = QColor("#ccc8c2")
GUTTER_FG_DARK  = QColor("#3e3930")
GUTTER_FG_CUR_LIGHT = QColor("#7090bb")
GUTTER_FG_CUR_DARK  = QColor("#6890b8")


class _LineNumberArea(QWidget):
    def __init__(self, editor: "MarkdownEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, event):
        self._editor._paint_gutter(event)


class MarkdownEditor(QPlainTextEdit):
    content_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = False
        self._line_numbers = True

        self._setup_font()
        self._setup_widget()

        self._gutter = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_gutter_width(0)

        self._highlighter = MarkdownHighlighter(self.document())

        # Debounce emission so preview doesn't lag while typing fast
        self._emit_timer = QTimer(singleShot=True, interval=250)
        self._emit_timer.timeout.connect(lambda: self.content_changed.emit(self.toPlainText()))
        self.textChanged.connect(self._emit_timer.start)

        self.set_dark(False)

    # ── Setup ────────────────────────────────────────────────────────────────

    def _setup_font(self):
        font = QFont()
        font.setFamilies([
            "JetBrains Mono", "Fira Code", "Cascadia Code",
            "Source Code Pro", "Consolas", "Monaco", "Courier New",
        ])
        font.setPointSize(13)
        font.setFixedPitch(True)
        self.setFont(font)

    def _setup_widget(self):
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setFrameStyle(0)
        self.document().setDocumentMargin(48)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def set_dark(self, dark: bool):
        self._is_dark = dark
        self.setStyleSheet(EDITOR_QSS_DARK if dark else EDITOR_QSS_LIGHT)
        if hasattr(self, "_highlighter"):
            self._highlighter.set_dark(dark)
            self._highlighter.rehighlight()
        self._highlight_current_line()
        self._gutter.update()

    def set_line_numbers(self, visible: bool):
        self._line_numbers = visible
        self._update_gutter_width(0)
        self._gutter.setVisible(visible)

    # ── Gutter (line numbers) ────────────────────────────────────────────────

    def gutter_width(self) -> int:
        if not self._line_numbers:
            return 0
        digits = len(str(max(1, self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits + 10

    def _update_gutter_width(self, _=None):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def _paint_gutter(self, event):
        painter = QPainter(self._gutter)
        bg = GUTTER_BG_DARK if self._is_dark else GUTTER_BG_LIGHT
        painter.fillRect(event.rect(), bg)

        current_block = self.textCursor().block()
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        small_font = QFont(self.font())
        small_font.setPointSize(max(9, small_font.pointSize() - 1))
        painter.setFont(small_font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                is_cur = (block == current_block)
                if is_dark := self._is_dark:
                    fg = GUTTER_FG_CUR_DARK if is_cur else GUTTER_FG_DARK
                else:
                    fg = GUTTER_FG_CUR_LIGHT if is_cur else GUTTER_FG_LIGHT
                painter.setPen(fg)
                painter.drawText(
                    0, top,
                    self._gutter.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(num + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1

    # ── Current-line highlight ───────────────────────────────────────────────

    def _highlight_current_line(self):
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(LINE_BG_DARK if self._is_dark else LINE_BG_LIGHT)
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    # ── Smart key handling ───────────────────────────────────────────────────

    _OPEN_PAIRS = {"(": ")", "[": "]", "{": "}"}
    _CLOSE_SET  = set(")]}")

    def keyPressEvent(self, event: QKeyEvent):
        cursor = self.textCursor()
        key   = event.key()
        text  = event.text()

        # Tab / Shift-Tab
        if key == Qt.Key.Key_Tab:
            if cursor.hasSelection():
                self._indent_block(cursor, indent=True)
            else:
                cursor.insertText("    ")
            return
        if key == Qt.Key.Key_Backtab:
            self._indent_block(cursor, indent=False)
            return

        # Enter: smart list/blockquote continuation
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._handle_enter(cursor):
                return

        # Auto-pair open brackets
        if text in self._OPEN_PAIRS and not cursor.hasSelection():
            close = self._OPEN_PAIRS[text]
            cursor.insertText(text + close)
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            return

        # Skip over already-present closing bracket
        if text in self._CLOSE_SET and not cursor.hasSelection():
            pos = cursor.position()
            doc = self.document()
            if pos < doc.characterCount() - 1 and doc.characterAt(pos) == text:
                cursor.movePosition(QTextCursor.MoveOperation.Right)
                self.setTextCursor(cursor)
                return

        # Delete matching close bracket on backspace
        if key == Qt.Key.Key_Backspace and not cursor.hasSelection():
            pos = cursor.position()
            doc = self.document()
            if pos > 0:
                prev_ch = doc.characterAt(pos - 1)
                next_ch = doc.characterAt(pos)
                if prev_ch in self._OPEN_PAIRS and next_ch == self._OPEN_PAIRS[prev_ch]:
                    cursor.movePosition(QTextCursor.MoveOperation.Right,
                                        QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                    cursor.movePosition(QTextCursor.MoveOperation.Left,
                                        QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                    return

        super().keyPressEvent(event)

    def _handle_enter(self, cursor: QTextCursor) -> bool:
        """Continue lists / blockquotes on Enter. Returns True if handled."""
        line = cursor.block().text()

        # Ordered list
        m = re.match(r"^(\s*)(\d+)(\.\s+)", line)
        if m:
            indent, num, sep = m.group(1), int(m.group(2)), m.group(3)
            content = line[len(m.group(0)):]
            if not content.strip():
                self._clear_line(cursor)
                return True
            cursor.insertText(f"\n{indent}{num + 1}. ")
            return True

        # Unordered list (with optional task checkbox)
        m = re.match(r"^(\s*)([-*+])(\s+)", line)
        if m:
            indent, marker = m.group(1), m.group(2)
            content = line[len(m.group(0)):]
            if not content.strip():
                self._clear_line(cursor)
                return True
            task_m = re.match(r"\[[ xX]\]\s", content)
            suffix = "[ ] " if task_m else ""
            cursor.insertText(f"\n{indent}{marker} {suffix}")
            return True

        # Blockquote
        m = re.match(r"^((?:>\s*)+)", line)
        if m:
            prefix = m.group(1)
            if not line[len(prefix):].strip():
                self._clear_line(cursor)
                return True
            cursor.insertText(f"\n{prefix}")
            return True

        return False

    def _clear_line(self, cursor: QTextCursor):
        """Replace current block content with a blank line."""
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("")
        cursor.insertText("\n")

    def _indent_block(self, cursor: QTextCursor, indent: bool):
        start = cursor.selectionStart()
        end   = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.beginEditBlock()
        while cursor.position() <= end:
            if indent:
                cursor.insertText("    ")
                end += 4
            else:
                line = cursor.block().text()
                if line.startswith("    "):
                    for _ in range(4):
                        cursor.deleteChar()
                    end -= 4
                elif line.startswith("\t"):
                    cursor.deleteChar()
                    end -= 1
            if not cursor.movePosition(QTextCursor.MoveOperation.NextBlock):
                break
        cursor.endEditBlock()

    # ── Format insertion helpers ─────────────────────────────────────────────

    def _wrap(self, before: str, after: str):
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertText(f"{before}{selected}{after}")
        else:
            pos = cursor.position()
            cursor.insertText(f"{before}{after}")
            cursor.setPosition(pos + len(before))
            self.setTextCursor(cursor)

    def insert_bold(self):          self._wrap("**", "**")
    def insert_italic(self):        self._wrap("*", "*")
    def insert_strikethrough(self): self._wrap("~~", "~~")
    def insert_code(self):          self._wrap("`", "`")

    def insert_code_block(self):
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertText(f"```\n{selected}\n```")
        else:
            pos = cursor.position()
            cursor.insertText("```\n\n```")
            cursor.setPosition(pos + 4)
            self.setTextCursor(cursor)

    def insert_link(self):
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            pos = cursor.selectionStart() + len(selected) + 3
            cursor.insertText(f"[{selected}](url)")
            cursor.setPosition(pos)
            cursor.setPosition(pos + 3, QTextCursor.MoveMode.KeepAnchor)
        else:
            pos = cursor.position()
            cursor.insertText("[link text](url)")
            cursor.setPosition(pos + 1)
            cursor.setPosition(pos + 10, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def insert_image(self):
        cursor = self.textCursor()
        cursor.insertText("![alt text](image.png)")

    def insert_heading(self, level: int):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
        line = re.sub(r"^#{1,6}\s*", "", cursor.selectedText())
        cursor.insertText("#" * level + " " + line)

    def insert_blockquote(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.beginEditBlock()
            while cursor.position() <= end:
                cursor.insertText("> ")
                end += 2
                if not cursor.movePosition(QTextCursor.MoveOperation.NextBlock):
                    break
            cursor.endEditBlock()
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.insertText("> ")

    def insert_ordered_list(self):
        c = self.textCursor()
        c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        c.insertText("1. ")

    def insert_unordered_list(self):
        c = self.textCursor()
        c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        c.insertText("- ")

    def insert_hr(self):
        c = self.textCursor()
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        c.insertText("\n\n---\n\n")

    def insert_table(self):
        c = self.textCursor()
        c.insertText(
            "\n| Column 1 | Column 2 | Column 3 |\n"
            "| -------- | -------- | -------- |\n"
            "| Cell     | Cell     | Cell     |\n"
        )
