"""配置加载器

负责从 YAML 文件加载配置。
"""

from __future__ import annotations

import typing
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any
import yaml
from loguru import logger

from .models import DanmakuConfig, DEFAULT_CONFIG
from ..errors import ConfigError


# =============================================================================
# 辅助函数
# =============================================================================

def _is_dataclass_type(tp: Any) -> bool:
    """检查类型是否为 dataclass"""
    if isinstance(tp, str):
        return False
    if typing.get_origin(tp) is not None:
        return False
    return is_dataclass(tp)


def _allows_none(tp: Any) -> bool:
    """判断类型注解是否显式允许 None。"""
    return type(None) in typing.get_args(tp)


# =============================================================================
# 配置搜索路径
# =============================================================================

def _config_search_paths(config_path: str | Path | None = None) -> list[Path]:
    """生成配置文件的搜索路径列表"""
    paths: list[Path] = []
    if config_path is not None:
        paths.append(Path(config_path))
    paths.append(Path("danmakustudio.yaml"))
    user_dir = Path.home() / "danmakustudio.yaml"
    paths.append(user_dir)
    return paths


# =============================================================================
# 配置转换
# =============================================================================

def _dict_to_config(data: dict[str, Any], config_cls: type[Any], path: str = "") -> Any:
    """递归将字典转换为 dataclass 实例"""
    if not isinstance(data, dict):
        location = path or "配置文件顶层"
        raise ConfigError(f"{location} 必须是键值映射")

    type_hints = typing.get_type_hints(config_cls)
    field_names = {f.name for f in fields(config_cls)}
    kwargs = {}
    for f in fields(config_cls):
        if f.name not in data:
            continue
        value = data[f.name]
        field_type = type_hints.get(f.name, f.type)
        field_path = f"{path}.{f.name}" if path else f.name
        if value is None:
            if _is_dataclass_type(field_type):
                # 空配置段沿用该段的默认配置，兼容现有配置文件。
                continue
            if _allows_none(field_type):
                kwargs[f.name] = None
                continue
            raise ConfigError(f"{field_path} 不能为 null")
        if _is_dataclass_type(field_type):
            if not isinstance(value, dict):
                raise ConfigError(f"{field_path} 必须是键值映射")
            kwargs[f.name] = _dict_to_config(
                value,
                typing.cast(type[Any], field_type),
                field_path,
            )
        else:
            kwargs[f.name] = value

    unknown_keys = set(data) - field_names
    if unknown_keys:
        location = path or "配置文件顶层"
        logger.warning(
            "{} 包含未知字段将被忽略: {}",
            location,
            ", ".join(sorted(unknown_keys)),
        )
    try:
        return config_cls(**kwargs)
    except (TypeError, ValueError) as e:
        location = path or "配置文件顶层"
        raise ConfigError(f"{location} 配置无效: {e}") from e


def _load_config_file(path: Path) -> DanmakuConfig:
    """读取单个 YAML 文件并转换为配置。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件解析失败: {path} - {e}") from e
    except OSError as e:
        raise ConfigError(f"配置文件读取失败: {path} - {e}") from e

    if data is None:
        return DEFAULT_CONFIG
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是键值映射: {path}")

    return _dict_to_config(data, DanmakuConfig)


def load_config(config_path: str | Path | None = None) -> DanmakuConfig:
    """加载配置文件。

    按优先级搜索配置文件：指定路径 > 当前目录 > 用户目录。
    指定路径不存在时报错；自动搜索未找到配置文件时返回默认配置。

    Args:
        config_path: 配置文件路径，为 None 时自动搜索

    Returns:
        DanmakuConfig 实例
    """
    if config_path is not None:
        path = Path(config_path).expanduser()
        if not path.exists():
            raise ConfigError(f"指定的配置文件不存在: {path}")
        if path.is_dir():
            raise ConfigError(f"指定的配置路径是目录: {path}")
        return _load_config_file(path)

    for path in _config_search_paths():
        if path.exists():
            if path.is_dir():
                raise ConfigError(f"配置路径是目录: {path}")
            return _load_config_file(path)

    return DEFAULT_CONFIG
