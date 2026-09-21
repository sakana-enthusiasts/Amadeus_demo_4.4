"""真实筛选图表的生成、导出与数据同步回归测试。"""

import json
import pytest
from pathlib import Path
import tempfile

from PIL import Image
from streamlit.testing.v1 import AppTest

from 核心系统.数据管理接口 import 文件数据访问管理器
from 插件.结果展示.筛选结果图表插件 import 筛选结果图表插件


项目根目录 = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration


def test_图表可生成且PNG_SVG非空(seethrough2, tmp_path) -> None:
    管理器 = seethrough2
    管理器.导出结果目录 = tmp_path
    路径 = 筛选结果图表插件().执行({"数据管理器": 管理器})
    for 键 in ["数量图PNG", "数量图SVG", "分布图PNG", "分布图SVG"]:
        assert 路径[键].is_file() and 路径[键].stat().st_size > 1000
    assert 路径["数量图PNG"].read_bytes().startswith(b"\x89PNG")
    assert b"<svg" in 路径["数量图SVG"].read_bytes()[:1000]


def test_数量图数据与真实筛选统计一致且无140(seethrough2) -> None:
    管理器 = seethrough2
    元数据路径 = 管理器.导出结果目录 / "图表" / "筛选结果图表元数据.json"
    元数据 = json.loads(元数据路径.read_text(encoding="utf-8"))
    assert list(元数据["软件真实计算链"].values()) == [1619, 1373, 1297, 225, 41, 20]
    assert 140 not in 元数据["软件真实计算链"].values()
    assert 元数据["自动候选数"] == 20
    assert 元数据["论文最终10恢复数"] == 10


def test_PNG为300_DPI导出(seethrough2) -> None:
    管理器 = seethrough2
    路径 = 管理器.导出结果目录 / "图表" / "候选试剂筛选数量变化图.png"
    with Image.open(路径) as 图片:
        DPI = 图片.info.get("dpi", (0, 0))
    assert DPI[0] >= 299 and DPI[1] >= 299


def test_修改输入统计后重新生成会同步写入元数据(seethrough2) -> None:
    管理器 = seethrough2
    原统计 = 管理器.读取中间结果("补充数据2_规则筛选步骤统计")
    原记录 = 管理器.读取筛选结果("补充数据2_规则筛选统一记录")

    class 临时数据管理器:
        def __init__(self, 导出目录: Path) -> None:
            self.导出结果目录 = 导出目录
        def 读取中间结果(self, 标识: str):
            assert 标识 == "补充数据2_规则筛选步骤统计"
            修改 = 原统计.copy()
            修改.loc[修改.index[1], "剩余数量"] = 1296
            return 修改
        def 读取筛选结果(self, 标识: str):
            assert 标识 == "补充数据2_规则筛选统一记录"
            return 原记录.copy()
    with tempfile.TemporaryDirectory() as 临时目录:
        路径 = 筛选结果图表插件().执行({"数据管理器": 临时数据管理器(Path(临时目录))})
        元数据 = json.loads(路径["元数据"].read_text(encoding="utf-8"))
        assert list(元数据["软件真实计算链"].values())[2] == 1296
