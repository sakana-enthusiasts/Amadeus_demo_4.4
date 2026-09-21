from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration
项目根目录 = Path(__file__).resolve().parents[2]


def test_规则筛选页面包含实际图片下载入口(paper_ui) -> None:
    应用 = AppTest.from_file(str(项目根目录 / "启动程序.py"))
    应用.run(timeout=30)
    应用.radio[0].set_value("规则筛选").run(timeout=30)
    标签 = [组件.label for 组件 in 应用.get("download_button")]
    assert len(应用.exception) == 0 and len(应用.image) == 2
    for 文本 in ["下载数量变化图 PNG（300 DPI）", "下载数量变化图 SVG", "下载候选分布图 PNG（300 DPI）", "下载候选分布图 SVG"]:
        assert 文本 in 标签
