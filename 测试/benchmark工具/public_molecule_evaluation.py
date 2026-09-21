"""Post-freeze label evaluation; never changes a candidate or its rank."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
import json
import sys
import math
import shutil

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "核心系统").is_dir())
sys.path.insert(0, str(ROOT / "测试"))
if __package__:
    from .public_molecule_benchmark import verify, seal, write_csv, write_json, event
else:
    from public_molecule_benchmark import verify, seal, write_csv, write_json, event
if __package__:
    from .benchmark_artifacts import benchmark_directory
else:
    from benchmark_artifacts import benchmark_directory


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def evaluate(out, references):
    out = benchmark_directory(out, ROOT)
    import numpy as np
    from scipy.stats import hypergeom
    from rdkit import Chem, DataStructs, RDLogger
    from rdkit.Chem import rdFingerprintGenerator
    RDLogger.DisableLog("rdApp.*")
    verify(out, "protocol_frozen.json")
    verify(out, "pool_frozen.json")
    verify(out, "ranking_frozen.json")
    if (out / "benchmark_frozen.json").exists():
        raise ValueError("Evaluation already sealed; do not overwrite")
    refs = json.loads(Path(references).read_text(encoding="utf-8"))
    event(out, "reference_labels_loaded", records=len(refs))
    write_json(out / "references_frozen.json", refs)
    (out / "evaluator_frozen.py").write_bytes(Path(__file__).read_bytes())
    seal(out, "references_seal.json", ["references_frozen.json", "evaluator_frozen.py"],
         ranking_frozen_sha256=__import__("hashlib").sha256((out / "ranking_frozen.json").read_bytes()).hexdigest())
    candidates = read_csv(out / "full_candidate_list.csv")
    ranked = [r for r in candidates if r["status"] == "rankable"]
    n = len(ranked)
    index = {mode: defaultdict(list) for mode in ("inchikey", "connectivity_key")}
    for r in candidates:
        for mode in index:
            if r.get(mode):
                index[mode][r[mode]].append(r)
    fps = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    top = ranked[:200]
    top_fp = [fps.GetFingerprint(Chem.MolFromSmiles(r["canonical_smiles"])) for r in top]
    matches = []
    for ref in refs:
        mol = Chem.MolFromSmiles(ref.get("smiles", "")) if ref.get("smiles") else None
        ik = Chem.MolToInchiKey(mol) if mol is not None else ref.get("inchikey", "")
        ck = ik.split("-")[0] if ik else ""
        neighbors = {}
        if mol is not None and top:
            sims = DataStructs.BulkTanimotoSimilarity(fps.GetFingerprint(mol), top_fp)
            at = max(range(len(sims)), key=sims.__getitem__)
            neighbors = {"nearest_top200_source_id": top[at]["source_id"], "nearest_top200_rank": top[at]["rank"],
                         "nearest_top200_tanimoto": sims[at], "neighborhood_ge_0_7": sims[at] >= 0.7}
        for mode, key in (("inchikey", ik), ("connectivity_key", ck)):
            present = index[mode].get(key, []) if key else []
            scored = [r for r in present if r["rank"]]
            best = min(scored, key=lambda r: int(r["rank"])) if scored else None
            reason = ("ranked" if best else "present_but_objectives_unknown" if present else
                      "identity_unresolved" if not key else "not_found_in_frozen_NCI_snapshot")
            matches.append({**ref, "match_mode": mode, "reference_inchikey": ik,
                "pool_present": bool(present), "rankable_present": bool(scored), "status": reason,
                "rank": int(best["rank"]) if best else None, "pareto_layer": best["pareto_layer"] if best else None,
                "candidate_source_id": best["source_id"] if best else None,
                "candidate_aliases": best["source_aliases"] if best else None,
                "all_matching_candidate_ranks": "|".join(str(r["rank"]) for r in scored),
                "matching_candidate_count": len(present),
                "specific_molar_refractivity": best["specific_molar_refractivity"] if best else None,
                "mol_logp": best["mol_logp"] if best else None,
                "one_random_order_best_rank": min(int(r["random_baseline_rank"]) for r in scored) if scored else None,
                **neighbors})
    write_csv(out / "reference_candidate_ranks.csv", matches)
    write_csv(out / "reference_missing_from_pool.csv", [r for r in matches if not r["pool_present"]])
    # Randomize ranks of the union of matching candidates, preserving identity overlaps.
    # Sampling distinct ranks is exactly equivalent to uniform full-pool permutations.
    union = sorted({int(x) for r in matches for x in r["all_matching_candidate_ranks"].split("|") if x})
    position = {v: i for i, v in enumerate(union)}
    rng = np.random.Generator(np.random.PCG64(20260914))
    samples = np.empty((10000, len(union)), dtype=np.int32)
    for i in range(10000):
        samples[i] = rng.choice(n, len(union), replace=False) + 1
    np.savez_compressed(out / "random_baseline_samples.npz", original_candidate_ranks=np.array(union), randomized_ranks=samples)
    metrics, baseline_rows = [], []
    groups = sorted({(r["set"], r["match_mode"]) for r in matches})
    for group, mode in groups:
        rr = [r for r in matches if (r["set"], r["match_mode"]) == (group, mode)]
        positive = sorted({int(x) for r in rr for x in r["all_matching_candidate_ranks"].split("|") if x})
        m = len(positive)
        columns = [position[v] for v in positive]
        ref_columns = [[position[int(x)] for x in r["all_matching_candidate_ranks"].split("|") if x] for r in rr]
        min_positions = [samples[:, col].min(axis=1) if col else np.full(10000, n + 1) for col in ref_columns]
        for k in (20, 50, 100, 200):
            kk = min(k, n)
            hits = sum(r["rank"] is not None and r["rank"] <= kk for r in rr)
            cand_hits = sum(v <= kk for v in positive)
            recalls = np.sum([a <= kk for a in min_positions], axis=0) / len(rr)
            counts = (samples[:, columns] <= kk).sum(axis=1) if columns else np.zeros(10000)
            efs = counts / (kk * m / n) if m else np.full(10000, np.nan)
            expected_recall = sum(float(hypergeom.sf(0, n, len(cols), kk)) for cols in ref_columns) / len(rr)
            metrics.append({"set": group, "match_mode": mode, "K": k, "reference_count": len(rr),
                "pool_covered_reference_count": sum(r["pool_present"] for r in rr),
                "rankable_reference_count": sum(r["rankable_present"] for r in rr),
                "ranked_pool_size": n, "positive_candidate_rows": m, "hits": hits,
                "recall": hits / len(rr),
                "conditional_recall": hits / sum(r["rankable_present"] for r in rr) if any(r["rankable_present"] for r in rr) else None,
                "matching_candidate_rows_topK": cand_hits,
                "enrichment_factor": cand_hits / (kk * m / n) if m else None,
                "random_recall_exact_mean": expected_recall, "random_recall_sim_mean": float(recalls.mean()),
                "random_recall_p025": float(np.quantile(recalls, .025)), "random_recall_p975": float(np.quantile(recalls, .975)),
                "random_EF_expected": 1 if m else None,
                "random_EF_sim_mean": float(efs.mean()) if m else None,
                "random_EF_p025": float(np.quantile(efs, .025)) if m else None,
                "random_EF_p975": float(np.quantile(efs, .975)) if m else None,
                "random_EF_exact_p025": float(hypergeom.ppf(.025, n, m, kk) / (kk*m/n)) if m else None,
                "random_EF_exact_p975": float(hypergeom.ppf(.975, n, m, kk) / (kk*m/n)) if m else None,
                "hypergeometric_p_ge_observed": float(hypergeom.sf(cand_hits-1, n, m, kk)) if m else None})
            for i in range(10000):
                baseline_rows.append({"set": group, "match_mode": mode, "K": k, "draw": i + 1,
                                      "recall": float(recalls[i]), "enrichment_factor": float(efs[i]) if m else None})
    write_csv(out / "benchmark_metrics.csv", metrics)
    write_json(out / "benchmark_metrics.json", metrics)
    write_csv(out / "random_baseline_10000_runs.csv", baseline_rows)
    seal(out, "benchmark_frozen.json", ["references_seal.json", "references_frozen.json", "reference_candidate_ranks.csv",
         "reference_missing_from_pool.csv", "benchmark_metrics.csv", "benchmark_metrics.json", "random_baseline_samples.npz",
         "random_baseline_10000_runs.csv", "evaluator_frozen.py"])
    event(out, "benchmark_complete", reference_rows=len(refs), ranked_pool=n)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("references", type=Path)
    a = p.parse_args()
    evaluate(a.out.resolve(), a.references.resolve())
