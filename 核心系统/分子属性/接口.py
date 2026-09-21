"""复用显式 StructureCandidate 输入；分子属性计算不执行结构搜索。"""

from typing import Iterable, Protocol
from 核心系统.结构查询 import StructureCandidate
from .数据结构 import CandidateMolecularProperties


class MolecularPropertyCalculator(Protocol):
    def calculate(self, candidates: Iterable[StructureCandidate], requested_metrics: Iterable[str],
                  *, extended_descriptors: Iterable[str] | None = None
                  ) -> tuple[CandidateMolecularProperties, ...]: ...

    def descriptor_catalog(self) -> list[dict]: ...
