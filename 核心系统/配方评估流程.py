"""颅骨用途流程编排；所有功能插件只读取上游上下文。"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from collections.abc import Callable
from 插件.插件接口 import 基础插件接口
from 核心系统.默认装配 import 装配工作流插件获取器


def 解析物性配置(值: Any) -> dict[str, Any]:
    """解析批次/UI 的物性 JSON 对象，保持空值、缺失与错误语义。"""
    if 值 is None or (not isinstance(值, (str, dict)) and pd.isna(值)):
        return {}
    if isinstance(值, str):
        值 = json.loads(值) if 值.strip() else {}
    if not isinstance(值, dict):
        raise ValueError("物性配置必须是 JSON 对象")
    return dict(值)


def 运行颅骨透明化流程(数据上下文: dict[str, Any], 获取插件: Callable[[str], 基础插件接口] | None = None) -> dict[str, Any]:
    上下文 = dict(数据上下文)
    上下文["用途配置"] = dict(上下文.get("用途配置") or {})
    上下文["用途配置"]["物性约束"] = 解析物性配置(上下文["用途配置"].get("物性约束"))
    获取插件 = 装配工作流插件获取器(获取插件)
    组装 = None
    if 上下文.get("配方定义"):
        组装 = 获取插件("配方输入组装").执行(上下文)
        上下文.update(组装)
        上下文["成分"] = pd.DataFrame(组装["成分"])
    配置 = 获取插件("颅骨透明化用途配置").执行(上下文)
    上下文["用途配置"] = 配置
    上下文["成分RI结果"] = 获取插件("折射率处理").执行(上下文 | {"目标折射率": 配置["目标折射率"]})
    上下文["成分水合结果"] = 获取插件("水合能力处理").执行(上下文)
    成分 = 获取插件("颅骨透明化成分评估").执行(上下文)
    上下文["成分评估"] = 成分
    上下文["成分"] = 成分
    上下文["HSP结果"] = 获取插件("通用HSP计算").执行({"HSP候选": 成分, "HSP参照": 上下文.get("HSP参照")})
    组分HSP = 获取插件("通用HSP计算").执行({"HSP候选": 成分, "HSP参照": 成分})
    if not 组分HSP.empty:
        组分HSP = 组分HSP.loc[组分HSP["候选标识"].astype(str).ne(组分HSP["参照标识"].astype(str))].copy()
        组分HSP["比较类型"] = "配方组分-配方组分"
    设置 = dict(上下文.get("配方设置") or {})
    for 字段 in ("物性模型选择", "物性模型参数", "物性条件"):
        上下文[字段] = 解析物性配置(设置.get(字段)) | 解析物性配置(上下文.get(字段))
    上下文["物性条件"] = {"温度_C": 配置["温度_C"]} | 上下文["物性条件"]
    上下文["配方物性"] = 获取插件("配方物性汇总").执行(上下文)
    上下文["配方摘要"], _ = 获取插件("颅骨透明化配方评估").执行(上下文)
    上下文["实验终点"] = 获取插件("颅骨透明化实验终点评价").执行(上下文)
    特征上下文 = 获取插件("颅骨透明化配方特征构建").执行(上下文)
    特征 = 获取插件("配方特征构建").执行(特征上下文)
    return {"用途配置": 配置, "成分评估": 成分, "配方摘要": 上下文["配方摘要"], "HSP结果": 上下文["HSP结果"],
            "组分HSP结果": 组分HSP, "配方特征": 特征, "实验终点": 上下文["实验终点"],
            "配方物性": pd.DataFrame(上下文["配方物性"].values()),
            "用途约束": 获取插件("颅骨透明化用途约束").执行(上下文), "配方组装": 组装}

# 旧私有 import 兼容；内部调用统一使用公开名称。
_配置对象 = 解析物性配置


class 颅骨透明化用途运行器:
    """旧入口兼容适配；实际编排在核心系统。"""

    def 运行(self, 成分: pd.DataFrame, 用途配置: dict[str, Any], HSP参照: pd.DataFrame | None = None, 配方设置: dict[str, Any] | None = None, 实验记录: pd.DataFrame | None = None) -> dict[str, pd.DataFrame | dict[str, Any]]:
        return 运行颅骨透明化流程({
            "成分": 成分,
            "用途配置": 用途配置,
            "HSP参照": pd.DataFrame() if HSP参照 is None else HSP参照,
            "配方设置": 配方设置 or {},
            "实验记录": pd.DataFrame() if 实验记录 is None else 实验记录,
        })
