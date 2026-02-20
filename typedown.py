#!/usr/bin/env python3
"""TypeDown — A beautiful, distraction-free markdown editor for Linux."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from src.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TypeDown")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("TypeDown")
    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            window.open_file(path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
