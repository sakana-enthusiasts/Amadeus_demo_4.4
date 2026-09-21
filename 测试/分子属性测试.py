"""独立离线、内存/tmp_path回归；不写项目真实数据和公开库。"""

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import socket
import subprocess
import sys

import pandas as pd
import pytest
from rdkit import Chem

from 核心系统.分子属性 import CORE_METRICS, MolecularPropertyResult
from 核心系统.结构查询 import StructureCandidate, StructureQuery, StructureQueryError
from 核心系统.目标规格 import Criterion, TargetProfile
from 核心系统.目标规格.执行计划 import compile_profile
from 插件.化学计算.RDKit分子属性计算器 import RDKit分子属性计算器
from 插件.化学计算.RDKit普通描述符插件 import RDKit普通描述符插件
from 插件.化学计算.确认批次描述符插件 import 确认批次描述符插件
from 插件.配方生成.发现约束插件 import 候选分子筛选插件
from 插件.筛选与评价.用户候选规则筛选插件 import 用户候选规则筛选插件


def calculate(smiles="CCO", metrics=None, **kwargs):
    return RDKit分子属性计算器().calculate([StructureCandidate("a", smiles, "smiles")],
                                          tuple(CORE_METRICS) if metrics is None else metrics, **kwargs)[0]


def values(result):
    return {x.metric_id: x.value for x in result.properties}


def profile(**criteria):
    return TargetProfile("molecular_execution_test", {k: Criterion(**v) for k, v in criteria.items()})


def pool():
    return [{"物质编号": i, "化学名称": i, "SMILES": s, "分子量_g_mol": 100,
             "来源类型": "用户独立输入", "数据来源": "内存合成测试", "相态": "液体",
             "密度_g_mL": 1, "密度温度_C": 20, "纯物质RI": 1.4,
             "RI温度_C": 20, "RI波长_nm": 589.3, "纯物质黏度_mPa_s": 1,
             "黏度温度_C": 20, "范特霍夫因子": 1}
            for i, s in [("a", "CCO"), ("b", "OCC"), ("high", "c1ccccc1"), ("invalid", "bad"), ("missing", None)]]


def config():
    return {"物性条件": {"温度_C": 20, "波长_nm": 589.3}, "目标折射率": 1.4,
            "优化轮数": 0, "最小组分数": 2, "最大组分数": 2, "最大配方数": 100}


MAPPING = {"id_field": "物质编号", "structure_field": "SMILES", "structure_format": "smiles"}


def test_公共模块独立导入无RDKit():
    subprocess.run([sys.executable, "-c", "import sys; import 核心系统.分子属性; "
                    "assert not any(n.startswith('rdkit') for n in sys.modules)"], check=True)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1", None, 10**1000])
def test_available非法值无NaN泄漏(value):
    with pytest.raises(ValueError):
        replace(calculate(metrics=["logp"]).properties[0], value=value)


@pytest.mark.parametrize("changes", [{"status": "made_up"}, {"status": "calculation_failed"},
    {"status": "invalid_structure", "value": 0, "reason": "bad"}, {"engine_version": ""},
    {"source": ""}, {"canonical_structure": None}])
def test_非法状态元数据拒绝(changes):
    with pytest.raises(ValueError):
        replace(calculate(metrics=["logp"]).properties[0], **changes)


def test_乙醇全部核心指标与JSON():
    result = calculate()
    assert values(result) == {
        "logp": pytest.approx(-.0014, abs=.001), "tpsa": pytest.approx(20.23, abs=.01),
        "h_bond_donors": 1, "h_bond_acceptors": 1, "rotatable_bonds": 0,
        "aromatic_rings": 0, "ring_count": 0, "heavy_atom_count": 3,
        "hetero_atom_count": 1, "fraction_csp3": 1, "formal_charge": 0}
    for r in result.properties:
        assert r.status == "available" and math.isfinite(r.value)
        assert r.unit == CORE_METRICS[r.metric_id].unit
        assert r.method == CORE_METRICS[r.metric_id].method
        assert r.engine == "RDKit" and r.engine_version and r.source
        assert r.canonical_structure == "CCO" and r.structure_format == "smiles"
        if CORE_METRICS[r.metric_id].data_type == "int":
            assert type(r.value) is int
    snapshot = result.to_dict()
    json.dumps(snapshot, allow_nan=False)
    snapshot["properties"][0]["value"] = 999
    assert result.properties[0].value != 999


