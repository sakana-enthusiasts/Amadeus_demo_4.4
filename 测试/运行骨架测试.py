"""注册原子性、值类型和正式运行路径的独立回归。"""

import ast
import json
from pathlib import Path
import re
import sys

import pytest

from 核心系统.插件管理器 import 插件管理器
from 核心系统.运行数据管理 import 运行数据管理器
from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器
from 核心系统.目标规格 import Criterion, TargetProfile
from 核心系统.目标规格.执行计划 import compile_profile
from 插件.插件接口 import 基础插件接口


class Plugin(基础插件接口):
    插件标识 = "test"
    def 执行(self, context):
        return context


def test_registry_collision_replacement_and_diagnostics():
    registry, first, second = 插件管理器(), Plugin(), Plugin()
    registry.注册插件(first, 别名=("old",))
    for instance, aliases in [(second, ()), (second, ("old",)), (second, ("test",))]:
        with pytest.raises(ValueError):
            registry.注册插件(instance, 别名=aliases)
    other = Plugin()
    other.插件标识 = "other"
    for aliases in [("old",), ("test",), ("duplicate", "duplicate")]:
        with pytest.raises(ValueError):
            registry.注册插件(other, 别名=aliases)
    registry.注册插件(other, 别名=("other_old",))
    with pytest.raises(ValueError):
        registry.替换插件(second, 别名=("other_old",))
    assert registry.获取插件("old") is first
    registry.替换插件(second)
    assert registry.获取插件("old") is second
    registry.替换插件(first, 别名=("new",))
    with pytest.raises(KeyError, match="可用注册"):
        registry.获取插件("old")
    snapshot = registry.注册列表()
    snapshot[0]["插件标识"] = "changed"
    assert registry.获取插件("new") is first
    with pytest.raises(TypeError):
        registry.注册插件(object())


def test_factory_ids_and_explicit_legacy_aliases(tmp_path):
    registry = 创建颅骨透明化筛选流程控制器(tmp_path).插件管理器
    rows = registry.注册列表()
    canonical = {x["插件标识"] for x in rows}
    aliases = [alias for row in rows for alias in row["别名"]]
    assert len(canonical) == len(rows)
    assert len(set(aliases)) == len(aliases)
    assert not canonical.intersection(aliases)
    assert {
        "论文表格导入", "RDKit结构处理", "RDKit普通描述符", "汉森距离计算", "化学属性合并",
        "普通表格导入", "通用候选表导入", "化合物身份转换", "公开证据聚合", "CompTox接口状态",
        "规则筛选", "用户候选规则筛选", "补充数据2汉森距离计算", "通用HSP计算", "折射率处理",
        "水合能力处理", "确认批次化学描述符", "用户候选HSP初筛", "配方特征构建", "配方物性汇总",
        "配方输入组装", "颅骨透明化用途约束", "颅骨透明化用途配置", "颅骨透明化成分评估",
        "颅骨透明化配方评估", "颅骨透明化实验终点评价", "颅骨透明化配方特征构建",
        "补充数据2属性合并", "官方数据冲突检测", "筛选报告导出", "毒性证据视图",
        "毒性判定指标", "毒理证据匹配", "通用运行报告导出", "筛选结果图表",
        "自动配方组合", "配方候选排序", "配方比例局部优化", "独立候选分子筛选", "发现配方约束评价",
    } <= canonical
    assert registry.获取插件("PubChem查询") is registry.获取插件("公开证据聚合")
    assert registry.获取插件("补充数据2表格导入") is registry.获取插件("普通表格导入")
    assert all(registry.获取插件(x["插件标识"]).插件标识 == x["插件标识"] for x in rows)
    for row in rows:
        for alias in row["别名"]:
            assert registry.获取插件(alias) is registry.获取插件(row["插件标识"])


