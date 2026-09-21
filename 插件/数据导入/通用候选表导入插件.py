"""受限且可审计的 CSV/XLSX 用户候选表导入插件。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from 插件.插件接口 import 基础插件接口
from 核心系统.候选表输入 import 安全文件名, 读取候选上传内容, 最大上传字节数, 支持扩展名


class 通用候选表导入插件(基础插件接口):
    插件标识 = "通用候选表导入"
    输出标识 = "用户导入_统一候选记录"
    最大上传字节数 = 最大上传字节数
    支持扩展名 = 支持扩展名

    字段映射 = {
        "化学名称列": "化学名称",
        "CAS列": "CAS号",
        "货号列": "货号",
        "候选编号列": "候选编号",
        "水合能力平均值列": "水合评分平均值",
        "水合能力标准差列": "水合评分标准差",
        "eRI列": "eRI",
        "pH列": "预测pH",
        "dD列": "dD",
        "dP列": "dP",
        "dH列": "dH",
        "实测RI列": "实测RI",
        "气味列": "气味",
        "毒性或安全性列": "毒性或安全性",
        "实际互溶状态列": "实际互溶状态",
    }

    # 旧公开入口保留为同一解析函数的别名；默认实现仅在核心输入边界维护。
    安全文件名 = staticmethod(安全文件名)
    读取上传内容 = staticmethod(读取候选上传内容)

    @staticmethod
    def _映射列(原始表: pd.DataFrame, 映射: dict[str, str | None], 映射键: str, 输出列: str) -> pd.Series:
        来源列 = 映射.get(映射键)
        if not 来源列:
            return pd.Series(pd.NA, index=原始表.index, dtype="object")
        if 来源列 not in 原始表.columns:
            raise ValueError(f"字段映射不存在：{映射键} -> {来源列}")
        值 = 原始表[来源列].replace("", pd.NA)
        return 值.astype("object")

    def 执行(self, 数据上下文: dict[str, Any]) -> pd.DataFrame:
        数据管理器 = 数据上下文["数据管理器"]
        文件名 = self.安全文件名(str(数据上下文["文件名"]))
        内容 = bytes(数据上下文["文件内容"])
        原始表 = self.读取上传内容(文件名, 内容)
        映射 = dict(数据上下文.get("字段映射") or {})
        名称列 = 映射.get("化学名称列")
        if not 名称列:
            raise ValueError("必须映射化学名称列")
        if 名称列 not in 原始表.columns:
            raise ValueError(f"化学名称列不存在：{名称列}")
        if hasattr(数据管理器, "当前运行编号") and not 数据管理器.当前运行编号:
            数据管理器.创建运行(str(数据上下文.get("应用配置", "user_custom")), 文件名)
        run_id = getattr(数据管理器, "当前运行编号", "legacy") or "legacy"
        数据管理器.保存用户导入原始文件(文件名, 内容)
        统一 = pd.DataFrame(index=原始表.index)
        for 映射键, 输出列 in self.字段映射.items():
            统一[输出列] = self._映射列(原始表, 映射, 映射键, 输出列)
            if 映射键 not in {"化学名称列", "CAS列", "货号列", "候选编号列"}:
                来源列 = 映射.get(映射键)
                统一[f"字段状态_{输出列}"] = "用户表格提供" if 来源列 else "缺失"
        自动编号 = [f"U{序号:05d}" for 序号 in range(1, len(统一) + 1)]
        统一["候选编号"] = 统一["候选编号"].fillna(pd.Series(自动编号, index=统一.index)).astype(str).str.strip()
        统一["化学名称"] = 统一["化学名称"].astype(str).str.strip()
        if 统一["化学名称"].eq("").any():
            raise ValueError("化学名称不能为空")
        统一["CAS号"] = 统一["CAS号"].fillna("").astype(str).str.strip()
        统一["货号"] = 统一["货号"].fillna("").astype(str).str.strip()
        统一["run_id"] = run_id
        统一["候选类型"] = str(数据上下文.get("候选类型", "通用候选"))
        统一["来源文件名"] = 文件名
        统一["导入状态"] = "可用"
        统一["导入冲突说明"] = ""
        重复编号 = 统一["候选编号"].duplicated(keep=False)
        统一.loc[重复编号, "导入状态"] = "重复编号"
        统一.loc[重复编号, "导入冲突说明"] = "重复编号"
        有效CAS = 统一["CAS号"].ne("")
        重复CAS = 有效CAS & 统一["CAS号"].duplicated(keep=False)
        统一.loc[重复CAS, "导入冲突说明"] = 统一.loc[重复CAS, "导入冲突说明"].replace("", "重复CAS")
        CAS格式异常 = 有效CAS & ~统一["CAS号"].str.fullmatch(r"\d{2,7}-\d{2}-\d", na=False)
        统一.loc[CAS格式异常, "导入冲突说明"] = 统一.loc[CAS格式异常, "导入冲突说明"].replace("", "CAS格式异常")
        同名多CAS = 统一.groupby("化学名称")["CAS号"].transform(lambda 值: 值[值.ne("")].nunique() > 1)
        统一.loc[同名多CAS, "导入冲突说明"] = 统一.loc[同名多CAS, "导入冲突说明"].replace("", "同名不同CAS")
        数据管理器.保存中间结果(self.输出标识, 统一)
        return 统一
