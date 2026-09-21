from copy import deepcopy
from dataclasses import replace
import json

import pytest

from 核心系统.公开证据.执行桥 import EvidenceBridgeConfig, PublicEvidenceExecutionBridge
from 核心系统.公开证据.数据结构 import EvidenceRequest, PropertyEvidence
from 核心系统.公开证据.证据存储 import SQLiteEvidenceRepository
from 核心系统.公开证据.证据选择器 import EvidenceResolver
from 核心系统.配方研发流程 import 运行发现模式
from 核心系统.目标规格 import Criterion, TargetProfile
from 核心系统.目标规格.执行计划 import compile_profile
from 插件.配方生成.发现约束插件 import 评价规格指标
from 插件.配方生成.配方输入组装插件 import 配方输入组装插件
from 设置.公开物性样例 import 公开物性演示库, 默认发现配置


def evidence(prop="molecular_weight", value=18.01528, unit="g/mol", **kwargs):
    return PropertyEvidence("pubchem:962", "neutral", prop, value, unit,
        observed_structure="O", evidence_type=kwargs.pop("evidence_type", "measured"),
        source=kwargs.pop("source", "fixture"), method="offline fixture", **kwargs)


def request(prop="molecular_weight", **kwargs):
    return EvidenceRequest("pubchem:962", prop, chemical_form="neutral", observed_structure="O", **kwargs)


@pytest.fixture
def repo(tmp_path):
    with SQLiteEvidenceRepository(tmp_path / "evidence.sqlite") as repository:
        yield repository


def test_off_never_accesses_dependencies():
    class Bomb:
        def __getattr__(self, name):
            raise AssertionError(name)
    rows = [{"物质编号": "water"}]
    bridge = PublicEvidenceExecutionBridge(Bomb(), resolver=Bomb(), fetcher=Bomb())
    result, report = bridge.apply(rows, Bomb())
    assert result is rows and report == {}


