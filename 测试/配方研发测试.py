import copy
import json
from math import isclose

import pytest

from 核心系统.配方研发流程 import 预测完整配方, 运行验证模式, 运行发现模式
from 插件.配方生成.配方输入组装插件 import 配方输入组装插件
from 插件.配方生成.自动组合插件 import 自动组合插件
from 插件.配方生成.比例优化插件 import 组成签名
from 插件.配方生成.发现约束插件 import 配方约束评价插件
from 设置.公开物性样例 import 公开物性演示库, 默认发现配置, 甘油验证数据
from 设置.配方验证设置 import 读取验证体系


def 示例输入():
    return copy.deepcopy(读取验证体系()[1])


@pytest.mark.parametrize("unit", ["质量分数", "摩尔分数", "体积分数"])
def test_三种明确比例守恒并生成全量(unit):
    x = 示例输入()
    for row in x["配方定义"]["组分"]:
        row.update(单位=unit, 用量="0.5")
    r = 配方输入组装插件().执行(x)
    for field in ["质量分数", "摩尔分数", "体积分数"]:
        assert sum(v[field] for v in r["成分"]) == pytest.approx(1)
    assert sum(v["质量_g"] for v in r["成分"]) == r["质量总和_g"]
    assert all(v["摩尔浓度_mol_L"] > 0 for v in r["成分"])
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize("amount,unit", [(20,"g"),(20000,"mg"),(20/92.094,"mol"),(20000/92.094,"mmol")])
def test_绝对用量等价(amount, unit):
    x = 示例输入()
    x["配方定义"]["组分"][0].update(用量=amount, 单位=unit)
    x["配方定义"]["组分"][1].update(用量=80, 单位="g")
    r = 配方输入组装插件().执行(x)
    assert r["成分"][0]["质量分数"] == pytest.approx(.2)


@pytest.mark.parametrize("bad", [-1, 0, float("nan"), float("inf"), True])
def test_非法用量拒绝(bad):
    x = 示例输入()
    x["配方定义"]["组分"][0]["用量"] = bad
    with pytest.raises(ValueError):
        配方输入组装插件().执行(x)


@pytest.mark.parametrize("unit", ["%", "w/v%", "饱和"])
def test_裸浓度基准拒绝(unit):
    x = 示例输入()
    for row in x["配方定义"]["组分"]:
        row["单位"] = unit
    with pytest.raises(ValueError):
        配方输入组装插件().执行(x)


def test_不补齐缺失溶剂或自动归一():
    x = 示例输入()
    x["配方定义"]["组分"].pop()
    with pytest.raises(ValueError, match="主溶剂"):
        配方输入组装插件().执行(x)
    x = 示例输入()
    x["配方定义"]["组分"][0]["用量"] = .3
    with pytest.raises(ValueError, match="之和"):
        配方输入组装插件().执行(x)


def test_BA_ANP混合绝对投料不冒充eRI():
    x = next(x for x in 读取验证体系() if x["编号"] == "seethrough_ba_anp")
    r = 预测完整配方(x["配方定义"], x["物质库"], x["物性条件"])
    anp = next(x for x in r["成分"] if x["成分键"] == "anp")
    assert anp["质量分数"] == pytest.approx(4/(5*1.045+4))
    assert anp["摩尔分数"] == pytest.approx((4/188.23)/(4/188.23+5*1.045/108.14))
    assert anp["体积分数"] is None
    assert anp["纯物质RI"] is None
    assert r["配方物性"]["混合折射率"]["值"] is None


def test_属性温度不匹配独立拒绝():
    x = 示例输入()
    x["物质库"][1]["RI温度_C"] = 25
    r = 预测完整配方(x["配方定义"], x["物质库"], x["物性条件"])
    assert r["配方物性"]["混合折射率"]["值"] is None
    assert r["配方物性"]["混合黏度"]["值"] is not None


def test_最终体积不等同纯组分相加且浓度传播():
    x = 示例输入()
    x["配方定义"].update(最终体积_mL=100, 最终体积来源="测试实测")
    r = 配方输入组装插件().执行(x)
    assert all(v["摩尔浓度_mol_L"] == pytest.approx(v["物质的量_mol"]/.1) for v in r["成分"])
    assert r["最终体积_mL"] == 100


def test_多种真实体系与不确定度不伪造():
    r = 运行验证模式()
    assert r["通过"]
    assert {"eci_pure", "tde_water_84596w", "seethrough_ba_anp"} <= {x["体系"] for x in r["体系"]}
    assert all(v["不确定度"] is None for x in r["体系"] for v in x["预测"]["配方物性"].values())
    assert all(x["通过"] for x in r["检查"] if x.get("参与门禁"))
    eta = next(x for x in r["体系"] if x["体系"] == "segur_50")["预测"]["配方物性"]["混合黏度"]["值"]
    assert eta == pytest.approx(6, rel=.02)
    assert r["待补文献协议"][0]["体系"] == "OPTIClear"


