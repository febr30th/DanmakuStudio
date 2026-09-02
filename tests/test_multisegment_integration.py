"""使用本机 FFmpeg 验证兼容视频片段的真实合并编码。"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from danmakustudio.config.models import EncodeMode
from danmakustudio.encode.ffmpeg import FFmpegManager
from danmakustudio.layout.params import LayerParams


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="本机未安装 FFmpeg/ffprobe",
)
def test_compatible_segments_can_be_encoded_as_one_output(tmp_path):
    segments = []
    for index, color in enumerate(("red", "blue"), start=1):
        segment = tmp_path / f"part{index}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=64x64:r=10:d=0.4",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-shortest", str(segment),
            ],
            check=True,
            capture_output=True,
        )
        segments.append(str(segment))

    output = tmp_path / "merged.mp4"
    manager = FFmpegManager(
        segments,
        str(output),
        encode_mode=EncodeMode.CPU,
    )
    info = manager.get_video_info()
    layer = LayerParams(layer_x=0, layer_y=0, layer_w=64, layer_h=64)
    command = manager.build_command(
        float(info["fps"]),
        int(info["w"]),
        int(info["h"]),
        layer,
    )

    manager.start(command)
    transparent_frame = memoryview(bytes(64 * 64 * 4))
    for _ in range(int(info["frames"])):
        manager.submit_frame(transparent_frame)
    manager.cleanup()

    assert output.is_file()
    assert output.stat().st_size > 0
    assert not list(tmp_path.glob("*.concat.txt"))
