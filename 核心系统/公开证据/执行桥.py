"""公开证据到执行候选的显式投影；只读原输入，只补缺失字段。"""

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite
from numbers import Real
from typing import Callable, Mapping, Sequence

from .数据结构 import CompoundIdentity, EvidenceRequest, ResolvedProperty
from .证据存储接口 import EvidenceRepository
from .证据选择器 import EvidenceResolver


PROPERTY_FIELDS = {
    "molecular_weight": ("分子量_g_mol", "g/mol", 1.0),
    "density": ("密度_g_mL", "kg/m3", 0.001),
    "refractive_index": ("纯物质RI", "", 1.0),
    "viscosity": ("纯物质黏度_mPa_s", "Pa s", 1000.0),
}
MAX_FETCH_CANDIDATES = 100


@dataclass(frozen=True)
class EvidenceBridgeConfig:
    mode: str = "off"
    max_candidates: int = 20

    def __post_init__(self):
        if self.mode not in {"off", "cache_only", "fetch_missing"}:
            raise ValueError("公开证据模式必须为 off/cache_only/fetch_missing")
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= MAX_FETCH_CANDIDATES:
            raise ValueError("公开证据联网候选上限必须为 1..100")


class PublicEvidenceExecutionBridge:
    """Repository/Resolver 可注入；fetcher 只在显式联网且匹配证据缺失时调用。

    requests 以发现物质编号关联；请求中的 compound_id 是证据库身份，二者不隐式等同。
    fetcher 接受 CompoundIdentity 序列并通过既有公开聚合入口写入同一 repository。
    资源由调用者管理，本对象不打开数据库、不创建网络客户端。
    """

    def __init__(self, repository: EvidenceRepository, *, resolver=None,
                 fetcher: Callable[[Sequence[CompoundIdentity]], object] | None = None):
        self.repository = repository
        self.resolver = resolver if resolver is not None else EvidenceResolver()
        self.fetcher = fetcher

    def apply(self, candidates: list[dict], requests: Mapping[str, Sequence[EvidenceRequest]],
              config: EvidenceBridgeConfig = EvidenceBridgeConfig()):
        if config.mode == "off":
            return candidates, {}
        ids = [x["物质编号"] for x in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("执行桥要求唯一物质编号")
        # Structure Query 可以排除原请求中的候选；只处理留下的候选。
        active = {i: tuple(requests.get(i, ())) for i in ids}
        for items in active.values():
            if len({r.property_id for r in items}) != len(items):
                raise ValueError("同一候选不能重复请求一个属性")
            if len({(r.compound_id, r.observed_structure, r.chemical_form) for r in items}) > 1:
                raise ValueError("同一候选请求的身份不一致")
            for r in items:
                if r.property_id not in PROPERTY_FIELDS:
                    raise ValueError("执行桥首版仅支持 molecular_weight/density/refractive_index/viscosity")
                if not r.compound_id or not r.observed_structure or not r.chemical_form or r.chemical_form == "unspecified":
                    raise ValueError("执行桥要求显式 compound_id、observed_structure 和 chemical_form")
                if r.allow_unknown_conditions:
                    raise ValueError("执行桥不允许采用未知请求条件")
        resolved = {i: [self._resolve(r) for r in items] for i, items in active.items()}
        missing = [i for i, items in resolved.items() if any(r.status == "missing" for r in items)]
        fetch_status = "not_requested"
        if config.mode == "fetch_missing" and missing:
            # 先检查整个批次，再联网，不能截断后静默漏掉候选。
            if len(missing) > config.max_candidates:
                raise ValueError("待查询候选数量超过公开证据联网硬上限")
            if self.fetcher is None:
                fetch_status = "capability_unavailable"
            else:
                identities = [CompoundIdentity(active[i][0].compound_id,
                    chemical_form=active[i][0].chemical_form,
                    observed_structure=active[i][0].observed_structure) for i in missing]
                self.fetcher(identities)
                for i in missing:
                    resolved[i] = [self._resolve(r) for r in active[i]]
                fetch_status = "completed"
        view, report = deepcopy(candidates), []
        for row in view:
            entries = []
            for result in resolved[row["物质编号"]]:
                entry = self._entry(result)
                entry["candidate_id"] = row["物质编号"]
                self._project(row, result, entry)
                entries.append(entry)
                report.append(deepcopy(entry))
            if entries:
                row["公开证据"] = entries
        return view, {"公开证据执行结果": report, "公开证据策略": asdict(config),
                      "公开证据查询状态": fetch_status}

    def _resolve(self, request):
        evidence = self.repository.query(compound_id=request.compound_id,
            property_id=request.property_id, sources=request.sources)
        return self.resolver.resolve(request, evidence)

    def _entry(self, result: ResolvedProperty):
        selected = result.selected
        # 保存完整原证据（含未采用类型/来源），不把规范化值写回 repository。
        evidence = self.repository.query(compound_id=result.request.compound_id,
            property_id=result.request.property_id, sources=result.request.sources)
        return {"compound_id": result.request.compound_id, "property_id": result.request.property_id,
                "value": selected.value if selected else None, "unit": selected.unit if selected else None,
                "conditions": {k: getattr(selected, k) if selected else None for k in
                    ("temperature", "pH", "pressure", "solvent", "concentration", "wavelength", "phase")},
                "chemical_form": selected.chemical_form if selected else result.request.chemical_form,
                "evidence_type": selected.evidence_type if selected else None,
                "source": selected.source if selected else None,
                "method": selected.method if selected else None,
                "model": {"name": selected.model_name, "version": selected.model_version} if selected else None,
                "provenance": [asdict(e) | {"evidence_id": e.evidence_id} for e in evidence],
                "resolver_status": result.status, "conflict": list(result.conflicts),
                "reason": result.reason, "request": asdict(result.request),
                "evidence_ids": list(result.evidence_ids), "applied": False}

    @staticmethod
    def _project(row, result, entry):
        e = result.selected
        if result.status != "resolved" or e is None:
            return
        field, unit, factor = PROPERTY_FIELDS[e.property_id]
        if e.evidence_type not in {"measured", "predicted"}:
            entry["reason"] = "summary/derived 证据只报告，不进入执行字段"
            return
        if e.unit != unit or isinstance(e.value, bool) or not isinstance(e.value, Real) or not isfinite(e.value) or e.value <= 0:
            entry["reason"] = "执行单位未审查或数值不是有限正数"
            return
        value = float(e.value) * factor
        if row.get(field) is not None and row.get(field) != "":
            entry["reason"] = "保留原始用户字段，公开证据独立报告"
            try:
                if abs(float(row[field]) - value) > 1e-9:
                    entry["conflict"].append("用户原值与公开采用值不同，未覆盖或平均")
            except (TypeError, ValueError):
                pass
            return
        extra = {}
        if e.property_id != "molecular_weight":
            if e.temperature is None or not isfinite(e.temperature) or e.temperature <= 0:
                entry["reason"] = "执行物性需要明确温度"
                return
            temperature_field = {"density": "密度温度_C", "refractive_index": "RI温度_C", "viscosity": "黏度温度_C"}[e.property_id]
            extra[temperature_field] = e.temperature - 273.15
        if e.property_id in {"refractive_index", "viscosity"}:
            if e.phase != "liquid" or row.get("相态") not in {None, "", "液体"}:
                entry["reason"] = "仅接受显式纯液体物性"
                return
            extra["相态"] = "液体"
        if e.property_id == "refractive_index":
            # wavelength 的公共契约为带单位对象，不猜测裸数字的量纲。
            w = e.wavelength
            if not isinstance(w, dict) or w.get("unit") != "nm" or type(w.get("value")) not in {int, float} or not isfinite(w["value"]) or w["value"] <= 0:
                entry["reason"] = "折射率波长必须显式为 {value: 正数, unit: nm}"
                return
            extra["RI波长_nm"] = w["value"]
        if e.solvent is not None or e.concentration is not None:
            entry["reason"] = "溶液测量不能替代纯组分物性"
            return
        if any(row.get(k) not in (None, "", v) for k, v in extra.items()):
            entry["reason"] = "公开物性条件与已有用户条件不一致"
            return
        row.update({field: value, **extra})
        entry.update(applied=True, execution_field=field, execution_value=value,
                     execution_unit={"density": "g/mL", "viscosity": "mPa·s"}.get(e.property_id, unit))
