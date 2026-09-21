"""用户候选的配置化规则筛选入口。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from 核心系统.通用规则引擎 import 毒性判定指标插件, 通用规则执行器
from 设置.规则注册设置 import 创建默认属性注册表, 创建默认规则注册表
from 核心系统.分子属性 import CORE_METRICS, CandidateMolecularProperties
from 插件.插件接口 import 基础插件接口


class 用户候选规则筛选插件(基础插件接口):
    插件标识 = "用户候选规则筛选"
    输入标识 = "用户导入_统一候选记录"
    输出标识 = "用户导入_规则筛选结果"

    属性字段 = {
        "水合评分平均值": "hydration_score",
        "水合评分标准差": "hydration_std",
        "水合能力": "hydration_ability",
        "eRI": "estimated_ri",
        "dD": "hansen_dD",
        "dP": "hansen_dP",
        "dH": "hansen_dH",
        "与BA的Hansen距离": "hansen_distance_ba",
        "与VA的Hansen距离": "hansen_distance_va",
    }

    @staticmethod
    def _run_id(候选: pd.DataFrame, 数据管理器: Any) -> str:
        if "run_id" in 候选.columns and 候选["run_id"].notna().any():
            return str(候选["run_id"].dropna().iloc[0])
        return str(getattr(数据管理器, "当前运行编号", None) or "legacy")

    @classmethod
    def _属性记录(cls, 候选: pd.DataFrame, run_id: str) -> pd.DataFrame:
        记录: list[dict[str, Any]] = []
        for _, 行 in 候选.iterrows():
            候选编号 = str(行["候选编号"])
            for 字段, 属性编号 in cls.属性字段.items():
                if 字段 not in 候选.columns:
                    continue
                当前值 = 行[字段]
                if isinstance(当前值, str) and not 当前值.strip():
                    当前值 = pd.NA
                记录.append({
                    "run_id": run_id,
                    "候选编号": 候选编号,
                    "属性编号": 属性编号,
                    "当前值": 当前值,
                    "条件": "用户导入",
                    "不确定性": 行.get("水合评分标准差", "") if 属性编号 == "hydration_score" else "",
                })
        return pd.DataFrame(记录, columns=["run_id", "候选编号", "属性编号", "当前值", "条件", "不确定性"])

    @staticmethod
    def _应用阈值覆盖(规则列表: list, 设置: dict[str, Any]) -> list:
        字段 = {
            "ST-AQ-001": "水合评分阈值",
            "ST-AQ-002": "eRI阈值",
            "ST-AQ-003": "Hansen距离阈值",
        }
        结果 = []
        for 规则 in 规则列表:
            阈值字段 = 字段.get(规则.规则编号)
            if 阈值字段 and 阈值字段 in 设置:
                结果.append(replace(规则, 阈值=设置[阈值字段]))
            else:
                结果.append(规则)
        return 结果

    @staticmethod
    def 分子属性记录(结果, run_id, 候选编号列表):
        """正式结果→既有属性长表；不读用户同名字段，不自动计算全部描述符。"""
        允许 = set(map(str, 候选编号列表))
        记录, 已见 = [], set()
        for 候选 in 结果:
            if not isinstance(候选, CandidateMolecularProperties) or 候选.compound_id not in 允许:
                raise ValueError("分子属性结果必须与当前候选编号显式关联")
            for r in 候选.properties:
                if r.metric_id not in CORE_METRICS:
                    continue
                key = (候选.compound_id, r.metric_id)
                if key in 已见:
                    raise ValueError("分子属性记录重复")
                已见.add(key)
                合格 = r.status == "available" and r.unit == CORE_METRICS[r.metric_id].unit
                记录.append({"run_id": run_id, "候选编号": 候选.compound_id, "属性编号": r.metric_id,
                             "当前值": r.value if 合格 else None, "条件": r.to_dict(),
                             "不确定性": r.reason or r.warning or "未量化"})
        return pd.DataFrame(记录, columns=["run_id", "候选编号", "属性编号", "当前值", "条件", "不确定性"])

    def 执行(self, 数据上下文: dict[str, Any]) -> pd.DataFrame:
        数据管理器 = 数据上下文["数据管理器"]
        输入标识 = str(数据上下文.get("候选输入标识", self.输入标识))
        候选 = 数据管理器.读取中间结果(输入标识).copy()
        if 候选.empty:
            raise ValueError("用户候选表为空，无法执行规则")
        if "候选编号" not in 候选.columns:
            raise ValueError("用户候选表缺少候选编号")
        设置 = dict(数据上下文.get("用户筛选设置") or {})
        run_id = self._run_id(候选, 数据管理器)
        配置编号 = str(设置.get("应用配置", "user_custom"))
        规则注册 = 数据上下文.get("规则注册表") or 创建默认规则注册表()
        启用覆盖 = dict(设置.get("规则启用覆盖") or {})
        规则列表 = self._应用阈值覆盖(规则注册.规则列表(配置编号, 启用覆盖), 设置)
        属性记录 = self._属性记录(候选, run_id)
        if 数据上下文.get("分子属性结果") is not None:
            属性记录 = pd.concat([属性记录, self.分子属性记录(
                数据上下文["分子属性结果"], run_id, 候选["候选编号"])], ignore_index=True)
        毒性指标 = 毒性判定指标插件().空数据指标(run_id, 候选["候选编号"].astype(str))
        毒性属性 = 毒性指标.rename(columns={"指标编号": "属性编号"})[["run_id", "候选编号", "属性编号", "当前值"]].copy()
        毒性属性["条件"] = "无毒性证据"
        毒性属性["不确定性"] = ""
        属性记录 = pd.concat([属性记录, 毒性属性], ignore_index=True)
        执行器 = 通用规则执行器(注册表=创建默认属性注册表())
        规则记录 = 执行器.执行(run_id, 候选["候选编号"].astype(str), 属性记录, 规则列表)
        汇总 = 执行器.候选汇总(规则记录)
        结果 = 候选.merge(汇总, how="left", on=["run_id", "候选编号"])
        if 规则列表:
            结果["规则总状态"] = 结果["规则总状态"].fillna("无法评估")
            结果["规则状态说明"] = 结果["规则状态说明"].fillna("未产生规则结果")
        else:
            结果["规则总状态"] = "跳过"
            结果["规则状态说明"] = "当前应用配置没有启用规则"
        结果["用户自动规则通过"] = 结果["规则总状态"].eq("通过")
        无法评估 = 规则记录[规则记录["规则状态"].eq("无法评估")]
        原因 = 无法评估.groupby("候选编号")["说明"].agg("；".join) if not 无法评估.empty else pd.Series(dtype=str)
        结果["无法执行规则原因"] = 结果["候选编号"].map(原因).fillna("")
        if hasattr(数据管理器, "保存属性记录"):
            数据管理器.保存属性记录(属性记录)
            数据管理器.保存规则结果(规则记录)
            数据管理器.保存毒性结果("毒性判定指标", 毒性指标)
        数据管理器.保存筛选结果(self.输出标识, 结果)
        return 结果
