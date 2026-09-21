"""扩展描述符报告契约；不注册 Target Profile metric。"""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Protocol, Sequence

from 核心系统.结构查询 import StructureCandidate


@dataclass(frozen=True)
class DescriptorRequest:
    descriptor_ids: tuple[str, ...]
    engine: str = "RDKit"
    dimension: str = "2D"

    def __post_init__(self):
        if isinstance(self.descriptor_ids, str):
            raise ValueError("descriptor_ids 必须为名称序列")
        object.__setattr__(self, "descriptor_ids", tuple(self.descriptor_ids))
        if any(not isinstance(x, str) or not x.strip() for x in self.descriptor_ids):
            raise ValueError("描述符名称不能为空")
        if len(set(self.descriptor_ids)) != len(self.descriptor_ids):
            raise ValueError("描述符请求不得重复")
        if self.engine not in {"RDKit", "Mordred-community"} or self.dimension != "2D":
            raise ValueError("仅支持 RDKit/Mordred-community 显式 2D 描述符")


@dataclass(frozen=True)
class DescriptorDefinition:
    descriptor_id: str
    engine: str
    engine_version: str
    method: str
    dimension: str = "2D"
    unit: str | None = None


@dataclass(frozen=True)
class DescriptorValue:
    descriptor_id: str
    value: float | int | None
    status: str
    unit: str | None
    engine: str
    engine_version: str
    method: str
    dimension: str
    canonical_structure: str | None
    reason: str | None = None
    warning: str = "report-only：单位/科学语义未经正式指标审查"
    value_kind: str = "computed"

    def __post_init__(self):
        if self.dimension != "2D" or self.value_kind != "computed":
            raise ValueError("扩展描述符首版只接受 computed 2D")
        if self.status not in {"available", "invalid_structure", "unsupported", "calculation_failed", "capability_unavailable"}:
            raise ValueError("未知描述符状态")
        if self.status == "available":
            if type(self.value) not in {int, float} or not isfinite(self.value) or not self.canonical_structure:
                raise ValueError("available 需要有限数值和计算结构")
        elif self.value is not None or not self.reason:
            raise ValueError("失败描述符须 value=None 并保留 reason")


@dataclass(frozen=True)
class CandidateDescriptorSet:
    compound_id: str
    input_structure: str
    values: tuple[DescriptorValue, ...]

    def to_dict(self):
        return asdict(self)


class DescriptorCalculator(Protocol):
    def calculate(self, candidates: Sequence[StructureCandidate], request: DescriptorRequest) -> tuple[CandidateDescriptorSet, ...]: ...
    def catalog(self) -> tuple[DescriptorDefinition, ...]: ...
