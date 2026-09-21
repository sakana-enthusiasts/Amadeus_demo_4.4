import ast
import copy
import json
from pathlib import Path
from math import exp, pi, sqrt

import pandas as pd
import pytest

from 插件.配方物性.配方物性汇总 import 配方物性汇总插件, 创建默认模型注册表
from 插件.配方物性.配方物性接口 import 输入不可用
from 插件.配方物性.扩散.接口 import 扩散模型接口
from 核心系统.配方评估流程 import 运行颅骨透明化流程
from 核心系统.颅骨透明化用途 import (
    保存成分证据, 保存配方设置, 运行用途评估, 配方物性标识, 读取配方设置,
)
from 核心系统.数据管理接口 import 文件数据访问管理器


@pytest.fixture
def 配方():
    return {
        "成分": [
            {"成分键": "A", "体积分数": 0.5, "摩尔分数": 0.25, "纯物质RI": 1.4, "纯物质黏度_mPa_s": 1,
             "渗透角色": "溶剂", "浓度值": 50, "浓度单位": "v/v%"},
            {"成分键": "B", "体积分数": 0.5, "摩尔分数": 0.75, "纯物质RI": 1.6, "纯物质黏度_mPa_s": 16,
             "渗透角色": "溶质", "摩尔浓度_mol_L": 0.1, "范特霍夫因子": 2, "浓度值": 50, "浓度单位": "v/v%"},
        ],
        "物性模型选择": {k: "auto" for k in 创建默认模型注册表().指标列表()},
        "物性条件": {"温度_C": 25, "探针水动力半径_nm": 1, "水成分键": "A"},
    }


def test_五类物性公式单位和回退(配方):
    r = 配方物性汇总插件().执行(配方)
    ll = 0.5 * ((1.4**2-1)/(1.4**2+2) + (1.6**2-1)/(1.6**2+2))
    assert r["混合折射率"]["值"] == pytest.approx(sqrt((1+2*ll)/(1-ll)))
    assert r["混合折射率"]["值"] != pytest.approx(1.5)
    assert r["混合黏度"]["值"] == pytest.approx(8)
    assert r["混合黏度"]["方法"] == "ideal_log"
    assert "grunberg_nissan 不可用" in r["混合黏度"]["警告"][0]
    assert r["溶液自由扩散系数"]["值"] == pytest.approx(1.380649e-23*298.15/(6*pi*8e-3*1e-9))
    assert r["溶液自由扩散系数"]["依赖"]["混合黏度"]["方法"] == "ideal_log"
    assert r["渗透压"]["值"] == pytest.approx(8.31446261815324*298.15*200)
    assert r["水活度"]["值"] == 0.25
    assert all(x["状态"] == "已预测" and x["置信度"] is None for x in r.values())


@pytest.mark.parametrize("n", [1, 2, 3, 5])
def test_任意组分数和纯物质极限(n, 配方):
    配方["成分"] = [{"成分键": str(i), "体积分数": 1/n, "纯物质RI": 1.5} for i in range(n)]
    r = 配方物性汇总插件().执行(配方)
    assert r["混合折射率"]["值"] == pytest.approx(1.5)


@pytest.mark.parametrize("bad", [-0.2, 0.1, float("inf"), float("nan"), "abc", None])
def test_比例错误不归一且不影响独立指标(bad, 配方):
    配方["成分"][0]["体积分数"] = bad
    配方["成分"][0]["浓度单位"] = "%"
    r = 配方物性汇总插件().执行(配方)
    assert r["混合折射率"]["值"] is None
    assert r["混合黏度"]["值"] == pytest.approx(8)


@pytest.mark.parametrize("unit,ok", [("%", False), ("w/w%", False), ("v/v%", True), ("% v/v", True)])
def test_只转换明确的体积比例(unit, ok, 配方):
    for row in 配方["成分"]:
        del row["体积分数"]
        row["浓度单位"] = unit
    r = 配方物性汇总插件().执行(配方)
    assert (r["混合折射率"]["值"] is not None) == ok


def test_零组分可缺物性而正组分不可(配方):
    配方["成分"].append({"成分键": "unused", "体积分数": 0, "摩尔分数": 0, "渗透角色": "溶质", "摩尔浓度_mol_L": 0})
    assert 配方物性汇总插件().执行(配方)["混合折射率"]["值"] is not None
    del 配方["成分"][0]["纯物质RI"]
    assert 配方物性汇总插件().执行(配方)["混合折射率"]["值"] is None


def test_同指标并存和显式模型不隐式回退(配方):
    配方["物性模型选择"]["混合黏度"] = "grunberg_nissan"
    r = 配方物性汇总插件().执行(配方)
    assert r["混合黏度"]["值"] is None
    assert r["溶液自由扩散系数"]["值"] is None
    配方["物性模型参数"] = {"grunberg_nissan": {"温度_C": 25, "Gij": {"A": {"B": 2}}}}
    r = 配方物性汇总插件().执行(配方)
    assert r["混合黏度"]["值"] == pytest.approx(8*exp(.25*.75*2))
    配方["物性模型参数"]["grunberg_nissan"]["温度_C"] = 20
    assert 配方物性汇总插件().执行(配方)["混合黏度"]["值"] is None