@pytest.mark.parametrize("smiles,expected", [
    ("c1ccccc1", {"aromatic_rings": 1, "ring_count": 1, "heavy_atom_count": 6, "fraction_csp3": 0}),
    ("CCCC", {"rotatable_bonds": 1}), ("[NH4+]", {"formal_charge": 1, "hetero_atom_count": 1}),
    ("CC(=O)[O-]", {"formal_charge": -1}), ("OCCO", {"h_bond_donors": 2, "h_bond_acceptors": 2}),
])
def test_稳定整数及简单性质(smiles, expected):
    actual = values(calculate(smiles))
    assert all(actual[k] == v for k, v in expected.items())


def test_无效单候选隔离不填零不改输入():
    original = [StructureCandidate(i, s, "smiles") for i, s in [("a", "CCO"), ("bad", "bad"), ("empty", "")]]
    snapshot = deepcopy(original)
    results = RDKit分子属性计算器().calculate(original, ["logp", "tpsa"])
    assert original == snapshot
    assert all(r.status == "available" for r in results[0].properties)
    for candidate in results[1:]:
        assert all(r.status == "invalid_structure" and r.value is None and r.reason for r in candidate.properties)
        json.dumps(candidate.to_dict(), allow_nan=False)


def test_计算失败及非有限返回隔离(monkeypatch):
    functions = RDKit分子属性计算器.CORE_FUNCTIONS.copy()
    functions["logp"] = lambda mol: float("nan")
    monkeypatch.setattr(RDKit分子属性计算器, "CORE_FUNCTIONS", functions)
    results = calculate(metrics=["logp", "tpsa"]).properties
    assert results[0].status == "calculation_failed" and results[0].value is None
    assert results[1].status == "available"


def test_批量多个请求同结构只解析一次(monkeypatch):
    original, calls = Chem.MolFromSmiles, []
    def parse(smiles, *args, **kwargs):
        calls.append(smiles)
        return original(smiles, *args, **kwargs)
    monkeypatch.setattr(Chem, "MolFromSmiles", parse)
    RDKit分子属性计算器().calculate([StructureCandidate("a", "CCO", "smiles"),
        StructureCandidate("b", "CCO", "smiles")], tuple(CORE_METRICS), extended_descriptors=["MolWt", "TPSA"])
    assert calls == ["CCO"]
    calls.clear()
    calculate(metrics=[])
    assert not calls


def test_扩展catalog报告不是正式指标(monkeypatch):
    engine = RDKit分子属性计算器()
    catalog = engine.descriptor_catalog()
    assert len(catalog) > 100 and all(x["engine_version"] and not x["target_profile_metric"] for x in catalog)
    names = [x["descriptor_name"] for x in catalog]
    result = calculate(metrics=[], extended_descriptors=names)
    assert len(result.extended_report) == len(catalog)
    assert all(r.descriptor_name and r.engine_version and r.unit is None and r.warning for r in result.extended_report)
    json.dumps(result.to_dict(), allow_nan=False)
    unsupported = calculate(metrics=["unimplemented"], extended_descriptors=["missing_name"])
    assert unsupported.properties[0].status == unsupported.extended_report[0].status == "unsupported"
    assert not compile_profile(profile(rdkit_molwt={"role": "report_only"}))[1]["passed"]
    from rdkit.Chem import Descriptors
    def broken(mol):
        raise RuntimeError("isolated test failure")
    monkeypatch.setattr(Descriptors, "descList", [("broken", broken), ("MolWt", Descriptors.MolWt)])
    report = calculate(metrics=[], extended_descriptors=["broken", "MolWt"]).extended_report
    assert report[0].status == "calculation_failed" and report[1].status == "available"


