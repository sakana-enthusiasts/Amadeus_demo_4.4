"""同一干净临时 run 的只读科学断言，不重复执行昂贵流程。"""

from math import isclose, sqrt

import pytest

pytestmark = pytest.mark.integration


def test_补充数据2清理后严格得到1619个候选(seethrough2) -> None:
    审计 = seethrough2.读取中间结果("补充数据2_导入清理审计")
    记录 = seethrough2.读取筛选结果("补充数据2_规则筛选统一记录")
    assert int(审计.loc[审计["项目"].eq("原始数据行数"), "数量"].iloc[0]) == 1632
    assert int(审计.loc[审计["项目"].eq("副表头行"), "数量"].iloc[0]) == 1
    assert int(审计.loc[审计["项目"].eq("C# 对照/非候选行"), "数量"].iloc[0]) == 12
    assert len(记录) == 1619
    assert 记录["候选编号"].str.fullmatch(r"#\d{4}").all()



def test_补充数据2数值初筛候选均计算BA和VA汉森距离(seethrough2) -> None:
    距离 = seethrough2.读取中间结果("补充数据2_汉森距离结果")
    assert len(距离) == 82
    assert 距离["候选编号"].nunique() == 41
    assert set(距离["参照试剂编号"]) == {"BA", "VA"}
    行 = 距离.loc[(距离["候选编号"].eq("#0093")) & (距离["参照试剂编号"].eq("BA"))].iloc[0]
    预期 = sqrt(4 * (行["候选_dD"] - 行["参照_dD"]) ** 2 + (行["候选_dP"] - 行["参照_dP"]) ** 2 + (行["候选_dH"] - 行["参照_dH"]) ** 2)
    assert isclose(行["汉森距离_Ra"], 预期, rel_tol=0, abs_tol=1e-6)



def test_补充数据2自动数值规则保留20个并恢复论文最终10个(seethrough2) -> None:
    记录 = seethrough2.读取筛选结果("补充数据2_规则筛选统一记录")
    自动通过 = 记录["自动规则通过"].astype(str).str.lower().eq("true")
    最终10 = 记录["论文最终10候选标签"].eq("是")
    assert int(自动通过.sum()) == 20
    assert int((自动通过 & 最终10).sum()) == 10
    assert int((自动通过 & ~最终10).sum()) == 10
    assert 记录.loc[最终10, "论文最终10对照状态"].eq("已由自动规则恢复").all()
    assert 记录.loc[~自动通过, "自动排除原因"].ne("").all()

