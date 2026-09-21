import json
from dataclasses import replace

import pytest

from 核心系统.公开证据.数据结构 import CompoundIdentity, EvidenceRequest, PropertyEvidence
from 核心系统.公开证据.数据源注册表 import ProviderRegistry
from 核心系统.公开证据.原始响应缓存 import RawResponseCache
from 核心系统.公开证据.证据存储 import SQLiteEvidenceRepository, DuckDBEvidenceRepository, ParquetEvidenceRepository
from 核心系统.公开证据.证据选择器 import EvidenceResolver
from 核心系统.公开证据.身份标准化 import standardize_identity
from 插件.公开数据.公开证据聚合插件 import 公开证据聚合插件
from 插件.公开数据.providers.网络客户端 import CachedHTTPClient, CacheMissError
from 插件.公开数据.providers.pubchem import PubChemProvider
from 插件.公开数据.providers.pubchem.parser import PUGViewParser
from 插件.公开数据.providers.comptox import CompToxProvider
from 插件.公开数据.providers.comptox.parser import CTXParser
from 插件.公开数据.providers.nist.parser import WebBookParser
from 插件.公开数据.providers.thermoml import ThermoMLProvider
from 插件.公开数据.providers.thermoml.parser import ThermoMLParser


def ev(value=10, **kwargs):
    return PropertyEvidence(compound_id="A", chemical_form="free_base", property_id="water_solubility",
        value=value, source=kwargs.pop("source", "pubchem"), unit=kwargs.pop("unit", "g/L"),
        temperature=kwargs.pop("temperature", 298.15), pH=kwargs.pop("pH", 7),
        solvent=kwargs.pop("solvent", "water"), evidence_type=kwargs.pop("evidence_type", "measured"), **kwargs)


def request(**kwargs):
    return EvidenceRequest("A", "water_solubility", chemical_form="free_base", temperature=298.15,
                           pH=7, solvent="water", measured_only=True, **kwargs)


@pytest.mark.parametrize("backend", [SQLiteEvidenceRepository, DuckDBEvidenceRepository, ParquetEvidenceRepository])
def test_长表查询保留多源条件原始值并去重(tmp_path, backend):
    path = tmp_path / ("shards" if backend is ParquetEvidenceRepository else "evidence.db")
    with backend(path) as repo:
        items = [ev(), ev(7.8, source="comptox"), ev(15, source="thermoml", temperature=310.15)]
        repo.add(items)
        repo.add(items)
        assert len(repo.query(compound_id="A")) == 3
        found = repo.query(property_id="water_solubility", sources=("pubchem", "comptox"), temperature_range=(293.15, 303.15))
        assert len(found) == 2
        assert found[0] in items and found[1] in items
        assert repo.query(compound_id="A' OR 1=1 --") == []
        repo.add([])
        repo.add([ev(22, pH=8)])
        assert len(repo.query()) == 4


def test_duckdb导出parquet可经独立后端无损读回(tmp_path):
    directory = tmp_path / "export"
    with DuckDBEvidenceRepository(tmp_path / "e.duckdb") as repo:
        original = ev(uncertainty={"expanded": 1, "coverage_factor": 2}, reference={"doi": "test"})
        repo.add([original])
        repo.export_parquet(directory / "evidence.parquet")
    with ParquetEvidenceRepository(directory) as repo:
        assert repo.query() == [original]


def test_条件与类型筛选不把预测或未知条件当实验():
    records = [ev(50, evidence_type="predicted"), ev(60, temperature=None), ev(80, pH=3),
               ev(90, solvent="ethanol"), ev(15, temperature=310.15), ev()]
    result = EvidenceResolver().resolve(request(), records)
    assert result.status == "resolved" and result.selected.value == 10
    assert EvidenceResolver().resolve(request(), records[:-1]).status == "missing"


def test_标准化单位后判定跨源冲突且不取平均():
    result = EvidenceResolver().resolve(request(), [ev(), ev(7800, source="comptox", unit="mg/L")])
    assert result.status == "conflict" and result.selected is None and len(result.evidence_ids) == 2
    result = EvidenceResolver().resolve(request(), [ev(), ev(10000, source="comptox", unit="mg/L")])
    assert result.status == "resolved" and result.selected.value == 10