@pytest.mark.parametrize("metric,kwargs", [("logp", {"unit": "count"}), ("tpsa", {"unit": "nm²"}),
    ("h_bond_donors", {"unit": "e"}), ("logp", {"evidence_requirement": "measured_only"})])
def test_单位或实测要求预检失败(metric, kwargs):
    assert not compile_profile(profile(**{metric: {"role": "report_only", **kwargs}}))[1]["passed"]


@pytest.mark.parametrize("metric", list(CORE_METRICS))
def test_正式指标角色边界(metric):
    for role in ("hard_constraint", "report_only"):
        args = {"role": role, "scope": "molecule"}
        if role == "hard_constraint":
            args["upper"] = 5
        execution, preflight = compile_profile(profile(**{metric: args}))
        assert preflight["passed"] and execution.required_molecular_metrics == (metric,)
        assert execution.criteria[0].binding.source == "分子计算属性"
    assert not compile_profile(profile(**{metric: {"role": "objective", "mode": "minimize"}}))[1]["passed"]


@pytest.mark.parametrize("metric,bounds,allowed", [
    ("logp", {"upper": 0}, True), ("logp", {"lower": 0}, False),
    ("tpsa", {"lower": 20, "upper": 21}, True), ("tpsa", {"upper": 20}, False),
    ("tpsa", {"lower": 21}, False), ("h_bond_donors", {"upper": 1}, True),
    ("h_bond_acceptors", {"upper": 0}, False),
])
def test_molecule硬约束(metric, bounds, allowed):
    p = profile(**{metric: {"role": "hard_constraint", **bounds}})
    execution, _ = compile_profile(p)
    row = pool()[0] | {"分子计算属性": {r.metric_id: r.to_dict() for r in calculate(metrics=[metric]).properties}}
    result = 候选分子筛选插件().执行({"物质库": [row], "执行计划": execution})
    assert bool(result["物质库"]) is allowed
    entry = (result["物质库"] or result["排除分子"])[0]["目标规格评价"][0]
    assert entry["engine_version"] and entry["method"] and entry["property_status"] == "available"


@pytest.mark.parametrize("policy,allowed", [("keep_unknown", True), ("exclude", False)])
def test_缺失策略原始状态保留(policy, allowed):
    execution, _ = compile_profile(profile(logp={"role": "hard_constraint", "upper": 1, "missing_policy": policy}))
    row = pool()[0] | {"logp": 0, "分子计算属性": {r.metric_id: r.to_dict() for r in calculate("bad", ["logp"]).properties}}
    result = 候选分子筛选插件().执行({"物质库": [row], "执行计划": execution})
    assert bool(result["物质库"]) is allowed
    entry = (result["物质库"] or result["排除分子"])[0]["目标规格评价"][0]
    assert entry["合格值"] is None and entry["状态"] == "unknown"
    assert entry["property_status"] == "invalid_structure"


def test_report_only缺失不影响资格及同名用户字段不充当计算():
    execution, _ = compile_profile(profile(logp={"role": "report_only"}))
    result = 候选分子筛选插件().执行({"物质库": [pool()[0] | {"logp": 5}], "执行计划": execution})
    assert result["物质库"][0]["目标规格评价"][0]["合格值"] is None