def test_cache_only_no_provider_and_preserves_all_sources(repo):
    records = [evidence(), evidence(value=19, evidence_type="predicted", model_name="test", model_version="v1")]
    repo.add(records)
    def forbidden(*args):
        raise AssertionError("network")
    rows = [{"物质编号": "water", "分子计算属性": {"logp": {"value_kind": "computed"}}}]
    original = deepcopy(rows)
    view, report = PublicEvidenceExecutionBridge(repo, fetcher=forbidden).apply(rows,
        {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert rows == original
    assert {e.evidence_id for e in repo.query()} == {e.evidence_id for e in records}
    assert view[0]["分子量_g_mol"] == 18.01528
    entry = report["公开证据执行结果"][0]
    assert entry["applied"] and entry["evidence_type"] == "measured"
    assert {e["evidence_type"] for e in entry["provenance"]} == {"measured", "predicted"}
    assert view[0]["分子计算属性"] == original[0]["分子计算属性"]
    json.dumps(report, allow_nan=False)


def test_conflicts_and_user_values_are_not_overwritten(repo):
    repo.add([evidence(), evidence(value=40, source="second")])
    bridge = PublicEvidenceExecutionBridge(repo)
    view, report = bridge.apply([{"物质编号": "water"}], {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert "分子量_g_mol" not in view[0]
    assert report["公开证据执行结果"][0]["resolver_status"] == "conflict"
    view, report = bridge.apply([{"物质编号": "water", "分子量_g_mol": 30}],
        {"water": [request(sources=("fixture",))]}, EvidenceBridgeConfig("cache_only"))
    assert view[0]["分子量_g_mol"] == 30
    assert report["公开证据执行结果"][0]["conflict"]


def test_fetch_missing_only_and_limit_before_io(repo):
    calls = []
    def fetch(identities):
        calls.append(identities)
        repo.add([evidence()])
    bridge = PublicEvidenceExecutionBridge(repo, fetcher=fetch)
    rows = [{"物质编号": "water"}]
    for _ in range(2):
        view, _ = bridge.apply(rows, {"water": [request()]}, EvidenceBridgeConfig("fetch_missing"))
        assert view[0]["分子量_g_mol"] == 18.01528
    assert len(calls) == 1 and calls[0][0].compound_id == "pubchem:962"
    with pytest.raises(ValueError, match="硬上限"):
        bridge.apply([{"物质编号": "a"}, {"物质编号": "b"}],
            {i: [replace(request(), compound_id=i)] for i in ("a", "b")}, EvidenceBridgeConfig("fetch_missing", 1))
    assert len(calls) == 1


@pytest.mark.parametrize("change", [{"chemical_form": None}, {"observed_structure": None},
    {"allow_unknown_conditions": True}, {"property_id": "logp"}])
def test_explicit_identity_conditions_and_supported_properties(repo, change):
    with pytest.raises(ValueError):
        PublicEvidenceExecutionBridge(repo).apply([{"物质编号": "water"}],
            {"water": [replace(request(), **change)]}, EvidenceBridgeConfig("cache_only"))


@pytest.mark.parametrize("e", [evidence(unit="unknown"), evidence(value=float("nan")),
    evidence(value=-1), evidence(evidence_type="summary"), evidence(evidence_type="derived")])
def test_unreviewed_or_invalid_values_do_not_execute(repo, e):
    # Invalid numeric records can be supplied by an injected resolver; no invalid fixture is persisted.
    class Resolver:
        def resolve(self, req, records):
            from 核心系统.公开证据.数据结构 import ResolvedProperty
            return ResolvedProperty(req, "resolved", selected=e)
    view, report = PublicEvidenceExecutionBridge(repo, resolver=Resolver()).apply(
        [{"物质编号": "water"}], {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert "分子量_g_mol" not in view[0] and not report["公开证据执行结果"][0]["applied"]


def test_four_properties_feed_existing_assembly_and_preserve_original(repo):
    records = [evidence(), evidence("density", .9982, "g/mL", temperature=293.15),
        evidence("refractive_index", 1.333, "", temperature=293.15, phase="liquid", wavelength={"value": 589.3, "unit": "nm"}),
        evidence("viscosity", 1.002, "cP", temperature=293.15, phase="liquid")]
    repo.add(records)
    rows = [{"物质编号": "water", "数据来源": "explicit user pool"}]
    reqs = [request(e.property_id) for e in records]
    view, _ = PublicEvidenceExecutionBridge(repo).apply(rows, {"water": reqs}, EvidenceBridgeConfig("cache_only"))
    result = 配方输入组装插件().执行({"物质库": view,
        "物性条件": {"温度_C": 20, "波长_nm": 589.3},
        "配方定义": {"纯组分验证": True, "组分": [{"物质编号": "water", "角色": "主溶剂", "用量": 1, "单位": "mL"}]}})
    assert result["成分"][0]["质量_g"] == pytest.approx(.9982)
    assert result["成分"][0]["纯物质黏度_mPa_s"] == pytest.approx(1.002)
    assert len(result["成分"][0]["公开证据"]) == 4
    assert "分子量_g_mol" not in rows[0]


def test_missing_fetch_backend_is_explicit(repo):
    view, report = PublicEvidenceExecutionBridge(repo).apply([{"物质编号": "water"}],
        {"water": [request()]}, EvidenceBridgeConfig("fetch_missing"))
    assert report["公开证据查询状态"] == "capability_unavailable"
    assert "分子量_g_mol" not in view[0]


@pytest.mark.parametrize("changes", [{"temperature": 310.15}, {"chemical_form": "salt"},
    {"observed_structure": "CCO"}, {"evidence_type": "predicted"}])
def test_conditions_form_structure_and_measured_request_do_not_cross(repo, changes):
    repo.add([replace(evidence("density", 1, "g/mL", temperature=293.15), **changes)])
    view, report = PublicEvidenceExecutionBridge(repo).apply([{"物质编号": "water"}],
        {"water": [request("density", temperature=293.15, measured_only=True)]}, EvidenceBridgeConfig("cache_only"))
    assert "密度_g_mL" not in view[0]
    assert report["公开证据执行结果"][0]["resolver_status"] == "missing"


def test_default_factory_is_lazy_and_fetcher_reuses_aggregate(repo, monkeypatch):
    from 核心系统.默认装配 import 创建公开证据执行桥
    from 插件.公开数据.公开证据聚合插件 import 公开证据聚合插件
    calls = []
    resolver = EvidenceResolver()
    def execute(self, context):
        calls.append(context)
        context["证据存储"].add([evidence()])
    monkeypatch.setattr(公开证据聚合插件, "执行", execute)
    bridge = 创建公开证据执行桥(repo, 证据选择器=resolver, 查询上下文={"公开数据源": ["pubchem"]})
    assert not calls
    bridge.apply([{"物质编号": "water"}], {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert not calls
    bridge.apply([{"物质编号": "water"}], {"water": [request()]}, EvidenceBridgeConfig("fetch_missing"))
    assert len(calls) == 1
    assert calls[0]["证据选择器"] is resolver and calls[0]["证据存储"] is repo
    assert calls[0]["允许网络公开查询"] is True


def test_evidence_requirement_distinguishes_prediction_and_user_original(repo):
    profile = TargetProfile.from_dict({"target_profile_version": "1.0",
        "name": "bridge", "criteria": {"molecular_weight": {"role": "hard_constraint", "upper": 20,
        "evidence_requirement": "measured_only"}}})
    assert not compile_profile(profile)[1]["passed"]
    plan, preflight = compile_profile(profile, public_evidence_enabled=True)
    assert preflight["passed"]
    repo.add([evidence(evidence_type="predicted")])
    bridge = PublicEvidenceExecutionBridge(repo)
    view, _ = bridge.apply([{"物质编号": "water"}], {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert 评价规格指标(plan.criteria[0], view[0])["状态"] == "unknown"
    repo.add([evidence()])
    view, _ = bridge.apply([{"物质编号": "water"}], {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert 评价规格指标(plan.criteria[0], view[0])["证据类型"] == "measured"
    view, _ = bridge.apply([{"物质编号": "water", "分子量_g_mol": 18, "数据来源": "user"}],
        {"water": [request()]}, EvidenceBridgeConfig("cache_only"))
    assert 评价规格指标(plan.criteria[0], view[0])["状态"] == "unknown"


def test_discovery_off_exact_equivalence_and_bridge_runs_before_filter(repo):
    pool, config = 公开物性演示库()[:1], 默认发现配置()
    config.update(最大组分数=1, 优化轮数=0)
    baseline = 运行发现模式(pool, config)
    class Bomb:
        def apply(self, *args):
            raise AssertionError("disabled")
    assert baseline == 运行发现模式(pool, config, 公开证据配置=EvidenceBridgeConfig(), 公开证据执行桥=Bomb())
    pool[0].pop("分子量_g_mol")
    original = deepcopy(pool)
    repo.add([evidence()])
    result = 运行发现模式(pool, config, 公开证据配置=EvidenceBridgeConfig("cache_only"),
        公开证据执行桥=PublicEvidenceExecutionBridge(repo), 公开证据请求={"water": [request()]},
        约束={"分子约束": {"分子量_g_mol": {"最大": 19}}})
    assert result["公开证据执行结果"][0]["applied"]
    assert result["生成数量"] > 0 and not result["排除分子"]
    assert pool == original and result["物质库快照"] == original
