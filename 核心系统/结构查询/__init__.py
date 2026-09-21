"""本地 Structure Query v1 公共 API，无 RDKit 依赖。"""

from .数据结构 import (SimilarityConfig, StructureCandidate, StructureHit, StructureQuery,
                    StructureQueryError, StructureSearchResult)
from .接口 import StructureSearch, adapt_candidates

__all__ = ["SimilarityConfig", "StructureCandidate", "StructureHit", "StructureQuery",
           "StructureQueryError", "StructureSearchResult", "StructureSearch", "adapt_candidates"]
