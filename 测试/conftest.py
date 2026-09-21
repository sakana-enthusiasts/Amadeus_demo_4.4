"""默认离线；论文集成测试只读命名原件，全部输出进入系统临时根。"""

import builtins
import io
from pathlib import Path
import shutil
import socket
import os
import tempfile

import pytest

from 核心系统.数据管理接口 import 文件数据访问管理器

REPOSITORY = Path(__file__).resolve().parents[1]
# session 完成后只保留路径；测试不能修改共享运行。
FROZEN_ROOTS = []


def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", help="运行版本控制离线输入的科学及 UI 集成回归")
    parser.addoption("--run-optimization", action="store_true", help="检查显式安装的优化可选依赖")


def pytest_configure(config):
    location = config.option.basetemp or os.environ.get("PYTEST_DEBUG_TEMPROOT") or tempfile.gettempdir()
    base = Path(location).resolve()
    if base == REPOSITORY or REPOSITORY in base.parents or base in REPOSITORY.parents:
        raise pytest.UsageError("pytest 临时根必须位于项目外的系统 TEMP，不得包含或覆盖源码树")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.get_closest_marker("external"):
            item.add_marker(pytest.mark.skip(reason="外部服务测试不属于离线验证"))
        elif item.get_closest_marker("integration") and not config.getoption("--run-integration"):
            item.add_marker(pytest.mark.skip(reason="需显式 --run-integration"))
        elif item.get_closest_marker("optimization") and not config.getoption("--run-optimization"):
            item.add_marker(pytest.mark.skip(reason="需安装 requirements-optimization.txt 并显式 --run-optimization"))


@pytest.fixture(scope="session", autouse=True)
def offline_and_readonly():
    # session fixture 生成结果时同样受离线和真实仓库写保护约束。
    with pytest.MonkeyPatch.context() as patch:
        def deny_network(*args, **kwargs):
            raise AssertionError("测试禁止真实联网；请注入 fake provider/client")
        for name in ("connect", "connect_ex"):
            patch.setattr(socket.socket, name, deny_network)
        patch.setattr(socket, "create_connection", deny_network)
        def checked_open(original):
            def open_file(file, mode="r", *args, **kwargs):
                if isinstance(file, (str, bytes, Path)) and any(x in str(mode) for x in "wax+"):
                    target = Path(file).resolve()
                    if any(target == root or root in target.parents for root in [REPOSITORY, *FROZEN_ROOTS]):
                        raise AssertionError(f"测试不能写真实项目或共享只读运行：{target}")
                return original(file, mode, *args, **kwargs)
            return open_file
        patch.setattr(builtins, "open", checked_open(builtins.open))
        patch.setattr(io, "open", checked_open(io.open))
        yield
        FROZEN_ROOTS.clear()


def copy_paper_inputs(root, supplement=2):
    fixtures = {
        "数据/论文原始数据/SeeThrough补充数据3_最终候选与混合折射率.xlsx": "数据/论文原始数据/SeeThrough补充数据3_最终候选与混合折射率.xlsx",
        "数据/软件数据库/补充数据3结构映射表.csv": "数据/软件数据库/补充数据3结构映射表.csv",
    }
    if supplement == 2:
        fixtures.update({
            "数据/论文原始数据/SeeThrough补充数据2_1619个水相候选.xlsx": "数据/论文原始数据/SeeThrough补充数据2_1619个水相候选.xlsx",
            "数据/软件数据库/补充数据2论文最终10标签表.csv": "数据/软件数据库/补充数据2论文最终10标签表.csv",
            "测试/fixtures/seethrough/补充数据2结构输入.csv": "数据/软件数据库/补充数据2结构缓存.csv",
            "测试/fixtures/seethrough/补充数据2身份输入.csv": "数据/软件数据库/化合物身份缓存.csv",
        })
    for relative, destination in fixtures.items():
        source = REPOSITORY / relative
        if not source.is_file():
            pytest.fail(f"缺少版本控制的 SeeThrough 输入：{relative}；禁止回退本地缓存/历史结果")
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


@pytest.fixture
def isolated_paper_root(tmp_path):
    return copy_paper_inputs(tmp_path)


@pytest.fixture(scope="session")
def seethrough2_run(tmp_path_factory, offline_and_readonly):
    from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器
    from 插件.结果展示.筛选结果图表插件 import 筛选结果图表插件
    root = copy_paper_inputs(tmp_path_factory.mktemp("seethrough2"))
    controller = 创建颅骨透明化筛选流程控制器(root)
    result = controller.执行补充数据2规则筛选流程(启用网络查询=False)
    if not result["结果可视化已启用"]:
        筛选结果图表插件().执行({"数据管理器": controller.数据管理器})
    FROZEN_ROOTS.append(root.resolve())
    return root, result["run_id"]


@pytest.fixture(scope="session")
def seethrough3_run(tmp_path_factory, offline_and_readonly):
    from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器
    root = copy_paper_inputs(tmp_path_factory.mktemp("seethrough3"), supplement=3)
    result = 创建颅骨透明化筛选流程控制器(root).执行补充数据3真实流程()
    FROZEN_ROOTS.append(root.resolve())
    return root, result["run_id"]


def run_reader(run):
    from 核心系统.运行数据管理 import 运行数据管理器
    root, run_id = run
    manager = 运行数据管理器(root)
    manager.激活运行(run_id)
    return manager


@pytest.fixture
def seethrough2(seethrough2_run):
    return run_reader(seethrough2_run)


@pytest.fixture
def seethrough3(seethrough3_run):
    return run_reader(seethrough3_run)


@pytest.fixture
def paper_ui(monkeypatch, seethrough2_run, seethrough3_run):
    # 页面使用真实 session run_id；只替换明确的输入根，不猜测模块或测试名称。
    import 软件界面.论文运行上下文 as context
    def reader(root, supplement):
        run = seethrough2_run if supplement == 2 else seethrough3_run
        return run_reader(run)
    monkeypatch.setattr(context, "读取论文运行", reader)
