"""移动后的导入、插件身份和历史参数接口回归。"""

import importlib
import json

import pandas as pd
import pytest


def test_工厂旧名与最终规则入口仅转发canonical(monkeypatch):
    from 核心系统.流程控制器 import 创建补充数据3流程控制器, 创建颅骨透明化筛选流程控制器
    from 插件.筛选与评价.规则筛选插件 import 规则筛选插件
    assert 创建补充数据3流程控制器 is 创建颅骨透明化筛选流程控制器
    plugin = 规则筛选插件()
    context, result = {}, object()
    seen = []
    monkeypatch.setattr(plugin, "执行最终自动规则筛选", lambda value: (seen.append(value), result)[1])
    assert plugin.执行最终规则筛选(context) is result
    assert seen == [context]


@pytest.mark.parametrize("old,new,old_name,new_name", [
    ("插件.数据导入.CompTox查询插件", "插件.数据导入.CompTox接口状态插件", "CompTox查询插件", "CompTox接口状态插件"),
    ("插件.数据导入.普通表格导入插件", "插件.数据导入.补充数据2表格导入插件", "普通表格导入插件", "补充数据2表格导入插件"),
    ("插件.数据导入.论文表格导入插件", "插件.数据导入.补充数据3表格导入插件", "论文表格导入插件", "补充数据3表格导入插件"),
    ("插件.数据合并.化学属性合并插件", "插件.数据合并.补充数据3属性合并插件", "化学属性合并插件", "补充数据3属性合并插件"),
    ("插件.数据合并.补充数据2属性合并插件", "插件.数据合并.补充数据2标签验证插件", "补充数据2属性合并插件", "补充数据2标签验证插件"),
    ("插件.化学计算.汉森距离计算插件", "插件.化学计算.补充数据3汉森距离计算插件", "汉森距离计算插件", "补充数据3汉森距离计算插件"),
    ("插件.数据导入.PubChem查询插件", "插件.公开数据.PubChem兼容接口", "PubChem查询插件", "PubChem查询插件"),
])
def test_旧类导入指向唯一实现(old, new, old_name, new_name):
    legacy = getattr(importlib.import_module(old), old_name)
    canonical = getattr(importlib.import_module(new), new_name)
    assert legacy is canonical
    assert legacy().插件标识 == canonical().插件标识


def test_PubChem旧网络注入路径保持同一个模块对象():
    old = importlib.import_module("插件.数据导入.PubChem查询插件")
    new = importlib.import_module("插件.公开数据.PubChem兼容接口")
    assert old.requests is new.requests


def test_旧用途运行器只适配参数并转发核心(monkeypatch):
    import 核心系统.配方评估流程 as core
    old = importlib.import_module("插件.颅骨透明化.颅骨透明化用途插件")
    new = importlib.import_module("插件.颅骨透明化.颅骨透明化功能插件")
    assert old.颅骨透明化用途运行器 is core.颅骨透明化用途运行器
    for name in old.__all__:
        if name != "颅骨透明化用途运行器":
            assert getattr(old, name) is getattr(new, name)
    seen = []
    marker = object()
    monkeypatch.setattr(core, "运行颅骨透明化流程", lambda context: (seen.append(context), marker)[1])
    ingredients = pd.DataFrame([{"成分键": "a"}])
    config = {"用途标识": "skull_clearing"}
    assert old.颅骨透明化用途运行器().运行(ingredients, config) is marker
    assert len(seen) == 1
    assert seen[0]["成分"] is ingredients and seen[0]["用途配置"] is config
    assert seen[0]["HSP参照"].empty and seen[0]["实验记录"].empty
    assert seen[0]["配方设置"] == {}


def test_公开配置解析保留旧语义与输入保护():
    from 核心系统.配方评估流程 import 解析物性配置, _配置对象
    assert _配置对象 is 解析物性配置
    original = {"温度_C": 25}
    assert 解析物性配置(original) == original
    assert 解析物性配置(original) is not original
    assert 解析物性配置(json.dumps(original)) == original
    for empty in (None, pd.NA, float("nan"), "", " "):
        assert 解析物性配置(empty) == {}
    for invalid in ("[]", "1", '"text"', 1):
        with pytest.raises(ValueError):
            解析物性配置(invalid)


