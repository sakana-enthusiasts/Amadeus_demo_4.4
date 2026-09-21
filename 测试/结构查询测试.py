"""Structure Query 离线内存回归；不读写项目数据库。"""

from copy import deepcopy
import json
import socket
import subprocess
import sys

import pytest

from 核心系统.结构查询 import (StructureCandidate, StructureQuery, StructureQueryError,
                         SimilarityConfig, adapt_candidates)
from 插件.化学计算.RDKit结构检索插件 import RDKit结构检索插件


def search(mode, text, pool, **kwargs):
    query = StructureQuery(mode, text, "smarts" if mode == "substructure" else "smiles", **kwargs)
    return RDKit结构检索插件().search(query, [StructureCandidate(i, s, "smiles") for i, s in pool])


def ids(result):
    return [h.compound_id for h in result.hits]


def test_exact规范化输入与原始结构保留():
    r = search("exact", "CCO", [("a", "OCC"), ("b", "CC"), ("invalid", "bad")])
    assert ids(r) == ["a"]
    assert r.hits[0].structure == "OCC" and r.hits[0].canonical_structure == "CCO"
    assert r.invalid_candidates[0].status == "invalid_structure"
    assert r.excluded_candidates[0].compound_id == "b"
    assert r.to_dict()["query"]["query"] == "CCO"
    assert r.engine_version and r.result_count == 1
    json.dumps(r.to_dict(), allow_nan=False)


@pytest.mark.parametrize("chirality,expected", [(True, ["same"]), (False, ["other", "same"])])
def test_exact立体设置(chirality, expected):
    r = search("exact", "F[C@H](Cl)Br", [("same", "F[C@H](Cl)Br"),
               ("other", "F[C@@H](Cl)Br")], use_chirality=chirality)
    assert ids(r) == expected
    assert r.to_dict()["settings"]["use_chirality"] is chirality


@pytest.mark.parametrize("form", ["[13CH3]O", "C[O-]", "CO.[Na+]", "C=O"])
def test_exact不合并不同化学形式或同位素(form):
    assert not search("exact", "CO", [("different", form)], use_chirality=False).hits


def test_substructure多匹配无命中和上限警告():
    r = search("substructure", "[OX2H]", [("a", "OCCO"), ("b", "CC"), ("bad", "x")])
    assert ids(r) == ["a"] and r.hits[0].match_count == 2
    assert len(r.hits[0].atom_indices) == 2
    assert r.excluded_candidates[0].match_count == 0
    assert len(r.invalid_candidates) == 1
    capped = search("substructure", "[OX2H]", [("a", "OCCO")], max_matches=1)
    assert capped.hits[0].warning and capped.hits[0].match_count == 1


@pytest.mark.parametrize("chirality,expected", [(True, ["same"]), (False, ["other", "same"])])
def test_substructure立体设置(chirality, expected):
    r = search("substructure", "F[C@H](Cl)Br", [("same", "F[C@H](Cl)Br"),
               ("other", "F[C@@H](Cl)Br")], use_chirality=chirality)
    assert ids(r) == expected
    assert r.to_dict()["settings"]["use_chirality"] is chirality


@pytest.mark.parametrize("mode,text", [("substructure", "["), ("exact", "bad"), ("similarity", "bad")])
def test_无效查询不是零命中(mode, text):
    with pytest.raises(StructureQueryError, match="invalid_query"):
        search(mode, text, [])


def test_similarity批量分数元数据与稳定排序():
    pool = [("z", "OCC"), ("a", "CCO"), ("different", "c1ccccc1"), ("bad", "bad")]
    r = search("similarity", "CCO", pool)
    assert ids(r) == ["a", "z", "different"]
    assert [h.score for h in r.hits[:2]] == [1, 1]
    assert r.hits[-1].score < 1
    assert r == search("similarity", "CCO", list(reversed(pool)))
    assert len(r.invalid_candidates) == 1
    settings = r.to_dict()["settings"]
    assert settings["similarity"] == {"fingerprint_type": "Morgan", "radius": 2,
        "fp_size": 2048, "metric": "Tanimoto", "threshold": None, "top_n": None}
    assert r.engine == "RDKit" and r.engine_version


@pytest.mark.parametrize("threshold,top_n,expected", [
    (1, None, ["a", "z"]), (None, 1, ["a"]), (1, 1, ["a"]),
    (0, 3, ["a", "z", "different"]),
])
def test_similarity阈值然后top_n(threshold, top_n, expected):
    r = search("similarity", "CCO", [("z", "OCC"), ("a", "CCO"), ("different", "c1ccccc1")],
               similarity=SimilarityConfig(threshold=threshold, top_n=top_n))
    assert ids(r) == expected
    assert len(r.hits) + len(r.excluded_candidates) == 3


@pytest.mark.parametrize("kwargs", [{"threshold": -1}, {"threshold": float("nan")},
    {"threshold": True}, {"top_n": 0}, {"top_n": True}, {"radius": -1}, {"fp_size": 0},
    {"metric": "Dice"}])
def test_similarity无效配置拒绝(kwargs):
    with pytest.raises(StructureQueryError):
        SimilarityConfig(**kwargs)


