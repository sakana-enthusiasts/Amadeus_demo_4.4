"""Local external benchmark. Stages freeze -> acquire -> rank -> benchmark.

Never import the legacy discovery workflow (it reads benchmarks automatically).
Artifacts live under 审计结果/benchmark/<run_id>; imports never start a run.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import sys
import time

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "核心系统").is_dir())
sys.path.insert(0, str(ROOT))
from 核心系统.目标规格 import Criterion, TargetProfile, save_profile, load_profile
if __package__:
    from .benchmark_artifacts import benchmark_directory
else:
    from benchmark_artifacts import benchmark_directory

SOURCE = "https://cactus.nci.nih.gov/download/nci/NCI0DA99.sdz"
SEED = "amadeus-public-molecule-round1-20260914"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def event(out, stage, **data):
    item = {"utc": datetime.now(timezone.utc).isoformat(), "stage": stage, **data}
    with (out / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps(item, ensure_ascii=True), flush=True)


def verify(out, manifest):
    data = json.loads((out / manifest).read_text(encoding="utf-8"))
    for name, expected in data["sha256"].items():
        if digest(out / name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    return data


def seal(out, name, files, **meta):
    path = out / name
    if path.exists():
        raise ValueError(f"Refusing to replace seal: {name}")
    write_json(path, {"utc": datetime.now(timezone.utc).isoformat(), **meta,
                      "sha256": {f: digest(out / f) for f in files}})


def freeze(out):
    out = benchmark_directory(out, ROOT)
    if out.exists():
        raise ValueError("Use a new run directory; no overwriting an existing run")
    out.mkdir(parents=True)
    profile = TargetProfile("public_data_only_molecule_round1", {
        "specific_molar_refractivity": Criterion("objective", scope="molecule", mode="maximize",
            unit="cm3/g", missing_policy="keep_unknown", evidence_requirement="predicted_allowed"),
        "mol_logp": Criterion("objective", scope="molecule", mode="minimize",
            missing_policy="keep_unknown", evidence_requirement="predicted_allowed"),
        "toxicity": Criterion("report_only", scope="molecule", missing_policy="keep_unknown"),
        **{key: Criterion("disabled", scope=scope) for key, scope in (
            ("systemic_pk", "delivery"), ("metabolism", "molecule"),
            ("final_formulation_viscosity", "formulation"), ("final_formulation_ri_target", "formulation"),
            ("ba_va_specific_compatibility", "formulation"), ("seethrough_hydration_threshold", "molecule"),
            ("seethrough_eri_threshold", "molecule"), ("seethrough_aromatic_class", "molecule"))},
    })
    save_profile(profile, out / "target_profile.json")
    write_json(out / "protocol.json", {
        "source": SOURCE, "source_release": "NCI Open Database October 1999 0D SDF, 249081 advertised records",
        "query": "entire archived 0D SDF file; no name, CAS, substructure, aromatic, MW, hydration or RI filtering",
        "prelabel_format_correction": "Initial SMILES acquisition failed due to HTTP automatic gzip decoding; inspection also found legacy bracket atoms incompatible with RDKit hydrogen semantics. Same 1999 collection is read from original 0D SDF instead. This historical file omits the V2000 marker and M END record, so those two syntax markers are restored before RDKit parsing; atoms and bonds are unchanged. Failed runs remain in sibling folders. No reference labels were read and no scientific objective changed.",
        "sampling": "none", "hard_constraints": [], "seed": SEED,
        "pool": "all source rows retained; canonical isomeric SMILES deduplication for ranking; invalid rows retained unknown",
        "structure_policy": "RDKit default SMILES parsing; do not strip salts, neutralize, choose fragments or fill missing data",
        "descriptor_element_domain": "H B C N O F Si P S Cl Br I only; all others retained unknown, not excluded from candidate pool",
        "objective_policy": "TargetProfile objective fields drive two dimensional Pareto nondominated depth; no weights",
        "objective_notes": "MolMR/MW is a proxy, not refractive index; MolLogP is a proxy, not measured aqueous solubility",
        "tie_break": "SHA256(seed + canonical isomeric SMILES), ascending within Pareto layer",
        "missing": "retain all; unavailable objective means unknown/unranked, never optimistic imputation",
        "report_only": "toxicity retained unknown_not_queried; no toxicity or PK remote requests",
        "identity_primary": "whole-record Standard InChIKey exact match; no tautomer/fragment rewriting",
        "identity_secondary": "first InChIKey block, connectivity match; kept separate from primary metrics",
        "chemical_region": "nearest Morgan radius2 2048-bit Tanimoto among frozen Top200; >=0.7 descriptive neighborhood only",
        "metrics": {"K": [20, 50, 100, 200],
            "recall": "hits in topK / full reference set size",
            "conditional_recall": "hits in topK / number of reference identities present and rankable",
            "EF": "(matching candidate rows in topK / K) / (matching candidate rows in all ranked candidates / N)",
            "coverage": "separate pool coverage; absence never silently removed from recall denominator",
            "unknown": "no rank is assigned to unavailable objectives; all records still listed"},
        "random_baseline": "10000 uniform random orderings over ranked candidate identities; NumPy PCG64 seed 20260914; exact expected recall and hypergeometric EF count interval; one full independent hash-random ordering saved",
        "label_freeze": "No reading reference labels until ranking seal exists. Prior conversation exposed some labels; this is process-isolated retrospective evaluation, not investigator-naive blinding.",
        "reference_stage": "existing local 41/20 workflow snapshots first; final10 local published mapping; post-ranking benchmark only; any PubChem identity resolution post-ranking cached",
        "no_tuning": True,
    })
    (out / "runner_frozen.py").write_bytes(Path(__file__).read_bytes())
    helper = Path(__file__).with_name("benchmark_artifacts.py")
    (out / "benchmark_artifacts.py").write_bytes(helper.read_bytes())
    seal(out, "protocol_frozen.json", ["protocol.json", "target_profile.json", "runner_frozen.py", "benchmark_artifacts.py"])
    event(out, "protocol_frozen", directory=str(out))


def acquire(out):
    out = benchmark_directory(out, ROOT)
    verify(out, "protocol_frozen.json")
    if (out / "pool_frozen.json").exists():
        verify(out, "pool_frozen.json")
        return
    import requests
    r = requests.get(SOURCE, timeout=(15, 90), stream=True)
    r.raise_for_status()
    raw = r.raw.read(decode_content=False)
    content = gzip.decompress(raw).decode("latin-1", errors="strict")
    (out / "NCI0DA99.sdz").write_bytes(raw)
    write_json(out / "download.json", {"url": SOURCE, "resolved_url": r.url,
        "utc": datetime.now(timezone.utc).isoformat(), "bytes": len(raw), "headers": dict(r.headers)})
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    def read_legacy_mol(block):
        lines = block.splitlines()
        if len(lines) < 4:
            return None
        try:
            atom_count, bond_count = int(lines[3][:3]), int(lines[3][3:6])
        except ValueError:
            return None
        last_bond = 4 + atom_count + bond_count
        if len(lines) < last_bond:
            return None
        counts = lines[3]
        if "V2000" not in counts and "V3000" not in counts:
            lines[3] = counts.ljust(33) + " V2000"
        molblock = "\n".join(lines[:last_bond] + ["M  END"]) + "\n"
        return Chem.MolFromMolBlock(molblock, sanitize=True, removeHs=True, strictParsing=True)

    rows = []
    for line_no, block in enumerate(content.split("$$$$\n"), 1):
        if not block.strip():
            continue
        mol = read_legacy_mol(block)
        rows.append({"source_line": line_no, "source_id": block.splitlines()[0].strip() or f"record_{line_no}",
                     "source_smiles": Chem.MolToSmiles(mol, isomericSmiles=True) if mol is not None else "",
                     "source_record": line_no})
        if line_no % 25000 == 0:
            event(out, "structure_parse_progress", source_rows=line_no)
    write_csv(out / "candidate_pool_frozen.csv", rows)
    seal(out, "pool_frozen.json", ["protocol.json", "target_profile.json", "NCI0DA99.sdz",
         "candidate_pool_frozen.csv"], source_records=len(rows))
    event(out, "pool_frozen", rows=len(rows), bytes=len(raw))


def pareto_depth(vectors):
    """Exact 2D minimization depth in O(N log N), grouping equal vectors."""
    ys = {v: i+1 for i, v in enumerate(sorted({x[1] for x in vectors}))}
    tree = [0] * (len(ys) + 1)
    order = sorted(range(len(vectors)), key=lambda i: vectors[i])
    depth = [0] * len(vectors)
    at = 0
    while at < len(order):
        end = at+1
        v = vectors[order[at]]
        while end < len(order) and vectors[order[end]] == v:
            end += 1
        pos = ys[v[1]]
        best, j = 0, pos
        while j:
            best = max(best, tree[j])
            j -= j & -j
        d = best+1
        for k in range(at, end):
            depth[order[k]] = d
        j = pos
        while j < len(tree):
            tree[j] = max(tree[j], d)
            j += j & -j
        at = end
    return depth


def rank(out):
    out = benchmark_directory(out, ROOT)
    verify(out, "protocol_frozen.json")
    verify(out, "pool_frozen.json")
    if (out / "ranking_frozen.json").exists():
        raise ValueError("Ranking is already frozen; no reranking")
    from rdkit import Chem, rdBase, RDLogger
    from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors
    from rdkit.Chem import rdchem
    RDLogger.DisableLog("rdApp.*")
    profile = load_profile(out / "target_profile.json")
    objectives = [(k, c) for k, c in profile.criteria.items() if c.role == "objective"]
    if {k for k, c in objectives} != {"specific_molar_refractivity", "mol_logp"}:
        raise ValueError("Runner supports only the frozen two proxy objectives")
    write_json(out / "environment.json", {"python": sys.version, "platform": platform.platform(),
        "rdkit": rdBase.rdkitVersion, "profile_version": profile.target_profile_version,
        "code_sha256": digest(out / "runner_frozen.py")})
    seen, records = {}, []
    rows = csv.DictReader((out / "candidate_pool_frozen.csv").open(encoding="utf-8-sig"))
    fields = ["source_line", "source_id", "source_smiles", "canonical_smiles", "inchikey", "connectivity_key",
              "molecular_weight", "mol_mr", "specific_molar_refractivity", "mol_logp", "tpsa", "hbd", "hba",
              "formal_charge", "fragment_count", "status", "error", "representative_source_id", "toxicity_status"]
    with (out / "all_source_records.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, raw in enumerate(rows, 1):
            row = {k: raw[k] for k in ("source_line", "source_id", "source_smiles")}
            row.update(status="unknown", error="", toxicity_status="unknown_not_queried")
            try:
                mol = Chem.MolFromSmiles(raw["source_smiles"])
                if mol is None or mol.GetNumAtoms() == 0:
                    raise ValueError("invalid_or_empty_structure")
                canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
                row["canonical_smiles"] = canonical
                row["inchikey"] = Chem.MolToInchiKey(mol)
                row["connectivity_key"] = row["inchikey"].split("-")[0] if row["inchikey"] else ""
                row.update(molecular_weight=Descriptors.MolWt(mol), tpsa=rdMolDescriptors.CalcTPSA(mol),
                    hbd=rdMolDescriptors.CalcNumHBD(mol), hba=rdMolDescriptors.CalcNumHBA(mol),
                    formal_charge=Chem.GetFormalCharge(mol), fragment_count=len(Chem.GetMolFrags(mol)))
                # Fragment models have no supported contribution for many metal/unknown atoms.
                # Keep such compounds as unknown rather than interpret default zeros as predictions.
                allowed = {1, 5, 6, 7, 8, 9, 14, 15, 16, 17, 35, 53}
                if any(a.GetAtomicNum() not in allowed for a in mol.GetAtoms()):
                    raise ValueError("unsupported_element_for_crippen_proxy; retained_unknown")
                mr, logp = Crippen.MolMR(mol), Crippen.MolLogP(mol)
                row.update(mol_mr=mr, specific_molar_refractivity=mr / row["molecular_weight"], mol_logp=logp)
                if not all(math.isfinite(row[k]) for k, c in objectives):
                    raise ValueError("nonfinite_objective")
                row["status"] = "rankable"
            except Exception as e:
                row["error"] = str(e)
            key = row.get("canonical_smiles") or f"invalid_line_{i}"
            if key in seen:
                row["representative_source_id"] = seen[key]["source_id"]
                row["status"] = "duplicate_" + row["status"]
                seen[key]["source_aliases"].append(raw["source_id"])
            else:
                row["representative_source_id"] = raw["source_id"]
                rec = dict(row, source_aliases=[raw["source_id"]])
                seen[key] = rec
                records.append(rec)
            w.writerow(row)
            if i % 10000 == 0:
                f.flush()
                event(out, "features_progress", source_rows=i, unique=len(records))
    ranked = [r for r in records if r["status"] == "rankable"]
    vectors = [tuple(r[k] * (-1 if c.mode == "maximize" else 1) for k, c in objectives) for r in ranked]
    depths = pareto_depth(vectors)
    for r, d in zip(ranked, depths):
        r["pareto_layer"] = d
        r["tie_hash"] = hashlib.sha256((SEED + r["canonical_smiles"]).encode()).hexdigest()
    ranked.sort(key=lambda r: (r["pareto_layer"], r["tie_hash"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    random_order = sorted(ranked, key=lambda r: hashlib.sha256(("baseline:" + SEED + r["canonical_smiles"]).encode()).hexdigest())
    for i, r in enumerate(random_order, 1):
        r["random_baseline_rank"] = i
    for r in records:
        r["source_aliases"] = "|".join(r["source_aliases"])
    unknown = [r for r in records if r["status"] != "rankable"]
    all_fields = list(dict.fromkeys(k for r in ranked + unknown for k in r))
    write_csv(out / "full_candidate_list.csv", ranked + unknown, all_fields)
    write_csv(out / "ranked_candidates.csv", ranked, all_fields)
    write_csv(out / "unknown_candidates.csv", unknown, all_fields)
    write_csv(out / "top200.csv", ranked[:200], all_fields)
    write_csv(out / "random_baseline_order.csv", random_order, all_fields)
    write_json(out / "ranking_summary.json", {"source_rows": i if not records else sum(len(r["source_aliases"].split("|")) for r in records),
        "unique_candidates": len(records), "rankable": len(ranked), "unknown_retained": len(unknown),
        "pareto_front_size": sum(r["pareto_layer"] == 1 for r in ranked),
        "unknown_policy": "all listed, no Pareto rank", "labels_read": False,
        "disabled": [k for k, c in profile.criteria.items() if c.role == "disabled"]})
    seal(out, "ranking_frozen.json", ["protocol_frozen.json", "pool_frozen.json", "target_profile.json",
        "runner_frozen.py", "all_source_records.csv", "full_candidate_list.csv", "ranked_candidates.csv",
        "unknown_candidates.csv", "top200.csv", "random_baseline_order.csv", "ranking_summary.json", "environment.json"])
    event(out, "ranking_frozen", unique=len(records), ranked=len(ranked), unknown=len(unknown))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["freeze", "acquire", "rank"])
    p.add_argument("out", type=Path, nargs="?", help="审计结果/benchmark/<run_id>；freeze 可省略以新建运行")
    args = p.parse_args()
    if args.stage != "freeze" and args.out is None:
        p.error("acquire/rank 必须指定已有的 benchmark 运行目录")
    resolved = benchmark_directory(args.out, ROOT)
    # The discovery process cannot open project datasets/reference labels.
    forbidden = str((ROOT / "数据").resolve()).casefold()
    def deny_reference_reads(event_name, arguments):
        if event_name == "open" and arguments and isinstance(arguments[0], (str, bytes)):
            path = str(Path(arguments[0]).resolve()).casefold()
            if Path(path) == Path(forbidden) or Path(forbidden) in Path(path).parents:
                raise PermissionError("Reference/data directories are locked until ranking is frozen")
    sys.addaudithook(deny_reference_reads)
    if args.stage != "freeze" and digest(Path(__file__)) != digest(resolved / "runner_frozen.py"):
        raise ValueError("Runner differs from frozen code")
    if args.stage == "freeze":
        freeze(resolved)
    else:
        try:
            {"acquire": acquire, "rank": rank}[args.stage](resolved)
        except Exception as error:
            event(resolved, "stage_failed", requested_stage=args.stage, error=repr(error))
            raise


if __name__ == "__main__":
    main()