def test_盐形式和条件不同不能静默混用():
    salt = replace(ev(100), chemical_form="hydrochloride")
    assert EvidenceResolver().resolve(request(), [salt]).status == "missing"
    assert EvidenceResolver().resolve(EvidenceRequest("A", "water_solubility"), [ev(), salt]).status == "conflict"


@pytest.mark.parametrize("qualifier,value", [("<", 10), ("range", {"lower": 7, "upper": 10}), ("text", "insoluble")])
def test_限定值不会变成确定值(qualifier, value):
    assert EvidenceResolver().resolve(request(), [ev(value, qualifier=qualifier)]).status == "missing"


def raw(cache, payload, source="pubchem", endpoint="fixture", status=200):
    return cache.save(source, endpoint, "1", status, json.dumps(payload) if not isinstance(payload, str) else payload, "v1")


def test_raw先落盘503可重试解析器更新离线复用():
    cache = RawResponseCache()
    calls = []
    class Response:
        headers = {"Retry-After": "0"}
        text = '{"payload":1}'
        def __init__(self, code):
            self.status_code = code
    def get(*args, **kwargs):
        calls.append(args)
        return Response(503 if len(calls) == 1 else 200)
    client = CachedHTTPClient(cache, "pubchem", "v1", allow_network=True, request_get=get, sleeper=lambda _: None)
    result = client.get("fixture")
    assert result.json() == {"payload": 1}
    assert [r.status_code for r in cache.records()] == [503, 200]
    offline = CachedHTTPClient(cache, "pubchem", "v2", allow_network=False)
    assert offline.get("fixture").raw_record_id == result.raw_record_id
    assert offline.get("fixture").cache_hit
    with pytest.raises(CacheMissError):
        offline.get("missing")
    cache.close()


def test_临时失败不能变成永久空缓存():
    cache = RawResponseCache()
    raw(cache, {}, status=503)
    assert cache.get("pubchem", "fixture") is None
    cache.close()


def test_身份多CID不自动采用及unsupported不报错():
    cache = RawResponseCache()
    provider = PubChemProvider(CachedHTTPClient(cache, "pubchem", "v1"))
    url = provider.rest.base + "/compound/name/ambiguous/cids/JSON"
    raw(cache, {"IdentifierList": {"CID": [1, 2]}}, endpoint=url)
    identity = CompoundIdentity("A", identifiers={"name": "ambiguous"})
    assert provider.resolve_identity(identity).status == "identity_conflict"
    assert provider.fetch_bioactivity(identity).status == "unsupported"
    cache.close()


def test_pubchem动态目录双通道保留证据及可离线重解析(tmp_path):
    cache = RawResponseCache()
    provider = PubChemProvider(CachedHTTPClient(cache, "pubchem", "v1"))
    identity = CompoundIdentity("A", "free_base", identifiers={"pubchem_cid": "1"})
    raw(cache, {"PropertyTable": {"Properties": [{"CID": 1, "XLogP": 1, "MolecularWeight": "46.07", "SMILES": "CCO"}]}},
        endpoint=provider.rest.base + "/compound/cid/1/property/" + ",".join(__import__("插件.公开数据.providers.pubchem.mapping", fromlist=["REST_PROPERTIES"]).REST_PROPERTIES) + "/JSON")
    index_url = provider.view.base + "/index/compound/1/JSON"
    raw(cache, {"Record": {"Section": [{"TOCHeading": "Experimental Properties", "Section": [
        {"TOCHeading": "Solubility"}, {"TOCHeading": "Unsupported Heading"}]}]}}, endpoint=index_url)
    heading_url = provider.view.base + "/data/compound/1/JSON?heading=Solubility"
    payload = {"Record": {"RecordNumber": 1, "Reference": [{"ReferenceNumber": 1, "SourceName": "Paper"}],
        "Section": [{"TOCHeading": "Solubility", "Information": [{"ReferenceNumber": 1, "Value": {
        "StringWithMarkup": [{"String": "10 g/L in water at 25 °C, pH 7 measured"},
                             {"String": "15 g/L in water at 37 °C, pH 7 measured"}]}}]}]}}
    raw(cache, payload, endpoint=heading_url)
    registry = ProviderRegistry()
    registry.register(provider)
    with DuckDBEvidenceRepository(tmp_path / "e.duckdb") as repo:
        context = {"公开候选": [identity], "公开数据源": ["pubchem"], "数据源注册表": registry,
                   "原始响应缓存": cache, "证据存储": repo, "物性请求": [request()]}
        result = 公开证据聚合插件().执行(context)
        assert len(result["证据"]) == 5
        assert result["物性采用结果"][0].selected.value == 10
        assert result["查询日志"].iloc[0]["status"] == "ok"
        assert len(repo.query(property_id="water_solubility")) == 2
        公开证据聚合插件().执行(context)
        assert len(repo.query()) == 5 and len(cache.records()) == 3
    cache.close()


