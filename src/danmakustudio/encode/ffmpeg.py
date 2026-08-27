"""FFmpeg 编码管理器

负责构建 FFmpeg 命令行、启动进程、写入帧数据、清理资源。
"""

from __future__ import annotations

from collections import deque
import json
import math
import os
import subprocess
import threading
from pathlib import Path
from typing import Deque
from uuid import uuid4

from loguru import logger

from ..config.models import EncodeMode, EncodeParams, SystemParams, DEFAULT_CONFIG
from ..errors import EncodeError
from ..layout.params import LayerParams


# Windows 的 GUI 进程没有可继承的控制台。显式禁止 FFmpeg/ffprobe
# 创建新控制台窗口；其他平台使用 0，保持 subprocess 的默认行为。
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_AUDIO_ENCODE_ARGS = ("-c:a", "aac", "-b:a", "192k")


class FFmpegManager:
    """FFmpeg 进程管理器"""

    def __init__(
        self,
        video_in: str,
        video_out: str,
        encode_mode: str = EncodeMode.AUTO,
        encode_params: EncodeParams = DEFAULT_CONFIG.encode,
        system_params: SystemParams = DEFAULT_CONFIG.system,
        force: bool = False,
    ):
        self.video_in = video_in
        self.video_out = video_out
        self.force = force
        self._temp_video_out = self._make_temporary_output_path(video_out)
        self.encode_mode = encode_mode
        self.encode_params = encode_params
        self.system_params = system_params
        self.active_pipeline: str = EncodeMode.CPU
        self.process: subprocess.Popen | None = None
        self.stderr_thread: threading.Thread | None = None
        self.stderr_tail: Deque[str] = deque(maxlen=20)

        self._resolve_encode_mode()

    @staticmethod
    def _make_temporary_output_path(video_out: str) -> str:
        """在最终输出目录中生成保留原扩展名的唯一临时路径。"""
        output_path = Path(video_out)
        temp_name = (
            f".{output_path.stem}.danmakustudio-{uuid4().hex}"
            f"{output_path.suffix}"
        )
        return str(output_path.with_name(temp_name))

    def _resolve_encode_mode(self) -> None:
        """解析编码模式。"""
        if self.encode_mode == EncodeMode.CPU:
            self.active_pipeline = EncodeMode.CPU
            logger.info("编码模式: CPU (libx264)")
            return

        if self.encode_mode == EncodeMode.GPU:
            if not self._check_nvenc_available():
                raise RuntimeError("未检测到 NVENC 编码器")
            self.active_pipeline = EncodeMode.GPU
            logger.info("编码模式: GPU (NVENC)")
            return

        if self.encode_mode == EncodeMode.QSV:
            if not self._check_qsv_available():
                raise RuntimeError("未检测到 QSV 编码器")
            self.active_pipeline = EncodeMode.QSV
            logger.info("编码模式: QSV")
            return

        if self._check_nvenc_available():
            self.active_pipeline = EncodeMode.GPU
            logger.info("编码模式: GPU (NVENC) — 自动检测")
            return

        if self._check_qsv_available():
            self.active_pipeline = EncodeMode.QSV
            logger.info("编码模式: QSV — 自动回退")
            return

        self.active_pipeline = EncodeMode.CPU
        logger.info("编码模式: CPU (libx264) — 自动回退")

    def _check_nvenc_available(self) -> bool:
        """检查 NVENC 是否可用"""
        timeout = self.system_params.ffmpeg_timeout
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            if "h264_nvenc" not in result.stdout:
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner",
                    "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
                    "-c:v", "h264_nvenc", "-f", "null", "-",
                ],
                capture_output=True, text=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _check_qsv_available(self) -> bool:
        """检查 QSV 是否可用"""
        timeout = self.system_params.ffmpeg_timeout
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            if "h264_qsv" not in result.stdout:
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner",
                    "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
                    "-c:v", "h264_qsv", "-f", "null", "-",
                ],
                capture_output=True, text=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _parse_fraction(value: str | None) -> float:
        """解析 ffprobe 分数字段。"""
        if not value or value in {"0/0", "N/A"}:
            return 0.0
        try:
            if "/" not in value:
                return float(value)
            num, den = map(int, value.split("/", 1))
        except (TypeError, ValueError):
            return 0.0
        return num / den if den else 0.0

    @staticmethod
    def _parse_positive_int(value: object) -> int:
        """解析 ffprobe 可能返回的 nb_frames。"""
        if value in (None, "", "N/A"):
            return 0
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, parsed)

    @staticmethod
    def _parse_duration(*values: object) -> float:
        for value in values:
            if value in (None, "", "N/A"):
                continue
            try:
                duration = float(value)
            except (TypeError, ValueError):
                continue
            if duration > 0:
                return duration
        return 0.0

    def get_video_info(self) -> dict[str, int | float]:
        """获取视频元数据"""
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,duration:format=duration",
            "-of", "json", self.video_in,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.system_params.ffmpeg_timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            data = json.loads(result.stdout)
            info = data["streams"][0]
        except subprocess.TimeoutExpired as e:
            raise EncodeError(
                f"读取视频信息超时（{self.system_params.ffmpeg_timeout} 秒）"
            ) from e
        except FileNotFoundError as e:
            raise EncodeError("未找到 ffprobe，请确认 FFmpeg 已安装并加入 Path") from e
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, IndexError) as e:
            raise EncodeError(f"读取视频信息失败: {e}") from e

        fps = self._parse_fraction(info.get("avg_frame_rate"))
        if fps <= 0:
            fps = self._parse_fraction(info.get("r_frame_rate"))
        if fps <= 0:
            raise EncodeError("无法读取有效视频帧率")

        frames = self._parse_positive_int(info.get("nb_frames"))
        if frames == 0:
            duration = self._parse_duration(
                info.get("duration"),
                data.get("format", {}).get("duration"),
            )
            if duration <= 0:
                raise EncodeError("无法读取视频帧数或时长")
            frames = max(1, math.ceil(duration * fps))

        try:
            width = int(info["width"])
            height = int(info["height"])
        except (KeyError, TypeError, ValueError) as e:
            raise EncodeError(f"无法读取有效视频尺寸: {e}") from e

        return {"w": width, "h": height, "fps": fps, "frames": frames}

    def build_command(self, fps: float, w: int, h: int, layer_params: LayerParams) -> list[str]:
        """构建 FFmpeg 命令"""
        if self.active_pipeline == EncodeMode.GPU:
            return self._build_gpu_command(fps, w, h, layer_params)
        if self.active_pipeline == EncodeMode.QSV:
            return self._build_qsv_command(fps, w, h, layer_params)
        return self._build_cpu_command(fps, w, h, layer_params)

    def _build_gpu_command(self, fps: float, w: int, h: int, lp: LayerParams) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-i", self.video_in,
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{lp.layer_w}x{lp.layer_h}",
            "-r", str(fps),
            "-i", "pipe:0",
            "-filter_complex",
            (
                f"[0:v]scale={w}:{h}:flags=lanczos,format=yuv420p[bg];"
                f"[1:v]format=yuva420p[fg];"
                f"[bg][fg]overlay=x={lp.layer_x}:y={lp.layer_y},format=yuv420p[out]"
            ),
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "h264_nvenc",
            "-preset", self.encode_params.gpu_preset,
            "-tune", "hq",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-rc:v", "constqp",
            "-qp", str(self.encode_params.gpu_cq),
            *_AUDIO_ENCODE_ARGS,
            self._temp_video_out,
        ]

    def _build_qsv_command(self, fps: float, w: int, h: int, lp: LayerParams) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-i", self.video_in,
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{lp.layer_w}x{lp.layer_h}",
            "-r", str(fps),
            "-i", "pipe:0",
            "-filter_complex",
            (
                f"[0:v]scale={w}:{h}:flags=lanczos,format=yuv420p[bg];"
                f"[1:v]format=yuva420p[fg];"
                f"[bg][fg]overlay=x={lp.layer_x}:y={lp.layer_y},format=nv12[out]"
            ),
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "h264_qsv",
            "-preset", self.encode_params.qsv_preset,
            "-profile:v", "high",
            "-pix_fmt", "nv12",
            "-global_quality", str(self.encode_params.qsv_quality),
            *_AUDIO_ENCODE_ARGS,
            self._temp_video_out,
        ]

    def _build_cpu_command(self, fps: float, w: int, h: int, lp: LayerParams) -> list[str]:
        cpu_count = os.cpu_count() or 4
        encode_threads = max(1, cpu_count - self.encode_params.cpu_min_reserve_threads)

        return [
            "ffmpeg", "-y",
            "-i", self.video_in,
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{lp.layer_w}x{lp.layer_h}",
            "-r", str(fps),
            "-i", "pipe:0",
            "-filter_complex",
            (
                f"[0:v]scale={w}:{h}:flags=lanczos[bg];"
                f"[1:v]format=yuva420p[fg];"
                f"[bg][fg]overlay=x={lp.layer_x}:y={lp.layer_y},format=yuv420p[out]"
            ),
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-preset", self.encode_params.cpu_preset,
            "-crf", str(self.encode_params.cpu_crf),
            "-threads", str(encode_threads),
            *_AUDIO_ENCODE_ARGS,
            self._temp_video_out,
        ]

    def start(self, ffmpeg_cmd: list[str]) -> None:
        """启动 FFmpeg 进程"""
        logger.debug("FFmpeg 命令: {}", subprocess.list2cmdline(ffmpeg_cmd))
        self.process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=self.system_params.pipe_buffer_size,
            creationflags=_CREATE_NO_WINDOW,
        )

        def _read_stderr():
            assert self.process is not None
            assert self.process.stderr is not None
            for line in self.process.stderr:
                line_str = line.decode("utf-8", errors="replace").rstrip("\n\r")
                if line_str:
                    self.stderr_tail.append(line_str)
                    logger.debug(line_str)

        self.stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        self.stderr_thread.start()
        logger.debug("FFmpeg 进程已启动")

    def _health_check(self) -> bool:
        """检查 FFmpeg 进程是否存活"""
        if self.process is None:
            return False
        if self.process.poll() is not None:
            logger.error(f"FFmpeg 异常退出 (code={self.process.returncode})")
            self._log_stderr_tail()
            return False
        return True

    def _log_stderr_tail(self) -> None:
        """输出最近几行 FFmpeg stderr，帮助定位失败原因。"""
        if not self.stderr_tail:
            return

        tail = "\n".join(self.stderr_tail)
        logger.error(f"FFmpeg 最近输出:\n{tail}")

    def submit_frame(self, data: memoryview) -> None:
        """提交一帧数据（同步写入 FFmpeg stdin）。

        Args:
            data: 帧像素数据的 memoryview 视图

        Raises:
            RuntimeError: FFmpeg 进程已死亡
            BrokenPipeError: FFmpeg 管道断开
        """
        if not self._health_check():
            raise RuntimeError("FFmpeg 进程已死亡")

        if self.process is None or self.process.stdin is None:
            raise RuntimeError("FFmpeg 未启动")

        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise BrokenPipeError(f"FFmpeg 管道断开: {e}") from e

    def _discard_temporary_output(self) -> None:
        """删除未发布的临时输出，不用清理错误掩盖原始任务异常。"""
        temp_path = Path(self._temp_video_out)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("无法删除临时输出: {} ({})", temp_path, e)

    def _publish_output(self) -> None:
        """把完整临时文件原子发布到最终输出路径。"""
        temp_path = Path(self._temp_video_out)
        output_path = Path(self.video_out)

        try:
            has_complete_file = temp_path.is_file() and temp_path.stat().st_size > 0
        except OSError as e:
            raise EncodeError(f"检查 FFmpeg 临时输出失败: {temp_path} - {e}") from e
        if not has_complete_file:
            raise EncodeError(f"FFmpeg 未生成输出文件: {temp_path}")
        if output_path.exists() and not self.force:
            raise EncodeError(f"编码期间输出文件已被创建，未覆盖: {output_path}")

        try:
            os.replace(temp_path, output_path)
        except OSError as e:
            raise EncodeError(f"发布输出文件失败: {output_path} - {e}") from e

    def cleanup(self, *, publish_output: bool = True) -> None:
        """清理资源。

        按顺序完成：
        1. 关闭 stdin 管道，通知 FFmpeg 输入结束
        2. 等待 FFmpeg 进程退出
        3. 等待 stderr 线程结束并关闭管道
        4. 成功时原子发布输出，否则删除临时文件
        """
        proc = self.process
        if proc is None:
            self._discard_temporary_output()
            return

        # 第一步：关闭 stdin，通知 FFmpeg 输入结束
        if proc.stdin:
            try:
                proc.stdin.close()
            except (OSError, BrokenPipeError):
                pass

        # 第二步：等待 FFmpeg 进程退出
        logger.debug("等待 FFmpeg 完成编码...")
        cleanup_error: EncodeError | None = None
        return_code: int | None = None
        try:
            return_code = proc.wait(timeout=300.0)
            if return_code != 0:
                logger.error(f"压制失败 (code={return_code})")
                self._log_stderr_tail()
                cleanup_error = EncodeError(f"FFmpeg 编码失败，退出码 {return_code}")
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg 超时，强制终止")
            proc.kill()
            proc.wait()
            self._log_stderr_tail()
            cleanup_error = EncodeError("FFmpeg 编码超时，已强制终止")
        finally:
            # 第三步：等待 stderr 线程结束，确保日志不丢失
            if self.stderr_thread and self.stderr_thread.is_alive():
                self.stderr_thread.join(timeout=self.system_params.stderr_thread_timeout)

            # 第四步：关闭 stderr 管道，释放资源
            if proc.stderr:
                try:
                    proc.stderr.close()
                except (OSError, BrokenPipeError):
                    pass
            self.process = None

        if cleanup_error is None and return_code == 0 and publish_output:
            try:
                self._publish_output()
            except EncodeError as e:
                cleanup_error = e
            else:
                logger.success(f"压制完成: {self.video_out}")

        if cleanup_error is not None or not publish_output:
            self._discard_temporary_output()

        if cleanup_error is not None:
            raise cleanup_error