def test_共享定义构建兼容旧调用且不修改输入():
    from 插件.配方生成.自动组合插件 import 组装定义 as legacy
    from 插件.配方生成.配方定义构建 import 组装定义
    assert legacy is 组装定义
    composition = {"b": .3, "a": .7}
    library = {"a": {"相态": "液体", "化学名称": "A"}, "b": {"相态": "固体", "化学名称": "B"}}
    result = 组装定义(composition, library, {})
    assert result["渗透参照溶剂"] == "a"
    assert result["组分"] == [{"物质编号": "a", "用量": .7, "单位": "质量分数", "角色": "主溶剂"}, {"物质编号": "b", "用量": .3, "单位": "质量分数", "角色": "候选成分"}]
    assert composition == {"b": .3, "a": .7}
    assert 组装定义({"b": 1}, library, {}) is None


def test_GHS仅接受正式H代码而不接受说明文字(monkeypatch) -> None:
    from 插件.数据导入.PubChem查询插件 import PubChem查询插件

    class 响应:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"Record": {"Section": [{"Information": [{"Value": {"StringWithMarkup": [{"String": "H302: Harmful if swallowed"}, {"String": "ECHA GHS system uses the letter H"}]}}]}]}}
    monkeypatch.setattr("插件.数据导入.PubChem查询插件.requests.get", lambda *a, **k: 响应())
    结果, 错误 = PubChem查询插件()._GHS("1")
    assert not 错误 and 结果["H代码"] == "H302" and "ECHA GHS system" not in 结果["危险说明"]


@pytest.mark.integration
def test_旧最终结果读取回退当前run的canonical筛选文件(seethrough2):
    标识 = "补充数据2_规则筛选统一记录"
    pd.testing.assert_frame_equal(seethrough2.读取筛选结果(标识), seethrough2.读取最终结果(标识))


def test_用途公开元数据继续重导出同一对象():
    from 设置 import 颅骨透明化用途设置 as current
    from 插件.颅骨透明化 import 颅骨透明化功能插件 as legacy
    for name in ("用途标识", "用途名称", "用途配置版本", "成分角色选项", "实验终点字段", "默认用途配置"):
        assert getattr(legacy, name) is getattr(current, name)
    one, two = current.默认用途配置(), current.默认用途配置()
    one["物性约束"]["test"] = 1
    assert two["物性约束"] == {}


def test_规则默认兼容入口等价且无共享可变状态():
    from 核心系统.通用规则引擎 import 属性定义, 属性注册表, 规则注册表, 应用配置
    from 设置.规则注册设置 import 创建默认属性注册表, 创建默认规则注册表
    old, new = 属性注册表.默认(), 创建默认属性注册表()
    pd.testing.assert_frame_equal(old.导出(), new.导出())
    old.注册(属性定义("extra", "extra", "test", "float", "", "test", "test"))
    assert "extra" not in new.导出()["属性编号"].tolist()
    rules, presets = 规则注册表.默认(), 创建默认规则注册表()
    assert rules.配置列表() == presets.配置列表()
    for config in presets.配置列表():
        pd.testing.assert_frame_equal(rules.导出规则(config.配置编号), presets.导出规则(config.配置编号))
    rules.注册配置(应用配置("extra", "extra", "test"))
    assert "extra" not in [x.配置编号 for x in presets.配置列表()]
    class CustomProperties(属性注册表):
        pass
    class CustomRules(规则注册表):
        pass
    assert isinstance(CustomProperties.默认(), CustomProperties)
    assert isinstance(CustomRules.默认(), CustomRules)


def test_上传旧入口与预览复用唯一parser():
    from 核心系统.候选表输入 import 读取候选上传内容, 安全文件名
    from 插件.数据导入.通用候选表导入插件 import 通用候选表导入插件
    from 软件界面 import 用户候选导入页面
    assert 通用候选表导入插件.读取上传内容 is 读取候选上传内容
    assert 通用候选表导入插件.安全文件名 is 安全文件名
    assert 用户候选导入页面.读取候选上传内容 is 读取候选上传内容
