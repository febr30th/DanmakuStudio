"""单一成品任务的视频与弹幕素材确认对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..batch import (
    BatchJob,
    SubtitleMode,
    default_output_path_for_videos,
    find_matching_subtitle,
    natural_path_key,
)
from ..utils.validation import SUPPORTED_OUTPUT_EXTS, SUPPORTED_VIDEO_EXTS


def _file_filter(label: str, extensions: list[str] | tuple[str, ...]) -> str:
    patterns = " ".join(f"*{extension}" for extension in extensions)
    return f"{label} ({patterns})"


VIDEO_FILTER = _file_filter("视频文件", sorted(SUPPORTED_VIDEO_EXTS))
SUBTITLE_FILTER = _file_filter("弹幕文件", [".xml", ".lrc"])
OUTPUT_FILTER = _file_filter("视频文件", sorted(SUPPORTED_OUTPUT_EXTS))


class TaskDetailDialog(QDialog):
    """以独立双列表确认视频和弹幕，内部自动确定时间轴模式。"""

    def __init__(self, job: BatchJob, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("taskDetailDialog")
        self.setWindowTitle("确认视频与弹幕")
        self.resize(940, 620)
        self.setMinimumSize(760, 540)

        self._video_paths = list(job.video_paths)
        self._subtitle_paths = [
            path for path in job.subtitle_paths if path is not None
        ]
        self._last_dir = (
            self._video_paths[0].parent
            if self._video_paths
            else self._subtitle_paths[0].parent
            if self._subtitle_paths
            else job.output_path.parent
        )
        self._result_job = job
        self._output_tracks_default = not self._video_paths or (
            job.output_path == default_output_path_for_videos(tuple(self._video_paths))
        )
        self._next_button: QPushButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("确认视频与弹幕")
        title.setObjectName("pageTitle")
        hint = QLabel(
            "左侧管理要合并的视频，右侧管理要加入成品的弹幕。"
        )
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)

        lists_layout = QHBoxLayout()
        lists_layout.setSpacing(14)

        video_panel = QVBoxLayout()
        video_header = QHBoxLayout()
        video_header.addWidget(QLabel("视频（从上到下合并）"))
        video_header.addStretch(1)
        self.btn_add_video = QPushButton("添加…")
        self.btn_remove_video = QPushButton("删除")
        self.btn_video_up = QPushButton("上移")
        self.btn_video_down = QPushButton("下移")
        for button in (
            self.btn_add_video,
            self.btn_remove_video,
            self.btn_video_up,
            self.btn_video_down,
        ):
            video_header.addWidget(button)
        video_panel.addLayout(video_header)
        self.video_list = QListWidget()
        self.video_list.setObjectName("videoSelectionList")
        self.video_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.video_list.setAlternatingRowColors(True)
        video_panel.addWidget(self.video_list, 1)
        lists_layout.addLayout(video_panel, 1)

        subtitle_panel = QVBoxLayout()
        subtitle_header = QHBoxLayout()
        subtitle_header.addWidget(QLabel("弹幕"))
        subtitle_header.addStretch(1)
        self.btn_add_subtitle = QPushButton("添加…")
        self.btn_remove_subtitle = QPushButton("删除")
        self.btn_subtitle_up = QPushButton("上移")
        self.btn_subtitle_down = QPushButton("下移")
        for button in (
            self.btn_add_subtitle,
            self.btn_remove_subtitle,
            self.btn_subtitle_up,
            self.btn_subtitle_down,
        ):
            subtitle_header.addWidget(button)
        subtitle_panel.addLayout(subtitle_header)
        self.subtitle_list = QListWidget()
        self.subtitle_list.setObjectName("subtitleSelectionList")
        self.subtitle_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.subtitle_list.setAlternatingRowColors(True)
        subtitle_panel.addWidget(self.subtitle_list, 1)
        lists_layout.addLayout(subtitle_panel, 1)
        layout.addLayout(lists_layout, 1)

        output_row = QGridLayout()
        output_row.addWidget(QLabel("输出文件"), 0, 0)
        self.output_edit = QLineEdit(str(job.output_path))
        self.output_edit.setObjectName("taskOutputEdit")
        output_row.addWidget(self.output_edit, 0, 1)
        self.btn_output = QPushButton("浏览…")
        output_row.addWidget(self.btn_output, 0, 2)
        layout.addLayout(output_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._next_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if self._next_button is not None:
            self._next_button.setText("下一步")
            self._next_button.setObjectName("primaryButton")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("取消")
        layout.addWidget(buttons)

        self.btn_add_video.clicked.connect(self.add_videos)
        self.btn_remove_video.clicked.connect(self.remove_video)
        self.btn_video_up.clicked.connect(lambda: self.move_video(-1))
        self.btn_video_down.clicked.connect(lambda: self.move_video(1))
        self.btn_add_subtitle.clicked.connect(self.add_subtitles)
        self.btn_remove_subtitle.clicked.connect(self.remove_subtitle)
        self.btn_subtitle_up.clicked.connect(lambda: self.move_subtitle(-1))
        self.btn_subtitle_down.clicked.connect(lambda: self.move_subtitle(1))
        self.btn_output.clicked.connect(self.choose_output)
        self.output_edit.textEdited.connect(self._mark_output_customized)
        buttons.accepted.connect(self.accept_task)
        buttons.rejected.connect(self.reject)

        self._refresh()

    @property
    def next_button(self) -> QPushButton | None:
        return self._next_button

    def result_job(self) -> BatchJob:
        return self._result_job

    def _start_dir(self) -> str:
        return str(self._last_dir)

    def _mark_output_customized(self) -> None:
        self._output_tracks_default = False

    def _refresh(self) -> None:
        selected_video = self.video_list.currentRow()
        selected_subtitle = self.subtitle_list.currentRow()

        self.video_list.clear()
        for index, path in enumerate(self._video_paths, start=1):
            self.video_list.addItem(f"{index}. {path.name}")
            self.video_list.item(index - 1).setToolTip(str(path))
        if self._video_paths:
            self.video_list.setCurrentRow(
                min(max(selected_video, 0), len(self._video_paths) - 1)
            )

        self.subtitle_list.clear()
        for index, path in enumerate(self._subtitle_paths, start=1):
            self.subtitle_list.addItem(f"{index}. {path.name}")
            self.subtitle_list.item(index - 1).setToolTip(str(path))
        if self._subtitle_paths:
            self.subtitle_list.setCurrentRow(
                min(max(selected_subtitle, 0), len(self._subtitle_paths) - 1)
            )

        if self._next_button is not None:
            self._next_button.setEnabled(
                bool(self._video_paths) and bool(self._subtitle_paths)
            )

    def _update_default_output(self) -> None:
        if self._output_tracks_default and self._video_paths:
            self.output_edit.setText(
                str(default_output_path_for_videos(tuple(self._video_paths)))
            )

    def add_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "添加视频",
            self._start_dir(),
            VIDEO_FILTER,
        )
        if not paths:
            return

        new_paths = [Path(path).resolve() for path in paths]
        self._last_dir = new_paths[0].parent
        existing_videos = {str(path).lower() for path in self._video_paths}
        existing_subtitles = {str(path).lower() for path in self._subtitle_paths}
        for path in sorted(new_paths, key=natural_path_key):
            if str(path).lower() in existing_videos:
                continue
            self._video_paths.append(path)
            existing_videos.add(str(path).lower())
            matching_subtitle = find_matching_subtitle(path)
            if (
                matching_subtitle is not None
                and str(matching_subtitle).lower() not in existing_subtitles
            ):
                self._subtitle_paths.append(matching_subtitle)
                existing_subtitles.add(str(matching_subtitle).lower())

        self._update_default_output()
        self._refresh()

    def remove_video(self) -> None:
        row = self.video_list.currentRow()
        if row < 0:
            return
        self._video_paths.pop(row)
        self._update_default_output()
        self._refresh()

    def move_video(self, offset: int) -> None:
        row = self.video_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= len(self._video_paths):
            return
        self._video_paths[row], self._video_paths[target] = (
            self._video_paths[target],
            self._video_paths[row],
        )
        self._update_default_output()
        self._refresh()
        self.video_list.setCurrentRow(target)

    def add_subtitles(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "添加弹幕",
            self._start_dir(),
            SUBTITLE_FILTER,
        )
        if not paths:
            return
        new_paths = [Path(path).resolve() for path in paths]
        self._last_dir = new_paths[0].parent
        existing = {str(path).lower() for path in self._subtitle_paths}
        for path in sorted(new_paths, key=natural_path_key):
            if str(path).lower() not in existing:
                self._subtitle_paths.append(path)
                existing.add(str(path).lower())
        self._refresh()

    def remove_subtitle(self) -> None:
        row = self.subtitle_list.currentRow()
        if row < 0:
            return
        self._subtitle_paths.pop(row)
        self._refresh()

    def move_subtitle(self, offset: int) -> None:
        row = self.subtitle_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= len(self._subtitle_paths):
            return
        self._subtitle_paths[row], self._subtitle_paths[target] = (
            self._subtitle_paths[target],
            self._subtitle_paths[row],
        )
        self._refresh()
        self.subtitle_list.setCurrentRow(target)

    def choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出文件",
            self.output_edit.text().strip() or self._start_dir(),
            OUTPUT_FILTER,
        )
        if path:
            self._output_tracks_default = False
            self.output_edit.setText(path)

    def _segment_subtitles(self) -> tuple[Path | None, ...]:
        """同名优先，再把其余弹幕依次放入尚未占用的视频槽位。"""
        slots: list[Path | None] = [None] * len(self._video_paths)
        remaining: list[Path] = []
        for subtitle_path in self._subtitle_paths:
            matching_index = next(
                (
                    index
                    for index, video_path in enumerate(self._video_paths)
                    if slots[index] is None
                    and video_path.stem.lower() == subtitle_path.stem.lower()
                ),
                None,
            )
            if matching_index is None:
                remaining.append(subtitle_path)
            else:
                slots[matching_index] = subtitle_path

        free_indexes = [index for index, path in enumerate(slots) if path is None]
        for index, subtitle_path in zip(free_indexes, remaining):
            slots[index] = subtitle_path
        return tuple(slots)

    def _validation_errors(self, job: BatchJob) -> list[str]:
        errors = job.validation_errors()
        for path in job.video_paths:
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
                errors.append(f"视频不可用: {path}")
        for path in job.subtitle_paths:
            if path is not None and (
                not path.is_file() or path.suffix.lower() not in {".xml", ".lrc"}
            ):
                errors.append(f"弹幕不可用: {path}")
        if job.output_path.suffix.lower() not in SUPPORTED_OUTPUT_EXTS:
            errors.append(f"不支持的输出格式: {job.output_path.suffix}")
        if not job.output_path.parent.is_dir():
            errors.append(f"输出目录不存在: {job.output_path.parent}")
        return errors

    def accept_task(self) -> None:
        if not self._video_paths or not self._subtitle_paths:
            return

        output_text = self.output_edit.text().strip()
        if not output_text:
            QMessageBox.warning(self, "素材尚未确认", "请选择输出文件。")
            return
        subtitle_mode = (
            SubtitleMode.FULL
            if len(self._subtitle_paths) == 1
            or len(self._subtitle_paths) > len(self._video_paths)
            else SubtitleMode.PER_SEGMENT
        )
        subtitle_paths = (
            tuple(self._subtitle_paths)
            if subtitle_mode == SubtitleMode.FULL
            else self._segment_subtitles()
        )
        job = BatchJob(
            video_paths=tuple(self._video_paths),
            subtitle_paths=subtitle_paths,
            output_path=Path(output_text).expanduser().resolve(),
            subtitle_mode=subtitle_mode,
        )
        errors = self._validation_errors(job)
        if errors:
            QMessageBox.warning(
                self,
                "素材尚未确认",
                "请先处理以下问题：\n\n" + "\n".join(f"• {error}" for error in errors),
            )
            return
        self._result_job = job
        self.accept()
