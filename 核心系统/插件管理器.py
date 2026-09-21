"""插件注册与查找接口；不负责任何业务流程编排。"""

from 插件.插件接口 import 基础插件接口


class 插件管理器:
    def __init__(self) -> None:
        self._已注册插件: dict[str, 基础插件接口] = {}
        self._别名: dict[str, str] = {}

    @staticmethod
    def _标识(值):
        if not isinstance(值, str) or not 值.strip() or 值 != 值.strip():
            raise ValueError("插件标识/别名必须为无首尾空格的非空字符串")
        return 值

    def _校验(self, 实例, 别名, *, 替换标识=None):
        if not isinstance(实例, 基础插件接口):
            raise TypeError("功能注册要求基础插件接口实例；专用能力使用自己的接口")
        标识 = self._标识(实例.插件标识)
        if 标识 == 基础插件接口.插件标识:
            raise ValueError("插件必须声明稳定标识")
        if 替换标识 is not None and 标识 != 替换标识:
            raise ValueError("替换实例必须保留 canonical 插件标识")
        if isinstance(别名, str):
            raise TypeError("别名必须为字符串序列")
        名称们 = tuple(self._标识(x) for x in 别名)
        if len(set((标识,) + 名称们)) != len(名称们) + 1:
            raise ValueError("canonical 与 alias 不得重复")
        占用 = (set(self._已注册插件) - {替换标识}) | {
            k for k, v in self._别名.items() if v != 替换标识}
        冲突 = 占用 & set((标识,) + 名称们)
        if 冲突:
            raise ValueError(f"插件标识/别名已注册：{sorted(冲突)}；替换请使用替换插件")
        return 标识, 名称们

    def 注册插件(self, 插件实例, *, 别名=()) -> None:
        标识, 名称们 = self._校验(插件实例, 别名)
        self._已注册插件[标识] = 插件实例
        self._别名.update({x: 标识 for x in 名称们})

    def 替换插件(self, 插件实例, *, 别名=None) -> None:
        if not isinstance(插件实例, 基础插件接口):
            raise TypeError("替换要求基础插件接口实例")
        标识 = self._标识(插件实例.插件标识)
        if 标识 not in self._已注册插件:
            raise KeyError(f"不能替换未注册 canonical ID：{标识}")
        旧别名 = tuple(k for k, v in self._别名.items() if v == 标识)
        标识, 名称们 = self._校验(插件实例, 旧别名 if 别名 is None else 别名, 替换标识=标识)
        self._已注册插件[标识] = 插件实例
        self._别名 = {k: v for k, v in self._别名.items() if v != 标识}
        self._别名.update({x: 标识 for x in 名称们})

    def 获取插件(self, 插件标识: str):
        标识 = self._别名.get(插件标识, 插件标识)
        try:
            return self._已注册插件[标识]
        except KeyError:
            raise KeyError(f"未知插件：{插件标识}；可用注册：{self.注册列表()}") from None

    def 注册列表(self):
        return tuple({"插件标识": k, "别名": tuple(a for a, c in self._别名.items() if c == k)}
                     for k in self._已注册插件)
