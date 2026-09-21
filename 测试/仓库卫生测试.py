"""有限源码目录的卫生门禁；不遍历数据、审计历史、依赖环境或 Git 对象。"""

import ast
from functools import lru_cache
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("核心系统", "插件", "软件界面", "设置")
ARTIFACT_DIRS = {".git", ".venv", ".cache", ".pytest_cache", "__pycache__", "数据", "审计结果", "模型保存"}
SHIMS = {
    "插件.数据导入.PubChem查询插件", "插件.数据导入.CompTox查询插件",
    "插件.数据导入.普通表格导入插件", "插件.数据导入.论文表格导入插件",
    "插件.数据合并.化学属性合并插件", "插件.数据合并.补充数据2属性合并插件",
    "插件.化学计算.汉森距离计算插件", "插件.颅骨透明化.颅骨透明化用途插件",
}


def layout_problems(root):
    """只检查根及源码区；生成目录不作为代码扫描。按产物职责剪枝，不限制合法源码深度。"""
    problems = []
    pending = [root]
    while pending:
        directory = pending.pop()
        if directory != root and all((directory / name).exists() for name in ("核心系统", "插件", "启动程序.py")):
            problems.append(directory)
            continue
        for path in directory.iterdir():
            if directory == root and (re.fullmatch(r"\d{10,17}", path.name) or re.fullmatch(r"\d{4}[-_]\d{2}[-_]\d{2}.*", path.name) or re.match(r"\.tmp_.*source", path.name) or path.name in {"运行记录", "骨架检查"}):
                problems.append(path)
            if path.suffix.lower() == ".zip" and (directory == root or "测试" in path.relative_to(root).parts):
                problems.append(path)
            if path.is_dir() and not path.is_symlink() and path.name not in ARTIFACT_DIRS:
                if "测试" in path.relative_to(root).parts and (path.name.startswith(("run_", "pytest", "SeeThrough_external_")) or path.name == "benchmark产物"):
                    problems.append(path)
                elif re.match(r"\.tmp_.*source", path.name):
                    problems.append(path)
                else:
                    pending.append(path)
    return problems


@lru_cache
def production_trees():
    files = [p for name in SOURCE_DIRS for p in (ROOT / name).rglob("*.py")]
    files += [ROOT / "启动程序.py", ROOT / "运行配方研发.py"]
    return {p: ast.parse(p.read_text(encoding="utf-8-sig")) for p in files}


def test_唯一源码根及无嵌套快照():
    assert all((ROOT / name).exists() for name in ("核心系统", "插件", "启动程序.py"))
    assert not layout_problems(ROOT)
    # 精确检查已清出的历史位置，不递归扫描审计结果。
    audit = ROOT / "审计结果" / "05_稳健性审计"
    for name in ("pytest沙盒", "流程无标签沙盒", "流程有标签沙盒", "运行复现器.py"):
        assert not (audit / name).exists(), audit / name


def test_检测器能发现二次源码和数字目录(tmp_path):
    nested = tmp_path / "backup" / "nested"
    for name in ("核心系统", "插件"):
        (nested / name).mkdir(parents=True, exist_ok=True)
    (nested / "启动程序.py").touch()
    (tmp_path / "1234567890123").mkdir()
    assert set(layout_problems(tmp_path)) == {nested, tmp_path / "1234567890123"}


def test_测试区只保留正式源码与明确占位():
    allowed_dirs = {"SeeThrough回归测试", "界面端到端测试", "benchmark工具", "fixtures", "__pycache__"}
    for path in (ROOT / "测试").iterdir():
        if path.is_dir():
            assert path.name in allowed_dirs, path
        else:
            assert path.suffix == ".py", path
    for name in allowed_dirs - {"__pycache__", "fixtures"}:
        for path in (ROOT / "测试" / name).iterdir():
            assert path.name == "__pycache__" or path.name == ".gitkeep" or (path.is_file() and path.suffix == ".py"), path


def test_生产代码不导入生成物或兼容旧路径():
    forbidden = {"测试", "审计结果", "运行记录", "运行结果", "cache", ".cache"}
    for path, tree in production_trees().items():
        own = path.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            else:
                continue
            for module in modules:
                assert not any(module == name or module.startswith(name + ".") for name in forbidden), (path, module)
                if own not in SHIMS:
                    assert module not in SHIMS, (path, module)


