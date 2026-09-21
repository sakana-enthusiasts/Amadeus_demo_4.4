"""离线输入缺失不能联网或写空缓存污染下一次运行。"""

import pandas as pd

from 核心系统.运行数据管理 import 运行数据管理器
from 插件.化学计算.RDKit结构处理插件 import RDKit结构处理插件


def test_无结构缓存的连续离线运行保留缺失且不生成空缓存(tmp_path, monkeypatch):
    manager = 运行数据管理器(tmp_path)
    plugin = RDKit结构处理插件()
    def forbid_query(*args):
        raise AssertionError("离线结构处理不能尝试网络查询")
    monkeypatch.setattr(plugin, "_查询PubChem", forbid_query)
    for _ in range(2):
        manager.创建运行(运行类型="离线结构回归")
        manager.保存中间结果("补充数据2_数值初筛记录", pd.DataFrame([{
            "候选编号": "S1", "论文_CAS号": "missing", "论文_化学名称": "明确缺失的输入",
            "数值初筛通过": True,
        }]))
        result = plugin.执行({"数据管理器": manager, "补充数据2结构处理": True})
        assert result.loc[0, "结构状态"] == "缺失"
        assert "网络查询未启用" in result.loc[0, "结构错误信息"]
        assert not (manager.软件数据库目录 / "补充数据2结构缓存.csv").exists()
