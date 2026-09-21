"""配置驱动的候选属性、规则和毒性指标基础设施。

该模块不修改候选人的核心行结构。物化属性和毒性指标均以长表记录保存，
通过 ``run_id`` 与候选编号关联；规则执行器只读取注册的属性记录。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import isnan
from typing import Any, Iterable, Mapping

import pandas as pd


规则状态 = ("通过", "排除", "无法评估", "跳过", "警告")


@dataclass(frozen=True)
class 属性定义:
    属性编号: str
    属性名称: str
    属性类别: str
    数据类型: str
    单位: str
    来源类别: str
    计算或测量方法: str
    是否允许缺失: bool = True


@dataclass(frozen=True)
class 属性记录:
    run_id: str
    候选编号: str
    属性编号: str
    当前值: Any
    条件: str = ""
    不确定性: str = ""


class 属性注册表:
    """属性定义的可扩展注册表；新增属性不需要改候选表的数据结构。"""

    def __init__(self, 定义: Iterable[属性定义] | None = None) -> None:
        self._定义: dict[str, 属性定义] = {}
        for 项目 in 定义 or ():
            self.注册(项目)

    def 注册(self, 定义: 属性定义) -> None:
        if not 定义.属性编号.strip():
            raise ValueError("属性编号不能为空")
        if 定义.属性编号 in self._定义:
            raise ValueError(f"属性编号已注册：{定义.属性编号}")
        self._定义[定义.属性编号] = 定义

    def 获取(self, 属性编号: str) -> 属性定义:
        try:
            return self._定义[属性编号]
        except KeyError as 错误:
            raise KeyError(f"未注册的属性：{属性编号}") from 错误

    def 导出(self) -> pd.DataFrame:
        return pd.DataFrame([
            asdict(项目) | {"当前值": pd.NA, "条件": "", "不确定性": ""}
            for 项目 in self._定义.values()
        ])

    @classmethod
    def 默认(cls) -> "属性注册表":
        """兼容入口；默认预设仅由设置工厂维护，保留子类构造语义。"""
        from 设置.规则注册设置 import 创建默认属性注册表
        return cls(创建默认属性注册表()._定义.values())


@dataclass(frozen=True)
class 规则定义:
    规则编号: str
    规则名称: str
    规则组: str
    所需属性: tuple[str, ...]
    比较方式: str
    阈值: Any
    单位: str
    是否启用: bool
    缺失数据策略: str
    严重级别: str
    规则来源: str
    规则版本: str

    def __post_init__(self) -> None:
        if self.缺失数据策略 not in {"无法评估", "跳过", "警告"}:
            raise ValueError("缺失数据策略只能为：无法评估、跳过或警告")


@dataclass(frozen=True)
class 应用配置:
    配置编号: str
    配置名称: str
    说明: str
    规则: tuple[规则定义, ...] = field(default_factory=tuple)


class 规则注册表:
    def __init__(self, 配置: Iterable[应用配置] | None = None) -> None:
        self._配置: dict[str, 应用配置] = {}
        for 项目 in 配置 or ():
            self.注册配置(项目)

    def 注册配置(self, 配置: 应用配置) -> None:
        if 配置.配置编号 in self._配置:
            raise ValueError(f"应用配置已注册：{配置.配置编号}")
        编号 = [规则.规则编号 for 规则 in 配置.规则]
        if len(编号) != len(set(编号)):
            raise ValueError(f"配置 {配置.配置编号} 包含重复规则编号")
        self._配置[配置.配置编号] = 配置

    def 获取配置(self, 配置编号: str) -> 应用配置:
        try:
            return self._配置[配置编号]
        except KeyError as 错误:
            raise KeyError(f"未知应用配置：{配置编号}") from 错误

    def 配置列表(self) -> list[应用配置]:
        return list(self._配置.values())

    def 规则列表(self, 配置编号: str, 启用覆盖: Mapping[str, bool] | None = None) -> list[规则定义]:
        覆盖 = 启用覆盖 or {}
        结果: list[规则定义] = []
        for 规则 in self.获取配置(配置编号).规则:
            结果.append(
                规则定义(
                    **(asdict(规则) | {"是否启用": bool(覆盖.get(规则.规则编号, 规则.是否启用))})
                )
            )
        return 结果

    def 导出规则(self, 配置编号: str, 启用覆盖: Mapping[str, bool] | None = None) -> pd.DataFrame:
        return pd.DataFrame([asdict(规则) for 规则 in self.规则列表(配置编号, 启用覆盖)])

    @classmethod
    def 默认(cls) -> "规则注册表":
        """兼容入口；新生产调用使用设置模块的显式工厂。"""
        from 设置.规则注册设置 import 创建默认规则注册表
        return cls(创建默认规则注册表().配置列表())


def _缺失(值: Any) -> bool:
    if 值 is None:
        return True
    if isinstance(值, str) and not 值.strip():
        return True
    try:
        return bool(pd.isna(值)) or (isinstance(值, float) and isnan(值))
    except (TypeError, ValueError):
        return False


class 通用规则执行器:
    """只产生五种规定状态，缺失值绝不转换成 0 或排除。"""

    def __init__(self, 注册表: 属性注册表 | None = None) -> None:
        from 设置.规则注册设置 import 创建默认属性注册表
        self.属性注册表 = 注册表 if 注册表 is not None else 创建默认属性注册表()

    @staticmethod
    def _比较(方式: str, 当前值: Any, 阈值: Any) -> bool:
        if 方式 == ">=":
            return float(当前值) >= float(阈值)
        if 方式 == ">":
            return float(当前值) > float(阈值)
        if 方式 == "<=":
            return float(当前值) <= float(阈值)
        if 方式 == "<":
            return float(当前值) < float(阈值)
        if 方式 == "==":
            return 当前值 == 阈值
        if 方式 == "!=":
            return 当前值 != 阈值
        raise ValueError(f"不支持的比较方式：{方式}")

    def 执行(
        self,
        run_id: str,
        候选编号列表: Iterable[str],
        属性数据: pd.DataFrame,
        规则列表: Iterable[规则定义],
    ) -> pd.DataFrame:
        必需列 = {"run_id", "候选编号", "属性编号", "当前值"}
        缺列 = 必需列 - set(属性数据.columns)
        if 缺列:
            raise ValueError(f"属性记录缺少字段：{sorted(缺列)}")
        本轮属性 = 属性数据[属性数据["run_id"].astype(str).eq(str(run_id))].copy()
        索引 = {
            (str(行["候选编号"]), str(行["属性编号"])): 行["当前值"]
            for _, 行 in 本轮属性.drop_duplicates(["候选编号", "属性编号"], keep="last").iterrows()
        }
        记录: list[dict[str, Any]] = []
        for 候选编号 in map(str, 候选编号列表):
            for 规则 in 规则列表:
                基础 = {
                    "run_id": run_id,
                    "候选编号": 候选编号,
                    "规则编号": 规则.规则编号,
                    "规则名称": 规则.规则名称,
                    "规则组": 规则.规则组,
                    "所需属性": "|".join(规则.所需属性),
                    "比较方式": 规则.比较方式,
                    "阈值": 规则.阈值,
                    "单位": 规则.单位,
                    "严重级别": 规则.严重级别,
                    "规则来源": 规则.规则来源,
                    "规则版本": 规则.规则版本,
                }
                if not 规则.是否启用:
                    记录.append(基础 | {"规则状态": "跳过", "实际值": "", "说明": "规则未启用"})
                    continue
                值 = [索引.get((候选编号, 属性编号)) for 属性编号 in 规则.所需属性]
                缺失属性 = [属性 for 属性, 当前值 in zip(规则.所需属性, 值) if _缺失(当前值)]
                if 缺失属性:
                    状态 = 规则.缺失数据策略
                    记录.append(基础 | {"规则状态": 状态, "实际值": "", "说明": f"缺少属性：{'、'.join(缺失属性)}"})
                    continue
                try:
                    通过 = self._比较(规则.比较方式, 值[0] if len(值) == 1 else 值, 规则.阈值)
                except (TypeError, ValueError) as 错误:
                    记录.append(基础 | {"规则状态": "无法评估", "实际值": "|".join(map(str, 值)), "说明": f"比较失败：{错误}"})
                    continue
                if 通过:
                    记录.append(基础 | {"规则状态": "通过", "实际值": "|".join(map(str, 值)), "说明": "满足规则"})
                else:
                    状态 = "警告" if 规则.严重级别 == "警告" else "排除"
                    记录.append(基础 | {"规则状态": 状态, "实际值": "|".join(map(str, 值)), "说明": "不满足规则"})
        return pd.DataFrame(记录, columns=[
            "run_id", "候选编号", "规则编号", "规则名称", "规则组", "所需属性", "比较方式", "阈值", "单位",
            "严重级别", "规则来源", "规则版本", "规则状态", "实际值", "说明",
        ])

    @staticmethod
    def 候选汇总(规则结果: pd.DataFrame) -> pd.DataFrame:
        if 规则结果.empty:
            return pd.DataFrame(columns=["run_id", "候选编号", "规则总状态", "规则状态说明"])
        优先级 = {"排除": 4, "无法评估": 3, "警告": 2, "通过": 1, "跳过": 0}
        结果: list[dict[str, str]] = []
        for (run_id, 候选编号), 分组 in 规则结果.groupby(["run_id", "候选编号"], dropna=False):
            状态 = max(分组["规则状态"].astype(str), key=lambda 项目: 优先级[项目])
            原因 = "；".join(分组.loc[分组["规则状态"].eq(状态), "说明"].astype(str).drop_duplicates())
            结果.append({"run_id": str(run_id), "候选编号": str(候选编号), "规则总状态": 状态, "规则状态说明": 原因})
        return pd.DataFrame(结果)


class 毒性判定指标插件:
    """从独立的毒性证据表生成规则可读指标，不把证据扁平化为风险总分。"""

    指标编号 = {
        "明确遗传毒性阳性": "tox_genotoxic_positive",
        "明确致癌证据": "tox_carcinogenic_evidence",
        "同物种同途径急性毒性证据": "tox_same_species_route_acute",
        "只有间接证据": "tox_indirect_only",
        "完全无数据": "tox_no_data",
    }

    @staticmethod
    def _值(行: pd.Series, 名称: str) -> str:
        for 列 in (名称, 名称.lower(), 名称.upper()):
            if 列 in 行.index and not _缺失(行[列]):
                return str(行[列])
        return ""

    def 执行(self, run_id: str, 毒性证据: pd.DataFrame) -> pd.DataFrame:
        必需列 = {"候选编号", "物种", "给药途径", "剂量", "暴露时长", "毒性终点", "实验或预测", "来源", "可信度"}
        if 毒性证据.empty:
            return pd.DataFrame(columns=["run_id", "候选编号", "指标编号", "指标名称", "当前值", "证据说明"])
        缺列 = 必需列 - set(毒性证据.columns)
        if 缺列:
            raise ValueError(f"毒性证据缺少字段：{sorted(缺列)}")
        结果: list[dict[str, Any]] = []
        for 候选编号, 分组 in 毒性证据.groupby("候选编号", dropna=False):
            文本 = " ".join(分组.astype(str).fillna("").agg(" ".join, axis=1)).lower()
            实验 = 分组["实验或预测"].astype(str).str.contains("实验|实测|animal|in vivo", case=False, regex=True).any()
            指标 = {
                "明确遗传毒性阳性": 实验 and any(词 in 文本 for 词 in ("遗传毒", "genotoxic", "ames")) and any(词 in 文本 for 词 in ("阳性", "positive")),
                "明确致癌证据": 实验 and any(词 in 文本 for 词 in ("致癌", "carcinogen", "carcinogenic")),
                "同物种同途径急性毒性证据": 实验 and any(词 in 文本 for 词 in ("急性", "acute", "ld50")),
            }
            任何明确 = any(指标.values())
            指标["只有间接证据"] = (not 任何明确) and len(分组) > 0
            指标["完全无数据"] = False
            for 名称, 当前值 in 指标.items():
                结果.append({
                    "run_id": run_id,
                    "候选编号": str(候选编号),
                    "指标编号": self.指标编号[名称],
                    "指标名称": 名称,
                    "当前值": bool(当前值),
                    "证据说明": f"保留 {len(分组)} 条独立毒性证据；未生成综合风险分数",
                    "生成时间": datetime.now(timezone.utc).isoformat(),
                })
        return pd.DataFrame(结果)

    def 空数据指标(self, run_id: str, 候选编号列表: Iterable[str]) -> pd.DataFrame:
        return pd.DataFrame([
            {"run_id": run_id, "候选编号": str(候选编号), "指标编号": self.指标编号["完全无数据"], "指标名称": "完全无数据", "当前值": True, "证据说明": "未提供毒性证据", "生成时间": datetime.now(timezone.utc).isoformat()}
            for 候选编号 in 候选编号列表
        ])
