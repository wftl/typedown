"""Live HTML preview using QWebEngineView."""

import markdown
from pygments.formatters import HtmlFormatter
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QColor


# ── CSS ───────────────────────────────────────────────────────────────────────

_COMMON_CSS = """
*, *::before, *::after { box-sizing: border-box; }

body {
    font-family: Georgia, 'DejaVu Serif', serif;
    font-size: 17px;
    line-height: 1.9;
    max-width: 700px;
    margin: 0 auto;
    padding: 52px 60px 110px;
    word-wrap: break-word;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

/* ── Headings ── */
h1, h2, h3, h4, h5, h6 {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-weight: 700;
    line-height: 1.25;
    letter-spacing: -0.022em;
    margin-top: 2.2em;
    margin-bottom: 0.5em;
}
h1 { font-size: 2.1em; margin-top: 0.4em; }
h2 { font-size: 1.5em; }
h3 { font-size: 1.22em; font-weight: 600; }
h4 { font-size: 1.05em; font-weight: 600; }
h5, h6 { font-size: 1em; font-weight: 600; }

/* ── Paragraphs & lists ── */
p { margin: 0 0 1.2em; }
ul, ol { padding-left: 1.7em; margin: 0 0 1.2em; }
li { margin: 0.4em 0; }
li > p { margin: 0; }

/* ── Task lists ── */
.task-list-item { list-style: none; margin-left: -1.4em; }
.task-list-item input[type=checkbox] { margin-right: 0.4em; }

/* ── Links ── */
a { text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Inline code ── */
code {
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
    font-size: 0.84em;
    border-radius: 4px;
    padding: 0.15em 0.45em;
}

/* ── Code blocks — always dark, editorial style ── */
pre {
    border-radius: 10px;
    padding: 20px 24px;
    overflow-x: auto;
    margin: 1.5em 0;
    font-size: 0.875em;
    line-height: 1.65;
    background: #1b1e2b;
    box-shadow: 0 4px 20px rgba(0,0,0,0.18);
}
pre code {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    font-size: inherit !important;
    border-radius: 0 !important;
    color: #cdd6f4;
}
.highlight { background: transparent !important; }

/* ── Blockquotes ── */
blockquote {
    margin: 1.5em 0;
    padding: 0 0 0 1.4em;
    font-style: italic;
}
blockquote p { margin: 0; }
blockquote > :first-child { margin-top: 0; }
blockquote > :last-child  { margin-bottom: 0; }

/* ── Horizontal rule ── */
hr { border: none; margin: 2.5em 0; height: 1px; }

/* ── Images ── */
img { max-width: 100%; height: auto; border-radius: 8px; display: block; margin: 1.5em auto; }

/* ── Tables — no grid, just row separators ── */
table { border-collapse: collapse; width: 100%; margin: 1.5em 0; font-size: 0.93em; }
th {
    text-align: left;
    padding: 10px 16px 10px 0;
    font-family: -apple-system, sans-serif;
    font-weight: 600;
    font-size: 0.82em;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    border-bottom: 2px solid;
}
td { padding: 10px 16px 10px 0; border-bottom: 1px solid; }
tr:last-child td { border-bottom: none; }

/* ── Definition lists ── */
dt { font-weight: 600; margin-top: 0.9em; }
dd { margin-left: 1.5em; }

/* ── Footnotes ── */
.footnote { font-size: 0.85em; opacity: 0.75; }
.footnote hr { display: none; }

/* ── TOC ── */
.toc { border-radius: 8px; padding: 1em 1.5em; margin: 1.5em 0; font-size: 0.93em; }
"""

_LIGHT_CSS = _COMMON_CSS + """
body { background: #fefefe; color: #1e1e1e; }
h1, h2, h3, h4, h5, h6 { color: #111111; }

a { color: #2563eb; }
a:hover { color: #1d4ed8; }

code { background: #f3eeeb; color: #be4030; }

blockquote { border-left: 3px solid #c8c0b8; color: #6b6560; }

hr { background: #e8e4e0; }

th { color: #7a7570; border-bottom-color: #ddd9d4; }
td { border-bottom-color: #f0ece8; }

.toc { background: #f8f5f2; }
"""

_DARK_CSS = _COMMON_CSS + """
body { background: #181612; color: #d5d0c7; }
h1, h2, h3, h4, h5, h6 { color: #ede9e0; }

a { color: #7db3e8; }
a:hover { color: #9ec8f0; }

code { background: #25221e; color: #e8956a; }

pre { background: #0e0d0b; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }

blockquote { border-left: 3px solid #3d3730; color: #807870; }

hr { background: #2a2722; }

th { color: #6b6560; border-bottom-color: #2a2722; }
td { border-bottom-color: #1e1c18; }

.toc { background: #1e1b17; }
"""

_MD_EXTENSIONS = ["extra", "codehilite", "toc", "sane_lists", "smarty"]
_MD_EXT_CFG = {
    "codehilite": {
        "css_class": "highlight",
        "linenums":  False,
        "guess_lang": True,
    },
    "smarty": {
        "smart_dashes":  True,
        "smart_ellipses": True,
        "smart_quotes":  False,  # leave quotes alone to avoid curly-quote surprises
    },
}


class PreviewWidget(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = False
        self._pending_markdown = ""
        self._scroll_y = 0

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        # Render after a short debounce so we don't thrash on every keystroke
        self._timer = QTimer(singleShot=True, interval=150)
        self._timer.timeout.connect(self._render)

        # Capture scroll before re-render so we can restore it
        self.loadFinished.connect(self._on_load_finished)

        self.render_markdown("")

    # ── Public API ────────────────────────────────────────────────────────────

    def set_dark(self, dark: bool):
        self._is_dark = dark
        # Immediate re-render if we already have content
        self._render()

    def render_markdown(self, text: str):
        self._pending_markdown = text
        # Save scroll position then schedule render
        self.page().runJavaScript("window.scrollY", self._save_scroll_and_render)

    def get_full_html(self) -> str:
        return self._build_html(self._pending_markdown)

    def print_to_pdf(self, path: str):
        self.page().printToPdf(path)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _save_scroll_and_render(self, y):
        self._scroll_y = y or 0
        self._timer.start()

    def _render(self):
        html = self._build_html(self._pending_markdown)
        self.setHtml(html, QUrl("about:blank"))

    def _on_load_finished(self, ok: bool):
        if self._scroll_y:
            self.page().runJavaScript(f"window.scrollTo(0, {self._scroll_y});")

    def _build_html(self, text: str) -> str:
        body_html = markdown.markdown(
            text,
            extensions=_MD_EXTENSIONS,
            extension_configs=_MD_EXT_CFG,
        )

        # dracula works for both: code blocks are always dark (#1b1e2b / #0e0d0b)
        pygments_css = HtmlFormatter(style="dracula").get_style_defs(".highlight")
        preview_css = _DARK_CSS if self._is_dark else _LIGHT_CSS
        bg = "#181612" if self._is_dark else "#fefefe"

        return (
            f'<!DOCTYPE html>\n<html lang="en">\n<head>\n'
            f'<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<style>\n{preview_css}\n{pygments_css}\n</style>\n"
            f'</head>\n<body style="background:{bg}">\n'
            f"{body_html}\n"
            f"</body>\n</html>"
        )
