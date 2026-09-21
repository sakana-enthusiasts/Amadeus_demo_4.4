"""本地候选结构检索，不调用身份查询、Provider、Benchmark 或网络。"""

from dataclasses import replace

from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator

from 核心系统.结构查询 import (StructureCandidate, StructureQuery, StructureQueryError,
                         StructureHit, StructureSearchResult)
from 插件.插件接口 import 基础插件接口


def _smiles(text):
    if not text.strip():
        return None
    try:
        # 不接受 SMILES 后面的自由名称作为结构输入。
        params = Chem.SmilesParserParams()
        params.parseName = False
        return Chem.MolFromSmiles(text, params)
    except (ValueError, RuntimeError):
        return None


def _canonical(mol, use_chirality):
    if not use_chirality:
        mol = Chem.Mol(mol)
        Chem.RemoveStereochemistry(mol)
    # 即使关闭 stereo，仍保留同位素，不能把不同 chemical form 合并。
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


class RDKit结构检索插件(基础插件接口):
    插件标识 = "RDKit结构检索"

    def 执行(self, 数据上下文):
        return self.search(数据上下文["结构查询"], 数据上下文["结构候选"])

    def search(self, query, candidates):
        if not isinstance(query, StructureQuery):
            raise StructureQueryError("需要正式 StructureQuery")
        candidates = tuple(candidates)
        if any(not isinstance(c, StructureCandidate) for c in candidates):
            raise StructureQueryError("需要正式 StructureCandidate")
        if len({c.compound_id for c in candidates}) != len(candidates):
            raise StructureQueryError("compound_id 不得重复")
        if query.mode == "substructure":
            try:
                query_mol = Chem.MolFromSmarts(query.query)
            except (ValueError, RuntimeError) as e:
                raise StructureQueryError("invalid_query: 无效 SMARTS") from e
        else:
            query_mol = _smiles(query.query)
        if query_mol is None or query_mol.GetNumAtoms() == 0:
            raise StructureQueryError("invalid_query: 无法解析查询结构")
        canonical_query = (Chem.MolToSmarts(query_mol) if query.mode == "substructure"
                           else _canonical(query_mol, query.use_chirality))
        hits, invalid, excluded, fingerprints, valid = [], [], [], [], []
        if query.mode == "similarity":
            config = query.similarity
            generator = rdFingerprintGenerator.GetMorganGenerator(
                radius=config.radius, fpSize=config.fp_size, includeChirality=query.use_chirality)
            query_fp = generator.GetFingerprint(query_mol)
        for candidate in sorted(candidates, key=lambda c: c.compound_id):
            mol = _smiles(candidate.structure)
            base = StructureHit(candidate.compound_id, "matched", candidate.structure,
                                candidate.structure_format)
            if mol is None or mol.GetNumAtoms() == 0:
                invalid.append(replace(base, status="invalid_structure", reason="无法解析候选 SMILES"))
                continue
            base = replace(base, canonical_structure=_canonical(mol, query.use_chirality))
            if query.mode == "exact":
                matched = base.canonical_structure == canonical_query
            elif query.mode == "substructure":
                matches = mol.GetSubstructMatches(query_mol, uniquify=True,
                          useChirality=query.use_chirality, maxMatches=query.max_matches)
                base = replace(base, match_count=len(matches), atom_indices=matches,
                               warning="达到 max_matches，实际匹配数可能更多" if len(matches) == query.max_matches else None)
                matched = bool(matches)
            else:
                valid.append(base)
                fingerprints.append(generator.GetFingerprint(mol))
                continue
            (hits if matched else excluded).append(base if matched else replace(
                base, status="not_matched", reason="结构不满足查询"))
        if query.mode == "similarity":
            scores = DataStructs.BulkTanimotoSimilarity(query_fp, fingerprints)
            ranked = sorted((replace(base, score=float(score)) for base, score in zip(valid, scores)),
                            key=lambda h: (-h.score, h.compound_id))
            for hit in ranked:
                if config.threshold is not None and hit.score < config.threshold:
                    excluded.append(replace(hit, status="below_threshold", reason="相似度低于 threshold"))
                elif config.top_n is not None and len(hits) >= config.top_n:
                    excluded.append(replace(hit, status="outside_top_n", reason="threshold 过滤后不在 top_n"))
                else:
                    hits.append(hit)
        return StructureSearchResult(query, "RDKit", rdBase.rdkitVersion, canonical_query,
                                     tuple(hits), tuple(invalid), tuple(excluded))
