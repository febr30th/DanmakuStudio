"""FFmpeg 命令构建与进程收尾测试。"""

from __future__ import annotations

from collections import deque
import io
import json
import subprocess
from pathlib import Path

import pytest

from danmakustudio.config.models import EncodeMode, EncodeParams, SystemParams
from danmakustudio.encode import ffmpeg as ffmpeg_module
from danmakustudio.encode.ffmpeg import FFmpegManager
from danmakustudio.errors import EncodeError
from danmakustudio.layout.params import LayerParams


def _make_manager(active_pipeline: str = EncodeMode.CPU) -> FFmpegManager:
    manager = FFmpegManager.__new__(FFmpegManager)
    manager.video_in = "input.webm"
    manager.video_out = "output.mp4"
    manager.force = False
    manager._temp_video_out = ".output.danmakustudio-test.mp4"
    manager.encode_mode = active_pipeline
    manager.encode_params = EncodeParams()
    manager.system_params = SystemParams()
    manager.active_pipeline = active_pipeline
    manager.process = None
    manager.stderr_thread = None
    manager.stderr_tail = deque(maxlen=20)
    return manager


def _layer_params() -> LayerParams:
    return LayerParams(layer_x=10, layer_y=20, layer_w=640, layer_h=180)


def test_temporary_output_stays_beside_final_output(tmp_path):
    final_output = tmp_path / "nested.name.mp4"

    temp_output = FFmpegManager._make_temporary_output_path(str(final_output))

    assert temp_output != str(final_output)
    assert Path(temp_output).parent == tmp_path
    assert Path(temp_output).suffix == final_output.suffix


def test_gpu_command_uses_generic_decode_and_nvenc_encode():
    manager = _make_manager(EncodeMode.GPU)
    cmd = manager.build_command(30.0, 1920, 1080, _layer_params())
    joined = " ".join(cmd)

    assert "h264_nvenc" in cmd
    assert "h264_cuvid" not in cmd
    assert "-hwaccel" not in cmd
    assert "scale_cuda" not in joined
    assert "format=yuv420p[out]" in joined


def test_qsv_command_keeps_software_overlay_before_qsv_encode():
    manager = _make_manager(EncodeMode.QSV)
    cmd = manager.build_command(30.0, 1920, 1080, _layer_params())
    joined = " ".join(cmd)

    assert "h264_qsv" in cmd
    assert "scale_qsv" not in joined
    assert "-hwaccel" not in cmd
    assert "format=nv12[out]" in joined


@pytest.mark.parametrize("pipeline", [EncodeMode.GPU, EncodeMode.QSV, EncodeMode.CPU])
def test_command_writes_to_temporary_output(pipeline):
    manager = _make_manager(pipeline)

    cmd = manager.build_command(30.0, 1920, 1080, _layer_params())

    assert cmd[-1] == manager._temp_video_out
    assert cmd[-1] != manager.video_out


@pytest.mark.parametrize("pipeline", [EncodeMode.GPU, EncodeMode.QSV, EncodeMode.CPU])
def test_command_transcodes_audio_to_container_compatible_aac(pipeline):
    manager = _make_manager(pipeline)

    cmd = manager.build_command(30.0, 1920, 1080, _layer_params())

    audio_codec_index = cmd.index("-c:a")
    audio_bitrate_index = cmd.index("-b:a")
    assert cmd[audio_codec_index + 1] == "aac"
    assert cmd[audio_bitrate_index + 1] == "192k"
    assert "copy" not in cmd


def test_get_video_info_handles_na_nb_frames(monkeypatch):
    manager = _make_manager()
    run_kwargs = {}
    ffprobe_data = {
        "streams": [{
            "width": 1919,
            "height": 1079,
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "60000/1001",
            "nb_frames": "N/A",
            "duration": "10.02",
        }],
        "format": {},
    }

    def fake_run(*_args, **kwargs):
        run_kwargs.update(kwargs)
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(ffprobe_data),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    info = manager.get_video_info()

    assert info["w"] == 1919
    assert info["h"] == 1079
    assert info["fps"] == pytest.approx(30000 / 1001)
    assert info["frames"] == 301
    assert run_kwargs["creationflags"] == ffmpeg_module._CREATE_NO_WINDOW
    assert run_kwargs["timeout"] == manager.system_params.ffmpeg_timeout


def test_get_video_info_reports_configured_timeout(monkeypatch):
    manager = _make_manager()
    manager.system_params = SystemParams(ffmpeg_timeout=3)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(EncodeError, match="读取视频信息超时（3 秒）"):
        manager.get_video_info()