def test_实测优先并传播依赖且默认不开预测(配方):
    配方["配方设置"] = {"混合液实测RI": 1.555, "混合液实测黏度_mPa_s": 2}
    r = 配方物性汇总插件().执行(配方)
    assert r["混合折射率"]["值"] == 1.555 and r["混合折射率"]["状态"] == "已实测"
    assert r["溶液自由扩散系数"]["依赖"]["混合黏度"]["状态"] == "已实测"
    del 配方["物性模型选择"]
    r = 配方物性汇总插件().执行(配方)
    assert r["水活度"]["状态"] == "待补实测"


@pytest.mark.parametrize("bad", ["typo", -1, float("inf")])
def test_无效实测不静默替换为预测(bad, 配方):
    配方["配方设置"] = {"混合液实测RI": bad}
    r = 配方物性汇总插件().执行(配方)
    assert r["混合折射率"]["状态"] == "输入无效"
    assert r["混合折射率"]["值"] is None


def test_非理想修正与缺失因子(配方):
    配方["物性模型参数"] = {"osmotic_coefficient": {"渗透系数": 0.9}, "water_activity_coefficient": {"水活度系数": 2}}
    r = 配方物性汇总插件().执行(配方)
    assert r["渗透压"]["方法"] == "osmotic_coefficient"
    assert r["渗透压"]["值"] == pytest.approx(8.31446261815324*298.15*200*.9)
    assert r["水活度"]["值"] == .5
    del 配方["成分"][1]["范特霍夫因子"]
    assert 配方物性汇总插件().执行(配方)["渗透压"]["值"] is None


def test_缺水键半径和无效温度都不猜(配方):
    配方["物性条件"] = {"温度_C": 25}
    r = 配方物性汇总插件().执行(配方)
    assert r["水活度"]["值"] is None and r["溶液自由扩散系数"]["值"] is None
    配方["物性条件"]["温度_C"] = -273.15
    assert all(x["值"] is None for x in 配方物性汇总插件().执行(配方).values())


def test_替换扩散模型用途不变且其他指标结果完全一致(配方):
    class 校准测试模型(扩散模型接口):
        方法 = "experimental_gp_v2"
        模型版本 = "2.0"
        自动优先级 = 100

        def 预测(self, 配方, 上游):
            if not 配方.条件.get("测试校准可用"):
                raise 输入不可用("未提供测试校准数据")
            return self.结果(1e-10)

    注册表 = 创建默认模型注册表()
    注册表.注册(校准测试模型())
    旧 = 配方物性汇总插件().执行(配方)
    聚合 = 配方物性汇总插件(注册表)
    assert 聚合.执行(配方)["溶液自由扩散系数"]["方法"] == "stokes_einstein"
    配方["物性条件"]["测试校准可用"] = True
    配方["物性模型选择"]["溶液自由扩散系数"] = "experimental_gp_v2"
    新 = 聚合.执行(配方)
    assert 新["溶液自由扩散系数"]["值"] == 1e-10
    for k in 旧.keys() - {"溶液自由扩散系数"}:
        for field in ("值", "方法", "模型版本", "状态", "警告"):
            assert 旧[k][field] == 新[k][field]
    from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        控制器 = 创建颅骨透明化筛选流程控制器(Path(d))
        # 获取入口注入新策略，保留其他插件。
        获取 = 控制器.插件管理器.获取插件
        结果 = 运行颅骨透明化流程(配方, lambda key: 聚合 if key == "配方物性汇总" else 获取(key))
        assert 结果["配方摘要"].iloc[0]["物性_溶液自由扩散系数_方法"] == "experimental_gp_v2"
        assert 结果["用途约束"].set_index("指标").loc["局部毒性", "约束状态"] == "未知"


def test_配置错误重复模型依赖成环(配方):
    配方["物性模型选择"]["混合折射率"] = "typo"
    with pytest.raises(ValueError, match="未知模型"):
        配方物性汇总插件().执行(配方)
    注册表 = 创建默认模型注册表()
    with pytest.raises(ValueError, match="重复"):
        注册表.注册(注册表.模型列表("混合折射率")[0])
    class 循环模型(扩散模型接口):
        方法 = "loop"
        依赖指标 = ("溶液自由扩散系数",)
        def 预测(self, 配方, 上游):
            return self.结果(1e-10)
    注册表.注册(循环模型())
    配方["物性模型选择"] = {"溶液自由扩散系数": "loop"}
    with pytest.raises(ValueError, match="成环"):
        配方物性汇总插件(注册表).执行(配方)


