"""完整配方组装 → 物性预测 → 验证门禁/独立搜索 → 最后文献对照。"""

from collections.abc import Callable
from 插件.插件接口 import 基础插件接口
from 核心系统.默认装配 import (
    装配工作流插件获取器, 创建默认结构检索器, 创建默认分子属性计算器,
    创建默认分子标准化器, 创建描述符计算器,
)
from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite

from 插件.配方生成.组成签名 import 搜索定义质量签名
from 核心系统.目标规格.执行计划 import compile_profile
from 核心系统.结构查询 import adapt_candidates, StructureQueryError

研发默认模型 = {"混合折射率": "lorentz_lorenz", "混合黏度": "auto",
                "溶液自由扩散系数": "stokes_einstein", "渗透压": "ideal_osmotic", "水活度": "ideal_water_activity"}
通用待补 = ["预测区间/模型误差校准", "真实混合体积及活度系数", "实验混溶性及相稳定性",
           "候选分子/组织扩散校准", "局部滞留与washout", "局部及系统毒理与暴露阈值"]


def 预测完整配方(配方定义, 物质库, 物性条件, *, 模型选择=None, 模型参数=None, 注册表=None, 获取插件: Callable[[str], 基础插件接口] | None = None):
    获取插件 = 装配工作流插件获取器(获取插件, 注册表=注册表)
    组装 = 获取插件("配方输入组装").执行({"配方定义": 配方定义, "物质库": 物质库, "物性条件": 物性条件})
    物性 = 获取插件("配方物性汇总").执行(组装 | {"物性模型选择": 研发默认模型 | (模型选择 or {}),
                                                             "物性模型参数": 模型参数 or {}})
    # 来源、体积近似等输入警告必须随每项输出一同导出，不能只留在组装日志中。
    for r in 物性.values():
        r["警告"] = list(dict.fromkeys(r["警告"] + 组装["组装警告"]))
        r["输入数据来源"] = {x["成分键"]: x.get("数据来源") for x in 组装["成分"]}
        r["不确定度说明"] = "未量化" if r["不确定度"] is None else str(r["不确定度"])
    缺失 = 组装["组装缺失"] + 通用待补 + [f"{k}：" + "；".join(v["警告"]) for k, v in 物性.items() if v["值"] is None]
    return 组装 | {"配方物性": 物性, "缺失数据": list(dict.fromkeys(缺失))}


