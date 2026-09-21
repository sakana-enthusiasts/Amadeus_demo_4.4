"""结构标准化派生视图；不修改原始身份。"""

from dataclasses import asdict, dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class StandardizationRequest:
    compound_id: str
    observed_structure: str
    observed_format: str = "smiles"
    calculation_view: str = "canonical"
    normalize_charge: bool = False
    extract_parent: bool = False
    canonicalize_tautomer: bool = False

    def __post_init__(self):
        if not isinstance(self.compound_id, str) or not self.compound_id.strip():
            raise ValueError("compound_id 必须明确")
        if not isinstance(self.observed_structure, str) or self.observed_format != "smiles":
            raise ValueError("只支持显式 SMILES 输入")
        if self.calculation_view not in {"observed", "canonical", "parent", "canonical_tautomer"}:
            raise ValueError("未知计算结构视图")
        if any(type(getattr(self, key)) is not bool for key in
               ("normalize_charge", "extract_parent", "canonicalize_tautomer")):
            raise ValueError("标准化步骤选项必须为布尔值")


@dataclass(frozen=True)
class StandardizationStep:
    method: str
    before: str
    after: str


@dataclass(frozen=True)
class StandardizedMolecule:
    compound_id: str
    observed_structure: str
    observed_format: str
    canonical_structure: str | None
    parent_structure: str | None
    canonical_tautomer: str | None
    fragments: tuple[str, ...]
    formal_charge: int | None
    steps: tuple[StandardizationStep, ...]
    engine: str
    engine_version: str
    status: str
    calculation_view: str
    calculation_structure: str | None
    warnings: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self):
        if self.status not in {"available", "invalid_structure", "calculation_failed"}:
            raise ValueError("未知标准化状态")
        if self.status == "available":
            if not self.canonical_structure or not self.calculation_structure or type(self.formal_charge) is not int:
                raise ValueError("标准化成功必须保留计算结构与形式电荷")
        elif self.calculation_structure is not None or not self.reason:
            raise ValueError("标准化失败不得静默回退结构，须保留原因")

    def to_dict(self):
        return asdict(self)


class MoleculeStandardizer(Protocol):
    def standardize(self, requests: Sequence[StandardizationRequest]) -> tuple[StandardizedMolecule, ...]: ...
