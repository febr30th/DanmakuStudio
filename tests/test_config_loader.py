"""配置加载器测试。"""

from __future__ import annotations

import pytest

from danmakustudio.config.loader import load_config
from danmakustudio.config.models import DEFAULT_CONFIG
from danmakustudio.errors import ConfigError


def test_load_config_explicit_missing_path_raises(tmp_path):
    missing = tmp_path / "missing.yaml"

    with pytest.raises(ConfigError, match="不存在"):
        load_config(missing)


def test_load_config_rejects_non_mapping_top_level(tmp_path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("- not\n- mapping\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="顶层"):
        load_config(config_path)


def test_load_config_rejects_non_mapping_section(tmp_path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("encode: 1\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="encode"):
        load_config(config_path)


def test_load_config_null_section_falls_back_to_default(tmp_path):
    config_path = tmp_path / "empty_section.yaml"
    config_path.write_text("encode:\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.encode == DEFAULT_CONFIG.encode


def test_load_config_preserves_null_for_optional_value(tmp_path):
    config_path = tmp_path / "optional_null.yaml"
    config_path.write_text(
        "animation:\n  gift_dwell_time: null\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.animation.gift_dwell_time is None


def test_load_config_rejects_null_for_required_value(tmp_path):
    config_path = tmp_path / "required_null.yaml"
    config_path.write_text("style:\n  font_size: null\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"style\.font_size 不能为 null"):
        load_config(config_path)


def test_load_config_validation_error_is_config_error(tmp_path):
    config_path = tmp_path / "invalid_value.yaml"
    config_path.write_text("system:\n  video_alignment: 3\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="video_alignment"):
        load_config(config_path)