def test_按批次持久化设置与物性追溯(tmp_path, 配方):
    管理器 = 文件数据访问管理器(tmp_path)
    清单 = pd.DataFrame(配方["成分"])
    清单["候选编号"] = ["A", "B"]
    保存成分证据(管理器, "batch1", 清单)
    保存配方设置(管理器, "batch1", {k: v for k, v in 配方.items() if k != "成分"})
    assert json.loads(读取配方设置(管理器, "batch1")["物性模型选择"])["混合折射率"] == "auto"
    r = 运行用途评估(管理器, "batch1", 清单)
    assert pd.isna(r["配方摘要"].iloc[0]["混合液实测RI"])
    assert r["配方摘要"].iloc[0]["混合液预测RI"] > 1.4
    运行用途评估(管理器, "batch1", 清单)
    运行用途评估(管理器, "batch2", 清单)
    表 = 管理器.读取软件数据库表格(配方物性标识)
    assert len(表) == 10
    行 = 表.loc[(表["批次编号"] == "batch1") & (表["指标"] == "溶液自由扩散系数")].iloc[0]
    assert json.loads(行["依赖"])["混合黏度"]["方法"] == "ideal_log"


def test_用途约束按值比较缺失保持未知(配方):
    配方["用途配置"] = {"物性约束": {"混合黏度": {"最大": 4}, "水活度": {"最小": 0.1}}}
    r = 运行颅骨透明化流程(配方)["用途约束"].set_index("指标")
    assert r.loc["混合黏度", "约束状态"] == "不通过"
    assert r.loc["水活度", "约束状态"] == "通过"
    assert r.loc["局部毒性", "约束状态"] == "未知"


def test_输入不修改用途插件没有跨插件调用(配方):
    原始 = copy.deepcopy(配方)
    配方物性汇总插件().执行(配方)
    assert 配方 == 原始
    import 插件.颅骨透明化.颅骨透明化功能插件 as module
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "执行")


def test_物性页面保存模型与条件(tmp_path):
    from streamlit.testing.v1 import AppTest

    def 页面(根目录):
        from pathlib import Path
        import pandas as pd
        from 核心系统.数据管理接口 import 文件数据访问管理器
        from 核心系统.颅骨透明化用途 import 默认成分证据, 读取配方设置
        from 软件界面.配方构建页面 import _物性录入
        管理器 = 文件数据访问管理器(Path(根目录))
        成分 = 默认成分证据(pd.DataFrame([{"成分键": "A", "候选编号": "A", "化学名称": "合成示例", "浓度值": 100, "浓度单位": "v/v%"}]))
        _物性录入(管理器, "ui_batch", 成分, 读取配方设置(管理器, "ui_batch"), {})

    app = AppTest.from_function(页面, args=(str(tmp_path),)).run()
    assert not app.exception
    app.selectbox(key="物性方法_混合折射率_ui_batch").select("lorentz_lorenz")
    app.text_input(key="物性温度_ui_batch").set_value("30")
    app.button(key="保存物性_ui_batch").click().run()
    assert not app.exception
    设置 = 读取配方设置(文件数据访问管理器(tmp_path), "ui_batch")
    assert json.loads(设置["物性模型选择"])["混合折射率"] == "lorentz_lorenz"
    assert json.loads(设置["物性条件"])["温度_C"] == "30"


def test_用途评估使用注入插件并保持顺序(配方, monkeypatch):
    import 核心系统.默认装配 as assembly
    registry = assembly.创建默认插件管理器()
    expected = 运行颅骨透明化流程(配方)
    calls = []

    def get(key):
        calls.append(key)
        return registry.获取插件(key)

    def forbidden(**kwargs):
        raise AssertionError("显式注入后不应装配默认插件")

    monkeypatch.setattr(assembly, "创建默认插件管理器", forbidden)
    actual = 运行颅骨透明化流程(配方, get)
    assert calls == ["颅骨透明化用途配置", "折射率处理", "水合能力处理", "颅骨透明化成分评估",
                     "通用HSP计算", "通用HSP计算", "配方物性汇总", "颅骨透明化配方评估",
                     "颅骨透明化实验终点评价", "颅骨透明化配方特征构建", "配方特征构建", "颅骨透明化用途约束"]
    for key, value in expected.items():
        if isinstance(value, pd.DataFrame):
            pd.testing.assert_frame_equal(actual[key], value)
        else:
            assert actual[key] == value


def test_确认批次描述符可注入并按原路径保存(tmp_path):
    from 核心系统.颅骨透明化用途 import 生成确认批次描述符, 读取确认批次描述符
    from 插件.插件接口 import 基础插件接口

    class Descriptor(基础插件接口):
        插件标识 = "确认批次化学描述符"
        def 执行(self, context):
            assert context["批次编号"] == "injected"
            assert context["确认清单"].iloc[0]["候选编号"] == "A"
            return pd.DataFrame([{"成分键": "A", "描述符名称": "fixture", "数值": 7}])

    plugin = Descriptor()
    def get(key):
        assert key == plugin.插件标识
        return plugin

    manager = 文件数据访问管理器(tmp_path)
    生成确认批次描述符(manager, "injected", pd.DataFrame([{"候选编号": "A"}]), 获取插件=get)
    saved = 读取确认批次描述符(manager, "injected")
    assert saved.iloc[0]["描述符名称"] == "fixture"
    assert float(saved.iloc[0]["数值"]) == 7
