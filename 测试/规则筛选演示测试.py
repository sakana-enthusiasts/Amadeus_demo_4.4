"""补充数据2真实筛选演示的离线回归测试；不访问网络。"""

import pytest

import openpyxl
import pandas as pd

from 核心系统.数据管理接口 import 文件数据访问管理器
from 插件.筛选与评价.规则筛选插件 import 规则筛选插件


pytestmark = pytest.mark.integration


def _自动记录(管理器) -> pd.DataFrame:
    return 管理器.读取中间结果("补充数据2_自动规则筛选记录")


def test_候选编号连续且唯一(seethrough2) -> None:
    管理器 = seethrough2
    数据 = 管理器.读取中间结果("补充数据2_统一候选记录")
    assert len(数据) == 1619
    assert 数据["候选编号"].is_unique
    assert set(数据["候选编号"]) == {f"#{编号:04d}" for 编号 in range(1, 1620)}


def test_自动筛选不依赖最终答案标签(seethrough2) -> None:
    管理器 = seethrough2
    class 禁止标签读取管理器:
        def __init__(self, 原管理器: 文件数据访问管理器) -> None:
            self.原管理器 = 原管理器
        def __getattr__(self, 名称: str):
            if 名称 == "读取软件数据库表格":
                raise AssertionError("自动规则不应读取论文最终10标签")
            if 名称.startswith("保存"):
                return lambda *args: None
            return getattr(self.原管理器, 名称)
    结果 = 规则筛选插件().执行最终自动规则筛选({"数据管理器": 禁止标签读取管理器(管理器)})
    原集合 = set(_自动记录(管理器).loc[_自动记录(管理器)["自动规则通过"].astype(str).str.lower().eq("true"), "候选编号"])
    新集合 = set(结果.loc[结果["自动规则通过"], "候选编号"])
    assert 新集合 == 原集合
    assert len(新集合) == 20


def test_论文140仅为方法对照而非自动步骤(seethrough2) -> None:
    管理器 = seethrough2
    步骤 = 管理器.读取中间结果("补充数据2_规则筛选步骤统计")
    assert 140 not in 步骤["剩余数量"].tolist()
    assert len(步骤) == 5


def test_41个候选完成结构处理并缓存(seethrough2) -> None:
    管理器 = seethrough2
    结构 = 管理器.读取中间结果("补充数据2_结构映射结果")
    缓存 = 管理器.读取软件数据库表格("补充数据2结构缓存.csv")
    assert len(结构) == 41 and len(缓存) >= 41
    assert {"PubChem CID", "SMILES", "查询时间", "名称核对状态", "结构查询失败原因"}.issubset(缓存.columns)


def test_RDKit结果已合并且失败可追溯(seethrough2) -> None:
    管理器 = seethrough2
    记录 = 管理器.读取筛选结果("补充数据2_规则筛选统一记录")
    assert {"分子量", "脂水分配指标_MolLogP", "芳香环数量", "结构状态"}.issubset(记录.columns)
    assert (记录["结构状态"].eq("缺失")).sum() == 1


def test_汉森距离和0777敏感性检查(seethrough2) -> None:
    管理器 = seethrough2
    冲突 = 管理器.读取筛选结果("补充数据2与3_官方数据冲突记录")
    记录 = 冲突[冲突["候选编号"].eq("#0777")]
    assert {"dD", "dP", "dH"}.issubset(set(记录["字段名称"]))
    assert 记录["是否影响通过或排除结果"].str.contains("结论不变").all()


def test_筛选结果目录和数据接口完整(seethrough2) -> None:
    管理器 = seethrough2
    assert 管理器.筛选结果目录.is_dir()
    for 名称 in ["读取软件数据库表格", "读取最终结果", "结果存在", "保存筛选结果", "读取筛选结果", "保存导出报告"]:
        assert hasattr(管理器, 名称)


def test_Excel报告已生成且包含要求工作表(seethrough2) -> None:
    管理器 = seethrough2
    路径 = 管理器.导出结果目录 / "SeeThrough规则筛选演示报告.xlsx"
    工作簿 = openpyxl.load_workbook(路径, read_only=True)
    必需 = {"运行摘要", "筛选步骤", "自动候选", "论文标签对照", "论文标签验证", "结构映射", "RDKit描述符", "Hansen距离", "毒性原始证据", "官方数据冲突", "筛选统一记录", "数据来源与版本"}
    assert 必需.issubset(set(工作簿.sheetnames))
