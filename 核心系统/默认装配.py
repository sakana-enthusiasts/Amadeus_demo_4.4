"""唯一默认装配边界：只构造和注册依赖，不执行流程、读用户数据或联网。"""

from collections.abc import Callable

from 核心系统.插件管理器 import 插件管理器
from 核心系统.结构查询 import StructureSearch
from 核心系统.分子属性 import MolecularPropertyCalculator
from 插件.插件接口 import 基础插件接口
from 插件.化学计算.RDKit普通描述符插件 import RDKit普通描述符插件
from 插件.化学计算.RDKit结构处理插件 import RDKit结构处理插件
from 插件.化学计算.补充数据3汉森距离计算插件 import 补充数据3汉森距离计算插件
from 插件.化学计算.补充数据2汉森距离计算插件 import 补充数据2汉森距离计算插件
from 插件.化学计算.HSP计算核心 import 通用HSP计算插件
from 插件.化学计算.折射率处理插件 import 折射率处理插件
from 插件.化学计算.水合能力处理插件 import 水合能力处理插件
from 插件.化学计算.确认批次描述符插件 import 确认批次描述符插件
from 插件.化学计算.用户候选HSP初筛插件 import 用户候选HSP初筛插件
from 插件.数据合并.补充数据3属性合并插件 import 补充数据3属性合并插件
from 插件.数据合并.补充数据2标签验证插件 import 补充数据2标签验证插件
from 插件.数据合并.官方数据冲突检测插件 import 官方数据冲突检测插件
from 插件.数据导入.补充数据3表格导入插件 import 补充数据3表格导入插件
from 插件.数据导入.补充数据2表格导入插件 import 补充数据2表格导入插件
from 插件.数据导入.通用候选表导入插件 import 通用候选表导入插件
from 插件.数据导入.化合物身份转换插件 import 化合物身份转换插件
from 插件.公开数据.公开证据聚合插件 import 公开证据聚合插件
from 插件.数据导入.CompTox接口状态插件 import CompTox接口状态插件
from 插件.筛选与评价.规则筛选插件 import 规则筛选插件
from 插件.筛选与评价.用户候选规则筛选插件 import 用户候选规则筛选插件
from 插件.筛选与评价.筛选报告导出插件 import 筛选报告导出插件
from 插件.筛选与评价.毒性证据视图插件 import 毒性证据视图插件
from 插件.筛选与评价.通用运行报告导出插件 import 通用运行报告导出插件
from 插件.筛选与评价.毒性判定指标插件 import 毒性判定指标规则插件
from 插件.筛选与评价.毒理证据匹配插件 import 毒理证据匹配插件
from 插件.筛选与评价.配方特征构建插件 import 配方特征构建插件
from 插件.颅骨透明化.颅骨透明化功能插件 import 颅骨透明化用途配置插件, 颅骨透明化成分评估插件, 颅骨透明化配方评估插件, 颅骨透明化实验终点评价插件, 颅骨透明化配方特征构建插件
from 插件.结果展示.筛选结果图表插件 import 筛选结果图表插件
from 插件.配方物性.配方物性汇总 import 配方物性汇总插件
from 插件.配方生成.配方输入组装插件 import 配方输入组装插件
from 插件.颅骨透明化.颅骨透明化功能插件 import 颅骨透明化用途约束插件
from 插件.配方生成.自动组合插件 import 自动组合插件
from 插件.配方生成.候选排序插件 import 配方候选排序插件
from 插件.配方生成.比例优化插件 import 比例优化插件
from 插件.配方生成.发现约束插件 import 候选分子筛选插件, 配方约束评价插件
from 插件.配方物性.配方物性汇总 import 模型注册表, 创建默认模型注册表
from 插件.数据导入.人工身份确认插件 import 人工身份确认插件


def 创建默认物性模型注册表() -> 模型注册表:
    """返回独立默认物性策略注册表，不执行模型或读取用户数据。"""
    return 创建默认模型注册表()


def 创建配方物性汇总(注册表: 模型注册表 | None = None) -> 配方物性汇总插件:
    """显式传入的注册表保持对象身份；不创建全局实例。"""
    return 配方物性汇总插件(注册表)


