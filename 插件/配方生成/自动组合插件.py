"""只从独立候选池生成配方。主体由相态和本次比例决定，无指定化学名称。"""

from itertools import combinations
from math import comb
from 插件.插件接口 import 基础插件接口


def 整数分割(总数, 长度):
    if 长度 == 1:
        yield (总数,)
    else:
        for 首项 in range(1, 总数-长度+2):
            for 剩余 in 整数分割(总数-首项, 长度-1):
                yield (首项, *剩余)


# 保留历史公开 import 名；构建实现与功能插件分离。
from .配方定义构建 import 组装定义


class 自动组合插件(基础插件接口):
    插件标识 = "自动配方组合"

    def 执行(self, 数据上下文):
        配置, 物质们 = 数据上下文["生成配置"], 数据上下文["物质库"]
        库 = {x["物质编号"]: x for x in 物质们}
        if len(库) != len(物质们) or len(库) > 100:
            raise ValueError("物质编号重复或筛后池超过100种；请先收紧分子约束")
        CAS们 = [x.get("CAS") for x in 物质们 if x.get("CAS")]
        if len(CAS们) != len(set(CAS们)):
            raise ValueError("候选池含重复CAS别名")
        for x in 物质们:
            if x.get("来源类型") not in {"独立公开物性", "用户独立输入"} or not x.get("数据来源"):
                raise ValueError(f"{x['物质编号']}不是有来源的独立候选，不能导入验证/论文专用记录")
        步长 = 配置.get("粗搜步长百分比", 20)
        最小, 最大 = 配置.get("最小组分数", 1), 配置.get("最大组分数", 3)
        上限 = 配置.get("最大配方数", 2000)
        if isinstance(步长, bool) or 步长 not in {5, 10, 20, 25, 50}:
            raise ValueError("粗搜步长须为5、10、20、25或50质量百分点")
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (最小, 最大, 上限)) or not 1 <= 最小 <= 最大 <= 6 or not 1 <= 上限 <= 5000:
            raise ValueError("组分数范围须在1–6，枚举上限须在1–5000")
        格数 = 100 // 步长
        组合们, 预计 = [], 0
        for k in range(最小, min(最大, len(库), 格数)+1):
            for c in combinations(sorted(库), k):
                if not any(库[i].get("相态") == "液体" for i in c):
                    continue
                预计 += comb(格数-1, len(c)-1)
                if 预计 > 上限:
                    raise ValueError(f"完整粗搜超过预算{上限}；请收紧分子约束或增大步长，不按池顺序截断")
                组合们.append(c)
        return [组装定义(dict(zip(c, (n/格数 for n in 分配))), 库, 配置)
                for c in 组合们 for 分配 in 整数分割(格数, len(c))]
