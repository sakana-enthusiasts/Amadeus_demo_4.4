"""通用上传、身份转换和非聚合毒性视图的回归测试。"""

from pathlib import Path

import pytest

import pandas as pd

from 核心系统.数据管理接口 import 文件数据访问管理器
from 插件.数据导入.通用候选表导入插件 import 通用候选表导入插件
from 插件.数据导入.化合物身份转换插件 import 化合物身份转换插件




def test_通用CSV上传生成统一记录和不可覆盖原件(tmp_path: Path) -> None:
    本地管理器 = 文件数据访问管理器(tmp_path)
    数据 = "编号,名称,CAS,货号\nA1,Benzyl Alcohol,100-51-6,X1\nA2,Benzyl Alcohol,100-51-6,X2\n"
    结果 = 通用候选表导入插件().执行({"数据管理器": 本地管理器, "文件名": "候选.csv", "文件内容": 数据.encode(), "字段映射": {"化学名称列": "名称", "CAS列": "CAS", "货号列": "货号", "候选编号列": "编号"}})
    assert len(结果) == 2 and "重复CAS" in 结果.iloc[0]["导入冲突说明"]
    assert len(list((tmp_path / "数据" / "用户导入数据").glob("候选*.csv"))) == 1


def test_CAS优先和多CID冲突不自动选结构(monkeypatch) -> None:
    插件 = 化合物身份转换插件()
    monkeypatch.setattr(插件, "_获取CID", lambda 值: [1, 2] if 值 == "CAS" else [1])
    行 = pd.Series({"候选编号": "X", "原始名称": "名称", "原始CAS": "CAS", "原始货号": ""})
    身份, 冲突 = 插件._转换一条(行)
    assert 身份["查询方式"] == "CAS" and 身份["匹配状态"] == "待人工确认" and 冲突


def test_盐水合物混合物与立体结构标记() -> None:
    标记 = 化合物身份转换插件._形式标记("Sodium compound dihydrate contains varying amounts", "C[C@H](O).O.[Na+]")
    assert 标记["是否为盐"] == "是" and 标记["是否为水合物或溶剂化物"] == "是" and 标记["是否为混合物"] == "是" and 标记["未定义立体结构"] == "含显式立体标记"


@pytest.mark.integration
def test_41候选身份和RDKit处理结果存在(seethrough2) -> None:
    管理器 = seethrough2
    身份 = 管理器.读取中间结果("补充数据2_41候选身份映射")
    结构 = 管理器.读取中间结果("补充数据2_结构映射结果")
    描述符 = 管理器.读取中间结果("补充数据2_RDKit描述符结果")
    assert len(身份) == 41 and len(结构) == 41 and 描述符["候选编号"].nunique() == 41


@pytest.mark.integration
def test_毒性证据保留所有关键维度且不覆盖(seethrough2) -> None:
    管理器 = seethrough2
    证据 = 管理器.读取筛选结果("毒性原始证据")
    必需 = {"候选编号", "CAS", "PubChem CID", "InChIKey", "化合物形式", "毒性终点", "物种", "给药途径", "剂量", "暴露时长", "结果", "实验值或预测值", "原始数据、数据库汇总或模型预测", "数据来源", "可信度", "数据是否与当前实验条件匹配"}
    assert len(证据) == 20 and 必需.issubset(证据.columns) and 证据["候选编号"].nunique() == 20


@pytest.mark.integration
def test_动物人体视图不合成总分且CompTox可降级(seethrough2) -> None:
    管理器 = seethrough2
    动物 = 管理器.读取筛选结果("当前动物实验模式结果")
    人体 = 管理器.读取筛选结果("未来人体口服模式结果")
    CompTox = 管理器.读取中间结果("CompTox毒性查询状态")
    assert len(动物) == 20 and 动物["当前实验给药途径"].eq("未配置（不作猜测）").all()
    assert len(人体) == 20 and 人体["说明"].str.contains("不作人体安全结论").all()
    assert CompTox["CompTox接口状态"].eq("未配置").all()


@pytest.mark.integration
def test_毒性终点字典基准物和扩展Excel报告(seethrough2) -> None:
    管理器 = seethrough2
    字典 = 管理器.读取筛选结果("毒性终点字典")
    基准物 = 管理器.读取筛选结果("项目基准物清单")
    assert {"急性毒性", "肝毒性", "遗传毒性", "安全药理"}.issubset(set(字典["毒性终点"]))
    assert {"BA", "VA", "ANP"}.issubset(set(基准物["候选编号"]))
    import openpyxl
    工作簿 = openpyxl.load_workbook(管理器.导出结果目录 / "SeeThrough规则筛选演示报告.xlsx", read_only=True)
    assert {"化合物身份映射", "毒性原始证据", "动物实验模式结果", "人体口服模式结果", "项目基准物比较", "数据缺口"}.issubset(工作簿.sheetnames)


@pytest.mark.integration
def test_待人工确认进入冲突表且0958存在(seethrough2) -> None:
    管理器 = seethrough2
    冲突 = 管理器.读取筛选结果("化合物身份冲突表")
    assert "#0958" in set(冲突["候选编号"].astype(str))
    assert 冲突.loc[冲突["候选编号"].astype(str).eq("#0958"), "人工确认状态"].eq("待确认").any()


def test_空CAS缓存主键不互相覆盖() -> None:
    插件 = 化合物身份转换插件()
    一 = 插件._缓存主键({"原始CAS": "", "原始名称": "A", "原始文件": "x.csv", "候选编号": "1"})
    二 = 插件._缓存主键({"原始CAS": "", "原始名称": "B", "原始文件": "x.csv", "候选编号": "2"})
    assert 一 != 二 and 一.startswith("名称文件编号:")


def test_通用物化字段映射标明来源(tmp_path: Path) -> None:
    本地管理器 = 文件数据访问管理器(tmp_path)
    数据 = "名称,CAS,eRI,dD\nA,100-51-6,1.60,18\n"
    结果 = 通用候选表导入插件().执行({"数据管理器": 本地管理器, "文件名": "字段.csv", "文件内容": 数据.encode(), "字段映射": {"化学名称列": "名称", "CAS列": "CAS", "货号列": None, "候选编号列": None, "eRI列": "eRI", "dD列": "dD"}})
    assert 结果.loc[0, "字段状态_eRI"] == "用户表格提供" and 结果.loc[0, "字段状态_dP"] == "缺失"
