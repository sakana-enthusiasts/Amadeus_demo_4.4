from pathlib import Path

from streamlit.testing.v1 import AppTest

import pytest

pytestmark = pytest.mark.integration


项目根目录 = Path(__file__).resolve().parents[2]


def test_候选与化学信息页面展示真实处理数据(paper_ui) -> None:
    应用 = AppTest.from_file(str(项目根目录 / "启动程序.py"))
    应用.run(timeout=30)
    应用.radio[0].set_value("候选试剂").run(timeout=30)
    assert any(组件.label == "导入试剂数量" and 组件.value == "12" for 组件 in 应用.metric)
    assert len(应用.dataframe) >= 1
    应用.radio[0].set_value("化学信息").run(timeout=30)
    assert "#0093" in 应用.selectbox[0].options
    assert len(应用.dataframe) >= 4
