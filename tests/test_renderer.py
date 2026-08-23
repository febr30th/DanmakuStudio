"""渲染器辅助逻辑测试。"""

from danmakustudio.render.renderer import _text_danmaku_opacity


def test_text_opacity_full_before_fade_zone():
    """弹幕未进入淡出区时应完全不透明。"""
    assert _text_danmaku_opacity(
        current_y=120.0,
        height=40,
        limit=100,
        fade_out_zone=10,
    ) == 1.0


def test_text_opacity_considers_multiline_height():
    """多行弹幕顶部过界时不应整块突然消失。"""
    alpha = _text_danmaku_opacity(
        current_y=95.0,
        height=120,
        limit=100,
        fade_out_zone=10,
    )
    assert 0.0 < alpha < 1.0


def test_text_opacity_zero_after_bottom_leaves_limit():
    """弹幕底部离开文本区顶部后应不可见。"""
    assert _text_danmaku_opacity(
        current_y=-30.0,
        height=30,
        limit=0,
        fade_out_zone=10,
    ) == 0.0
