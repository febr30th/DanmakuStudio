"""GUI 主题和主窗口状态测试。"""

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from danmakustudio.batch import BatchJob, SubtitleMode, create_job_from_videos
from danmakustudio.config.models import EncodeMode
from danmakustudio.ui._shared import config_dialog_start_location
import danmakustudio.ui.main_window as main_window_module
from danmakustudio.ui.main_window import DanmakuStudioWindow
from danmakustudio.ui.task_editor import TaskDetailDialog
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
    assert window.btn_choose.text() == "选择视频…"
    assert window.pending_job is None
    assert not window.btn_start.isEnabled()
    assert window.btn_cancel.isHidden()
    assert window.progress_bar.value() == 0

    window.close()


def test_choose_button_opens_empty_then_current_materials(qapp, tmp_path, monkeypatch):
    captured_jobs = []

    class FakeDialog:
        def __init__(self, job, _parent):
            captured_jobs.append(job)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(main_window_module, "TaskDetailDialog", FakeDialog)
    window = DanmakuStudioWindow()
    window.last_dir = str(tmp_path)

    window.choose_items()
    assert captured_jobs[-1].video_paths == ()
    assert captured_jobs[-1].subtitle_paths == ()

    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "video.xml"
    current = BatchJob.single(video, subtitle)
    window.pending_job = current
    window.choose_items()
    assert captured_jobs[-1] is current

    window.close()


def test_config_dialog_prefers_selected_file_then_last_directory(tmp_path):
    selected = tmp_path / "selected.yaml"
    selected.write_text("style: {}", encoding="utf-8")
    previous = tmp_path / "previous"
    previous.mkdir()

    assert config_dialog_start_location(str(selected), str(previous)) == str(selected)
    assert config_dialog_start_location("", str(previous)) == str(previous)


def test_main_window_reports_single_task_progress(qapp):
    window = DanmakuStudioWindow()

    window.on_worker_progress(
        task_index=1,
        task_total=1,
        percent=20.0,
        elapsed=65.0,
    )

    assert window.progress_bar.value() == 200
    assert "任务 1/1" not in window.summary_label.text()
    assert "20.0%" in window.summary_label.text()
    assert "01:05" in window.summary_label.text()

    window.close()


def test_task_editor_keeps_missing_subtitle_editable(qapp, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("", encoding="utf-8")
    job = BatchJob.single(video, None)

    dialog = TaskDetailDialog(job)

    assert dialog.windowTitle() == "确认视频与弹幕"
    assert dialog.video_list.count() == 1
    assert dialog.subtitle_list.count() == 0
    assert not hasattr(dialog, "mode_combo")
    assert dialog.next_button is not None
    assert not dialog.next_button.isEnabled()

    dialog.close()


def test_task_editor_shows_independent_video_and_subtitle_lists(qapp, tmp_path):
    first = tmp_path / "part1.mp4"
    second = tmp_path / "part2.mp4"
    first_subtitle = tmp_path / "part1.xml"
    second_subtitle = tmp_path / "part2.xml"
    for path in (first, second, first_subtitle, second_subtitle):
        path.write_text("", encoding="utf-8")

    job = create_job_from_videos([second, first])
    dialog = TaskDetailDialog(job)

    assert dialog.video_list.count() == 2
    assert dialog.subtitle_list.count() == 2
    assert dialog.video_list.item(0).text().endswith("part1.mp4")
    assert dialog.subtitle_list.item(0).text().endswith("part1.xml")
    assert dialog.subtitle_list.item(1).text().endswith("part2.xml")
    assert dialog.next_button is not None
    assert dialog.next_button.isEnabled()

    dialog.close()


def test_task_editor_allows_removing_all_videos_and_disables_next(qapp, tmp_path):
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "video.xml"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")
    dialog = TaskDetailDialog(BatchJob.single(video, subtitle))

    dialog.video_list.setCurrentRow(0)
    dialog.remove_video()

    assert dialog.video_list.count() == 0
    assert dialog.subtitle_list.count() == 1
    assert dialog.next_button is not None
    assert not dialog.next_button.isEnabled()

    dialog.close()


def test_adding_video_also_adds_its_matching_subtitle(
    qapp, tmp_path, monkeypatch
):
    original = tmp_path / "original.mp4"
    added = tmp_path / "later" / "part2.mp4"
    matching = tmp_path / "later" / "part2.xml"
    original.write_text("", encoding="utf-8")
    added.parent.mkdir()
    added.write_text("", encoding="utf-8")
    matching.write_text("", encoding="utf-8")
    dialog = TaskDetailDialog(BatchJob.single(original, None))
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(added)], ""),
    )

    dialog.add_videos()

    assert dialog.video_list.count() == 2
    assert dialog.subtitle_list.count() == 1
    assert dialog.subtitle_list.item(0).toolTip() == str(matching.resolve())
    assert dialog.next_button is not None
    assert dialog.next_button.isEnabled()

    dialog.close()


def test_multiple_subtitles_map_to_same_name_videos_before_list_order(qapp, tmp_path):
    videos = tuple(tmp_path / f"part{index}.mp4" for index in (1, 2, 3))
    subtitles = (tmp_path / "part3.xml", tmp_path / "part1.xml")
    for path in (*videos, *subtitles):
        path.write_text("", encoding="utf-8")
    job = BatchJob(
        video_paths=videos,
        subtitle_paths=subtitles,
        output_path=tmp_path / "output.mp4",
        subtitle_mode=SubtitleMode.PER_SEGMENT,
    )
    dialog = TaskDetailDialog(job)

    assert dialog._segment_subtitles() == (subtitles[1], None, subtitles[0])

    dialog.close()


def test_more_subtitles_than_videos_remain_allowed(qapp, tmp_path):
    video = tmp_path / "video.mp4"
    subtitles = (tmp_path / "one.xml", tmp_path / "two.lrc")
    for path in (video, *subtitles):
        path.write_text("", encoding="utf-8")
    dialog = TaskDetailDialog(
        BatchJob(
            video_paths=(video,),
            subtitle_paths=subtitles,
            output_path=tmp_path / "output.mp4",
            subtitle_mode=SubtitleMode.FULL,
        )
    )

    assert dialog.next_button is not None
    assert dialog.next_button.isEnabled()
    dialog.accept_task()
    assert dialog.result_job().subtitle_paths == subtitles
    assert dialog.result_job().subtitle_mode == SubtitleMode.FULL


def test_cancel_button_confirms_and_requests_worker_cancel(qapp, monkeypatch):
    class FakeWorker:
        requested = False

        def isRunning(self):
            return True

        def request_cancel(self):
            self.requested = True

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    window = DanmakuStudioWindow()
    worker = FakeWorker()
    window.worker = worker
    window.btn_cancel.setVisible(True)

    window.cancel_running_job()

    assert worker.requested
    assert not window.btn_cancel.isEnabled()
    assert window.btn_cancel.text() == "正在取消…"

    window.worker = None
    window.close()


def test_cancelled_summary_keeps_current_materials_for_retry(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "video.xml"
    job = BatchJob.single(video, subtitle)
    window = DanmakuStudioWindow()
    window.pending_job = job

    window.on_worker_summary(1, 0, 0, 0, True)

    assert window.pending_job is job
    assert window.btn_start.isEnabled()
    assert window.status_badge.text() == "任务已取消"
    assert "临时文件已清理" in window.summary_label.text()

    window.close()
