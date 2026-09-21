"""可替换结构检索接口和显式记录适配；不猜字段，不读取候选库。"""

from typing import Iterable, Protocol

from .数据结构 import StructureCandidate, StructureQuery, StructureQueryError, StructureSearchResult


class StructureSearch(Protocol):
    def search(self, query: StructureQuery,
               candidates: Iterable[StructureCandidate]) -> StructureSearchResult: ...


def adapt_candidates(records, *, id_field, structure_field, structure_format):
    """调用方指定稳定ID/结构字段；缺失结构记为空串，缺失ID报契约错误。"""
    if any(not isinstance(x, str) or not x.strip() for x in (id_field, structure_field)):
        raise StructureQueryError("id_field/structure_field 必须为明确的非空字段名")
    candidates = []
    for record in records:
        if id_field not in record:
            raise StructureQueryError(f"缺少稳定ID字段 {id_field}")
        structure = record.get(structure_field)
        candidates.append(StructureCandidate(record[id_field],
                          "" if structure is None else structure, structure_format))
    if len({x.compound_id for x in candidates}) != len(candidates):
        raise StructureQueryError("compound_id 不得重复")
    return tuple(candidates)
