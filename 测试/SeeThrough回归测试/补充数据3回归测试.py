"""同一干净临时 run 的只读科学断言，不重复执行昂贵流程。"""

from math import isclose, sqrt

import pytest

pytestmark = pytest.mark.integration


def test_RDKit为补充数据3全部真实试剂计算必需描述符(seethrough3) -> None:
    描述符 = seethrough3.读取中间结果("补充数据3_RDKit描述符结果")
    必需描述符 = {"分子量", "脂水分配指标_MolLogP", "极性表面积_TPSA", "氢键供体数", "氢键受体数", "芳香环数量", "可旋转键数量", "芳香性", "基础官能团"}
    assert 描述符["候选编号"].nunique() == 12
    assert 必需描述符.issubset(set(描述符["描述符名称"]))
    assert 描述符["是否计算成功"].astype(str).str.lower().eq("true").all()
    assert 描述符["工具版本"].notna().all()



def test_统一记录保留论文结构RDKit与汉森来源字段(seethrough3) -> None:
    统一记录 = seethrough3.读取最终结果("补充数据3_化学属性统一记录")
    必需列 = {"论文_dD", "结构映射_SMILES", "RDKit_分子量", "汉森距离_与BA", "汉森距离_与VA", "论文原始字段来源", "分子结构来源", "RDKit描述符来源", "汉森距离来源", "缺失状态", "错误信息"}
    assert len(统一记录) == 12
    assert 必需列.issubset(统一记录.columns)
    assert 统一记录["论文原始字段来源"].eq("SeeThrough Supplementary Data 3").all()
    assert 统一记录["结构映射_SMILES"].notna().all()



def test_每种真实水相候选均计算BA与VA汉森距离(seethrough3) -> None:
    距离 = seethrough3.读取中间结果("补充数据3_汉森距离结果")
    assert len(距离) == 20
    assert set(距离["参照试剂编号"]) == {"BA", "VA"}
    行 = 距离.loc[(距离["候选编号"] == "#0093") & (距离["参照试剂编号"] == "BA")].iloc[0]
    预期 = sqrt(4 * (行["候选_dD"] - 行["参照_dD"]) ** 2 + (行["候选_dP"] - 行["参照_dP"]) ** 2 + (行["候选_dH"] - 行["参照_dH"]) ** 2)
    assert isclose(行["汉森距离_Ra"], 预期, rel_tol=0, abs_tol=1e-6)
    assert 距离["数据来源"].eq("SeeThrough Supplementary Data 3").all()



def test_补充数据3所有真实试剂均有经核对的可读结构(seethrough3) -> None:
    结构结果 = seethrough3.读取中间结果("补充数据3_结构映射结果")
    assert len(结构结果) == 12
    assert 结构结果["结构状态"].eq("已获得").all()
    assert 结构结果["结构映射_来源URL"].str.startswith("https://pubchem.ncbi.nlm.nih.gov/compound/").all()
    assert 结构结果["结构映射_人工核对状态"].str.contains("CAS").all()



def test_补充数据3真实导入为12条统一候选基础记录(seethrough3) -> None:
    记录 = seethrough3.读取中间结果("补充数据3_统一候选基础记录")
    assert len(记录) == 12
    assert set(记录.loc[记录["试剂角色"].eq("有机相参照"), "候选编号"]) == {"BA", "VA"}
    assert int(记录["试剂角色"].eq("水相候选").sum()) == 10
    assert set(["论文_dD", "论文_dP", "论文_dH"]).issubset(记录.columns)

