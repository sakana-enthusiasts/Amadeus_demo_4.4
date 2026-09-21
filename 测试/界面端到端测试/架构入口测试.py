"""隔离的小型 UI 入口回归，不读取论文、历史运行或科学 fixture。"""

import pandas as pd
from streamlit.testing.v1 import AppTest

from 核心系统.运行数据管理 import 运行数据管理器
from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器


def test_人工身份确认页面通过facade保存当前运行(tmp_path, monkeypatch):
    from 软件界面 import 身份冲突审核页面 as page
    manager = 运行数据管理器(tmp_path)
    run_id = manager.创建运行()
    manager.保存中间结果("补充数据2_41候选身份映射", pd.DataFrame([{
        "候选编号": "C1", "化学名称": "sample", "CAS号": "", "货号": "", "匹配状态": "待人工确认",
    }]))
    manager.保存筛选结果("化合物身份冲突表", pd.DataFrame([{"候选编号": "C1"}]))
    monkeypatch.setattr(page.论文运行上下文, "读取论文运行", lambda *args: manager)
    monkeypatch.setattr(page, "项目根目录", tmp_path)
    app = AppTest.from_string("from 软件界面.身份冲突审核页面 import 渲染身份冲突审核页面\n渲染身份冲突审核页面()")
    app.run()
    app.radio[0].set_value("标记无法确认")
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert manager.当前运行编号 == run_id
    saved = manager.读取中间结果("补充数据2_41候选身份映射")
    assert saved.iloc[0]["匹配状态"] == "无法确认"
    assert manager.读取软件数据库表格("人工身份确认记录.csv").iloc[0]["候选编号"] == "C1"


def test_规则页面重绘图表传入选定run(tmp_path, monkeypatch):
    from 软件界面 import 规则筛选页面 as page
    manager = 运行数据管理器(tmp_path)
    manager.创建运行()
    manager.保存筛选结果(page.结果标识, pd.DataFrame([{
        "候选编号": "C1", "自动规则通过": True, "论文最终10候选标签": "否",
    }]))
    monkeypatch.setattr(page.论文运行上下文, "读取论文运行", lambda *args: manager)
    controller = 创建颅骨透明化筛选流程控制器(tmp_path)
    seen = []
    monkeypatch.setattr(controller.插件管理器.获取插件("筛选结果图表"), "执行", lambda context: seen.append(context))
    monkeypatch.setattr(page, "创建颅骨透明化筛选流程控制器", lambda *args: controller)
    monkeypatch.setattr(page, "启用结果可视化", lambda: True)
    monkeypatch.setattr(page, "渲染候选散点图", lambda *args: None)
    monkeypatch.setattr(page, "渲染筛选过程图", lambda *args: None)
    app = AppTest.from_string("from 软件界面.规则筛选页面 import 渲染规则筛选页面\n渲染规则筛选页面()")
    app.run()
    assert not app.exception
    next(button for button in app.button if button.label == "重新生成图表").click().run()
    assert not app.exception and not app.error
    assert len(seen) == 1 and seen[0]["数据管理器"] is manager
