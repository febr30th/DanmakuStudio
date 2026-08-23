"""弹幕压制核心引擎

DanmakuBurner 是弹幕压制的编排器，负责组合各子模块完成完整的处理管线。
"""

from __future__ import annotations

import sys
from itertools import chain
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from loguru import logger
from tqdm import tqdm

from ..config.models import DanmakuConfig, DEFAULT_CONFIG, EncodeMode
from ..errors import EncodeError, DanmakuStudioError
from ..input.parser import parse_subtitle
from ..layout.engine import LayoutEngine, LayoutContext
from ..layout.params import LayoutParams, LayerParams
from ..render.renderer import DanmakuRenderer
from ..render.assets import AssetLoader
from ..encode.ffmpeg import FFmpegManager
from ..utils.validation import validate_video_input, validate_subtitle_input, validate_output_path


ProgressCallback = Callable[[int, int, float, float], None]


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def _stderr_is_tty() -> bool:
    isatty = getattr(sys.stderr, "isatty", None)
    return bool(isatty and isatty())


class DanmakuBurner:
    """弹幕压制引擎"""

    def __init__(
        self,
        video_in: str,
        xml_in: str,
        video_out: str | None = None,
        encode_mode: str = EncodeMode.AUTO,
        config: DanmakuConfig = DEFAULT_CONFIG,
        force: bool = False,
        progress_callback: ProgressCallback | None = None,
    ):
        """初始化弹幕压制引擎
        Args:
            video_in: 输入视频路径
            xml_in: 输入弹幕 XML/LRC 文件路径
            video_out: 输出视频路径
            encode_mode: 编码模式
            config: 弹幕配置
            force: 是否强制覆盖输出文件
            progress_callback: 进度回调，用于 GUI 更新当前任务进度
        """
        validate_video_input(video_in)
        validate_subtitle_input(xml_in)

        self.video_in = video_in
        self.xml_in = xml_in
        self.subtitle_in = xml_in
        self._config = config
        self._progress_callback = progress_callback

        if video_out:
            self.video_out = video_out
        else:
            video_path = Path(video_in)
            self.video_out = str(video_path.parent / f"{video_path.stem}-弹幕版.mp4")

        validate_output_path(self.video_out, force)

        self._asset_provider = AssetLoader(font_size=self._config.style.font_size)
        self._frame_encoder = FFmpegManager(
            video_in, self.video_out, encode_mode,
            self._config.encode, self._config.system,
        )

    def run(self) -> None:
        """执行完整的弹幕压制流程。

        按顺序执行 8 个步骤：
        1. 解析弹幕字幕
        2. 加载资源文件
        3. 获取视频元数据
        4. 计算布局参数
        5. 预创建弹幕对象
        6. 构建 FFmpeg 编码命令
        7. 启动 FFmpeg 编码器
        8. 压制渲染

        KeyboardInterrupt 会被捕获并输出警告，其他异常按策略处理。
        无论成功或失败，finally 块都会执行资源清理。

        Raises:
            DanmakuStudioError: 弹幕压制相关的已知错误
            RuntimeError: 不可恢复的致命错误
        """
        cfg = self._config
        style = cfg.style
        syscfg = cfg.system

        # Step 1
        events = parse_subtitle(self.subtitle_in, min_gift_price=cfg.animation.min_gift_price)
        subtitle_type = Path(self.subtitle_in).suffix.upper().lstrip(".")
        logger.info(f"[1/8] 解析 {subtitle_type}: {len(events)} 条事件")

        # Step 2
        self._asset_provider.load_assets(events)
        logger.info(
            f"[2/8] 加载资源: "
            f"Emoji {len(self._asset_provider.emoji_cache)}, "
            f"礼物 {len(self._asset_provider.gift_cache)}"
        )

        # Step 3
        v_info = self._frame_encoder.get_video_info()
        raw_w: int = int(v_info['w'])
        raw_h: int = int(v_info['h'])
        fps: float = float(v_info['fps'])
        total_frames: int = int(v_info['frames'])

        align = syscfg.video_alignment
        w = int(((raw_w + align - 1) // align) * align)
        h = int(((raw_h + align - 1) // align) * align)

        duration = total_frames / fps if fps > 0 else 0
        logger.info(
            f"[3/8] 视频信息: {raw_w}x{raw_h}, {fps:.2f} fps, "
            f"{total_frames} 帧, 时长 {_format_duration(duration)}"
        )
        if (w, h) != (raw_w, raw_h):
            logger.info(f"[3/8] 画面尺寸对齐: {raw_w}x{raw_h} -> {w}x{h}")

        # Step 4
        layout_params, layer_params = LayoutEngine.calculate_params(
            w, h, style, cfg.ratio, self._asset_provider.line_height,
        )
        logger.info("[4/8] 计算布局参数")

        # Step 5
        danmaku_pool = LayoutEngine.preload_danmaku_objects(
            events, layout_params, self._asset_provider, style,
        )
        logger.info(f"[5/8] 预创建弹幕对象: {len(danmaku_pool)} 个")

        # Step 6
        ffmpeg_cmd = self._frame_encoder.build_command(fps, w, h, layer_params)
        logger.info("[6/8] 构建编码命令")

        # Step 7
        run_failed = False
        try:
            self._frame_encoder.start(ffmpeg_cmd)
            logger.info("[7/8] 启动 FFmpeg: 已启动")
            # 刷新异步日志队列，避免与 tqdm 进度条输出交叠
            logger.complete()
            self._render_loop(
                fps, total_frames, danmaku_pool,
                layout_params, layer_params,
            )
        except KeyboardInterrupt:
            run_failed = True
            logger.warning("用户中断压制")
            raise
        except DanmakuStudioError:
            run_failed = True
            raise
        except Exception as e:
            run_failed = True
            raise RuntimeError(f"压制失败: {e}") from e
        finally:
            logger.debug("清理资源")
            try:
                self._frame_encoder.cleanup()
            except DanmakuStudioError:
                if run_failed:
                    logger.exception("FFmpeg 清理阶段也发生错误")
                else:
                    raise

    def _encode_frame(
        self,
        frame_encoder: FFmpegManager,
        renderer: DanmakuRenderer,
        pbar: tqdm,
        frame_idx: int,
        total_frames: int,
    ) -> None:
        """提交单帧编码，处理编码错误。

        Args:
            frame_encoder: 帧编码器
            renderer: 渲染器
            pbar: 进度条
            frame_idx: 当前帧索引
            total_frames: 总帧数

        Raises:
            EncodeError: 编码器错误且策略为中止
        """
        try:
            frame_encoder.submit_frame(renderer.get_frame_data())
            pbar.update(1)
        except (BrokenPipeError, OSError, RuntimeError) as e:
            raise EncodeError(f"编码器错误 [帧 {frame_idx}]: {e}") from e

    def _render_loop(
        self,
        fps: float,
        total_frames: int,
        danmaku_pool: list[Any],
        layout_params: LayoutParams,
        layer_params: LayerParams,
    ) -> None:
        """渲染主循环（单线程）
        Args:
            fps: 视频帧率
            total_frames: 总帧数
            danmaku_pool: 弹幕对象池
            layout_params: 布局参数
            layer_params: 层参数
        Raises:
            DanmakuStudioError: 弹幕压制过程中发生错误
        """
        frame_encoder = self._frame_encoder
        anim = self._config.animation

        active_text: list[Any] = []
        active_gift: list[Any] = []

        layout_ctx = LayoutContext(animation=anim)

        renderer = DanmakuRenderer(layer_params)

        total_danmaku = len(danmaku_pool)
        total_text_danmaku = sum(1 for d in danmaku_pool if not d.event.is_gift)
        total_gift_danmaku = total_danmaku - total_text_danmaku

        logger.info(
            f"[8/8] 渲染压制: "
            f"弹幕 {total_danmaku} (文本 {total_text_danmaku}+礼物 {total_gift_danmaku}), "
            f"{total_frames} 帧"
        )

        # 强制刷新异步日志队列，确保步骤日志在 tqdm 进度条之前输出
        logger.complete()

        show_progress_bar = _stderr_is_tty()
        pbar = tqdm(
            total=total_frames,
            desc="压制进度",
            unit="帧",
            disable=not show_progress_bar,
        )

        fade_out_zone = self._config.style.fade_out_zone
        total_text_spawned = 0
        total_gift_spawned = 0
        started_at = perf_counter()
        last_log_at = started_at
        last_callback_at = started_at
        progress_log_interval = 5.0
        progress_callback_interval = 0.5

        if self._progress_callback:
            self._progress_callback(0, total_frames, 0.0, 0.0)

        def report_progress(done_frames: int, force: bool = False) -> None:
            nonlocal last_log_at, last_callback_at

            now = perf_counter()
            elapsed = now - started_at
            percent = (done_frames / total_frames * 100.0) if total_frames else 100.0

            if self._progress_callback and (
                force or now - last_callback_at >= progress_callback_interval
            ):
                self._progress_callback(done_frames, total_frames, percent, elapsed)
                last_callback_at = now

            if show_progress_bar:
                return

            should_log = (
                force
                or done_frames == total_frames
                or now - last_log_at >= progress_log_interval
            )
            if not should_log:
                return

            speed = done_frames / elapsed if elapsed > 0 else 0.0
            remaining = (total_frames - done_frames) / speed if speed > 0 else 0.0
            logger.info(
                f"进度: {percent:5.1f}% ({done_frames}/{total_frames} 帧), "
                f"速度 {speed:.1f} 帧/s, "
                f"已用 {_format_duration(elapsed)}, 剩余 {_format_duration(remaining)}"
            )
            last_log_at = now

        try:
            for frame_idx in range(total_frames):
                current_time = frame_idx / fps

                # 弹幕逻辑
                text_has_new, gift_has_new, text_emitted, gift_emitted = (
                    LayoutEngine.spawn_new_danmakus(
                        layout_ctx, current_time, danmaku_pool, active_text, active_gift,
                        self._asset_provider,
                        max_text_rows=self._config.ratio.max_text_rows,
                        max_gift_rows=self._config.ratio.max_gift_rows,
                    )
                )
                total_text_spawned += text_emitted
                total_gift_spawned += gift_emitted

                LayoutEngine.update_danmaku_layer(
                    active_text, text_has_new,
                    layout_params.bottom, layout_params.text_top,
                    layout_params.gap, anim.text_damping_factor,
                )
                LayoutEngine.update_danmaku_layer(
                    active_gift, gift_has_new,
                    layout_params.text_top, layout_params.gift_top,
                    layout_params.gap, anim.gift_damping_factor,
                    current_time, anim.gift_dwell_time,
                )

                # 渲染当前帧
                renderer.render_frame(
                    chain(active_text, active_gift),
                    layout_params,
                    fade_out_zone,
                )

                # 编码
                self._encode_frame(
                    frame_encoder, renderer, pbar, frame_idx, total_frames,
                )
                report_progress(frame_idx + 1)
        finally:
            renderer.end()
            pbar.close()

        elapsed = perf_counter() - started_at
        report_progress(total_frames, force=True)

        # 仅在正常完成时输出统计（异常时不会执行到这里）
        logger.info(
            f"完成: {total_frames} 帧, "
            f"弹幕 {total_text_spawned}/{total_text_danmaku} + 礼物 {total_gift_spawned}/{total_gift_danmaku}, "
            f"用时 {_format_duration(elapsed)}"
        )
        if total_text_spawned < total_text_danmaku:
            logger.warning(
                f"文本弹幕未完全发射: {total_text_spawned}/{total_text_danmaku}"
            )
        if total_gift_spawned < total_gift_danmaku:
            logger.warning(
                f"礼物弹幕未完全发射: {total_gift_spawned}/{total_gift_danmaku}"
            )
