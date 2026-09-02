"""单一成品任务的素材整理与字幕匹配。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from loguru import logger

from .utils.validation import SUPPORTED_VIDEO_EXTS

SUPPORTED_BATCH_SUBTITLE_EXTS = (".xml", ".lrc")


class SubtitleMode(StrEnum):
    """字幕时间轴模式。"""

    FULL = "full"
    PER_SEGMENT = "per_segment"


@dataclass(frozen=True, slots=True)
class BatchJob:
    """一个成品对应的视频片段、字幕和输出路径。"""

    video_paths: tuple[Path, ...]
    subtitle_paths: tuple[Path | None, ...]
    output_path: Path
    subtitle_mode: SubtitleMode = SubtitleMode.FULL

    @classmethod
    def single(cls, video_path: Path, subtitle_path: Path | None) -> BatchJob:
        return cls(
            video_paths=(video_path,),
            subtitle_paths=(subtitle_path,),
            output_path=default_output_path_for_video(video_path),
        )

    @classmethod
    def empty(cls, start_dir: Path) -> BatchJob:
        """创建供素材编辑器使用的空任务草稿。"""
        return cls(
            video_paths=(),
            subtitle_paths=(),
            output_path=start_dir / "弹幕版.mp4",
        )

    @property
    def video_path(self) -> Path:
        """兼容单视频调用方：返回第一段视频。"""
        return self.video_paths[0]

    @property
    def subtitle_path(self) -> Path | None:
        """兼容单字幕调用方：返回第一份已选择字幕。"""
        return next((path for path in self.subtitle_paths if path is not None), None)

    @property
    def is_merged(self) -> bool:
        return len(self.video_paths) > 1

    def validation_errors(self) -> list[str]:
        """返回任务进入 worker 前必须解决的问题。"""
        errors: list[str] = []
        if not self.video_paths:
            errors.append("未选择视频")
        if not any(path is not None for path in self.subtitle_paths):
            errors.append("未选择字幕")
        if (
            self.subtitle_mode == SubtitleMode.PER_SEGMENT
            and len(self.subtitle_paths) != len(self.video_paths)
        ):
            errors.append("分段字幕数量必须与视频片段数量一致")
        if not self.output_path.suffix:
            errors.append("未设置输出文件")

        return errors


def default_output_path_for_video(video_path: Path) -> Path:
    """生成单视频默认输出路径。"""
    return video_path.parent / f"{video_path.stem}-弹幕版.mp4"


def default_output_path_for_videos(video_paths: tuple[Path, ...]) -> Path:
    """为一个或多个视频片段生成默认输出路径。"""
    if not video_paths:
        raise ValueError("至少需要一个视频")
    if len(video_paths) == 1:
        return default_output_path_for_video(video_paths[0])
    first = video_paths[0]
    return first.parent / f"{first.stem}-合并弹幕版.mp4"


def natural_path_key(path: Path) -> tuple[object, ...]:
    """按人类直觉排序带数字的文件名，例如 part2 位于 part10 之前。"""
    parts = re.split(r"(\d+)", path.name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def is_supported_video(path: Path) -> bool:
    """判断文件是否是支持的视频格式。"""
    try:
        return path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTS
    except OSError as error:
        logger.warning("无法访问文件，已跳过: {} ({})", path, error)
        return False


def find_subtitle_candidates(video_path: Path) -> list[Path]:
    """返回视频同目录下所有字幕候选，同名 XML/LRC 排在最前。"""
    if not video_path.is_file():
        return []

    stem_key = video_path.stem.lower()
    candidates: list[Path] = []
    try:
        siblings = list(video_path.parent.iterdir())
    except OSError as error:
        logger.warning("无法读取字幕目录，已跳过: {} ({})", video_path.parent, error)
        return []

    for path in siblings:
        try:
            if path.is_file() and path.suffix.lower() in SUPPORTED_BATCH_SUBTITLE_EXTS:
                candidates.append(path)
        except OSError as error:
            logger.warning("无法访问字幕候选文件，已跳过: {} ({})", path, error)

    def candidate_key(path: Path) -> tuple[int, int, tuple[object, ...]]:
        exact_rank = 0 if path.stem.lower() == stem_key else 1
        extension_rank = SUPPORTED_BATCH_SUBTITLE_EXTS.index(path.suffix.lower())
        return exact_rank, extension_rank, natural_path_key(path)

    return sorted(candidates, key=candidate_key)


def find_matching_subtitle(video_path: Path) -> Path | None:
    """查找同名字幕；同时存在时优先 XML。"""
    stem_key = video_path.stem.lower()
    for path in find_subtitle_candidates(video_path):
        if path.stem.lower() == stem_key:
            return path
    return None


def suggest_subtitle(video_path: Path) -> Path | None:
    """为单视频建议字幕：同名优先，目录仅有一份字幕时使用该字幕。"""
    candidates = find_subtitle_candidates(video_path)
    if not candidates:
        return None
    if candidates[0].stem.lower() == video_path.stem.lower() or len(candidates) == 1:
        return candidates[0]
    return None


def create_job_from_videos(paths: Sequence[str | Path]) -> BatchJob:
    """把一次选择的视频整理为一个成品任务。"""
    video_map: dict[str, Path] = {}
    for path_value in paths:
        path = Path(path_value).expanduser().resolve()
        if not is_supported_video(path):
            raise ValueError(f"视频不可用或格式不受支持: {path}")
        video_map[str(path).lower()] = path

    videos = tuple(sorted(video_map.values(), key=natural_path_key))
    if not videos:
        raise ValueError("至少需要选择一个视频")
    matches = tuple(find_matching_subtitle(path) for path in videos)
    candidates = find_subtitle_candidates(videos[0])
    if len(videos) == 1:
        subtitle_paths = (suggest_subtitle(videos[0]),)
        mode = SubtitleMode.FULL
    elif matches and all(path is not None for path in matches):
        subtitle_paths = matches
        mode = SubtitleMode.PER_SEGMENT
    elif len(candidates) == 1:
        subtitle_paths = (candidates[0],)
        mode = SubtitleMode.FULL
    else:
        subtitle_paths = matches
        mode = SubtitleMode.PER_SEGMENT

    return BatchJob(
        video_paths=videos,
        subtitle_paths=subtitle_paths,
        output_path=default_output_path_for_videos(videos),
        subtitle_mode=mode,
    )