def 创建默认插件管理器(*, 物性注册表: 模型注册表 | None = None) -> 插件管理器:
    """每次返回独立管理器；canonical/alias 冲突由管理器显式拒绝。"""
    管理器 = 插件管理器()
    管理器.注册插件(补充数据3表格导入插件())
    管理器.注册插件(RDKit结构处理插件())
    管理器.注册插件(RDKit普通描述符插件())
    管理器.注册插件(补充数据3汉森距离计算插件())
    管理器.注册插件(补充数据3属性合并插件())
    管理器.注册插件(补充数据2表格导入插件(), 别名=("补充数据2表格导入",))
    管理器.注册插件(通用候选表导入插件())
    管理器.注册插件(化合物身份转换插件())
    管理器.注册插件(人工身份确认插件())
    公开插件 = 公开证据聚合插件()
    管理器.注册插件(公开插件, 别名=("PubChem查询",))
    管理器.注册插件(CompTox接口状态插件())
    管理器.注册插件(规则筛选插件())
    管理器.注册插件(用户候选规则筛选插件())
    管理器.注册插件(补充数据2汉森距离计算插件())
    管理器.注册插件(通用HSP计算插件())
    管理器.注册插件(折射率处理插件())
    管理器.注册插件(水合能力处理插件())
    管理器.注册插件(确认批次描述符插件())
    管理器.注册插件(用户候选HSP初筛插件())
    管理器.注册插件(配方特征构建插件())
    管理器.注册插件(创建配方物性汇总(物性注册表))
    管理器.注册插件(配方输入组装插件())
    管理器.注册插件(颅骨透明化用途约束插件())
    管理器.注册插件(颅骨透明化用途配置插件())
    管理器.注册插件(颅骨透明化成分评估插件())
    管理器.注册插件(颅骨透明化配方评估插件())
    管理器.注册插件(颅骨透明化实验终点评价插件())
    管理器.注册插件(颅骨透明化配方特征构建插件())
    管理器.注册插件(补充数据2标签验证插件())
    管理器.注册插件(官方数据冲突检测插件())
    管理器.注册插件(筛选报告导出插件())
    管理器.注册插件(毒性证据视图插件())
    管理器.注册插件(毒性判定指标规则插件())
    管理器.注册插件(毒理证据匹配插件())
    管理器.注册插件(通用运行报告导出插件())
    管理器.注册插件(筛选结果图表插件())
    管理器.注册插件(自动组合插件())
    管理器.注册插件(配方候选排序插件())
    管理器.注册插件(比例优化插件())
    管理器.注册插件(候选分子筛选插件())
    管理器.注册插件(配方约束评价插件())
    return 管理器


def 装配工作流插件获取器(
    获取插件: Callable[[str], 基础插件接口] | None = None,
    *, 注册表: 模型注册表 | None = None,
) -> Callable[[str], 基础插件接口]:
    """仅装配功能依赖；显式注册表只覆盖本次获取器的物性汇总，不修改调用方管理器。"""
    if 获取插件 is None:
        return 创建默认插件管理器(物性注册表=注册表).获取插件
    if 注册表 is None:
        return 获取插件
    物性汇总 = 创建配方物性汇总(注册表)

    def 获取(标识: str) -> 基础插件接口:
        return 物性汇总 if 标识 == "配方物性汇总" else 获取插件(标识)

    return 获取


def 创建默认结构检索器() -> StructureSearch:
    # 专用能力 composition boundary 延迟导入：仅请求该能力时选择 RDKit 实现。
    from 插件.化学计算.RDKit结构检索插件 import RDKit结构检索插件
    return RDKit结构检索插件()


def 创建默认分子属性计算器() -> MolecularPropertyCalculator:
    # 与业务流程分离，保留专用 Protocol，不注册到通用功能 ABI。
    from 插件.化学计算.RDKit分子属性计算器 import RDKit分子属性计算器
    return RDKit分子属性计算器()


def 创建公开证据执行桥(证据存储, *, 证据选择器=None, 查询上下文=None):
    """仅装配；cache_only 不调用聚合器，联网必须由调用方提供查询上下文并启用。"""
    from 核心系统.公开证据.执行桥 import PublicEvidenceExecutionBridge
    from 插件.公开数据.执行桥查询适配 import ExecutionEvidenceFetcher

    fetcher = None
    if 查询上下文 is not None:
        fetcher = ExecutionEvidenceFetcher(证据存储, 查询上下文, 证据选择器)
    return PublicEvidenceExecutionBridge(证据存储, resolver=证据选择器, fetcher=fetcher)


def 创建默认分子标准化器():
    from 插件.化学计算.RDKit分子标准化 import RDKitMoleculeStandardizer
    return RDKitMoleculeStandardizer()


def 创建描述符计算器(engine="RDKit"):
    from 插件.化学计算.扩展描述符后端 import RDKitDescriptorCalculator, MordredDescriptorCalculator
    if engine == "RDKit":
        return RDKitDescriptorCalculator()
    if engine == "Mordred-community":
        return MordredDescriptorCalculator()
    raise ValueError("未知描述符后端")
