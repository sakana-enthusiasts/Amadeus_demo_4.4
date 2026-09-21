from __future__ import annotations

from pathlib import Path

import pandas as pd

from 核心系统.化合物确认清单 import 创建确认清单, 获取当前工作草稿, 保存工作草稿成分, 向工作草稿追加候选, 确认工作草稿, 已确认清单目录, 读取确认清单
from 核心系统.毒理分析 import 指定, 未知, 毒理证据匹配引擎, 默认会话
from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器
from 核心系统.运行数据管理 import 运行数据管理器


def _会话() -> dict:
    会话 = 默认会话()
    会话["条件"]["物种"] = {"状态": 指定, "值": "小鼠"}
    会话["条件"]["品系"] = {"状态": 指定, "值": "C57BL/6J"}
    会话["条件"]["给药途径"] = {"状态": 指定, "值": "口服"}
    会话["化合物清单"] = [{"候选编号": "C1"}, {"候选编号": "C2"}]
    return 会话


def _证据(品系: str = "C57BL/6J") -> pd.DataFrame:
    return pd.DataFrame([{
        "候选编号": "C1", "物种": "小鼠", "品系": 品系, "给药途径": "口服",
        "毒性终点": "肝毒性", "来源名称或文献": "本地实验记录",
    }])


def test_指定条件满足时为A级且未知条件只标记未比较() -> None:
    会话 = _会话()
    结果, 缺口 = 毒理证据匹配引擎(会话).匹配(_证据())
    assert 结果.loc[0, "匹配等级"] == "A级"
    assert "年龄（天）" in 结果.loc[0, "未比较字段"]
    assert not 结果.loc[0, "记录未报告字段"]
    assert "C2" in set(缺口["候选编号"])


def test_记录空白绝不算A级匹配而是D级参考() -> None:
    结果, _ = 毒理证据匹配引擎(_会话()).匹配(_证据(""))
    assert 结果.loc[0, "匹配等级"] == "D级参考"
    assert "品系" in 结果.loc[0, "记录未报告字段"]


def test_没有任何明确条件时输出数据缺口而非匹配成功() -> None:
    会话 = 默认会话()
    assert 会话["条件"]["物种"]["状态"] == 未知
    结果, _ = 毒理证据匹配引擎(会话).匹配(_证据())
    assert 结果.loc[0, "匹配等级"] == "数据缺口"


def test_关闭自动降级时不显示B级或C级() -> None:
    会话 = _会话()
    会话["匹配策略"]["允许自动降级"] = False
    会话["条件"]["品系"] = {"状态": 指定, "值": "BALB/c"}
    结果, _ = 毒理证据匹配引擎(会话).匹配(_证据())
    assert 结果.loc[0, "匹配等级"] != "B级"
    assert 结果.loc[0, "匹配等级"] != "C级"


def test_流程保存匹配和公开库接口状态但不查询公开库(tmp_path: Path) -> None:
    控制器 = 创建颅骨透明化筛选流程控制器(tmp_path)
    会话 = _会话()
    会话["化合物批次"] = {"批次编号": "batch-demo", "来源运行编号": "run-demo", "确认清单标识": "化合物确认清单_batch-demo"}
    输出 = 控制器.执行毒理证据匹配(会话, _证据())
    assert len(输出["匹配结果"]) == 1
    assert 输出["匹配结果"].loc[0, "化合物批次编号"] == "batch-demo"
    assert 输出["来源接口状态"].loc[0, "状态"] == "未启用"
    assert (tmp_path / "数据" / "筛选结果" / "毒理匹配结果.csv").is_file()


def test_确认清单是关联运行的不可覆盖快照并可供毒理引用(tmp_path: Path) -> None:
    管理器 = 运行数据管理器(tmp_path)
    run_id = 管理器.创建运行("user_custom", "candidates.csv")
    管理器.保存筛选结果("用户导入_规则筛选结果", pd.DataFrame([{
        "候选编号": "C1", "化学名称": "Compound A", "CAS号": "100-00-0", "规则总状态": "通过",
    }]))
    管理器.保存中间结果("用户导入_化合物身份映射", pd.DataFrame([{
        "候选编号": "C1", "PubChem CID": "123", "InChIKey": "KEY", "Canonical SMILES": "CCO", "匹配状态": "已匹配",
    }]))
    元数据, 清单 = 创建确认清单(管理器, run_id, ["C1"], "第一轮确认", "单成分毒理评估")
    管理器.保存筛选结果("用户导入_规则筛选结果", pd.DataFrame([{
        "候选编号": "C1", "化学名称": "Changed", "CAS号": "100-00-0", "规则总状态": "通过",
    }]))
    新管理器 = 运行数据管理器(tmp_path)
    assert 元数据["批次编号"] in set(已确认清单目录(新管理器)["批次编号"])
    已读元数据, 已读清单 = 读取确认清单(新管理器, 元数据["批次编号"])
    assert 已读元数据["来源运行编号"] == run_id
    assert 清单.loc[0, "化学名称"] == "Compound A"
    assert 已读清单.loc[0, "化学名称"] == "Compound A"