def test_pubchem非水溶解度与未知单位保持原始记录():
    cache = RawResponseCache()
    identity = CompoundIdentity("A", identifiers={"pubchem_cid": "1"})
    payload = {"Record": {"Section": [{"TOCHeading": "Solubility", "Information": [{"Value": {
        "StringWithMarkup": [{"String": "10 g/L in ethanol at 25 °C"}, {"String": "miscible"}, {"String": "10%"}]}}]}]}}
    entries = PUGViewParser().parse(raw(cache, payload), identity, "Solubility")
    assert entries[0].property_id == "solubility" and entries[0].solvent == "ethanol"
    assert entries[1].qualifier == entries[2].qualifier == "text"
    cache.close()


def test_comptox实验预测条件模型与AD分开(monkeypatch):
    cache = RawResponseCache()
    identity = CompoundIdentity("A", "free_base", identifiers={"dtxsid": "DTXSID1"})
    parser = CTXParser()
    data = {"id": 12, "dtxsid": "DTXSID1", "propName": "Water Solubility", "propValue": 7800,
            "propUnit": "mg/L", "expDetailsTemperatureC": 25, "expDetailsPh": 7, "lsDoi": "10.test/example"}
    measured = parser.parse(raw(cache, [data], "comptox"), identity, "experimental")[0]
    predicted = parser.parse(raw(cache, [{**data, "modelName": "OPERA", "adConclusion": "In"}], "comptox"), identity, "predicted")[0]
    assert measured.evidence_type == "measured" and measured.value == 7.8 and measured.temperature == 298.15
    assert predicted.evidence_type == "predicted" and predicted.model_name == "OPERA"
    assert predicted.applicability_domain["adConclusion"] == "In"
    monkeypatch.delenv("COMPTOX_API_KEY", raising=False)
    provider = CompToxProvider(CachedHTTPClient(cache, "comptox", "v1", allow_network=True))
    assert provider.fetch_properties(identity).status == "unconfigured"
    cache.close()


def test_nist平均值与单条实验记录不混淆():
    html = '<table class="data"><tr class="cal"><td>T<sub>boil</sub></td><td>350 ± 2</td><td>K</td><td>AVG</td><td>N/A</td><td>Average</td></tr><tr class="exp"><td>T<sub>boil</sub></td><td>351.2</td><td>K</td><td>EB</td><td>Paper 2001</td><td>at 1 atm</td></tr></table>'
    cache = RawResponseCache()
    entries = WebBookParser().parse(raw(cache, html, "nist"), CompoundIdentity("A", identifiers={"nist_id": "C64175"}))
    assert len(entries) == 2 and entries[0].evidence_type == "summary" and entries[1].evidence_type == "measured"
    assert entries[0].uncertainty == 2 and entries[1].pressure == 101325
    cache.close()