def 运行验证模式(*, 模型选择=None, 模型参数=None, 注册表=None, 获取插件: Callable[[str], 基础插件接口] | None = None):
    获取插件 = 装配工作流插件获取器(获取插件, 注册表=注册表)
    from 设置.配方验证设置 import 读取验证体系, 读取待补文献协议, 验证集版本
    记录, 检查 = [], []
    for 体系 in 读取验证体系():
        try:
            预测 = 预测完整配方(体系["配方定义"], 体系["物质库"], 体系["物性条件"],
                                模型选择=模型选择, 模型参数=模型参数, 获取插件=获取插件)
        except (ValueError, TypeError) as e:
            检查.append({"体系": 体系["编号"], "检查": "完整配方执行", "通过": False, "参与门禁": True, "说明": str(e)})
            continue
        记录.append({"体系": 体系["编号"], "预测": 预测, "数据说明": 体系["数据说明"], "参考": deepcopy(体系["参考"])})
        if 体系["要求五项数值"]:
            可计算 = all(v["状态"] == "已预测" and v["值"] is not None and isfinite(v["值"]) for v in 预测["配方物性"].values())
            检查.append({"体系": 体系["编号"], "检查": "完整配方五项数值", "通过": 可计算, "参与门禁": True,
                         "说明": "只代表数值链路；扩散、渗透压和水活度尚无实测精度验证"})
        for ref in 体系["参考"]:
            v = 预测["配方物性"][ref["指标"]]["值"]
            误差 = abs(v-ref["参考值"]) if v is not None else None
            容差 = ref.get("绝对容差", ref.get("相对容差", 0) * abs(ref["参考值"]))
            检查.append({"体系": 体系["编号"], "检查": ref["指标"], "预测值": v, "参考值": ref["参考值"],
                         "绝对误差": 误差, "容差": 容差, "通过": 误差 is not None and 误差 <= 容差,
                         "参与门禁": ref["参与门禁"], "说明": ref["类型"] + "；" + ref["条件说明"], "来源": ref["来源"]})
        if 体系.get("边界检查"):
            安全拒绝 = 预测["配方物性"]["混合折射率"]["值"] is None and all(
                x.get("纯物质RI") is None for x in 预测["成分"] if x.get("相态") == "固体")
            检查.append({"体系": 体系["编号"], "检查": 体系["边界检查"], "通过": 安全拒绝, "参与门禁": True,
                         "说明": "BA+ANP保留质量/摩尔分数，缺失体积分数及混合RI；禁止用论文eRI补空"})
    门禁项 = [r for r in 检查 if r["参与门禁"]]
    通过 = bool(门禁项) and all(r["通过"] for r in 门禁项)
    指纹材料 = {"版本": 验证集版本, "模型选择": 模型选择, "模型参数": 模型参数, "检查": 检查,
                "模型": [{k: (v["方法"], v["模型版本"]) for k, v in x["预测"]["配方物性"].items()} for x in 记录]}
    指纹 = sha256(json.dumps(指纹材料, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"模式": "验证", "版本": 验证集版本, "验证指纹": 指纹, "通过": 通过, "检查": 检查, "体系": 记录,
            "待补文献协议": 读取待补文献协议(),
            "门禁范围": "完整配方五项数值、甘油水黏度校准来源复现、固体eRI隔离；只开放探索试算，不等于新体系精度或生物安全验证"}


def 运行数值自检(*, 模型选择=None, 模型参数=None, 注册表=None, 必需指标=None, 获取插件: Callable[[str], 基础插件接口] | None = None):
    """无实验标签的合成输入，验证组装和五项接口；不作为候选或搜索种子。"""
    获取插件 = 装配工作流插件获取器(获取插件, 注册表=注册表)
    库 = [{"物质编号": i, "化学名称": i, "CAS": "7732-18-5" if i == "test_water" else "test_solute",
           "分子量_g_mol": mw, "相态": "液体", "密度_g_mL": rho, "密度温度_C": 20,
           "纯物质RI": ri, "RI温度_C": 20, "RI波长_nm": 589.3, "纯物质黏度_mPa_s": eta,
           "黏度温度_C": 20, "范特霍夫因子": 1, "数据来源": "合成接口测试输入，不能用于实验"}
          for i, mw, rho, ri, eta in (("test_water", 18, 1, 1.33, 1), ("test_solute", 100, 1.2, 1.5, 5))]
    定义 = {"组分": [{"物质编号": i, "用量": .5, "单位": "质量分数", "角色": role}
                     for i, role in (("test_water", "主溶剂"), ("test_solute", "候选成分"))],
            "体积策略": "纯组分体积可加", "渗透参照溶剂": "test_water",
            "扩散探针": {"名称": "接口探针", "半径_nm": 1, "来源": "合成接口测试"}}
    预测 = 预测完整配方(定义, 库, {"温度_C": 20, "波长_nm": 589.3}, 模型选择=模型选择, 模型参数=模型参数, 获取插件=获取插件)
    检查指标 = 预测["配方物性"] if 必需指标 is None else 必需指标
    通过 = all(预测["配方物性"][k]["状态"] == "已预测" and 预测["配方物性"][k]["值"] is not None
              and isfinite(预测["配方物性"][k]["值"]) for k in 检查指标)
    return {"通过": 通过, "说明": "组装及模型数值接口自检；不证明预测精度，不读取Benchmark", "物性": 预测["配方物性"]}


def 运行发现模式(物质库, 生成配置, *, 约束=None, 配方证据=None, 模型选择=None, 模型参数=None, 注册表=None, 目标规格=None,
             结构查询=None, 结构字段映射=None, 结构检索器=None,
             分子属性计算器=None, 扩展描述符报告=None, 获取插件: Callable[[str], 基础插件接口] | None = None,
             公开证据配置=None, 公开证据执行桥=None, 公开证据请求=None,
             标准化配置=None, 分子标准化器=None, 描述符请求=None, 描述符计算器=None):
    if not isinstance(物质库, list) or any(not isinstance(x, dict) for x in 物质库):
        raise ValueError("物质库须为记录列表")
    if 配方证据 is not None and (not isinstance(配方证据, list) or any(not isinstance(x, dict) for x in 配方证据)):
        raise ValueError("配方证据须为记录列表")
    支持约束 = {"排除CAS", "分子约束", "要求可购", "物性约束", "成本上限_元_kg", "毒理条件", "细胞存活率下限_pct", "缺失策略", "优化目标"}
    if not isinstance(约束 or {}, dict) or set(约束 or {}) - 支持约束:
        raise ValueError("未知约束字段，请按发现约束格式配置")
    获取插件 = 装配工作流插件获取器(获取插件, 注册表=注册表)
    候选池, 结构结果, 结构排除 = _筛选结构候选(物质库, 结构查询, 结构字段映射, 结构检索器)
    计划, 规格结果 = None, 结构结果
    if 目标规格 is not None:
        计划, 预检 = compile_profile(目标规格, legacy_constraints=约束,
            available_properties=获取插件("配方物性汇总").注册表.指标列表(),
            model_selection=研发默认模型 | (模型选择 or {}),
            public_evidence_enabled=公开证据配置 is not None and 公开证据配置.mode != "off")
        规格结果 = 结构结果 | {"Target Profile快照": 目标规格.to_dict(), "Target Profile version": 目标规格.target_profile_version,
                    "执行计划": 计划.to_dict(), "执行预检": 预检}
        if not 预检["passed"]:
            return 规格结果 | {"模式": "发现", "状态": "Target Profile执行预检失败，搜索未启动",
                               "候选": [], "生成数量": 0, "排除": [], "排除分子": 结构排除}
    必需 = None if 计划 is None else {x.binding.field for x in 计划.criteria
                                    if x.binding.source == "配方物性" and x.criterion.role != "report_only"}
    if 计划 is not None and not 计划.objectives:
        必需 |= {"混合折射率", "混合黏度"}  # 无 Profile objectives 时仍用 legacy 排序。
    自检 = 运行数值自检(模型选择=模型选择, 模型参数=模型参数, 获取插件=获取插件, 必需指标=必需)
    if not 自检["通过"]:
        return 规格结果 | {"模式": "发现", "状态": "数值自检未通过，搜索未启动", "数值自检": 自检, "候选": [], "生成数量": 0, "排除": [], "排除分子": 结构排除}
    候选池, 计算映射, 标准化报告 = _标准化计算视图(候选池, 结构字段映射, 标准化配置, 分子标准化器)
    规格结果.update(标准化报告)
    候选池, 属性报告 = _计算候选分子属性(候选池, 计划, 计算映射, 分子属性计算器, 扩展描述符报告)
    规格结果.update(属性报告)
    if 描述符请求 is not None and 描述符请求.descriptor_ids:
        if 计算映射 is None or 计算映射.get("id_field") != "物质编号":
            raise ValueError("描述符计算须显式提供发现结构字段映射")
        calculator = 描述符计算器 if 描述符计算器 is not None else 创建描述符计算器(描述符请求.engine)
        batch = calculator.calculate(adapt_candidates(候选池, **计算映射), 描述符请求)
        if len(batch) != len(候选池) or {r.compound_id for r in batch} != {r["物质编号"] for r in 候选池}:
            raise ValueError("描述符计算器返回候选身份不完整或重复")
        规格结果["扩展描述符结果"] = [r.to_dict() for r in batch]
    if 公开证据配置 is not None and 公开证据配置.mode != "off":
        if 公开证据执行桥 is None:
            raise ValueError("启用公开证据时须显式注入执行桥及其 Repository")
        候选池, 证据报告 = 公开证据执行桥.apply(候选池, 公开证据请求 or {}, 公开证据配置)
        规格结果.update(证据报告)
    约束 = deepcopy(约束 or {})
    筛选 = 获取插件("独立候选分子筛选").执行({"物质库": 候选池, "约束": 约束, "执行计划": 计划})
    搜索库 = 筛选["物质库"]
    排序, 预测们, 搜索摘要 = _搜索并优化配方(
        搜索库, 生成配置, 约束, 配方证据, 计划, 模型选择, 模型参数, 获取插件)
    if 计划:
        规格结果["全部配方评价"] = 预测们
        规格结果["最终排序objectives"] = list(排序["排序规则"]["优化目标"])
    # 生成、排名及规格报告已经完成，才附上文献对照；标签不写入预测输入、目标或评分。
    对照错误 = None
    try:
        验证 = 运行验证模式(模型选择=模型选择, 模型参数=模型参数, 获取插件=获取插件)
        对照 = [{"体系": x["体系"], "参考": x["参考"], "数据说明": x["数据说明"],
                 "预测物性": x["预测"]["配方物性"]} for x in 验证["体系"]]
        待补协议 = 验证["待补文献协议"]
    except (ValueError, TypeError, KeyError) as e:
        对照, 待补协议 = [], []
        对照错误 = f"最后文献对照失败，不影响已完成的候选排名：{e}"
    return 排序 | 规格结果 | 搜索摘要 | {"模式": "发现", "状态": "已完成探索试算", "数值自检": 自检,
                   "排除分子": 结构排除 + 筛选["排除分子"], "最后文献对照": 对照,
                   "待补文献协议": 待补协议, "对照错误": 对照错误,
                   "生成配置": deepcopy(生成配置), "物质库快照": deepcopy(物质库),
                   "约束": 约束, "配方证据": deepcopy(配方证据 or []),
                   "适用范围": "独立池分子筛选→自动主体/组合→局部比例优化→约束评价→Pareto；模型外推未验证，最后才加载Benchmark"}


def _标准化计算视图(候选池, 映射, 配置, 标准化器):
    if 配置 is None:
        return 候选池, 映射, {}
    from 核心系统.分子标准化 import StandardizationRequest
    if not isinstance(映射, dict) or 映射.get("id_field") != "物质编号":
        raise ValueError("标准化须显式提供发现结构字段映射")
    inputs = adapt_candidates(候选池, **映射)
    engine = 标准化器 if 标准化器 is not None else 创建默认分子标准化器()
    batch = engine.standardize([StandardizationRequest(c.compound_id, c.structure, c.structure_format, **配置) for c in inputs])
    results = {r.compound_id: r for r in batch}
    if len(batch) != len(候选池) or set(results) != {c.compound_id for c in inputs}:
        raise ValueError("标准化器返回候选身份不完整或重复")
    if any(results[c.compound_id].observed_structure != c.structure for c in inputs):
        raise ValueError("标准化器不得改变 observed_structure")
    view = [dict(row) | {"标准化计算结构": results[row["物质编号"]].calculation_structure or "",
                       "分子标准化": results[row["物质编号"]].to_dict()} for row in 候选池]
    return view, dict(映射, structure_field="标准化计算结构"), {"分子标准化结果": [r.to_dict() for r in batch]}


def _筛选结构候选(物质库, 结构查询, 结构字段映射, 结构检索器):
    """结构阶段仅筛候选，保留排除原因和查询快照。"""
    结构结果, 结构排除, 候选池 = {}, [], 物质库
    if 结构查询 is not None:
        if not isinstance(结构字段映射, dict) or set(结构字段映射) != {"id_field", "structure_field", "structure_format"}:
            raise StructureQueryError("结构查询须显式提供 id_field/structure_field/structure_format 映射")
        if 结构字段映射["id_field"] != "物质编号":
            raise StructureQueryError("发现入口的稳定ID字段必须为现有物质编号")
        结构候选 = adapt_candidates(物质库, **结构字段映射)
        if 结构检索器 is None:
            结构检索器 = 创建默认结构检索器()
        查询结果 = 结构检索器.search(结构查询, 结构候选)
        结构结果 = {"结构查询结果": 查询结果.to_dict()}
        命中 = {x.compound_id for x in 查询结果.hits}
        候选池 = [x for x in 物质库 if x["物质编号"] in 命中]
        结构排除 = [{"物质编号": x.compound_id, "原因": x.reason, "状态": x.status,
                    "来源": "Structure Query"} for x in 查询结果.invalid_candidates + 查询结果.excluded_candidates]
    return 候选池, 结构结果, 结构排除


def _计算候选分子属性(候选池, 计划, 结构字段映射, 分子属性计算器, 扩展描述符报告):
    """按需计算，不覆盖用户物性；计算报告独立返回。"""
    请求指标 = 计划.required_molecular_metrics if 计划 is not None else ()
    if 扩展描述符报告 is not None and (not isinstance(扩展描述符报告, (list, tuple)) or
            any(not isinstance(x, str) or not x.strip() for x in 扩展描述符报告)):
        raise ValueError("扩展描述符报告须为显式RDKit原始名称列表")
    if 请求指标 or 扩展描述符报告:
        if not isinstance(结构字段映射, dict) or set(结构字段映射) != {"id_field", "structure_field", "structure_format"}:
            raise StructureQueryError("分子属性计算须显式提供 id_field/structure_field/structure_format 映射")
        if 结构字段映射["id_field"] != "物质编号":
            raise StructureQueryError("发现入口的稳定ID字段必须为现有物质编号")
        if 分子属性计算器 is None:
            分子属性计算器 = 创建默认分子属性计算器()
        属性批次 = 分子属性计算器.calculate(adapt_candidates(候选池, **结构字段映射), 请求指标,
                                          extended_descriptors=扩展描述符报告)
        # 独立命名空间：不读取用户同名字段，不覆盖实测值或组装用分子量。
        属性索引 = {x.compound_id: {r.metric_id: r.to_dict() for r in x.properties} for x in 属性批次}
        if set(属性索引) != {x["物质编号"] for x in 候选池} or len(属性批次) != len(候选池):
            raise ValueError("分子属性计算器返回候选身份不完整或重复")
        候选池 = [dict(x) | {"分子计算属性": 属性索引[x["物质编号"]]} for x in 候选池]
        return 候选池, {"分子属性结果": [x.to_dict() for x in 属性批次]}
    return 候选池, {}


def _搜索并优化配方(搜索库, 生成配置, 约束, 配方证据, 计划, 模型选择, 模型参数, 获取插件):
    """粗搜与局部优化共用同一评价和排序契约，不读取 Benchmark。"""
    定义们 = 获取插件("自动配方组合").执行({"物质库": 搜索库, "生成配置": 生成配置})
    预测们, 组装失败 = [], []
    def 批量评估(定义列表):
        for 定义 in 定义列表:
            try:
                预测 = 预测完整配方(定义, 搜索库, 生成配置["物性条件"],
                                    模型选择=模型选择, 模型参数=模型参数, 获取插件=获取插件)
                评价 = 获取插件("发现配方约束评价").执行({"配方": 预测, "约束": 约束, "配方证据": 配方证据 or [], "执行计划": 计划})
                预测们.append(预测 | 评价)
            except (ValueError, TypeError) as e:
                组装失败.append({"配方名称": 定义["配方名称"], "原因": str(e)})
    def 排序当前():
        return 获取插件("配方候选排序").执行({"预测配方": 预测们, "目标折射率": 生成配置.get("目标折射率"),
                "返回数量": 生成配置.get("返回数量", 8), "优化目标": 约束.get("优化目标"), "执行计划": 计划})
    批量评估(定义们)
    排序 = 排序当前()
    已有 = {搜索定义质量签名(x) for x in 定义们}
    优化记录 = []
    轮数 = 生成配置.get("优化轮数", 2)
    if isinstance(轮数, bool) or not isinstance(轮数, int) or not 0 <= 轮数 <= 5:
        raise ValueError("优化轮数须为0–5")
    for 轮 in range(轮数):
        新定义 = 获取插件("配方比例局部优化").执行({"当前前沿": 排序["Pareto前沿"], "已有签名": 已有,
                                       "物质库": 搜索库, "生成配置": 生成配置})
        if len(已有) + len(新定义) > 生成配置.get("最大配方数", 2000):
            优化记录.append({"轮": 轮+1, "状态": "本轮完整邻域超过预算，保留此前结果", "新增": 0})
            break
        优化记录.append({"轮": 轮+1, "状态": "当前搜索前沿局部质量转移", "新增": len(新定义)})
        if not 新定义:
            break
        已有.update(搜索定义质量签名(x) for x in 新定义)
        批量评估(新定义)
        排序 = 排序当前()
    return 排序, 预测们, {"生成数量": len(已有), "粗搜数量": len(定义们),
                       "优化记录": 优化记录, "组装失败": 组装失败}
