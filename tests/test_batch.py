"""单一成品任务的素材整理与字幕匹配测试。"""

from pathlib import Path

from danmakustudio.batch import (
    BatchJob,
    SubtitleMode,
    create_job_from_videos,
    find_matching_subtitle,
    suggest_subtitle,
)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_find_matching_subtitle_prefers_xml(tmp_path):
    video = _touch(tmp_path / "demo.mp4")
    xml = _touch(tmp_path / "demo.xml")
    _touch(tmp_path / "demo.lrc")

    assert find_matching_subtitle(video) == xml


def test_find_matching_subtitle_uses_lrc_without_xml(tmp_path):
    video = _touch(tmp_path / "demo.mp4")
    lrc = _touch(tmp_path / "demo.lrc")

    assert find_matching_subtitle(video) == lrc


def test_single_video_can_suggest_only_non_matching_subtitle(tmp_path):
    video = _touch(tmp_path / "recording.mp4")
    subtitle = _touch(tmp_path / "danmaku.xml")

    assert suggest_subtitle(video) == subtitle


def test_multiple_videos_with_one_subtitle_create_one_full_timeline_job(tmp_path):
    second = _touch(tmp_path / "part2.mp4")
    first = _touch(tmp_path / "part1.mp4")
    subtitle = _touch(tmp_path / "complete.xml")

    job = create_job_from_videos([second, first])

    assert job.video_paths == (first, second)
    assert job.subtitle_paths == (subtitle,)
    assert job.subtitle_mode == SubtitleMode.FULL
    assert job.output_path == tmp_path / "part1-合并弹幕版.mp4"


def test_multiple_videos_with_matching_subtitles_create_segment_timeline_job(tmp_path):
    first = _touch(tmp_path / "part1.mp4")
    second = _touch(tmp_path / "part2.mp4")
    first_subtitle = _touch(tmp_path / "part1.xml")
    second_subtitle = _touch(tmp_path / "part2.lrc")

    job = create_job_from_videos([first, second])

    assert job.video_paths == (first, second)
    assert job.subtitle_paths == (first_subtitle, second_subtitle)
    assert job.subtitle_mode == SubtitleMode.PER_SEGMENT


def test_multiple_videos_keep_missing_segment_subtitle_editable(tmp_path):
    first = _touch(tmp_path / "part1.mp4")
    second = _touch(tmp_path / "part2.mp4")
    first_subtitle = _touch(tmp_path / "part1.xml")
    _touch(tmp_path / "unrelated.lrc")

    job = create_job_from_videos([first, second])

    assert job.subtitle_paths == (first_subtitle, None)
    assert job.subtitle_mode == SubtitleMode.PER_SEGMENT


def test_create_job_allows_videos_from_different_folders(tmp_path):
    first = _touch(tmp_path / "one" / "part1.mp4")
    second = _touch(tmp_path / "two" / "part2.mp4")
    first_subtitle = _touch(tmp_path / "one" / "part1.xml")
    second_subtitle = _touch(tmp_path / "two" / "part2.xml")

    job = create_job_from_videos([first, second])

    assert job.video_paths == (first, second)
    assert job.subtitle_paths == (first_subtitle, second_subtitle)


def test_job_allows_subtitle_from_different_folder(tmp_path):
    video = _touch(tmp_path / "video.mp4")
    subtitle = _touch(tmp_path / "other" / "video.xml")
    job = BatchJob.single(video, subtitle)

    assert job.validation_errors() == []


def test_segment_job_requires_one_slot_per_video(tmp_path):
    videos = (_touch(tmp_path / "part1.mp4"), _touch(tmp_path / "part2.mp4"))
    subtitle = _touch(tmp_path / "part1.xml")
    job = BatchJob(
        video_paths=videos,
        subtitle_paths=(subtitle,),
        output_path=tmp_path / "merged.mp4",
        subtitle_mode=SubtitleMode.PER_SEGMENT,
    )

    assert "分段字幕数量必须与视频片段数量一致" in job.validation_errors()


def test_find_matching_subtitle_returns_none_when_directory_unreadable(
    tmp_path, monkeypatch
):
    video = _touch(tmp_path / "demo.mp4")

    def fake_iterdir(path: Path):
        if path == tmp_path:
            raise OSError("permission denied")
        raise AssertionError("unexpected path")

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    assert find_matching_subtitle(video) is None