def test_明确字段适配和身份拒绝():
    original = [{"编号": "a", "本地结构": "CCO"}, {"编号": "missing"}]
    snapshot = deepcopy(original)
    candidates = adapt_candidates(original, id_field="编号", structure_field="本地结构", structure_format="smiles")
    assert original == snapshot and candidates[1].structure == ""
    with pytest.raises(StructureQueryError):
        adapt_candidates(original, id_field="guess", structure_field="本地结构", structure_format="smiles")
    with pytest.raises(StructureQueryError, match="重复"):
        RDKit结构检索插件().search(StructureQuery("exact", "CCO", "smiles"), [candidates[0]] * 2)


def test_公共契约独立导入无RDKit依赖():
    code = "import sys; import 核心系统.结构查询; assert not any(n.startswith('rdkit') for n in sys.modules)"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_发现入口顺序排除隔离兼容且离线(monkeypatch):
    import 核心系统.配方研发流程 as flow
    from 核心系统.默认装配 import 创建默认插件管理器
    getter = 创建默认插件管理器().获取插件
    from 核心系统.目标规格 import Criterion, TargetProfile
    pool = [{"物质编号": i, "化学名称": i, "SMILES": s, "分子量_g_mol": 100,
        "来源类型": "用户独立输入", "数据来源": "内存合成测试", "相态": "液体",
        "密度_g_mL": 1, "密度温度_C": 20, "纯物质RI": 1.4,
        "RI温度_C": 20, "RI波长_nm": 589.3, "纯物质黏度_mPa_s": 1,
        "黏度温度_C": 20, "范特霍夫因子": 1}
        for i, s in [("a", "CCO"), ("b", "OCC"), ("excluded", "CC"), ("invalid", "bad")]]
    cfg = {"物性条件": {"温度_C": 20, "波长_nm": 589.3}, "目标折射率": 1.4,
        "优化轮数": 0, "最小组分数": 2, "最大组分数": 2}
    snapshot, events = deepcopy(pool), []
    def offline(*args, **kwargs):
        pytest.fail("结构查询与发现不得联网")
    monkeypatch.setattr(socket.socket, "connect", offline)
    monkeypatch.setattr(socket, "create_connection", offline)
    monkeypatch.setattr(flow, "运行验证模式", lambda **kw: {"体系": [], "待补文献协议": []})
    legacy = flow.运行发现模式(pool, cfg)
    assert legacy == flow.运行发现模式(pool, cfg, 结构查询=None)
    class Engine:
        def search(self, query, candidates):
            events.append("structure")
            return RDKit结构检索插件().search(query, candidates)
    original_compile = flow.compile_profile
    def compiled(*args, **kwargs):
        assert events == ["structure"]
        events.append("profile")
        return original_compile(*args, **kwargs)
    monkeypatch.setattr(flow, "compile_profile", compiled)
    original_filter = getter("独立候选分子筛选").执行
    def filtered(ctx):
        assert events[-1] == "profile"
        assert {x["物质编号"] for x in ctx["物质库"]} == {"a", "b"}
        events.append("filter")
        return original_filter(ctx)
    monkeypatch.setattr(getter("独立候选分子筛选"), "执行", filtered)
    original_combine = getter("自动配方组合").执行
    def combine(ctx):
        assert events[-1] == "filter"
        assert {x["物质编号"] for x in ctx["物质库"]} == {"a", "b"}
        events.append("combine")
        return original_combine(ctx)
    monkeypatch.setattr(getter("自动配方组合"), "执行", combine)
    original_sort = getter("配方候选排序").执行
    def sort(ctx):
        events.append("sort")
        return original_sort(ctx)
    monkeypatch.setattr(getter("配方候选排序"), "执行", sort)
    def benchmark(**kwargs):
        assert events[-1] == "sort"
        events.append("benchmark")
        return {"体系": [], "待补文献协议": []}
    monkeypatch.setattr(flow, "运行验证模式", benchmark)
    p = TargetProfile("test", {"molecular_weight": Criterion(role="hard_constraint", upper=200)})
    r = flow.运行发现模式(pool, cfg, 目标规格=p, 获取插件=getter,
        结构查询=StructureQuery("exact", "CCO", "smiles"), 结构检索器=Engine(),
        结构字段映射={"id_field": "物质编号", "structure_field": "SMILES", "structure_format": "smiles"})
    assert events == ["structure", "profile", "filter", "combine", "sort", "benchmark"]
    assert r["候选"] and pool == snapshot
    assert all({x["成分键"] for x in f["成分"]} == {"a", "b"} for f in r["候选"])
    assert r["结构查询结果"]["result_count"] == 2 and r["结构查询结果"]["invalid_count"] == 1
    assert {x["物质编号"] for x in r["排除分子"]} == {"excluded", "invalid"}
    json.dumps(r, allow_nan=False)


def test_发现入口要求显式映射():
    from 核心系统.配方研发流程 import 运行发现模式
    with pytest.raises(StructureQueryError, match="映射"):
        运行发现模式([], {}, 结构查询=StructureQuery("exact", "CCO", "smiles"))