XML = '''<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML"><Citation><sDOI>10.test/paper</sDOI></Citation>
<Compound><RegNum><nOrgNum>1</nOrgNum></RegNum><sStandardInChIKey>KEY</sStandardInChIKey></Compound>
<Compound><RegNum><nOrgNum>2</nOrgNum></RegNum></Compound>
<PureOrMixtureData><nPureOrMixtureDataNumber>1</nPureOrMixtureDataNumber><Component><RegNum><nOrgNum>1</nOrgNum></RegNum></Component>
<Property><nPropNumber>1</nPropNumber><Property-MethodID><PropertyGroup><VolumetricProp><ePropName>Mass density, kg/m3</ePropName><eMethodName>Vibrating tube method</eMethodName></VolumetricProp></PropertyGroup></Property-MethodID><PropPhaseID><ePropPhase>Liquid</ePropPhase></PropPhaseID></Property>
<Constraint><ConstraintID><ConstraintType><ePressure>Pressure, kPa</ePressure></ConstraintType></ConstraintID><nConstraintValue>101.325</nConstraintValue></Constraint>
<Variable><nVarNumber>1</nVarNumber><VariableID><VariableType><eTemperature>Temperature, K</eTemperature></VariableType></VariableID></Variable>
<NumValues><VariableValue><nVarNumber>1</nVarNumber><nVarValue>298.15</nVarValue></VariableValue><PropertyValue><nPropNumber>1</nPropNumber><nPropValue>998.2</nPropValue><CombinedUncertainty><nCombExpandUncertValue>0.2</nCombExpandUncertValue><nCoverageFactor>2</nCoverageFactor></CombinedUncertainty></PropertyValue></NumValues>
</PureOrMixtureData></DataReport>'''


def test_thermoml命名空间条件不确定度文献与混合物无损保存():
    cache = RawResponseCache()
    identity = CompoundIdentity("A", "free_base", inchikey="KEY", identifiers={"thermoml_org_num": "1"})
    parser = ThermoMLParser()
    record = raw(cache, XML, "thermoml")
    assert parser.resolve_org_number(record, identity) == "1"
    entry = parser.parse(record, identity)[0]
    assert entry.value == 998.2 and entry.temperature == 298.15 and entry.pressure == 101325
    assert entry.method == "Vibrating tube method" and entry.phase == "Liquid"
    assert "nCoverageFactor" in entry.uncertainty["xml"][0] and "10.test/paper" in entry.reference["citation_xml"]
    mixture = XML.replace('<Property>', '<Component><RegNum><nOrgNum>2</nOrgNum></RegNum></Component><Property>', 1)
    mix_entry = parser.parse(raw(cache, mixture, "thermoml"), identity)[0]
    assert mix_entry.chemical_form == "mixture" and mix_entry.compound_id != identity.compound_id
    assert len(mix_entry.extra["components"]) == 2
    with pytest.raises(ValueError):
        parser.resolve_org_number(record, replace(identity, inchikey="DIFFERENT"))
    cache.close()


def test_结构标准化保留盐原件和独立parent():
    identity = CompoundIdentity("salt", "hydrochloride", observed_structure="CC[NH3+].[Cl-]")
    parent = standardize_identity(identity)
    assert parent.observed_structure == identity.observed_structure and parent.chemical_form == "hydrochloride"
    assert parent.standardized_parent_structure == "CCN" and parent.standardization_version


def test_聚合器unsupported不触网而缺失来源隔离(tmp_path):
    cache = RawResponseCache()
    registry = ProviderRegistry()
    registry.register(ThermoMLProvider(CachedHTTPClient(cache, "thermoml", "v1")))
    with SQLiteEvidenceRepository() as repo:
        result = 公开证据聚合插件().执行({"公开候选": [CompoundIdentity("A")], "公开数据源": ["thermoml"],
            "公开能力": ["hazard", "properties"], "证据存储": repo, "原始响应缓存": cache, "数据源注册表": registry})
        assert set(result["查询日志"]["status"]) == {"unsupported", "identity_missing"}
        assert result["证据"] == () and cache.records() == []
    cache.close()


def test_数值单位中附带条件被拆分且保留原始信息():
    cache = RawResponseCache()
    payload = {"Record": {"Section": [{"TOCHeading": "Solubility", "Information": [{"Value": {
        "Number": [1000000], "Unit": "mg/L (at 25 °C)"}}]}]}}
    identity = CompoundIdentity("A", identifiers={"pubchem_cid": "1"})
    entry = PUGViewParser().parse(raw(cache, payload), identity, "Solubility")[0]
    assert entry.value == 1000 and entry.unit == "g/L" and entry.temperature == 298.15
    assert entry.extra["original_information"]["Value"]["Unit"] == "mg/L (at 25 °C)"
    cache.close()


