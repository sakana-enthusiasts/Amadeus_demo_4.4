"""产物路径、导入副作用和冻结保护回归；所有输入/输出仅用 tmp_path。"""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from benchmark工具 import public_molecule_benchmark as benchmark
from benchmark工具 import public_molecule_evaluation as evaluation
from benchmark工具 import prepare_seethrough_references as references
from benchmark工具 import public_molecule_report as report
from benchmark工具.benchmark_artifacts import benchmark_directory


@pytest.mark.parametrize("relative", ["测试/run", "核心系统/run", "运行记录/run", ".cache/run", "审计结果/benchmark", "审计结果/benchmark/run/nested"])
def test_benchmark拒绝源码缓存和非运行目标(tmp_path, relative):
    with pytest.raises(ValueError, match="审计结果/benchmark"):
        benchmark_directory(tmp_path / relative, tmp_path)
    assert not (tmp_path / relative).exists()


@pytest.mark.parametrize("entry", [benchmark.freeze, benchmark.acquire, benchmark.rank, evaluation.evaluate, references.main, report.build_report])
def test_所有写入入口先验证位置(tmp_path, monkeypatch, entry):
    module = importlib.import_module(entry.__module__)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    args = [tmp_path / "测试" / "污染"]
    if entry is evaluation.evaluate:
        args.append(tmp_path / "不存在的参考.json")
    with pytest.raises(ValueError, match="审计结果/benchmark"):
        entry(*args)
    assert not list(tmp_path.iterdir())


def test_冻结使用独立审计运行并保护原记录(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    out = benchmark_directory(None, tmp_path)
    assert out != benchmark_directory(None, tmp_path)
    benchmark.freeze(out)
    frozen = benchmark.verify(out, "protocol_frozen.json")
    assert set(frozen["sha256"]) == {"protocol.json", "target_profile.json", "runner_frozen.py", "benchmark_artifacts.py"}
    before = (out / "protocol_frozen.json").read_bytes()
    with pytest.raises(ValueError, match="no overwriting"):
        benchmark.freeze(out)
    assert (out / "protocol_frozen.json").read_bytes() == before
    assert not (tmp_path / "测试").exists()


def test_报告导入无副作用且输出在显式运行内(tmp_path, monkeypatch):
    importlib.reload(report)
    monkeypatch.setattr(report, "ROOT", tmp_path)
    out = benchmark_directory(None, tmp_path)
    out.mkdir(parents=True)
    (out / "ranking_summary.json").write_text(json.dumps({"source_rows": 1, "unique_candidates": 1, "rankable": 1, "unknown_retained": 0, "pareto_front_size": 1}))
    for name in ("benchmark_metrics.csv", "reference_candidate_ranks.csv", "top200.csv"):
        (out / name).write_text("placeholder\n")
    benchmark.seal(out, "ranking_frozen.json", ["ranking_summary.json", "top200.csv"])
    benchmark.seal(out, "benchmark_frozen.json", ["benchmark_metrics.csv", "reference_candidate_ranks.csv"])
    scripts = tmp_path / "测试" / "benchmark工具"
    scripts.mkdir(parents=True)
    names = ("public_molecule_benchmark.py", "public_molecule_evaluation.py", "prepare_seethrough_references.py", "public_molecule_report.py", "public_molecule_benchmark测试.py", "benchmark_artifacts.py")
    for name in names:
        target = scripts.parent / name if name.endswith("测试.py") else scripts / name
        target.write_text("# fixture source\n")
    report.build_report(out)
    assert (out / "结果说明.md").is_file()
    content = (out / "结果说明.md").read_text(encoding="utf-8")
    assert "1 个正式候选" in content and "222,765" not in content
    assert "没有在 Top 200 富集" not in content
    with zipfile.ZipFile(out / "完整结果.zip") as archive:
        assert not any(name.endswith("完整结果.zip") for name in archive.namelist())
    with pytest.raises(ValueError, match="不覆盖"):
        report.build_report(out)


def test_pytest拒绝以源码或其祖先作为可清空临时根():
    import conftest
    for base in (conftest.REPOSITORY, conftest.REPOSITORY / "测试" / "tmp", conftest.REPOSITORY.parent):
        with pytest.raises(pytest.UsageError):
            conftest.pytest_configure(SimpleNamespace(option=SimpleNamespace(basetemp=str(base))))
