from pathlib import Path

from streamlit.testing.v1 import AppTest

import pytest

pytestmark = pytest.mark.integration


项目根目录 = Path(__file__).resolve().parents[2]


def test_规则筛选页面展示真实统计候选和标签审计(paper_ui) -> None:
    应用 = AppTest.from_file(str(项目根目录 / "启动程序.py"))
    应用.run(timeout=30)
    应用.sidebar.radio[0].set_value("规则筛选").run(timeout=30)
    assert any(组件.label == "清理后真实候选" and str(组件.value) == "1619" for 组件 in 应用.metric)
    assert any(组件.label == "论文最终10恢复" and str(组件.value) == "10/10" for 组件 in 应用.metric)
    assert len(应用.dataframe) >= 3


def test_页面按钮创建run并在切换页面后读取本轮结果(isolated_paper_root, monkeypatch):
    from 软件界面 import 候选试剂页面, 化学信息页面, 规则筛选页面, 毒性评估页面, 身份冲突审核页面
    for module in (候选试剂页面, 化学信息页面, 规则筛选页面, 毒性评估页面, 身份冲突审核页面):
        monkeypatch.setattr(module, "项目根目录", isolated_paper_root)
    应用 = AppTest.from_file(str(项目根目录 / "启动程序.py"))
    应用.run(timeout=30)
    next(x for x in 应用.button if x.label == "导入并处理补充数据3").click().run(timeout=30)
    表3run = 应用.session_state["补充数据3run_id"]
    assert any(x.label == "导入试剂数量" and x.value == "12" for x in 应用.metric)
    应用.sidebar.radio[0].set_value("规则筛选").run(timeout=30)
    next(x for x in 应用.button if x.label == "重新运行完整筛选").click().run(timeout=30)
    assert 应用.session_state["补充数据2run_id"] != 表3run
    assert any(x.label == "论文最终10恢复" and x.value == "10/10" for x in 应用.metric)
    应用.sidebar.radio[0].set_value("化学信息").run(timeout=30)
    assert "#0093" in 应用.selectbox[0].options
    应用.sidebar.radio[0].set_value("毒性评估").run(timeout=30)
    assert any(len(x.value) == 20 and "当前动物实验物种" in x.value.columns for x in 应用.dataframe)
    应用.sidebar.radio[0].set_value("身份冲突审核").run(timeout=30)
    assert "#0958" in 应用.selectbox[0].options
    assert not 应用.exception
