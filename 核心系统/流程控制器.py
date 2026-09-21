"""公开流程 facade；复杂阶段委托核心流程，正式产物以 run_id 隔离。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from 核心系统.运行数据管理 import 运行数据管理器
from 核心系统.插件管理器 import 插件管理器
from 核心系统.默认装配 import 创建默认插件管理器
from 核心系统.配方评估流程 import 运行颅骨透明化流程
from 核心系统.SeeThrough复现流程 import 运行补充数据2复现, 运行补充数据3复现
from 核心系统.用户候选流程 import 运行用户候选导入
from 核心系统.毒理分析 import 运行毒理公开数据查询


class 流程控制器:
    def __init__(self, 插件管理器实例: 插件管理器, 数据管理器: 运行数据管理器) -> None:
        self.插件管理器 = 插件管理器实例
        self.数据管理器 = 数据管理器

    def 执行颅骨透明化用途流程(self, 数据上下文: dict[str, Any]) -> dict[str, Any]:
        return 运行颅骨透明化流程(数据上下文, self.插件管理器.获取插件)

    def 执行补充数据3真实流程(self) -> dict[str, Any]:
        return 运行补充数据3复现(self.数据管理器, self.插件管理器.获取插件)

    def 执行用户候选导入(
        self,
        文件名: str,
        文件内容: bytes,
        字段映射: dict[str, str | None],
        用户筛选设置: dict[str, Any] | None = None,
        候选类型: str = "通用候选",
        应用配置: str | None = None,
    ) -> dict[str, Any]:
        return 运行用户候选导入(self.数据管理器, self.插件管理器.获取插件, 文件名, 文件内容, 字段映射, 用户筛选设置, 候选类型, 应用配置)

    def 执行补充数据2规则筛选流程(self, 启用网络查询: bool = False) -> dict[str, Any]:
        return 运行补充数据2复现(self.数据管理器, self.插件管理器.获取插件, 启用网络查询)

    def 执行毒理证据匹配(self, 毒理会话: dict[str, Any], 毒理证据: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """执行本地/人工/已启用公开来源的毒理证据匹配。"""
        return self.插件管理器.获取插件("毒理证据匹配").执行({
            "数据管理器": self.数据管理器,
            "毒理会话": 毒理会话,
            "毒理证据": 毒理证据,
        })

    def 执行公开证据查询(self, 数据上下文: dict[str, Any]) -> dict[str, Any]:
        """显式查询公开来源并按条件生成采用结果，证据不进入 descriptor 宽表。"""
        return self.插件管理器.获取插件("公开证据聚合").执行({"数据管理器": self.数据管理器, **数据上下文})

    def 执行毒理公开数据查询(self, 毒理会话: dict[str, Any]) -> pd.DataFrame:
        """按会话中勾选的来源查询公开数据；当前仅实现 PubChem GHS。"""
        return 运行毒理公开数据查询(self.数据管理器, self.插件管理器.获取插件, 毒理会话)

    def 执行人工身份确认(self, 数据上下文: dict[str, Any]) -> pd.DataFrame:
        """转发 canonical 人工确认能力；允许指定页面当前运行的数据管理器。"""
        return self.插件管理器.获取插件("人工身份确认").执行({"数据管理器": self.数据管理器, **数据上下文})

    def 重新生成筛选结果图表(self, 数据上下文: dict[str, Any]) -> dict[str, Path]:
        """读取指定运行结果并委托现有图表插件。"""
        return self.插件管理器.获取插件("筛选结果图表").执行({"数据管理器": self.数据管理器, **数据上下文})


def 创建颅骨透明化筛选流程控制器(项目根目录: Path) -> 流程控制器:
    数据管理器 = 运行数据管理器(项目根目录)
    管理器 = 创建默认插件管理器()
    return 流程控制器(管理器, 数据管理器)


创建补充数据3流程控制器 = 创建颅骨透明化筛选流程控制器
