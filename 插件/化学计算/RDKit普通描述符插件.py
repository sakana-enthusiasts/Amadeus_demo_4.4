"""论文/用户长表 adapter；唯一公式实现在 RDKit分子属性计算器，不在此维护描述符算法。"""

from typing import Any

import pandas as pd
from .RDKit分子属性计算器 import RDKit分子属性计算器

from 插件.插件接口 import 基础插件接口


class RDKit普通描述符插件(基础插件接口):
    插件标识 = "RDKit普通描述符"
    输入标识 = "补充数据3_结构映射结果"
    输出标识 = "补充数据3_RDKit描述符结果"
    工具版本 = RDKit分子属性计算器.engine_version

    def 执行(self, 数据上下文: dict[str, Any]) -> pd.DataFrame:
        数据管理器 = 数据上下文["数据管理器"]
        输入标识 = "补充数据2_结构映射结果" if 数据上下文.get("补充数据2描述符处理") else self.输入标识
        输出标识 = "补充数据2_RDKit描述符结果" if 数据上下文.get("补充数据2描述符处理") else self.输出标识
        if 数据上下文.get("用户描述符处理"):
            输入标识, 输出标识 = "用户导入_结构映射结果", "用户导入_RDKit描述符结果"
        候选表 = 数据管理器.读取中间结果(输入标识)
        结果记录: list[dict[str, Any]] = []
        计算器 = RDKit分子属性计算器()
        for _, 行 in 候选表.iterrows():
            基础信息 = {
                "候选编号": 行["候选编号"],
                "候选名称": 行.get("论文_化学名称", 行.get("原始名称", "")),
                "CAS号": 行.get("论文_CAS号", 行.get("原始CAS", "")),
                "结构来源": 行.get("结构映射_来源", ""),
                "计算工具": "RDKit",
                "工具版本": self.工具版本,
            }
            SMILES = str(行.get("结构映射_SMILES", "") or "").strip()
            分子 = 计算器.parse_structure(SMILES)
            if 分子 is None:
                原因 = str(行.get("结构错误信息", "SMILES 缺失或无效"))
                for 描述符名称 in 计算器.LEGACY_NAMES:
                    结果记录.append({**基础信息, "描述符名称": 描述符名称, "数值": None, "是否计算成功": False, "失败原因": 原因})
                continue
            for 描述符名称, r in 计算器.legacy_descriptors(分子).items():
                结果记录.append({**基础信息, "描述符名称": 描述符名称, "数值": r["value"], "是否计算成功": r["status"] == "available", "失败原因": r["reason"] or ""})
        结果 = pd.DataFrame(结果记录)
        数据管理器.保存中间结果(输出标识, 结果)
        return 结果
