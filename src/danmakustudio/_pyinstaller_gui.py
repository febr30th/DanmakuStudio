"""PyInstaller GUI entry point."""

from __future__ import annotations

import sys


def smoke_test(report_path: str) -> int:
    """Exercise frozen imports and native Qt initialization without user interaction."""
    import traceback
    from pathlib import Path

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from danmakustudio.gui import DanmakuStudioWindow, apply_theme

        app = QApplication([sys.argv[0]])
        apply_theme(app)
        window = DanmakuStudioWindow()
        window.create()
        window.ensurePolished()
        QTimer.singleShot(100, app.quit)
        result = app.exec()
        window.close()
        if result != 0:
            raise RuntimeError(f"Qt event loop returned {result}")
        Path(report_path).write_text("OK\n", encoding="utf-8")
        return 0
    except Exception:
        Path(report_path).write_text(traceback.format_exc(), encoding="utf-8")
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        raise SystemExit(smoke_test(sys.argv[2]))
    from danmakustudio.gui import main

    main()
