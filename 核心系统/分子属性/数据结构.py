"""工具无关的单分子2D属性契约；不替代物质身份、实测值或配方物性。"""

from dataclasses import asdict, dataclass
from math import isfinite
from types import MappingProxyType
import re


@dataclass(frozen=True)
class MolecularMetric:
    metric_id: str
    descriptor_name: str
    data_type: str
    unit: str
    method: str
    roles: tuple[str, ...] = ("hard_constraint", "report_only")

    def to_dict(self):
        return asdict(self)


CORE_METRICS = MappingProxyType({x.metric_id: x for x in (
    MolecularMetric("logp", "MolLogP", "float", "", "Crippen.MolLogP"),
    MolecularMetric("tpsa", "TPSA", "float", "Å²", "rdMolDescriptors.CalcTPSA"),
    MolecularMetric("h_bond_donors", "NumHDonors", "int", "count", "Lipinski.NumHDonors"),
    MolecularMetric("h_bond_acceptors", "NumHAcceptors", "int", "count", "Lipinski.NumHAcceptors"),
    MolecularMetric("rotatable_bonds", "NumRotatableBonds", "int", "count", "Lipinski.NumRotatableBonds"),
    MolecularMetric("aromatic_rings", "NumAromaticRings", "int", "count", "Lipinski.NumAromaticRings"),
    MolecularMetric("ring_count", "RingCount", "int", "count", "Lipinski.RingCount"),
    MolecularMetric("heavy_atom_count", "HeavyAtomCount", "int", "count", "Lipinski.HeavyAtomCount"),
    MolecularMetric("hetero_atom_count", "NumHeteroatoms", "int", "count", "Lipinski.NumHeteroatoms"),
    MolecularMetric("fraction_csp3", "FractionCSP3", "float", "", "Lipinski.FractionCSP3"),
    MolecularMetric("formal_charge", "FormalCharge", "int", "e", "Chem.GetFormalCharge"),
)})


@dataclass(frozen=True)
class MolecularPropertyResult:
    metric_id: str
    value: float | int | None
    unit: str | None
    status: str
    method: str
    engine: str
    engine_version: str
    source: str
    canonical_structure: str | None
    structure_format: str
    reason: str | None = None
    warning: str | None = None
    descriptor_name: str | None = None
    value_kind: str = "computed"

    def __post_init__(self):
        if self.value_kind != "computed":
            raise ValueError("确定性分子描述符必须标为 computed")
        if not isinstance(self.metric_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.metric_id):
            raise ValueError("metric_id 必须为稳定英文 snake_case")
        if self.status not in {"available", "invalid_structure", "unsupported", "calculation_failed"}:
            raise ValueError("非法分子属性状态")
        for field in ("method", "engine", "engine_version", "source", "structure_format"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"{field} 必须明确保留")
        if self.unit is not None and not isinstance(self.unit, str):
            raise ValueError("unit 必须为字符串或扩展报告的未知单位 None")
        if self.status == "available":
            try:
                valid = type(self.value) in {int, float} and isfinite(self.value)
            except OverflowError:
                valid = False
            if not valid or not self.canonical_structure:
                raise ValueError("available 必须有有限数值和 canonical_structure")
        elif self.value is not None or not self.reason:
            raise ValueError("失败状态必须保留 reason 且 value=None；不能填0/NaN")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CandidateMolecularProperties:
    compound_id: str
    structure: str
    structure_format: str
    properties: tuple[MolecularPropertyResult, ...]
    extended_report: tuple[MolecularPropertyResult, ...] = ()

    def __post_init__(self):
        if not isinstance(self.compound_id, str) or not self.compound_id.strip():
            raise ValueError("compound_id 必须为明确稳定ID")
        if not isinstance(self.structure, str) or self.structure_format != "smiles":
            raise ValueError("复用显式smiles结构输入，空串表示缺失")
        object.__setattr__(self, "properties", tuple(self.properties))
        object.__setattr__(self, "extended_report", tuple(self.extended_report))
        for results in (self.properties, self.extended_report):
            if any(not isinstance(x, MolecularPropertyResult) for x in results):
                raise ValueError("必须保留正式属性结果契约")
            if len({x.metric_id for x in results}) != len(results):
                raise ValueError("属性结果不得重复")

    def to_dict(self):
        return asdict(self)