@pytest.mark.parametrize("filename,allowed", [
    ("流程控制器.py", {}),
    ("配方研发流程.py", {"插件.插件接口": {"基础插件接口"},
                        "插件.配方生成.组成签名": {"搜索定义质量签名"}}),
    ("配方评估流程.py", {"插件.插件接口": {"基础插件接口"}}),
    ("颅骨透明化用途.py", {"插件.插件接口": {"基础插件接口"}}),
])
def test_workflows_depend_on_contracts_not_concrete_plugins(filename, allowed):
    path = Path(__file__).resolve().parents[1] / "核心系统" / filename
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("插件"):
            assert node.module in allowed, (filename, node.module)
            assert {x.name for x in node.names} <= allowed[node.module]
        if isinstance(node, ast.Import):
            assert not any(x.name == "插件" or x.name.startswith("插件.") for x in node.names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert not node.func.id.endswith("插件") or node.func.id == "获取插件"


def test_default_assembly_is_independent_and_preserves_custom_registry():
    from 核心系统.默认装配 import 创建默认插件管理器, 装配工作流插件获取器
    from 插件.配方物性.配方物性汇总 import 创建默认模型注册表
    first, second = 创建默认插件管理器(), 创建默认插件管理器()
    assert first.获取插件("配方物性汇总") is not second.获取插件("配方物性汇总")
    custom = 创建默认模型注册表()
    assert 创建默认插件管理器(物性注册表=custom).获取插件("配方物性汇总").注册表 is custom
    getter = first.获取插件
    assert 装配工作流插件获取器(getter) is getter
    combined = 装配工作流插件获取器(getter, 注册表=custom)
    assert combined("配方物性汇总").注册表 is custom
    assert getter("配方物性汇总").注册表 is not custom
    assert combined("自动配方组合") is getter("自动配方组合")


@pytest.mark.parametrize("requirement,passed", [("any", True), ("measured_only", False),
    ("measured_or_predicted", False), ("predicted_allowed", False)])
def test_computed_is_not_prediction(requirement, passed):
    from 核心系统.分子属性 import CORE_METRICS
    from 核心系统.结构查询 import StructureCandidate
    from 插件.化学计算.RDKit分子属性计算器 import RDKit分子属性计算器
    from 插件.配方生成.发现约束插件 import 评价规格指标
    profile = TargetProfile("test", {"logp": Criterion(role="report_only", evidence_requirement=requirement)})
    plan, preflight = compile_profile(profile)
    assert preflight["passed"] == passed
    results = RDKit分子属性计算器().calculate([StructureCandidate("a", "CCO", "smiles")], tuple(CORE_METRICS))[0]
    assert all(x.value_kind == "computed" for x in results.properties)
    row = 评价规格指标(plan.criteria[0], {"分子计算属性": {x.metric_id: x.to_dict() for x in results.properties}})
    assert row["证据类型"] == "computed"
    assert (row["合格值"] is not None) == passed


def test_run_paths_metadata_and_escape(tmp_path):
    before = {x.name for x in tmp_path.iterdir()}
    manager = 运行数据管理器(tmp_path)
    run_id = manager.创建运行(运行类型="配方发现", 输入来源="内存fixture")
    assert re.fullmatch(r"run_\d{8}T\d{6}Z_[a-z0-9]+", run_id)
    assert manager.运行目录() == tmp_path / "数据" / "运行记录" / run_id
    assert json.loads((manager.运行目录() / "运行元数据.json").read_text(encoding="utf-8"))["输入来源"] == "内存fixture"
    for value in ("../escape", "run_20260101T000000Z_a/../bad", str(tmp_path), "1789722128015"):
        with pytest.raises(ValueError):
            manager.运行目录(value)
        with pytest.raises(ValueError):
            manager.激活运行(value)
    assert {x.name for x in tmp_path.iterdir()} - before == {"数据"}


@pytest.mark.parametrize("mode", ["发现", "验证"])
def test_cli_uses_only_formal_run_directory(tmp_path, monkeypatch, mode):
    import 运行配方研发 as cli
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "运行配方研发.py"))
    monkeypatch.setattr(cli, "运行验证模式", lambda: {"体系": []})
    monkeypatch.setattr(cli, "运行发现模式", lambda *a, **k: {"候选": [], "状态": "fixture", "生成数量": 0})
    monkeypatch.setattr(sys, "argv", ["cli", mode] + (["--试跑演示库"] if mode == "发现" else []))
    before = {x.name for x in tmp_path.iterdir()}
    cli.主程序()
    assert {x.name for x in tmp_path.iterdir()} - before == {"数据"}
    outputs = list((tmp_path / "数据" / "运行记录").glob("run_*/完整结果.json"))
    assert len(outputs) == 1 and (outputs[0].parent / "试跑报告.md").is_file()
    assert not (tmp_path / "运行记录").exists()
    assert not any(re.fullmatch(r"\d{13}", x.name) for x in tmp_path.iterdir())


def test_默认物性装配独立且不执行或读写(monkeypatch):
    import pandas as pd
    from 核心系统.默认装配 import 创建默认物性模型注册表, 创建默认插件管理器
    first = 创建默认物性模型注册表()
    def forbidden(*args, **kwargs):
        pytest.fail("装配阶段不应执行模型、读取用户数据或保存状态")
    for metric in first.指标列表():
        for model in first.模型列表(metric):
            monkeypatch.setattr(type(model), "预测", forbidden)
    for method in ("open", "read_text", "read_bytes", "write_text", "write_bytes", "mkdir"):
        monkeypatch.setattr(Path, method, forbidden)
    monkeypatch.setattr(pd, "read_csv", forbidden)
    monkeypatch.setattr(pd, "read_excel", forbidden)
    second = 创建默认物性模型注册表()
    manager = 创建默认插件管理器()
    assert manager.获取插件("人工身份确认").插件标识 == "人工身份确认"
    assert first is not second
    assert first.指标列表() == second.指标列表()
    for metric in first.指标列表():
        assert first.方法列表(metric) == second.方法列表(metric)
        assert all(a is not b for a, b in zip(first.模型列表(metric), second.模型列表(metric)))