def test_普通用途插件不反向导入编排且UI不读私有配置():
    plugin = production_trees()[ROOT / "插件/颅骨透明化/颅骨透明化功能插件.py"]
    for node in ast.walk(plugin):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("核心系统"), node.module
    ui = production_trees()[ROOT / "软件界面/配方构建页面.py"]
    assert not any(isinstance(node, ast.ImportFrom) and node.module == "核心系统.配方评估流程" and any(item.name.startswith("_") for item in node.names) for node in ast.walk(ui))


def test_旧路径仅作导出不保存第二份业务():
    for module in SHIMS:
        path = ROOT / (module.replace(".", "/") + ".py")
        tree = production_trees()[path]
        assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Call)) for node in ast.walk(tree)), path


def test_git白名单不会放行生成树内Python():
    paths = ["测试/pytest输出/核心系统/伪源码.py", "测试/SeeThrough回归测试/pytest输出/插件/伪源码.py", "测试/SeeThrough_external_20990101/runner.py", "审计结果/benchmark/run_x/runner_frozen.py", ".cache/temp/插件/伪源码.py"]
    result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], input="\n".join(paths), cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == len(paths)
    public = subprocess.run(["git", "check-ignore", "--no-index", "测试/新增单元测试.py", "测试/界面端到端测试/新增界面测试.py", "测试/SeeThrough回归测试/新增科学测试.py"], cwd=ROOT, capture_output=True, check=False)
    assert public.returncode == 1


def test_AI搜索明确排除产物():
    rules = set((ROOT / ".ignore").read_text(encoding="utf-8").splitlines())
    assert {"审计结果/", "数据/", ".cache/", "模型保存/", "__pycache__/", ".venv/", "*.zip"} <= rules


def test_合法深层源码不应被判定污染(tmp_path):
    source = tmp_path / "插件/公开数据/providers/pubchem/schema/version/fields"
    source.mkdir(parents=True)
    (source / "mapping.py").touch()
    assert not layout_problems(tmp_path)


def test_正常测试使用canonical接口():
    for path in (ROOT / "测试").rglob("*测试.py"):
        if path.name == "兼容边界测试.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in SHIMS, (path, node.module)
                assert not any(x.name in {"创建补充数据3流程控制器", "_配置对象"} for x in node.names), path
            elif isinstance(node, ast.Import):
                assert all(x.name not in SHIMS for x in node.names), path


def test_最小离线fixture有明确白名单():
    allowed = {"README.md", "补充数据2结构输入.csv", "补充数据2身份输入.csv"}
    fixture = ROOT / "测试/fixtures/seethrough"
    assert {p.name for p in fixture.iterdir()} == allowed
    result = subprocess.run(["git", "check-ignore", "--no-index", *[str(p.relative_to(ROOT)) for p in fixture.iterdir()]], cwd=ROOT, capture_output=True)
    assert result.returncode == 1


def test_UI只依赖核心公开入口与设置():
    for path, tree in production_trees().items():
        if "软件界面" not in path.parts:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").split(".")[0] == "插件", (path, node.lineno)
            if isinstance(node, ast.Import):
                assert not any(x.name.split(".")[0] == "插件" for x in node.names), path
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"插件管理器", "plugin_manager"}, (path, node.lineno)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "执行":
                assert not isinstance(node.func.value, ast.Call), (path, node.lineno)


def test_生产默认规则只从显式factory获取():
    for path, tree in production_trees().items():
        aliases = {"属性注册表", "规则注册表"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                aliases.update(x.asname or x.name for x in node.names if x.name in aliases)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "默认":
                owner = node.func.value
                name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
                assert name not in aliases, (path, node.lineno)
    engine = production_trees()[ROOT / "核心系统/通用规则引擎.py"]
    # 数据结构/执行器不再内嵌领域预设构造；所有预设由设置模块提供。
    for node in ast.walk(engine):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"属性定义", "应用配置"}
        if isinstance(node, ast.Name):
            assert node.id != "CORE_METRICS"