def test_不强制任何名字和溶剂支持三元四元():
    库 = 公开物性演示库()
    for i, row in enumerate(库):
        row["物质编号"], row["化学名称"], row["CAS"] = f"custom{i}", f"独立物质{i}", f"CAS_{i}"
    defs = 自动组合插件().执行({"物质库": 库, "生成配置": 默认发现配置() | {"最大组分数": 4}})
    assert {len(x["组分"]) for x in defs} == {1,2,3,4}
    assert len({组成签名(x) for x in defs}) == len(defs)
    for x in defs:
        assert sum(v["用量"] for v in x["组分"]) == pytest.approx(1)
        assert all(v["物质编号"].startswith("custom") for v in x["组分"])
    for row in 库:
        assert any(all(v["物质编号"] != row["物质编号"] for v in x["组分"]) for x in defs)


def test_甘油可以独立加入但不会强制或默认加入():
    库 = 公开物性演示库()
    assert not any(x["CAS"] == "56-81-5" for x in 库)
    库.append(甘油验证数据() | {"来源类型": "用户独立输入", "数据来源": "测试用户独立提供"})
    defs = 自动组合插件().执行({"物质库": 库, "生成配置": 默认发现配置()})
    assert any(any(v["物质编号"] == "glycerol" for v in x["组分"]) for x in defs)
    assert any(all(v["物质编号"] != "glycerol" for v in x["组分"]) for x in defs)


def test_发现结果不受Benchmark修改删除或损坏影响(monkeypatch):
    import 设置.配方验证设置 as bench
    cfg = 默认发现配置() | {"最小组分数":3}
    first = 运行发现模式(公开物性演示库(), cfg)
    snapshots = [(x["配方编号"],x["非支配层"],x["配方物性"]) for x in first["候选"]]
    monkeypatch.setattr(bench, "读取验证体系", lambda: [])
    empty = 运行发现模式(公开物性演示库(), cfg)
    assert snapshots == [(x["配方编号"],x["非支配层"],x["配方物性"]) for x in empty["候选"]]
    monkeypatch.setattr(bench, "读取验证体系", lambda: [{"非法": "损坏"}])
    broken = 运行发现模式(公开物性演示库(), cfg)
    assert [x["配方编号"] for x in first["候选"]] == [x["配方编号"] for x in broken["候选"]]
    assert broken["对照错误"]
    assert first["优化记录"][0]["新增"] > 0
    assert all(len(x["成分"]) == 3 for x in first["候选"])


def test_论文来源候选不进入发现池():
    库 = 公开物性演示库()
    库[0]["来源类型"] = "验证专用"
    r = 运行发现模式(库, 默认发现配置())
    assert r["排除分子"]
    assert all(all(x["成分键"] != "water" for x in f["成分"]) for f in r["候选"])


def test_论文标签不能改变独立池排序():
    库 = 公开物性演示库()
    a = 运行发现模式(库, 默认发现配置())
    for i, x in enumerate(库):
        x.update(eRI=100-i, 论文排名=i, 参考得分=i*100)
    b = 运行发现模式(库, 默认发现配置())
    assert [x["配方编号"] for x in a["候选"]] == [x["配方编号"] for x in b["候选"]]


def test_缺失安全证据不当成可行且硬物性约束有效():
    cfg, 库 = 默认发现配置(), 公开物性演示库()
    严格 = 运行发现模式(库, cfg, 约束={"缺失策略":"排除"})
    assert not 严格["候选"]
    硬约束 = 运行发现模式(库, cfg, 约束={"物性约束":{"混合折射率":{"最小":1.6}}})
    assert not 硬约束["候选"]
    软 = 运行发现模式(库, cfg)
    assert all(x["约束状态"] == "待补证据" for x in 软["候选"])


def test_配方毒理只接受相同配方及暴露条件():
    r = 运行发现模式(公开物性演示库(), 默认发现配置())["候选"][0]
    条件 = {"物种":"鼠", "组织":"测试组织", "给药途径":"测试", "剂量":1, "剂量单位":"mg/mL", "暴露时长_h":1}
    ev = {"质量分数组成": [(x["成分键"], x["质量分数"]) for x in r["成分"]], "指标":"局部细胞存活率", "单位":"%", "值":50,
          "数据来源":"仅用于测试的记录", "条件":条件}
    ctx = {"配方":r, "约束":{"毒理条件":条件,"细胞存活率下限_pct":80}, "配方证据":[ev]}
    assert not 配方约束评价插件().执行(ctx)["可参与排序"]
    ev["条件"] = 条件 | {"暴露时长_h":24}
    assert 配方约束评价插件().执行(ctx)["约束状态"] == "待补证据"


