"""GUI 主题和主窗口状态测试。"""

from PySide6.QtWidgets import QApplication

from danmakustudio.config.models import EncodeMode
from danmakustudio.ui._shared import config_dialog_start_location
from danmakustudio.ui.file_picker import FileFolderPickerDialog
from danmakustudio.ui.main_window import DanmakuStudioWindow
from danmakustudio.ui.theme import APP_STYLESHEET, CheckMarkCheckBox, apply_theme


def test_apply_theme_sets_application_stylesheet(qapp):
    assert isinstance(qapp, QApplication)

    apply_theme(qapp)

    assert qapp.style() is not None
    assert qapp.styleSheet() == APP_STYLESHEET


def test_main_window_initial_state(qapp):
    apply_theme(qapp)
    window = DanmakuStudioWindow()

    assert window.status_badge.text() == "等待任务"
    assert window.status_badge.property("state") == "idle"
    assert window.encode_combo.currentData() == EncodeMode.AUTO
    assert isinstance(window.force_checkbox, CheckMarkCheckBox)
    assert window.windowTitle() == "DanmakuStudio · 弹幕压制工作台"
    assert not window.windowIcon().isNull()
    assert window.btn_choose.text() == "选择视频或文件夹"
    assert not window.btn_start.isEnabled()
    assert window.progress_bar.value() == 0

    window.close()


def test_file_picker_uses_styled_controls(qapp, tmp_path):
    apply_theme(qapp)
    dialog = FileFolderPickerDialog(start_dir=str(tmp_path))

    assert dialog.tree.objectName() == "fileTree"
    assert dialog.tree.alternatingRowColors()
    assert dialog.windowTitle() == "选择视频或文件夹"
    assert dialog.btn_current.text() == "＋  使用当前文件夹"
    assert dialog.path_label.objectName() == "pathButton"

    dialog.close()


def test_config_dialog_prefers_selected_file_then_last_directory(tmp_path):
    selected = tmp_path / "selected.yaml"
    selected.write_text("style: {}", encoding="utf-8")
    previous = tmp_path / "previous"
    previous.mkdir()

    assert config_dialog_start_location(str(selected), str(previous)) == str(selected)
    assert config_dialog_start_location("", str(previous)) == str(previous)


def test_main_window_reports_overall_batch_progress(qapp):
    window = DanmakuStudioWindow()

    window.on_worker_progress(
        task_index=2,
        task_total=4,
        percent=20.0,
        elapsed=65.0,
    )

    assert window.progress_bar.value() == 300
    assert "任务 2/4" in window.summary_label.text()
    assert "20.0%" in window.summary_label.text()
    assert "01:05" in window.summary_label.text()

    window.close()
