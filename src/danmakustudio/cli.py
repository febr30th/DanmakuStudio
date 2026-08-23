"""命令行入口模块

用法: danmakustudio
     danmakustudio video.mp4 danmaku.xml
     danmakustudio video.mp4 lyrics.lrc
     danmakustudio source/5.flv source/5.xml --encode gpu --config ./danmakustudio.yaml -f
"""

from __future__ import annotations

import os
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.qpa.fonts=false;qt.text.font.db=false",
)

import argparse

from loguru import logger
from PySide6.QtWidgets import QApplication

from .core.burner import DanmakuBurner
from .config.models import EncodeMode
from .config.loader import load_config
from .errors import DanmakuStudioError, handle_error
from .logger_config import configure_logger
from .utils.helpers import ensure_qt_app


def main() -> None:
    """主入口函数"""
    parser = argparse.ArgumentParser(
        prog="danmakustudio",
        description="抖音直播弹幕压制工具",
    )
    parser.add_argument("video", nargs="?", help="视频文件路径")
    parser.add_argument("subtitle", nargs="?", help="弹幕 XML/LRC 文件路径")
    parser.add_argument("-o", "--output", default=None, help="输出视频路径")
    parser.add_argument(
        "--encode",
        choices=[EncodeMode.AUTO, EncodeMode.GPU, EncodeMode.QSV, EncodeMode.CPU],
        default=EncodeMode.AUTO,
        help="编码模式",
    )
    parser.add_argument("-c", "--config", default=None, help="配置文件路径")
    parser.add_argument(
        "-f", "--force", action="store_true", default=False,
        help="强制覆盖已存在的输出文件",
    )
    parser.add_argument(
        "--gui", action="store_true", default=False,
        help="启动图形界面",
    )
    args = parser.parse_args()

    if args.gui or (args.video is None and args.subtitle is None):
        from .gui import main as gui_main

        gui_main()
        return

    if args.video is None or args.subtitle is None:
        parser.error("请同时提供视频文件和 XML/LRC 字幕文件，或直接运行 danmakustudio 打开图形界面")

    configure_logger()
    ensure_qt_app()
    # 捕获创建Burner时的异常，避免程序崩溃
    try:
        config = load_config(args.config)
        burner = DanmakuBurner(
            video_in=args.video, xml_in=args.subtitle,
            video_out=args.output, encode_mode=args.encode,
            config=config, force=args.force,
        )
    except DanmakuStudioError as e:
        logger.error(f"[{e.category.value}] {e}")
        raise SystemExit(1)
    except Exception as e:
        handle_error(e, component="cli", operation="create_burner")
        raise SystemExit(1)
    logger.info(f"开始处理: {args.video}")
    # 捕获处理Burner时的异常，避免程序崩溃
    try:
        burner.run()
    except DanmakuStudioError as e:
        logger.error(f"压制失败 [{e.category.value}]: {e}")
        raise SystemExit(1)
    except Exception as e:
        handle_error(e, component="cli", operation="run")
        raise SystemExit(1)
    finally:
        app = QApplication.instance()
        if app is not None:
            app.quit()
            app.deleteLater()


if __name__ == "__main__":
    main()
