"""与化学工具、UI、数据库和用途无关的本地结构查询契约。"""

from dataclasses import asdict, dataclass
from math import isfinite


class StructureQueryError(ValueError):
    """查询或候选身份契约错误；结构解析错误由实现隔离。"""


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise StructureQueryError(f"{name} 必须为非空字符串")


@dataclass(frozen=True)
class StructureCandidate:
    compound_id: str
    structure: str
    structure_format: str

    def __post_init__(self):
        _text(self.compound_id, "compound_id")
        if not isinstance(self.structure, str):
            raise StructureQueryError("structure 必须为字符串，空串作为无效候选记录")
        if self.structure_format != "smiles":
            raise StructureQueryError("v1 候选仅支持显式 smiles 格式")


@dataclass(frozen=True)
class SimilarityConfig:
    threshold: float | None = None
    top_n: int | None = None
    radius: int = 2
    fp_size: int = 2048
    fingerprint_type: str = "Morgan"
    metric: str = "Tanimoto"

    def __post_init__(self):
        if self.fingerprint_type != "Morgan" or self.metric != "Tanimoto":
            raise StructureQueryError("v1 仅支持 Morgan / Tanimoto")
        for name, value, minimum in (("radius", self.radius, 0), ("fp_size", self.fp_size, 1),
                                     ("top_n", self.top_n, 1)):
            if value is None and name == "top_n":
                continue
            if type(value) is not int or value < minimum:
                raise StructureQueryError(f"{name} 必须为不小于{minimum}的整数")
        if self.threshold is not None and (isinstance(self.threshold, bool)
                or not isinstance(self.threshold, (int, float)) or not isfinite(self.threshold)
                or not 0 <= self.threshold <= 1):
            raise StructureQueryError("threshold 必须为[0,1]有限数值")


@dataclass(frozen=True)
class StructureQuery:
    mode: str
    query: str
    query_format: str
    use_chirality: bool = True
    similarity: SimilarityConfig | None = None
    max_matches: int = 10000

    def __post_init__(self):
        if self.mode not in {"exact", "substructure", "similarity"}:
            raise StructureQueryError("mode 必须为 exact/substructure/similarity")
        _text(self.query, "query")
        expected = "smarts" if self.mode == "substructure" else "smiles"
        if self.query_format != expected:
            raise StructureQueryError(f"{self.mode} query_format 必须为 {expected}")
        if type(self.use_chirality) is not bool:
            raise StructureQueryError("use_chirality 必须为布尔值")
        if type(self.max_matches) is not int or self.max_matches < 1:
            raise StructureQueryError("max_matches 必须为正整数")
        if self.mode == "similarity":
            if self.similarity is None:
                object.__setattr__(self, "similarity", SimilarityConfig())
            elif not isinstance(self.similarity, SimilarityConfig):
                raise StructureQueryError("similarity 必须为 SimilarityConfig")
        elif self.similarity is not None:
            raise StructureQueryError("仅 similarity 模式接受 similarity 配置")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class StructureHit:
    compound_id: str
    status: str
    structure: str
    structure_format: str
    canonical_structure: str | None = None
    score: float | None = None
    match_count: int | None = None
    atom_indices: tuple[tuple[int, ...], ...] = ()
    reason: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class StructureSearchResult:
    query: StructureQuery
    engine: str
    engine_version: str
    canonical_query: str
    hits: tuple[StructureHit, ...]
    invalid_candidates: tuple[StructureHit, ...]
    excluded_candidates: tuple[StructureHit, ...]

    @property
    def result_count(self):
        return len(self.hits)

    def to_dict(self):
        result = asdict(self)
        result["result_count"] = self.result_count
        result["invalid_count"] = len(self.invalid_candidates)
        result["settings"] = self.query.to_dict()
        if self.query.mode == "similarity":
            result["settings"]["selection_order"] = "threshold -> score descending / compound_id ascending -> top_n"
        if self.query.mode == "substructure":
            result["settings"]["match_count_semantics"] = "unique atom matches, capped at max_matches; cap warning recorded"
        return result