@pytest.mark.parametrize(
    ("method_name", "encoder_name"),
    [
        ("_check_nvenc_available", "h264_nvenc"),
        ("_check_qsv_available", "h264_qsv"),
    ],
)
def test_encoder_detection_uses_configured_timeout(
    monkeypatch,
    method_name,
    encoder_name,
):
    manager = _make_manager()
    manager.system_params = SystemParams(ffmpeg_timeout=4)
    timeouts = []

    def fake_run(args, **kwargs):
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=encoder_name,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert getattr(manager, method_name)() is True
    assert timeouts == [4, 4]


def test_start_hides_ffmpeg_console(monkeypatch):
    manager = _make_manager()
    popen_kwargs = {}

    class FakeProcess:
        stdin = io.BytesIO()
        stderr = io.BytesIO()

    def fake_popen(*_args, **kwargs):
        popen_kwargs.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    manager.start(["ffmpeg", "-version"])
    if manager.stderr_thread is not None:
        manager.stderr_thread.join(timeout=1)

    assert popen_kwargs["creationflags"] == ffmpeg_module._CREATE_NO_WINDOW


class _FakeProcess:
    def __init__(self, return_code: int):
        self.stdin = io.BytesIO()
        self.stderr = io.BytesIO()
        self.return_code = return_code

    def wait(self, timeout=None):
        return self.return_code

    def kill(self):
        raise AssertionError("kill should not be called")


def _set_output_paths(
    manager: FFmpegManager,
    tmp_path,
    *,
    force: bool = False,
) -> None:
    manager.video_out = str(tmp_path / "output.mp4")
    manager._temp_video_out = str(
        tmp_path / ".output.danmakustudio-test.mp4"
    )
    manager.force = force


def test_cleanup_publishes_complete_output(tmp_path):
    manager = _make_manager()
    _set_output_paths(manager, tmp_path)
    temp_output = tmp_path / ".output.danmakustudio-test.mp4"
    final_output = tmp_path / "output.mp4"
    temp_output.write_bytes(b"complete video")
    manager.process = _FakeProcess(0)

    manager.cleanup()

    assert final_output.read_bytes() == b"complete video"
    assert not temp_output.exists()


def test_cleanup_raises_when_ffmpeg_returns_nonzero(tmp_path):
    manager = _make_manager()
    _set_output_paths(manager, tmp_path, force=True)
    manager.stderr_tail.append("muxing failed")
    temp_output = tmp_path / ".output.danmakustudio-test.mp4"
    final_output = tmp_path / "output.mp4"
    temp_output.write_bytes(b"partial video")
    final_output.write_bytes(b"original video")
    manager.process = _FakeProcess(1)

    with pytest.raises(EncodeError, match="退出码 1"):
        manager.cleanup()

    assert manager.process is None
    assert final_output.read_bytes() == b"original video"
    assert not temp_output.exists()


def test_cleanup_does_not_publish_interrupted_output(tmp_path):
    manager = _make_manager()
    _set_output_paths(manager, tmp_path)
    temp_output = tmp_path / ".output.danmakustudio-test.mp4"
    final_output = tmp_path / "output.mp4"
    temp_output.write_bytes(b"partial video")
    manager.process = _FakeProcess(0)

    manager.cleanup(publish_output=False)

    assert not final_output.exists()
    assert not temp_output.exists()


def test_cleanup_without_started_process_discards_temp_output(tmp_path):
    manager = _make_manager()
    _set_output_paths(manager, tmp_path)
    temp_output = tmp_path / ".output.danmakustudio-test.mp4"
    temp_output.write_bytes(b"startup remnant")

    manager.cleanup(publish_output=False)

    assert not temp_output.exists()


def test_cleanup_does_not_overwrite_output_created_during_encode(tmp_path):
    manager = _make_manager()
    _set_output_paths(manager, tmp_path)
    temp_output = tmp_path / ".output.danmakustudio-test.mp4"
    final_output = tmp_path / "output.mp4"
    temp_output.write_bytes(b"complete video")
    final_output.write_bytes(b"other process output")
    manager.process = _FakeProcess(0)

    with pytest.raises(EncodeError, match="编码期间输出文件已被创建"):
        manager.cleanup()

    assert final_output.read_bytes() == b"other process output"
    assert not temp_output.exists()


def test_cleanup_atomically_replaces_existing_output_when_forced(tmp_path):
    manager = _make_manager()
    _set_output_paths(manager, tmp_path, force=True)
    temp_output = tmp_path / ".output.danmakustudio-test.mp4"
    final_output = tmp_path / "output.mp4"
    temp_output.write_bytes(b"complete video")
    final_output.write_bytes(b"original video")
    manager.process = _FakeProcess(0)

    manager.cleanup()

    assert final_output.read_bytes() == b"complete video"
    assert not temp_output.exists()
