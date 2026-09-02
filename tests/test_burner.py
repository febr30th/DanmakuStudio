"""多片段压制编排测试。"""

import threading

import pytest

from danmakustudio.batch import SubtitleMode
from danmakustudio.config import DEFAULT_CONFIG
from danmakustudio.core.burner import DanmakuBurner
from danmakustudio.errors import TaskCancelled


def test_segment_subtitles_are_shifted_to_combined_timeline(tmp_path):
    first = tmp_path / "part1.lrc"
    second = tmp_path / "part2.lrc"
    first.write_text("[00:01.00]第一段", encoding="utf-8")
    second.write_text("[00:02.00]第二段", encoding="utf-8")

    burner = DanmakuBurner.__new__(DanmakuBurner)
    burner._config = DEFAULT_CONFIG
    burner.subtitle_mode = SubtitleMode.PER_SEGMENT
    burner.subtitle_inputs = (str(first), str(second))

    events = burner._parse_subtitle_events((10.0, 20.0))

    assert [(event.time, event.text) for event in events] == [
        (1.0, "第一段"),
        (12.0, "第二段"),
    ]


def test_full_subtitle_keeps_original_timeline(tmp_path):
    subtitle = tmp_path / "complete.lrc"
    subtitle.write_text("[12:34.00]完整字幕", encoding="utf-8")

    burner = DanmakuBurner.__new__(DanmakuBurner)
    burner._config = DEFAULT_CONFIG
    burner.subtitle_mode = SubtitleMode.FULL
    burner.subtitle_inputs = (str(subtitle),)

    events = burner._parse_subtitle_events((100.0, 200.0))

    assert len(events) == 1
    assert events[0].time == 754.0


def test_full_timeline_combines_multiple_subtitle_files_without_offset(tmp_path):
    first = tmp_path / "one.lrc"
    second = tmp_path / "two.lrc"
    first.write_text("[00:03.00]第一份", encoding="utf-8")
    second.write_text("[00:01.00]第二份", encoding="utf-8")
    burner = DanmakuBurner.__new__(DanmakuBurner)
    burner._config = DEFAULT_CONFIG
    burner.subtitle_mode = SubtitleMode.FULL
    burner.subtitle_inputs = (str(first), str(second))

    events = burner._parse_subtitle_events((10.0,))

    assert [(event.time, event.text) for event in events] == [
        (1.0, "第二份"),
        (3.0, "第一份"),
    ]


def test_cancel_check_raises_task_cancelled():
    burner = DanmakuBurner.__new__(DanmakuBurner)
    burner._cancel_event = threading.Event()
    burner._cancel_event.set()

    with pytest.raises(TaskCancelled):
        burner._check_cancelled()