@pytest.mark.parametrize("with_query", [True, False])
def test_发现流程顺序按需计算及输入隔离(with_query, monkeypatch):
    import 核心系统.配方研发流程 as flow
    from 核心系统.默认装配 import 创建默认插件管理器
    getter = 创建默认插件管理器().获取插件
    original_pool, events = pool(), []
    original_pool[0]["logp"] = 999
    snapshot = deepcopy(original_pool)
    def offline(*args, **kwargs):
        pytest.fail("发现不能联网")
    monkeypatch.setattr(socket.socket, "connect", offline)
    monkeypatch.setattr(socket, "create_connection", offline)
    class Search:
        def search(self, query, candidates):
            from 插件.化学计算.RDKit结构检索插件 import RDKit结构检索插件
            events.append("query")
            return RDKit结构检索插件().search(query, candidates)
    class Calculator(RDKit分子属性计算器):
        def calculate(self, candidates, requested_metrics, **kwargs):
            assert requested_metrics == ("logp",)
            assert len(candidates) == (2 if with_query else 5)
            events.append("descriptor")
            return super().calculate(candidates, requested_metrics, **kwargs)
    old_filter, old_combine, old_sort = getter("独立候选分子筛选").执行, getter("自动配方组合").执行, getter("配方候选排序").执行
    def filtered(ctx):
        assert events[-1] == "descriptor"
        events.append("filter")
        return old_filter(ctx)
    def combined(ctx):
        assert events[-1] == "filter"
        assert {x["物质编号"] for x in ctx["物质库"]} == {"a", "b"}
        assert all(x["分子量_g_mol"] == 100 for x in ctx["物质库"])
        events.append("combine")
        return old_combine(ctx)
    def sorted_(ctx):
        events.append("sort")
        return old_sort(ctx)
    def benchmark(**kwargs):
        assert events[-1] == "sort"
        events.append("benchmark")
        return {"体系": [], "待补文献协议": []}
    monkeypatch.setattr(getter("独立候选分子筛选"), "执行", filtered)
    monkeypatch.setattr(getter("自动配方组合"), "执行", combined)
    monkeypatch.setattr(getter("配方候选排序"), "执行", sorted_)
    monkeypatch.setattr(flow, "运行验证模式", benchmark)
    result = flow.运行发现模式(original_pool, config(),
        目标规格=profile(logp={"role": "hard_constraint", "upper": 0, "missing_policy": "exclude"}),
        结构查询=StructureQuery("exact", "CCO", "smiles") if with_query else None,
        结构字段映射=MAPPING, 结构检索器=Search(), 分子属性计算器=Calculator(), 获取插件=getter)
    assert events == (["query"] if with_query else []) + ["descriptor", "filter", "combine", "sort", "benchmark"]
    assert original_pool == snapshot and result["候选"] and not result["组装失败"]
    assert all({x["成分键"] for x in f["成分"]} == {"a", "b"} for f in result["候选"])
    json.dumps(result, allow_nan=False)


def test_不请求属性不调用计算器及失败预检不启动(monkeypatch):
    import 核心系统.配方研发流程 as flow
    class Fail:
        def calculate(self, *args, **kwargs):
            pytest.fail("不请求descriptor不应调用计算器")
    monkeypatch.setattr(flow, "运行验证模式", lambda **kw: {"体系": [], "待补文献协议": []})
    for p in (None, profile(logp={"role": "disabled"}), profile(molecular_weight={"role": "report_only"})):
        result = flow.运行发现模式(pool()[:2], config(), 目标规格=p, 分子属性计算器=Fail())
        assert "分子属性结果" not in result
    monkeypatch.setattr(flow, "运行数值自检", lambda **kw: pytest.fail("预检失败不得自检"))
    result = flow.运行发现模式(pool(), config(), 目标规格=profile(logp={"role": "objective", "mode": "minimize"}),
                              分子属性计算器=Fail())
    assert not result["执行预检"]["passed"] and result["生成数量"] == 0


def test_发现显式扩展报告与映射要求(monkeypatch):
    import 核心系统.配方研发流程 as flow
    monkeypatch.setattr(flow, "运行验证模式", lambda **kw: {"体系": [], "待补文献协议": []})
    with pytest.raises(StructureQueryError, match="映射"):
        flow.运行发现模式(pool(), config(), 目标规格=profile(logp={"role": "report_only"}))
    result = flow.运行发现模式(pool()[:2], config(), 结构字段映射=MAPPING, 扩展描述符报告=["MolWt"])
    assert result["分子属性结果"][0]["properties"] == ()
    assert result["分子属性结果"][0]["extended_report"][0]["descriptor_name"] == "MolWt"
    assert result["物质库快照"][0]["分子量_g_mol"] == 100