def test_旧GHS缓存迁移后离线保留视图及标准证据(tmp_path):
    import pandas as pd
    from 核心系统.数据管理接口 import 文件数据访问管理器
    manager = 文件数据访问管理器(tmp_path)
    payload = {"Record": {"RecordNumber": 1, "Section": [{"Information": [{"Value": {
        "StringWithMarkup": [{"String": "H302: Harmful if swallowed"}]}}]}]}}
    manager.保存软件数据库表格("PubChem_GHS缓存.csv", pd.DataFrame([{
        "PubChem CID": "1", "原始响应": json.dumps(payload), "查询时间": "2020-01-01T00:00:00+00:00"}]))
    result = 公开证据聚合插件().执行({"数据管理器": manager,
        "公开毒理候选": [{"候选编号": "A", "PubChem CID": "1"}], "允许网络公开查询": False})
    assert result.iloc[0]["查询状态"] == "已查询" and result.iloc[0]["缓存命中"] == "是"
    assert result.iloc[0]["证据可参与条件匹配"] == False
    with SQLiteEvidenceRepository(manager.软件数据库目录 / "公开证据/evidence.sqlite") as repo:
        entry = repo.query()[0]
        assert entry.retrieved_at == "2020-01-01T00:00:00+00:00" and entry.raw_record_id
    cache = RawResponseCache(manager.软件数据库目录 / "公开证据/raw.sqlite")
    assert len(cache.records()) == 1 and cache.records()[0].parser_version == "legacy-ghs-csv-import"
    cache.close()


def test_不一致的observed结构与key拒绝标准化():
    with pytest.raises(ValueError):
        standardize_identity(CompoundIdentity("A", observed_structure="CCO", inchikey="WRONG"))


def test_同候选编号不同observed结构不能混合采用():
    a, b = replace(ev(), observed_structure="CCO"), replace(ev(100), observed_structure="CCN")
    assert EvidenceResolver().resolve(request(), [a, b]).status == "conflict"
    assert EvidenceResolver().resolve(replace(request(), observed_structure="CCO"), [a, b]).selected.value == 10


def test_坏身份隔离并不影响下一候选及不擅自修正原件():
    cache = RawResponseCache()
    registry = ProviderRegistry()
    registry.register(ThermoMLProvider(CachedHTTPClient(cache, "thermoml", "v1")))
    with SQLiteEvidenceRepository() as repo:
        result = 公开证据聚合插件().执行({"公开候选": [
            CompoundIdentity("bad", observed_structure="CCO", inchikey="WRONG"), CompoundIdentity("good")],
            "公开数据源": ["thermoml"], "数据源注册表": registry, "原始响应缓存": cache, "证据存储": repo})
        assert result["查询日志"]["status"].tolist() == ["identity_conflict", "identity_missing"]
        assert result["候选身份"][0].observed_structure == "CCO"
        assert result["候选身份"][0].inchikey == "WRONG"
    cache.close()


@pytest.mark.parametrize("backend", [SQLiteEvidenceRepository, DuckDBEvidenceRepository])
def test_非法证据不能破坏已有数据或下一次写入(backend):
    with backend() as repo:
        repo.add([ev()])
        with pytest.raises(ValueError):
            repo.add([ev(9), ev(float("nan"))])
        assert len(repo.query()) == 1
        repo.add([ev(7.8, source="comptox")])
        assert len(repo.query()) == 2


def test_身份冲突不从旧存储采用历史结果():
    cache = RawResponseCache()
    registry = ProviderRegistry()
    with SQLiteEvidenceRepository() as repo:
        repo.add([replace(ev(), observed_structure="CCO")])
        result = 公开证据聚合插件().执行({"公开候选": [CompoundIdentity("A", observed_structure="CCO", inchikey="WRONG")],
            "公开数据源": [], "数据源注册表": registry, "原始响应缓存": cache, "证据存储": repo,
            "物性请求": [request()]})
        assert result["物性采用结果"][0].status == "identity_conflict"
        assert result["物性采用结果"][0].selected is None
    cache.close()