@pytest.mark.parametrize("method,canonical", [
    ("执行人工身份确认", "人工身份确认"), ("重新生成筛选结果图表", "筛选结果图表"),
])
def test_页面facade使用canonical获取器并保留当前运行(tmp_path, method, canonical):
    from 核心系统.流程控制器 import 流程控制器
    registry = 插件管理器()
    plugin = Plugin()
    plugin.插件标识 = canonical
    registry.注册插件(plugin)
    controller = 流程控制器(registry, 运行数据管理器(tmp_path / "default"))
    current = 运行数据管理器(tmp_path / "selected")
    current.创建运行()
    payload = {"数据管理器": current, "候选编号": "C1", "操作": "标记无法确认"}
    result = getattr(controller, method)(payload)
    assert result == payload and result is not payload
    assert result["数据管理器"] is current


def test_毒理公开查询保留来源选择校验及批次(tmp_path):
    import pandas as pd
    from 核心系统.流程控制器 import 流程控制器
    from 核心系统.毒理分析 import 运行毒理公开数据查询
    seen = []
    class Evidence(Plugin):
        插件标识 = "公开证据聚合"
        def 执行(self, context):
            seen.append(context)
            return context["公开毒理候选"]
    registry = 插件管理器()
    registry.注册插件(Evidence())
    manager = 运行数据管理器(tmp_path)
    controller = 流程控制器(registry, manager)
    assert controller.执行毒理公开数据查询({}).empty and seen == []
    session = {"来源策略": {"启用公开数据源": ["PubChem GHS"], "是否允许缓存结果": False}}
    with pytest.raises(ValueError, match="已确认化合物清单"):
        controller.执行毒理公开数据查询(session)
    session.update({"化合物清单": [{"候选编号": "C1"}], "化合物批次": {"批次编号": "B1"}})
    result = controller.执行毒理公开数据查询(session)
    direct = 运行毒理公开数据查询(manager, registry.获取插件, session)
    pd.testing.assert_frame_equal(result, direct)
    assert result.iloc[0]["批次编号"] == "B1"
    assert result.iloc[0]["来源运行编号"] == result.iloc[0]["确认清单标识"] == ""
    assert seen[0]["数据管理器"] is manager and seen[0]["允许使用缓存"] is False
    assert session["化合物清单"] == [{"候选编号": "C1"}]


@pytest.mark.parametrize("identifier", ["../x", "a/b", "a\\b", "C:\\x", "C:x", "/x", "", " ", ".", "..", "a..b", None])
@pytest.mark.parametrize("running", [False, True])
def test_数据标识读写同样拒绝路径逃逸(tmp_path, identifier, running):
    import pandas as pd
    from 核心系统.数据管理接口 import 文件数据访问管理器
    manager = 运行数据管理器(tmp_path) if running else 文件数据访问管理器(tmp_path)
    if running:
        manager.创建运行()
    for method in ("保存中间结果", "保存筛选结果", "保存最终结果", "保存软件数据库表格"):
        with pytest.raises(ValueError, match="数据标识"):
            getattr(manager, method)(identifier, pd.DataFrame({"值": [1]}))
    for method in ("读取中间结果", "读取筛选结果", "读取最终结果", "读取软件数据库表格", "结果存在"):
        with pytest.raises(ValueError, match="数据标识"):
            getattr(manager, method)(identifier)
    assert not list(tmp_path.rglob("*.csv"))


@pytest.mark.parametrize("identifier", ["合法中文_123", "existing_name.csv", "run_123_结果"])
def test_合法数据标识保留内容与名字(tmp_path, identifier):
    import pandas as pd
    manager = 运行数据管理器(tmp_path)
    manager.创建运行()
    expected = pd.DataFrame({"值": [1, 2]})
    for save, read in (("保存中间结果", "读取中间结果"), ("保存筛选结果", "读取筛选结果"),
                       ("保存最终结果", "读取最终结果")):
        path = getattr(manager, save)(identifier, expected)
        assert path.name == (identifier if identifier.endswith(".csv") else identifier + ".csv")
        pd.testing.assert_frame_equal(getattr(manager, read)(identifier), expected)
    manager.保存软件数据库表格(identifier, expected)
    pd.testing.assert_frame_equal(manager.读取软件数据库表格(identifier), expected.astype(str))
