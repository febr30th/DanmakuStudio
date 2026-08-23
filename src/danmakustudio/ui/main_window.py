"""DanmakuStudio 主窗口。"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..batch import BatchJob, collect_batch_jobs
from ..config.models import EncodeMode
from ._shared import (
    dialog_start_dir_from_path,
    format_duration,
    get_app_dir,
    last_dir_path,
)
from .file_picker import FileFolderPickerDialog
from .worker import BatchWorker


class DanmakuStudioWindow(QWidget):
    """DanmakuStudio 主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DanmakuStudio")
        self.resize(780, 560)
        self.worker: BatchWorker | None = None
        self.pending_jobs: list[BatchJob] = []
        self.last_dir = str(get_app_dir())
        self._load_last_dir()

        layout = QVBoxLayout(self)

        options = QGridLayout()
        options.addWidget(QLabel("编码模式"), 0, 0)
        self.encode_combo = QComboBox()
        self.encode_combo.addItems([
            EncodeMode.AUTO,
            EncodeMode.GPU,
            EncodeMode.QSV,
            EncodeMode.CPU,
        ])
        options.addWidget(self.encode_combo, 0, 1)

        self.force_checkbox = QCheckBox("覆盖已存在输出")
        options.addWidget(self.force_checkbox, 0, 2)

        options.addWidget(QLabel("配置文件"), 1, 0)
        self.config_edit = QLineEdit()
        default_config = get_app_dir() / "danmakustudio.yaml"
        if default_config.exists():
            self.config_edit.setText(str(default_config))
        options.addWidget(self.config_edit, 1, 1)

        self.btn_config = QPushButton("浏览")
        self.btn_config.clicked.connect(self.choose_config)
        options.addWidget(self.btn_config, 1, 2)
        layout.addLayout(options)

        actions = QHBoxLayout()
        self.btn_choose = QPushButton("选择视频文件和/或文件夹")
        self.btn_choose.clicked.connect(self.choose_items)
        actions.addWidget(self.btn_choose)

        self.btn_start = QPushButton("开始处理")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_pending_jobs)
        actions.addWidget(self.btn_start)
        layout.addLayout(actions)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        self.summary_label = QLabel("等待选择任务")
        layout.addWidget(self.summary_label)

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

    def choose_config(self) -> None:
        start_dir = dialog_start_dir_from_path(self.config_edit.text(), self.last_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择配置文件",
            start_dir,
            "YAML 文件 (*.yaml *.yml);;所有文件 (*)",
        )
        if file_path:
            self.config_edit.setText(file_path)

    def append_log(self, text: str) -> None:
        if text:
            self.log.append(text)
        else:
            self.log.append("")

    def choose_items(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "已有任务正在处理，请稍候。")
            return

        dialog = FileFolderPickerDialog(self, self.last_dir)
        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.selected_paths()
        self._remember_selection_dir(selected, dialog.current_directory())

        selection = collect_batch_jobs(selected)
        self.pending_jobs = []
        self.btn_start.setEnabled(False)
        self.log.clear()

        self.append_log("已选择:")
        for path in selected:
            self.append_log(f"  {path}")

        if selection.ignored_paths:
            self.append_log("")
            self.append_log("已忽略不支持的路径:")
            for path in selection.ignored_paths:
                self.append_log(f"  {path}")

        if selection.missing_subtitles:
            self.append_log("")
            self.append_log("未找到同名 XML/LRC 字幕的视频:")
            for path in selection.missing_subtitles:
                self.append_log(f"  {path}")

        if not selection.jobs:
            QMessageBox.warning(self, "提示", "没有找到可处理的视频和同名字幕。")
            self.summary_label.setText("没有可处理任务")
            return

        self.pending_jobs = selection.jobs

        self.append_log("")
        self.append_log("将处理:")
        for job in selection.jobs:
            subtitle_kind = job.subtitle_path.suffix.upper().lstrip(".")
            self.append_log(
                f"  {job.video_path.name} + {subtitle_kind} {job.subtitle_path.name}"
            )

        self.btn_start.setEnabled(True)
        self.summary_label.setText(f"已准备 {len(self.pending_jobs)} 个任务，点击开始处理")

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

        if not self.pending_jobs:
            QMessageBox.warning(self, "提示", "请先选择可处理的视频和字幕。")
            return

        self.start_worker(list(self.pending_jobs))

    def start_worker(self, jobs: list[BatchJob]) -> None:
        config_path = self.config_edit.text().strip() or None
        self.btn_choose.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_config.setEnabled(False)
        self.encode_combo.setEnabled(False)
        self.force_checkbox.setEnabled(False)
        self.summary_label.setText(f"处理中: 0/{len(jobs)}")
        self.append_log("")
        self.append_log("开始处理...")

        self.worker = BatchWorker(
            jobs=jobs,
            encode_mode=self.encode_combo.currentText(),
            config_path=config_path,
            force=self.force_checkbox.isChecked(),
        )
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.summary.connect(self.on_worker_summary)
        self.worker.start()

    def on_worker_progress(
        self,
        task_index: int,
        task_total: int,
        percent: float,
        elapsed: float,
    ) -> None:
        self.summary_label.setText(
            f"处理中: 任务 {task_index}/{task_total} | "
            f"{percent:5.1f}% | 已用 {format_duration(elapsed)}"
        )

    def on_worker_summary(
        self,
        total: int,
        generated: int,
        skipped: int,
        failed: int,
    ) -> None:
        self.btn_choose.setEnabled(True)
        self.btn_config.setEnabled(True)
        self.encode_combo.setEnabled(True)
        self.force_checkbox.setEnabled(True)
        self.btn_start.setEnabled(False)
        self.pending_jobs = []
        self.worker = None

        self.summary_label.setText(
            f"完成: 共 {total} 个，成功 {generated} 个，跳过 {skipped} 个，失败 {failed} 个"
        )
        QMessageBox.information(
            self,
            "处理完成",
            (
                f"共 {total} 个任务\n"
                f"成功 {generated} 个\n"
                f"跳过 {skipped} 个\n"
                f"失败 {failed} 个"
            ),
            QMessageBox.Ok,
        )
