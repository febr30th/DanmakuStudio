"""DanmakuStudio 主窗口。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..batch import BatchJob
from ..config.models import EncodeMode
from ._shared import (
    config_dialog_start_location,
    format_duration,
    get_app_dir,
    last_config_dir_path,
    last_dir_path,
)
from .task_editor import TaskDetailDialog
from .theme import CheckMarkCheckBox, refresh_dynamic_style
from .worker import BatchWorker


class DanmakuStudioWindow(QWidget):
    """DanmakuStudio 主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DanmakuStudio · 弹幕压制工作台")
        self.setObjectName("appRoot")
        self.resize(880, 680)
        self.setMinimumSize(760, 600)
        self.worker: BatchWorker | None = None
        self.pending_job: BatchJob | None = None
        self.last_dir = str(get_app_dir())
        self.last_config_dir = ""
        self._load_last_dir()
        self._load_last_config_dir()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(13)
        brand_mark = QLabel("弹")
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(brand_mark)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)
        title = QLabel("DanmakuStudio")
        title.setObjectName("pageTitle")
        subtitle = QLabel("弹幕压制工作台")
        subtitle.setObjectName("pageSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header.addLayout(title_layout)
        header.addStretch(1)

        self.status_badge = QLabel("等待任务")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setProperty("state", "idle")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.status_badge)
        layout.addLayout(header)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(18, 16, 18, 18)
        settings_layout.setSpacing(13)

        settings_title = QLabel("输出设置")
        settings_title.setObjectName("sectionTitle")
        settings_description = QLabel("选择编码方式，也可以按需加载自定义 YAML 配置。")
        settings_description.setObjectName("sectionDescription")
        settings_layout.addWidget(settings_title)
        settings_layout.addWidget(settings_description)

        options = QGridLayout()
        options.setHorizontalSpacing(12)
        options.setVerticalSpacing(11)
        options.setColumnStretch(1, 1)

        encode_label = QLabel("编码模式")
        encode_label.setObjectName("fieldLabel")
        options.addWidget(encode_label, 0, 0)
        self.encode_combo = QComboBox()
        self.encode_combo.addItem("自动选择（推荐）", EncodeMode.AUTO)
        self.encode_combo.addItem("NVIDIA GPU", EncodeMode.GPU)
        self.encode_combo.addItem("Intel QSV", EncodeMode.QSV)
        self.encode_combo.addItem("CPU", EncodeMode.CPU)
        self.encode_combo.setToolTip("自动模式会优先尝试硬件编码，不可用时回退到 CPU。")
        options.addWidget(self.encode_combo, 0, 1)

        self.force_checkbox = CheckMarkCheckBox("覆盖已存在输出")
        options.addWidget(self.force_checkbox, 0, 2)

        config_label = QLabel("配置文件")
        config_label.setObjectName("fieldLabel")
        options.addWidget(config_label, 1, 0)
        self.config_edit = QLineEdit()
        self.config_edit.setPlaceholderText("留空则使用内置默认配置")
        self.config_edit.setClearButtonEnabled(True)
        default_config = get_app_dir() / "danmakustudio.yaml"
        if default_config.exists():
            self.config_edit.setText(str(default_config))
        options.addWidget(self.config_edit, 1, 1)

        self.btn_config = QPushButton("浏览…")
        self.btn_config.clicked.connect(self.choose_config)
        options.addWidget(self.btn_config, 1, 2)
        settings_layout.addLayout(options)
        layout.addWidget(settings_card)

        task_card = QFrame()
        task_card.setObjectName("card")
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(18, 16, 18, 18)
        task_layout.setSpacing(12)

        task_header = QHBoxLayout()
        task_heading_layout = QVBoxLayout()
        task_heading_layout.setSpacing(2)
        task_title = QLabel("当前任务")
        task_title.setObjectName("sectionTitle")
        task_description = QLabel("分别确认视频和弹幕，多个视频将合并为一个成品。")
        task_description.setObjectName("sectionDescription")
        task_heading_layout.addWidget(task_title)
        task_heading_layout.addWidget(task_description)
        task_header.addLayout(task_heading_layout)
        task_header.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_choose = QPushButton("选择视频…")
        self.btn_choose.clicked.connect(self.choose_items)
        actions.addWidget(self.btn_choose)

        self.btn_start = QPushButton("开始压制  →")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_pending_jobs)
        actions.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("取消任务")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.cancel_running_job)
        actions.addWidget(self.btn_cancel)
        task_header.addLayout(actions)
        task_layout.addLayout(task_header)

        self.log = QTextEdit()
        self.log.setObjectName("logView")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("选择素材后，这里会显示匹配结果和处理日志。")
        self.log.document().setMaximumBlockCount(5000)
        task_layout.addWidget(self.log, 1)

        self.summary_label = QLabel("等待选择视频")
        self.summary_label.setObjectName("fieldHint")
        task_layout.addWidget(self.summary_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setAccessibleName("任务处理进度")
        task_layout.addWidget(self.progress_bar)
        layout.addWidget(task_card, 1)

    def _set_status(self, text: str, state: str) -> None:
        self.status_badge.setText(text)
        self.status_badge.setProperty("state", state)
        refresh_dynamic_style(self.status_badge)

    def _load_last_dir(self) -> None:
        cfg = last_dir_path()
        if not cfg.exists():
            return

        try:
            path = cfg.read_text(encoding="utf-8").strip()
        except OSError:
            return

        if path and os.path.isdir(path):
            self.last_dir = path

    def _save_last_dir(self, dir_path: str) -> None:
        try:
            last_dir_path().write_text(dir_path, encoding="utf-8")
        except OSError:
            pass

    def _load_last_config_dir(self) -> None:
        cfg = last_config_dir_path()
        if not cfg.exists():
            return

        try:
            path = cfg.read_text(encoding="utf-8").strip()
        except OSError:
            return

        if path and os.path.isdir(path):
            self.last_config_dir = path

    def _save_last_config_dir(self, dir_path: str) -> None:
        try:
            last_config_dir_path().write_text(dir_path, encoding="utf-8")
        except OSError:
            pass

    def choose_config(self) -> None:
        start_location = config_dialog_start_location(
            self.config_edit.text(),
            self.last_config_dir,
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择配置文件",
            start_location,
            "YAML 文件 (*.yaml *.yml);;所有文件 (*)",
        )
        if file_path:
            self.config_edit.setText(file_path)
            self.last_config_dir = os.path.dirname(file_path)
            self._save_last_config_dir(self.last_config_dir)

    def append_log(self, text: str) -> None:
        if text:
            self.log.append(text)
        else:
            self.log.append("")

    def choose_items(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "已有任务正在处理，请稍候。")
            return

        draft_job = self.pending_job or BatchJob.empty(Path(self.last_dir))
        confirmation = TaskDetailDialog(draft_job, self)
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return

        self.pending_job = None
        self.btn_start.setEnabled(False)
        self.log.clear()
        self.progress_bar.setValue(0)

        self.pending_job = confirmation.result_job()
        job = self.pending_job
        self._remember_selection_dir(
            [str(path) for path in job.video_paths],
            self.last_dir,
        )

        self.append_log("已确认一个成品任务:")
        for index, video_path in enumerate(job.video_paths, start=1):
            self.append_log(f"  视频 {index}: {video_path}")
        subtitles = [path for path in job.subtitle_paths if path is not None]
        for index, subtitle_path in enumerate(subtitles, start=1):
            self.append_log(f"  弹幕 {index}: {subtitle_path}")
        self.append_log(f"  输出: {job.output_path}")

        self.btn_start.setEnabled(True)
        self.summary_label.setText(
            f"已就绪：{len(job.video_paths)} 个视频，{len(subtitles)} 份弹幕"
        )
        self._set_status("任务就绪", "ready")

    def _remember_selection_dir(self, selected: list[str], fallback: str) -> None:
        selected_for_last_dir = selected[0] if selected else fallback
        current_dir = (
            selected_for_last_dir
            if os.path.isdir(selected_for_last_dir)
            else os.path.dirname(selected_for_last_dir)
        )
        if os.path.isdir(current_dir):
            self.last_dir = current_dir
            self._save_last_dir(self.last_dir)

    def start_pending_jobs(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "已有任务正在处理，请稍候。")
            return

        if self.pending_job is None:
            QMessageBox.warning(self, "提示", "请先选择可处理的视频和字幕。")
            return

        self.start_worker(self.pending_job)

    def start_worker(self, job: BatchJob) -> None:
        config_path = self.config_edit.text().strip() or None
        self.btn_choose.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_config.setEnabled(False)
        self.encode_combo.setEnabled(False)
        self.force_checkbox.setEnabled(False)
        self.btn_cancel.setText("取消任务")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setVisible(True)
        self.summary_label.setText("正在处理当前任务")
        self.progress_bar.setValue(0)
        self._set_status("正在处理", "busy")
        self.append_log("")
        self.append_log("开始处理...")

        self.worker = BatchWorker(
            jobs=[job],
            encode_mode=self.encode_combo.currentData(),
            config_path=config_path,
            force=self.force_checkbox.isChecked(),
        )
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.summary.connect(self.on_worker_summary)
        self.worker.start()

    def cancel_running_job(self) -> None:
        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        answer = QMessageBox.question(
            self,
            "确认取消任务",
            "确定要取消正在进行的压制吗？\n已生成的临时文件会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("正在取消…")
        self.summary_label.setText("正在取消并清理临时文件…")
        worker.request_cancel()

    def on_worker_progress(
        self,
        task_index: int,
        task_total: int,
        percent: float,
        elapsed: float,
    ) -> None:
        overall_percent = (
            (max(1, task_index) - 1) + max(0.0, min(100.0, percent)) / 100.0
        ) / max(1, task_total)
        self.progress_bar.setValue(round(overall_percent * self.progress_bar.maximum()))
        self.summary_label.setText(
            f"处理中: {percent:5.1f}% | 已用 {format_duration(elapsed)}"
        )

    def on_worker_summary(
        self,
        total: int,
        generated: int,
        skipped: int,
        failed: int,
        cancelled: bool = False,
    ) -> None:
        self.btn_choose.setEnabled(True)
        self.btn_config.setEnabled(True)
        self.encode_combo.setEnabled(True)
        self.force_checkbox.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setText("取消任务")
        self.worker = None

        if cancelled:
            self.btn_start.setEnabled(self.pending_job is not None)
            self.summary_label.setText("任务已取消，临时文件已清理")
            self._set_status("任务已取消", "idle")
            QMessageBox.information(
                self,
                "任务已取消",
                "压制已取消，临时文件已清理。",
                QMessageBox.StandardButton.Ok,
            )
            return

        self.btn_start.setEnabled(False)
        self.pending_job = None
        self.progress_bar.setValue(self.progress_bar.maximum())

        if failed:
            result_text = "处理失败"
        elif skipped:
            result_text = "输出已存在，任务已跳过"
        else:
            result_text = "处理完成"
        self.summary_label.setText(result_text)
        if failed:
            self._set_status(f"完成 · {failed} 个失败", "error")
        else:
            self._set_status("全部完成", "done")
        QMessageBox.information(
            self,
            "处理结果",
            result_text,
            QMessageBox.StandardButton.Ok,
        )
