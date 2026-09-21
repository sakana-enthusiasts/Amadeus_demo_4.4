"""现有属性与规则的默认预设；通用引擎仅保留数据契约和执行能力。"""

from 核心系统.通用规则引擎 import 属性定义, 属性注册表, 规则定义, 应用配置, 规则注册表
from 核心系统.分子属性 import CORE_METRICS


def 创建默认属性注册表() -> 属性注册表:
    return 属性注册表(
        [
            属性定义("hydration_score", "水合评分平均值", "物化", "float", "kcal/mol", "导入或计算", "水合自由能计算"),
            属性定义("hydration_std", "水合评分标准差", "物化", "float", "kcal/mol", "导入或计算", "水合自由能计算"),
            属性定义("hydration_ability", "水合能力", "物化", "float", "", "导入或计算", "水合能力评价"),
            属性定义("estimated_ri", "eRI", "物化", "float", "", "导入或计算", "折射率估算"),
            属性定义("hansen_dD", "dD", "Hansen 参数", "float", "MPa^0.5", "导入或计算", "Hansen 参数测量或估算"),
            属性定义("hansen_dP", "dP", "Hansen 参数", "float", "MPa^0.5", "导入或计算", "Hansen 参数测量或估算"),
            属性定义("hansen_dH", "dH", "Hansen 参数", "float", "MPa^0.5", "导入或计算", "Hansen 参数测量或估算"),
            属性定义("hansen_distance_ba", "与 BA 的 Hansen 距离", "Hansen 参数", "float", "MPa^0.5", "计算", "Hansen 距离公式"),
            属性定义("hansen_distance_va", "与 VA 的 Hansen 距离", "Hansen 参数", "float", "MPa^0.5", "计算", "Hansen 距离公式"),
            属性定义("tox_genotoxic_positive", "明确遗传毒性阳性", "毒性判定指标", "bool", "", "毒性证据", "毒性判定指标插件"),
            属性定义("tox_carcinogenic_evidence", "明确致癌证据", "毒性判定指标", "bool", "", "毒性证据", "毒性判定指标插件"),
            属性定义("tox_same_species_route_acute", "同物种同途径急性毒性证据", "毒性判定指标", "bool", "", "毒性证据", "毒性判定指标插件"),
            属性定义("tox_indirect_only", "只有间接证据", "毒性判定指标", "bool", "", "毒性证据", "毒性判定指标插件"),
            属性定义("tox_no_data", "完全无数据", "毒性判定指标", "bool", "", "毒性证据", "毒性判定指标插件"),
        ] + [属性定义(x.metric_id, x.descriptor_name, "分子2D计算属性", x.data_type,
                    x.unit, "RDKit计算", x.method) for x in CORE_METRICS.values()]
    )


def 创建默认规则注册表() -> 规则注册表:
    水相规则 = (
        规则定义("ST-AQ-001", "水合评分下限", "SeeThrough 水相", ("hydration_score",), ">=", -1.5, "kcal/mol", True, "无法评估", "排除", "SeeThrough Supplementary Fig. 2a", "1.0"),
        规则定义("ST-AQ-002", "eRI 下限", "SeeThrough 水相", ("estimated_ri",), ">", 1.58, "", True, "无法评估", "排除", "SeeThrough Supplementary Note 1", "1.0"),
        规则定义("ST-AQ-003", "与 BA 的 Hansen 距离", "SeeThrough 水相", ("hansen_distance_ba",), "<", 10.0, "MPa^0.5", True, "无法评估", "排除", "SeeThrough Methods", "1.0"),
        规则定义("TOX-001", "明确遗传毒性阳性", "毒性", ("tox_genotoxic_positive",), "==", False, "", False, "无法评估", "警告", "毒性判定指标插件", "1.0"),
        规则定义("TOX-002", "明确致癌证据", "毒性", ("tox_carcinogenic_evidence",), "==", False, "", False, "无法评估", "警告", "毒性判定指标插件", "1.0"),
    )
    有机相规则 = (
        规则定义("ST-OR-001", "eRI 下限", "SeeThrough 有机相", ("estimated_ri",), ">", 1.58, "", True, "无法评估", "排除", "SeeThrough Supplementary Note 1", "1.0"),
        规则定义("TOX-001", "明确遗传毒性阳性", "毒性", ("tox_genotoxic_positive",), "==", False, "", False, "无法评估", "警告", "毒性判定指标插件", "1.0"),
    )
    用户自定义规则 = (
        规则定义("CUS-001", "水合评分下限", "用户自定义", ("hydration_score",), ">=", -1.5, "kcal/mol", False, "无法评估", "排除", "用户配置", "1.0"),
        规则定义("CUS-002", "eRI 下限", "用户自定义", ("estimated_ri",), ">", 1.58, "", False, "无法评估", "排除", "用户配置", "1.0"),
        规则定义("CUS-003", "与 BA 的 Hansen 距离", "用户自定义", ("hansen_distance_ba",), "<", 10.0, "MPa^0.5", False, "无法评估", "排除", "用户配置", "1.0"),
        规则定义("CUS-TOX-001", "明确遗传毒性阳性", "毒性", ("tox_genotoxic_positive",), "==", False, "", False, "无法评估", "警告", "用户配置", "1.0"),
    )
    return 规则注册表(
        [
            应用配置("seethrough_aqueous", "SeeThrough 水相配置", "SeeThrough 水相公开规则；可逐条覆盖。", 水相规则),
            应用配置("seethrough_organic", "SeeThrough 有机相配置", "SeeThrough 有机相规则；可逐条覆盖。", 有机相规则),
            应用配置("generic_compound", "通用化合物配置", "不预设物化排除规则，按用户启用的规则运行。", tuple()),
            应用配置("user_custom", "用户自定义配置", "由用户单独启用、禁用或扩展规则。", 用户自定义规则),
        ]
    )
