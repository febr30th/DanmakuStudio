"""字幕解析器

从抖音格式 XML 或 LRC 文件中解析弹幕事件。
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree  # type: ignore
from loguru import logger

from ..errors import InputError
from .event import DanmakuEvent

SUPPORTED_SUBTITLE_EXTS = frozenset({".xml", ".lrc"})

_LRC_TIMESTAMP_RE = re.compile(
    r"\[(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]"
)
_LRC_COLON_USER_RE = re.compile(
    r"^(?P<user>[^:：\t\r\n]{1,32})\s*[:：]\s*(?P<text>.+)$"
)
_LRC_TAB_USER_RE = re.compile(
    r"^(?P<user>[^\t\r\n]{1,32})\t+(?P<text>.+)$"
)
_LRC_WIDE_SPACE_USER_RE = re.compile(
    r"^(?P<user>\S.{0,31}?)\s{2,}(?P<text>\S.*)$"
)
_LRC_SINGLE_SPACE_USER_RE = re.compile(
    r"^(?P<user>\S{2,24})\s+(?P<text>\S.*)$"
)
_LRC_DISALLOWED_USER_CHARS = set("，。！？,.!?；;、()（）[]【】<>《》\"'")


def parse_xml(xml_path: str, min_gift_price: float = 1.0) -> list[DanmakuEvent]:
    """解析 XML 弹幕文件

    Args:
        xml_path: XML 文件路径
        min_gift_price: 最低礼物价格过滤（单位：元）

    Returns:
        按时间排序的弹幕事件列表

    Note:
        XML 中 gift 的 price 属性单位为厘（1元=1000厘），
        解析时自动转换为元。
    """
    events: list[DanmakuEvent] = []

    for _event, elem in etree.iterparse(
        xml_path, events=('end',), tag=('d', 'gift'),
        recover=True, encoding='utf-8',
    ):
        if elem.tag == 'd':
            p_attr = elem.get('p')
            if p_attr:
                try:
                    comma_idx = p_attr.find(',')
                    time_val = float(p_attr[:comma_idx])
                    user = elem.get('user') or elem.get('uid') or "匿名"
                    text = elem.text or ""
                    events.append(DanmakuEvent(time=time_val, user=user, text=text))
                except (ValueError, IndexError):
                    logger.debug(f"弹幕解析失败: p={p_attr}")
        elif elem.tag == 'gift':
            try:
                time_val = float(elem.get('ts', 0))
                user = elem.get('user') or "匿名"
                gift_name = elem.get('giftname') or ""
                gift_count = int(elem.get('giftcount', 1))
                price = float(elem.get('price', 0)) / 1000

                if price >= min_gift_price:
                    events.append(DanmakuEvent(
                        time=time_val, user=user, text=f"{gift_name}x{gift_count}",
                        is_gift=True, gift_name=gift_name, gift_count=gift_count,
                    ))
            except (ValueError, TypeError):
                logger.debug("礼物解析失败")
        
        elem.clear()

    events.sort(key=lambda e: e.time)
    return events


def _lrc_timestamp_to_seconds(match: re.Match[str]) -> float:
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = (match.group(4) or "0").ljust(3, "0")[:3]
    milliseconds = int(fraction)
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _has_ascii_alpha(text: str) -> bool:
    return any(("a" <= ch.lower() <= "z") for ch in text)


def _looks_like_lrc_username(user: str, *, allow_plain_cjk: bool) -> bool:
    """判断 LRC 行首片段是否像弹幕用户名。

    LRC 本身没有用户名标准，这里只做保守启发式判断，避免把普通歌词
    如 ``Hello world`` 拆成用户名和正文。
    """
    user = user.strip()
    if not user or len(user) > 32:
        return False
    if any(ch.isspace() for ch in user):
        return False
    if any(ch in _LRC_DISALLOWED_USER_CHARS for ch in user):
        return False

    has_cjk = _has_cjk(user)
    has_ascii = _has_ascii_alpha(user)
    has_digit = any(ch.isdigit() for ch in user)
    has_user_symbol = any(ch in "_-@." for ch in user)

    if has_digit or has_user_symbol:
        return True
    if has_cjk and has_ascii:
        return True
    if has_ascii and user.upper() == user and len(user) >= 2:
        return True
    if allow_plain_cjk and has_cjk and 2 <= len(user) <= 16:
        return True

    return False


def _split_lrc_user_text(text: str) -> tuple[str, str]:
    """从 LRC 正文中拆出可选用户名。

    支持常见弹幕导出写法：
    - ``用户名: 内容`` / ``用户名：内容``
    - ``用户名<TAB>内容``
    - ``用户名  内容``（两个或更多空格）
    - ``QQYYQQ 内容`` 这类明显用户名的单空格写法

    未识别时返回空用户名和原正文，保证普通 LRC 歌词仍按纯文本处理。
    """
    stripped = text.strip()
    if not stripped:
        return "", ""

    for pattern in (
        _LRC_COLON_USER_RE,
        _LRC_TAB_USER_RE,
        _LRC_WIDE_SPACE_USER_RE,
    ):
        match = pattern.match(stripped)
        if not match:
            continue

        user = match.group("user").strip()
        body = match.group("text").strip()
        if user and body:
            return user, body

    match = _LRC_SINGLE_SPACE_USER_RE.match(stripped)
    if match:
        user = match.group("user").strip()
        body = match.group("text").strip()
        if body and _looks_like_lrc_username(user, allow_plain_cjk=True):
            return user, body

    return "", stripped


def parse_lrc(lrc_path: str) -> list[DanmakuEvent]:
    """解析 LRC 字幕文件。

    支持一行多个时间戳，例如 ``[00:01.00][00:02.00]文本``。
    LRC 没有标准用户名字段；若正文使用常见弹幕导出格式，会尽量识别
    行首用户名，否则按普通字幕正文处理。
    """
    events: list[DanmakuEvent] = []

    try:
        with open(lrc_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                matches = list(_LRC_TIMESTAMP_RE.finditer(line))
                if not matches:
                    continue

                text = _LRC_TIMESTAMP_RE.sub("", line).strip()
                if not text:
                    continue
                user, text = _split_lrc_user_text(text)
                if not text:
                    continue

                for match in matches:
                    events.append(DanmakuEvent(
                        time=_lrc_timestamp_to_seconds(match),
                        user=user,
                        text=text,
                    ))
    except OSError as e:
        raise InputError(f"LRC 文件读取失败: {lrc_path} - {e}") from e

    events.sort(key=lambda e: e.time)
    return events


def parse_subtitle(path: str, min_gift_price: float = 1.0) -> list[DanmakuEvent]:
    """根据扩展名自动解析 XML 或 LRC 字幕。"""
    suffix = Path(path).suffix.lower()
    if suffix == ".xml":
        return parse_xml(path, min_gift_price=min_gift_price)
    if suffix == ".lrc":
        return parse_lrc(path)
    raise ValueError(f"不支持的弹幕格式: {suffix}")
