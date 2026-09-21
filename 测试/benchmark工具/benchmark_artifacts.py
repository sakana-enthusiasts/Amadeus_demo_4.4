"""Benchmark 保留产物路径；不承载科学计算，也不自动删除历史结果。"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def benchmark_directory(out, project_root):
    """只接受项目审计区下的单个运行目录；None 生成未创建的唯一运行路径。"""
    root = Path(project_root).resolve()
    base = root / "审计结果" / "benchmark"
    if base.resolve() != base:
        raise ValueError("Benchmark 审计目录不能通过链接重定向")
    if out is None:
        name = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ_") + uuid4().hex[:8]
        return base / name
    target = Path(out).resolve()
    if target.parent != base or target.name.startswith(".") or target.suffix.lower() == ".zip":
        raise ValueError("Benchmark 产物必须位于 审计结果/benchmark/<run_id>/")
    return target