def test_多轮工作草稿可追加浓度并在最终确认后生成完整批次(tmp_path: Path) -> None:
    管理器 = 运行数据管理器(tmp_path)
    run_id = 管理器.创建运行("user_custom", "round1.csv")
    管理器.保存筛选结果("用户导入_规则筛选结果", pd.DataFrame([{
        "候选编号": "C1", "化学名称": "Compound A", "CAS号": "100-00-0", "规则总状态": "通过",
    }]))
    管理器.保存中间结果("用户导入_化合物身份映射", pd.DataFrame([{"候选编号": "C1", "PubChem CID": "123"}]))
    草稿元数据, 草稿 = 向工作草稿追加候选(管理器, run_id, ["C1"])
    草稿.loc[0, "浓度值"] = 15.0
    草稿.loc[0, "浓度单位"] = "mM"
    草稿.loc[0, "是否纳入颅骨透明化计算"] = True
    保存工作草稿成分(管理器, 草稿元数据["草稿编号"], 草稿)
    批次, 清单 = 确认工作草稿(管理器, 草稿元数据["草稿编号"], "完整配方候选", "单成分毒理评估；颅骨透明化计算")
    assert 清单.loc[0, "浓度值"] == 15.0 and 清单.loc[0, "浓度单位"] == "mM"
    assert bool(清单.loc[0, "是否纳入颅骨透明化计算"])
    assert 清单.loc[0, "透明化计算接口状态"] == "已预留，待接入"
    新草稿, 新草稿成分 = 获取当前工作草稿(运行数据管理器(tmp_path))
    assert 新草稿["草稿编号"] != 草稿元数据["草稿编号"] and 新草稿成分.empty
    _, 已读清单 = 读取确认清单(运行数据管理器(tmp_path), 批次["批次编号"])
    assert 已读清单.loc[0, "候选编号"] == "C1"


class _PubChem响应:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"Record": {"Section": [{"Information": [{"Value": {"StringWithMarkup": [{"String": "H302: Harmful if swallowed"}, {"String": "Warning"}]}}]}]}}


def _公开会话() -> dict:
    会话 = _会话()
    会话["化合物清单"] = [{"候选编号": "C1", "化学名称": "Compound A", "CAS": "100-00-0", "PubChem CID": "123"}]
    会话["化合物批次"] = {"批次编号": "batch-public", "来源运行编号": "run-public", "确认清单标识": "化合物确认清单_batch-public"}
    会话["来源策略"]["启用公开数据源"] = ["PubChem GHS"]
    return 会话


def test_单一公开数据源可查询并只输出危险提示(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("插件.公开数据.providers.网络客户端.requests.get", lambda *args, **kwargs: _PubChem响应())
    控制器 = 创建颅骨透明化筛选流程控制器(tmp_path)
    会话 = _公开会话()
    公开证据 = 控制器.执行毒理公开数据查询(会话)
    输出 = 控制器.执行毒理证据匹配(会话, 公开证据)
    assert 公开证据.loc[0, "查询状态"] == "已查询"
    assert 公开证据.loc[0, "证据可参与条件匹配"] == False
    assert len(输出["危险提示"]) == 1 and 输出["匹配结果"].empty
    assert "C1" in set(输出["数据缺口"]["候选编号"])


def test_公开数据与本地实验数据可合并且不混淆用途(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("插件.公开数据.providers.网络客户端.requests.get", lambda *args, **kwargs: _PubChem响应())
    控制器 = 创建颅骨透明化筛选流程控制器(tmp_path)
    会话 = _公开会话()
    公开证据 = 控制器.执行毒理公开数据查询(会话)
    本地证据 = _证据()
    输出 = 控制器.执行毒理证据匹配(会话, pd.concat([公开证据, 本地证据], ignore_index=True))
    assert len(输出["危险提示"]) == 1
    assert 输出["匹配结果"].loc[0, "匹配等级"] == "A级"
    assert 输出["摘要"].loc[0, "本地或人工证据数"] == 1
    assert 输出["摘要"].loc[0, "公开危险提示数"] == 1


def test_公开查询会复用本地缓存(monkeypatch, tmp_path: Path) -> None:
    调用次数 = {"值": 0}

    def 请求(*args, **kwargs):
        调用次数["值"] += 1
        return _PubChem响应()

    monkeypatch.setattr("插件.公开数据.providers.网络客户端.requests.get", 请求)
    控制器 = 创建颅骨透明化筛选流程控制器(tmp_path)
    会话 = _公开会话()
    首次 = 控制器.执行毒理公开数据查询(会话)
    二次 = 控制器.执行毒理公开数据查询(会话)
    assert 调用次数["值"] == 1
    assert 首次.loc[0, "缓存命中"] == "否" and 二次.loc[0, "缓存命中"] == "是"
