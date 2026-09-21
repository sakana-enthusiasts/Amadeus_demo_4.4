from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from 核心系统.分子标准化 import StandardizationRequest
from 核心系统.分子属性 import CORE_METRICS
from 核心系统.分子属性.描述符契约 import DescriptorRequest
from 核心系统.结构查询 import StructureCandidate, StructureQuery
from 核心系统.配方研发流程 import 运行发现模式
from 插件.化学计算.RDKit分子标准化 import RDKitMoleculeStandardizer
from 插件.化学计算.扩展描述符后端 import RDKitDescriptorCalculator, MordredDescriptorCalculator
from 设置.公开物性样例 import 公开物性演示库, 默认发现配置


def test_salt_parent_charge_and_observed_are_independent():
    request = StandardizationRequest("salt", "CC(=O)[O-].[Na+]")
    plain = RDKitMoleculeStandardizer().standardize([request])[0]
    assert plain.observed_structure == request.observed_structure
    assert plain.parent_structure is None and len(plain.fragments) == 2
    assert "." in plain.calculation_structure and plain.formal_charge == 0
    parent = RDKitMoleculeStandardizer().standardize([StandardizationRequest("salt", request.observed_structure,
        calculation_view="parent", normalize_charge=True)])[0]
    assert parent.observed_structure == request.observed_structure
    assert "." not in parent.calculation_structure
    assert any("FragmentParent" in step.method for step in parent.steps)
    assert any("Uncharger" in step.method for step in parent.steps)
    json.dumps(parent.to_dict(), allow_nan=False)


def test_tautomer_is_explicit_and_invalid_candidate_is_isolated():
    results = RDKitMoleculeStandardizer().standardize([
        StandardizationRequest("a", "CC(O)=C", calculation_view="canonical_tautomer"),
        StandardizationRequest("bad", "not-smiles"), StandardizationRequest("empty", "")])
    assert results[0].canonical_tautomer == "CC(C)=O"
    assert all(x.status == "invalid_structure" and x.calculation_structure is None and x.reason for x in results[1:])
    assert results[0].observed_structure == "CC(O)=C"


def test_rdkit_delegates_and_preserves_core_metrics():
    candidates = [StructureCandidate("a", "CCO", "smiles"), StructureCandidate("bad", "bad", "smiles")]
    result = RDKitDescriptorCalculator().calculate(candidates, DescriptorRequest(("MolWt", "missing")))
    assert result[0].values[0].value == pytest.approx(46.069)
    assert result[0].values[1].status == "unsupported"
    assert result[1].values[0].status == "invalid_structure"
    assert len(CORE_METRICS) == 11 and "MolWt" not in CORE_METRICS
    assert len(RDKitDescriptorCalculator().catalog()) > 100
    json.dumps([x.to_dict() for x in result], allow_nan=False)


def test_mordred_empty_never_loads_and_missing_dependency_is_unavailable(monkeypatch):
    calls = []
    def missing():
        calls.append(True)
        raise ImportError("not installed")
    monkeypatch.setattr(MordredDescriptorCalculator, "_load", staticmethod(missing))
    engine = MordredDescriptorCalculator()
    candidates = [StructureCandidate("a", "CCO", "smiles")]
    assert engine.calculate(candidates, DescriptorRequest((), "Mordred-community"))[0].values == ()
    assert not calls
    result = engine.calculate(candidates, DescriptorRequest(("MW",), "Mordred-community"))
    assert result[0].values[0].status == "capability_unavailable" and result[0].values[0].value is None


def test_mordred_mock_selects_only_requested_2d_and_isolates_errors(monkeypatch):
    calls = []
    class Descriptor:
        def __init__(self, name): self.name = name
        def __str__(self): return self.name
    descriptors = [Descriptor(n) for n in ("MW", "bad", "not_requested")]
    class Calculator:
        def __init__(self, selected, *, ignore_3D):
            assert ignore_3D is True
            self.descriptors = selected
        def __call__(self, mol):
            calls.append([str(d) for d in self.descriptors])
            return [46.069 if str(d) == "MW" else float("nan") for d in self.descriptors]
    module = SimpleNamespace(Calculator=Calculator, descriptors=descriptors)
    monkeypatch.setattr(MordredDescriptorCalculator, "_load", staticmethod(lambda: (module, "test-version")))
    result = MordredDescriptorCalculator().calculate([StructureCandidate("a", "CCO", "smiles")],
        DescriptorRequest(("MW", "bad", "3D_unregistered"), "Mordred-community"))[0]
    assert calls == [["MW", "bad"]]
    assert [v.status for v in result.values] == ["available", "calculation_failed", "unsupported"]
    assert all(v.value_kind == "computed" and v.dimension == "2D" for v in result.values)
    json.dumps(result.to_dict(), allow_nan=False)


def test_no_3d_or_implicit_all_request():
    with pytest.raises(ValueError): DescriptorRequest(("MW",), "Mordred-community", "3D")
    with pytest.raises(ValueError): DescriptorRequest("MW")
    with pytest.raises(ValueError): DescriptorRequest(("MW", "MW"))


def test_discovery_query_precedes_standardization_and_off_is_identical():
    pool, config = 公开物性演示库()[:1], 默认发现配置()
    pool[0]["SMILES"] = "O.[Na+]"
    config.update(最大组分数=1, 优化轮数=0)
    snapshot = deepcopy(pool)
    class Bomb:
        def standardize(self, *args): raise AssertionError("disabled")
        def calculate(self, *args): raise AssertionError("disabled")
    baseline = 运行发现模式(pool, config)
    assert baseline == 运行发现模式(pool, config, 分子标准化器=Bomb(), 描述符计算器=Bomb())
    result = 运行发现模式(pool, config, 结构查询=StructureQuery("exact", "O", "smiles"),
        结构字段映射={"id_field": "物质编号", "structure_field": "SMILES", "structure_format": "smiles"},
        标准化配置={"calculation_view": "parent"}, 描述符请求=DescriptorRequest(("MolWt",)))
    assert not result["分子标准化结果"] and not result["扩展描述符结果"]
    assert pool == snapshot and result["排除分子"]


def test_selected_view_flows_to_descriptor_without_overwriting_observed():
    pool, config = 公开物性演示库()[:1], 默认发现配置()
    pool[0]["SMILES"] = "CCO.[Na+]"
    config.update(最大组分数=1, 优化轮数=0)
    result = 运行发现模式(pool, config,
        结构字段映射={"id_field": "物质编号", "structure_field": "SMILES", "structure_format": "smiles"},
        标准化配置={"calculation_view": "parent"}, 描述符请求=DescriptorRequest(("MolWt",)))
    assert result["扩展描述符结果"][0]["values"][0]["value"] == pytest.approx(46.069)
    assert result["分子标准化结果"][0]["observed_structure"] == "CCO.[Na+]"
    assert result["物质库快照"] == pool