def test_数值自检失败不开放搜索():
    r = 运行发现模式(公开物性演示库(), 默认发现配置(), 模型选择={"混合折射率":"measured_only"})
    assert r["生成数量"] == 0 and not r["候选"]
    assert not r["数值自检"]["通过"]


def test_搜索预算不按输入顺序截断():
    with pytest.raises(ValueError, match="预算"):
        自动组合插件().执行({"物质库":公开物性演示库(), "生成配置":默认发现配置()|{"最大配方数":2}})


def test_页面无确认批次也能运行且默认池为空():
    from streamlit.testing.v1 import AppTest
    a = AppTest.from_string("from 软件界面.配方研发页面 import 渲染配方研发页面\n渲染配方研发页面()").run()
    assert not a.exception
    a.radio[0].set_value("发现模式").run()
    assert a.button[1].disabled
    a.button[0].click().run()
    assert not a.button[1].disabled
    a.button[1].click().run(timeout=30)
    assert not a.exception and not a.error
    assert len(a.session_state["研发发现结果"]["候选"]) == 8


def test_发现全流程复用一次默认装配(monkeypatch):
    import 核心系统.默认装配 as assembly
    factory = assembly.创建默认插件管理器
    managers = []

    def create(**kwargs):
        manager = factory(**kwargs)
        managers.append(manager)
        return manager

    monkeypatch.setattr(assembly, "创建默认插件管理器", create)
    result = 运行发现模式(公开物性演示库(), 默认发现配置())
    assert len(managers) == 1
    assert result["候选"] and result["最后文献对照"]
    assert result["优化记录"][0]["新增"] > 0


def test_注入获取器贯穿自检生成约束排序细化和最后验证(monkeypatch):
    import 核心系统.默认装配 as assembly
    registry = assembly.创建默认插件管理器()
    calls = []

    class Wrapped:
        def __init__(self, plugin):
            self.plugin = plugin
        def 执行(self, context):
            calls.append(self.plugin.插件标识)
            return self.plugin.执行(context)

    wrapped = {row["插件标识"]: Wrapped(registry.获取插件(row["插件标识"]))
               for row in registry.注册列表()}
    expected = 运行发现模式(公开物性演示库(), 默认发现配置())

    def forbidden(**kwargs):
        raise AssertionError("已注入获取器时不能另建默认管理器")

    monkeypatch.setattr(assembly, "创建默认插件管理器", forbidden)
    result = 运行发现模式(公开物性演示库(), 默认发现配置(), 获取插件=wrapped.__getitem__)
    assert result == expected
    assert {"配方输入组装", "配方物性汇总", "独立候选分子筛选", "自动配方组合",
            "发现配方约束评价", "配方候选排序", "配方比例局部优化"} <= set(calls)
    assert calls.index("独立候选分子筛选") < calls.index("自动配方组合")
    assert calls.index("发现配方约束评价") < calls.index("配方候选排序") < calls.index("配方比例局部优化")
    assert calls[-2:] == ["配方输入组装", "配方物性汇总"]


@pytest.mark.parametrize("inject_getter", [False, True])
def test_研发自定义模型注册表贯穿自检搜索和验证(inject_getter):
    from 核心系统.默认装配 import 创建默认插件管理器
    from 插件.配方物性.配方物性汇总 import 创建默认模型注册表
    from 插件.配方物性.扩散.接口 import 扩散模型接口

    class CustomDiffusion(扩散模型接口):
        方法 = "test_injected_diffusion"
        模型版本 = "test"
        def 预测(self, 配方, 上游):
            return self.结果(1e-10)

    custom = 创建默认模型注册表()
    custom.注册(CustomDiffusion())
    getter = 创建默认插件管理器().获取插件 if inject_getter else None
    result = 运行发现模式(公开物性演示库(), 默认发现配置(), 注册表=custom,
        模型选择={"溶液自由扩散系数": CustomDiffusion.方法}, 获取插件=getter)
    assert result["数值自检"]["通过"] and result["候选"] and result["最后文献对照"]
    assert result["数值自检"]["物性"]["溶液自由扩散系数"]["方法"] == CustomDiffusion.方法
    for candidate in result["候选"]:
        assert candidate["配方物性"]["溶液自由扩散系数"]["方法"] == CustomDiffusion.方法
    for benchmark in result["最后文献对照"]:
        assert benchmark["预测物性"]["溶液自由扩散系数"]["方法"] == CustomDiffusion.方法
