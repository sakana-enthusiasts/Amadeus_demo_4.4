"""显式生成已冻结 SeeThrough 评估的报告；导入时不读取或写入结果。"""
import argparse
import csv
import json
from pathlib import Path
import zipfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "核心系统").is_dir())
if __package__:
    from .benchmark_artifacts import benchmark_directory
else:
    from benchmark_artifacts import benchmark_directory
if __package__:
    from .public_molecule_benchmark import verify
else:
    from public_molecule_benchmark import verify


def rows(out, name):
    with (out / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_report(out):
    OUT = benchmark_directory(out, ROOT)
    if (OUT / "结果说明.md").exists() or (OUT / "完整结果.zip").exists():
        raise ValueError("报告或归档已存在；保留历史结果，不覆盖")
    verify(OUT, "ranking_frozen.json")
    verify(OUT, "benchmark_frozen.json")
    summary = json.loads((OUT / "ranking_summary.json").read_text(encoding="utf-8"))
    metrics = rows(OUT, "benchmark_metrics.csv")
    matches = rows(OUT, "reference_candidate_ranks.csv")
    exact = [r for r in matches if r["match_mode"] == "inchikey"]
    connectivity = {(r["set"], r["reference_id"]): r for r in matches if r["match_mode"] == "connectivity_key"}
    top = rows(OUT, "top200.csv")[:20]

    lines = [
        "# SeeThrough 外部 benchmark 结果",
        "",
        "## 评估范围",
        "",
        "本报告读取指定运行的冻结排名与 benchmark 统计，逐项展示覆盖率、Recall、富集因子及候选排名。随机排序只作为基线，不参与正式排名；本报告不重新计算或调整科学目标。",
        "",
        "是否富集及候选分布应依据下表和对应运行的原始记录判断，不沿用其他历史运行的结论。",
        "",
        "## 运行规模",
        "",
        f"- NCI 1999 原始记录：{summary['source_rows']:,}",
        f"- 唯一候选：{summary['unique_candidates']:,}",
        f"- 可计算并正式排名：{summary['rankable']:,}",
        f"- 保留为 unknown：{summary['unknown_retained']:,}",
        f"- Pareto 第一层：{summary['pareto_front_size']:,}",
        "- 标签加载时点：候选池、Target Profile、描述符与正式排名全部冻结之后",
        "",
        "## Recall 与富集因子",
        "",
        "主结果使用完整 Standard InChIKey 精确匹配。连接层匹配作为盐型、质子化状态和立体化学差异的补充诊断。",
        "",
        "| 集合 | 匹配方法 | K | 入池/总数 | 可排名 | 命中 | Recall | 条件Recall | EF | 随机Recall期望 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(f"| {m['set']} | {m['match_mode']} | {m['K']} | {m['pool_covered_reference_count']}/{m['reference_count']} | {m['rankable_reference_count']} | {m['hits']} | {float(m['recall']):.6f} | {float(m['conditional_recall'] or 0):.6f} | {float(m['enrichment_factor'] or 0):.3f} | {float(m['random_recall_exact_mean']):.8f} |")

    lines += [
        "",
        "10,000 次随机排列的逐次结果保存在 `random_baseline_10000_runs.csv`，另有一个完整、固定哈希随机顺序保存在 `random_baseline_order.csv`。随机结果不是正式筛选结果。",
        "",
        "## 每个参考候选的实际正式排名",
        "",
        "若精确结构没有入池，表中同时给出连接层匹配结果。空排名表示无法在冻结候选池中获得排名，而不是被缺失指标悄悄删除。",
        "",
        "| 集合 | 编号 | 名称 | CAS | 精确状态 | 精确排名 | 连接层状态 | 连接层排名 | MolMR/MW | MolLogP |",
        "|---|---|---|---|---|---:|---|---:|---:|---:|",
    ]
    for r in exact:
        c = connectivity[(r["set"], r["reference_id"])]
        lines.append(f"| {r['set']} | {r['reference_id']} | {r['name'].replace('|','/')} | {r['cas']} | {r['status']} | {r['rank'] or ''} | {c['status']} | {c['rank'] or ''} | {r['specific_molar_refractivity'] or ''} | {r['mol_logp'] or ''} |")

    lines += [
        "",
        "## 正式排名 Top 20",
        "",
        "NCI 文件主要提供 NSC 编号与结构，因此这里报告编号和结构，不伪造名称。完整 Top 200 在 `top200.csv`。",
        "",
        "| 排名 | Pareto层 | NCI/NSC编号 | SMILES | MolMR/MW | MolLogP |",
        "|---:|---:|---:|---|---:|---:|",
    ]
    for r in top:
        smi = r["canonical_smiles"]
        if len(smi) > 110:
            smi = smi[:107] + "..."
        lines.append(f"| {r['rank']} | {r['pareto_layer']} | {r['source_id']} | `{smi}` | {float(r['specific_molar_refractivity']):.6f} | {float(r['mol_logp']):.6f} |")

    lines += [
        "",
        "## 文件说明",
        "",
        f"- `all_source_records.csv`：{summary['source_rows']:,} 条原始行逐条结果，包括重复、解析失败、计算失败与原因。",
        f"- `full_candidate_list.csv`：{summary['unique_candidates']:,} 个唯一候选的完整清单；先列正式排名候选，再列 unknown。",
        f"- `ranked_candidates.csv`：{summary['rankable']:,} 个正式候选及排名、Pareto 层、目标值和通用描述符。",
        f"- `unknown_candidates.csv`：{summary['unknown_retained']:,} 个无法进入 Pareto 的候选及明确原因。",
        "- `reference_candidate_ranks.csv`：41、20、final10 的每个候选，分别给出精确匹配和连接层匹配的实际排名。",
        "- `reference_missing_from_pool.csv`：未进入冻结候选池或身份未解析的参考记录。",
        "- `benchmark_metrics.csv`：全部 Recall@20/50/100/200、EF、覆盖率、条件 Recall 和随机基线统计。",
        "- `random_baseline_10000_runs.csv`：10,000 次随机排序的逐次基线结果。",
        "- `target_profile.json`、`protocol.json`、各个 `*_frozen.json`：冻结配置和 SHA-256 完整性记录。",
        "",
        "## 限制",
        "",
        "候选覆盖受输入来源快照限制；精确结构与连接层覆盖分别列在统计表中。身份未解析或来源请求失败的具体原因以该运行的参考记录为准，不从其他运行复制。",
        "",
        "MolMR/MW 不是折射率，MolLogP 也不是水溶性。本轮按预先冻结的目标保留它们作为通用结构代理值，没有在看到标签后增加分子量、片段数、盐型、芳香性、水合或 eRI 条件。",
    ]

    (OUT / "结果说明.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    archive = OUT / "完整结果.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path != archive:
                z.write(path, Path(OUT.name) / path.name)
        for name in ("public_molecule_benchmark.py", "public_molecule_evaluation.py",
                     "prepare_seethrough_references.py", "public_molecule_report.py",
                     "public_molecule_benchmark测试.py", "benchmark_artifacts.py"):
            source = ROOT / "测试" / name if name.endswith("测试.py") else ROOT / "测试" / "benchmark工具" / name
            z.write(source, Path(OUT.name) / "scripts" / name)
    print(json.dumps({"report": str(OUT / "结果说明.md"), "archive": str(archive),
                      "archive_bytes": archive.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path, help="已有 审计结果/benchmark/<run_id>")
    args = parser.parse_args()
    build_report(args.out)