class MemoryManager:
    def __init__(self, data):
        self.data, self.saved = data, {}
    def 读取中间结果(self, name):
        self.input_name = name
        return self.data.copy()
    def 保存中间结果(self, name, data):
        self.saved[name] = data.copy()


@pytest.mark.parametrize("context,input_name,output_name", [
    ({}, "补充数据3_结构映射结果", "补充数据3_RDKit描述符结果"),
    ({"补充数据2描述符处理": True}, "补充数据2_结构映射结果", "补充数据2_RDKit描述符结果"),
    ({"用户描述符处理": True}, "用户导入_结构映射结果", "用户导入_RDKit描述符结果"),
])
def test_旧长表及确认批次兼容(context, input_name, output_name):
    data = pd.DataFrame([{"候选编号": "a", "结构映射_SMILES": "CCO", "原始名称": "ethanol"},
                         {"候选编号": "bad", "结构映射_SMILES": "bad", "结构错误信息": "保留旧原因"}])
    snapshot = data.copy(deep=True)
    manager = MemoryManager(data)
    result = RDKit普通描述符插件().执行(context | {"数据管理器": manager})
    assert manager.input_name == input_name and output_name in manager.saved
    assert set(result.columns) == {"候选编号", "候选名称", "CAS号", "结构来源", "计算工具", "工具版本", "描述符名称", "数值", "是否计算成功", "失败原因"}
    good = result[result["候选编号"] == "a"].set_index("描述符名称")["数值"].to_dict()
    assert len(good) == 27 and good["分子量"] == pytest.approx(46.069)
    assert good["脂水分配指标_MolLogP"] == pytest.approx(-.0014)
    assert good["功能基团_Alcohol"] == "是" and good["功能基团是否人工确认"] == "否"
    assert good["基础官能团"] == "羟基:1"
    bad = result[result["候选编号"] == "bad"]
    assert len(bad) == 9 and not bad["是否计算成功"].any() and bad["数值"].isna().all()
    assert set(bad["失败原因"]) == {"保留旧原因"}
    confirmed = 确认批次描述符插件().执行({"确认清单": data, "批次编号": "test_batch"})
    other = confirmed[confirmed["候选编号"] == "a"].set_index("描述符名称")["数值"].to_dict()
    assert good == other and len(confirmed[confirmed["候选编号"] == "bad"]) == 1
    pd.testing.assert_frame_equal(data, snapshot)
    source = Path("插件/化学计算/确认批次描述符插件.py").read_text(encoding="utf-8")
    assert "._描述符值" not in source and "._Fig1c标签" not in source and "RDKit普通描述符插件" not in source


def test_用户规则复用同一metric不建新引擎():
    from 核心系统.通用规则引擎 import 属性注册表, 通用规则执行器, 规则定义
    registry = 属性注册表.默认()
    assert all(registry.获取(k).单位 == m.unit for k, m in CORE_METRICS.items())
    records = 用户候选规则筛选插件.分子属性记录([calculate(metrics=["logp"])], "r1", ["a"])
    rule = 规则定义("descriptor_rule", "logp上限", "user", ("logp",), "<=", 0, "", True,
                    "无法评估", "排除", "测试", "1")
    result = 通用规则执行器(registry).执行("r1", ["a"], records, [rule])
    assert result.iloc[0]["规则状态"] == "通过"
    assert records.iloc[0]["条件"]["engine_version"]
    missing = 用户候选规则筛选插件.分子属性记录([calculate("bad", ["logp"])], "r1", ["a"])
    assert 通用规则执行器(registry).执行("r1", ["a"], missing, [rule]).iloc[0]["规则状态"] == "无法评估"
