"""Markdown syntax highlighter."""

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
)


def _fmt(color, bold=False, italic=False, strikeout=False, family=None):
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    if strikeout:
        fmt.setFontStrikeOut(True)
    if family:
        fmt.setFontFamilies([family, "monospace"])
    return fmt


# ── Colour palettes ──────────────────────────────────────────────────────────

LIGHT = dict(
    h1="#1d4ed8", h2="#1d4ed8", h3="#2563eb",
    h4="#374151", h5="#374151", h6="#374151",
    bold="#111111", italic="#4a4a4a",
    strike="#aaaaaa",
    code_fg="#be4030", code_bg="#f4f0ee",
    link="#2563eb",
    list_marker="#adb5c0",
    blockquote="#adb5c0",
    hr="#d8d5d0",
    html_tag="#adb5c0",
    fence="#adb5c0",
)

DARK = dict(
    h1="#7db3e8", h2="#7db3e8", h3="#9fc8e8",
    h4="#8abcb8", h5="#8abcb8", h6="#8abcb8",
    bold="#ede9e0", italic="#bfb8ac",
    strike="#504a44",
    code_fg="#e8956a", code_bg="#25221e",
    link="#7db3e8",
    list_marker="#504a44",
    blockquote="#607060",
    hr="#35302a",
    html_tag="#7090b0",
    fence="#453f39",
)

# Heading sizes (point delta from base)
H_SIZES = [6, 4, 2, 1, 0, 0]


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self._is_dark = False
        self._rules = []
        self._code_block_fmt = QTextCharFormat()
        self._build_rules()

    def set_dark(self, dark: bool):
        self._is_dark = dark
        self._build_rules()

    def _build_rules(self):
        c = DARK if self._is_dark else LIGHT
        rules = []

        # Headings — matched by prefix length so H1 before H6
        for level in range(1, 7):
            key = f"h{level}"
            fmt = _fmt(c[key], bold=True)
            # Slight size bump for top headings
            if H_SIZES[level - 1]:
                fmt.setFontPointSize(14 + H_SIZES[level - 1])
            pat = QRegularExpression(rf"^#{{{level}}}(?!#)[^\n]*")
            rules.append((pat, fmt))

        # Bold (**…** or __…__)
        bold_fmt = _fmt(c["bold"], bold=True)
        rules.append((QRegularExpression(r"\*\*(?!\s).+?(?<!\s)\*\*"), bold_fmt))
        rules.append((QRegularExpression(r"__(?!\s).+?(?<!\s)__"), bold_fmt))

        # Italic (*…* or _…_) — after bold so ** doesn't re-match
        italic_fmt = _fmt(c["italic"], italic=True)
        rules.append((QRegularExpression(r"(?<!\*)\*(?!\*)(?!\s).+?(?<!\s)(?<!\*)\*(?!\*)"), italic_fmt))
        rules.append((QRegularExpression(r"(?<!_)_(?!_)(?!\s).+?(?<!\s)(?<!_)_(?!_)"), italic_fmt))

        # Strikethrough ~~…~~
        strike_fmt = _fmt(c["strike"], strikeout=True)
        rules.append((QRegularExpression(r"~~.+?~~"), strike_fmt))

        # Inline code `…`
        code_fmt = _fmt(c["code_fg"], family="monospace")
        code_fmt.setBackground(QColor(c["code_bg"]))
        rules.append((QRegularExpression(r"`[^`\n]+`"), code_fmt))

        # Links — [text](url) and [text][ref]
        link_fmt = _fmt(c["link"])
        rules.append((QRegularExpression(r"!?\[[^\]\n]*\]\([^\)\n]*\)"), link_fmt))
        rules.append((QRegularExpression(r"!?\[[^\]\n]*\]\[[^\]\n]*\]"), link_fmt))

        # Unordered list markers
        list_fmt = _fmt(c["list_marker"], bold=True)
        rules.append((QRegularExpression(r"^\s*[-*+](?=\s)"), list_fmt))

        # Ordered list markers
        rules.append((QRegularExpression(r"^\s*\d+\.(?=\s)"), list_fmt))

        # Task list checkboxes
        rules.append((QRegularExpression(r"^\s*[-*+]\s+\[[ xX]\]"), list_fmt))

        # Blockquotes
        bq_fmt = _fmt(c["blockquote"], italic=True)
        rules.append((QRegularExpression(r"^>.*"), bq_fmt))

        # Horizontal rules
        hr_fmt = _fmt(c["hr"])
        rules.append((QRegularExpression(r"^(\*{3,}|-{3,}|_{3,})\s*$"), hr_fmt))

        # HTML tags
        html_fmt = _fmt(c["html_tag"])
        rules.append((QRegularExpression(r"</?[A-Za-z][^>\n]*>"), html_fmt))

        self._rules = rules

        # Code fence format (``` lines and content)
        self._code_block_fmt = _fmt(c["fence"], family="monospace")
        self._code_block_fmt.setBackground(QColor(c["code_bg"]))

    # ── Per-block highlight ──────────────────────────────────────────────────

    def highlightBlock(self, text: str):
        prev_state = self.previousBlockState()
        in_fence = (prev_state == 1)

        # Detect fence open/close
        if text.strip().startswith("```") or text.strip().startswith("~~~"):
            self.setFormat(0, len(text), self._code_block_fmt)
            self.setCurrentBlockState(0 if in_fence else 1)
            return

        if in_fence:
            self.setFormat(0, len(text), self._code_block_fmt)
            self.setCurrentBlockState(1)
            return

        self.setCurrentBlockState(0)

        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
