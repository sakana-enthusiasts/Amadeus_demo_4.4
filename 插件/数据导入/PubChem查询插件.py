"""旧路径 shim；参数适配在 插件.公开数据.PubChem兼容接口，查询统一使用 Provider。"""

from 插件.公开数据.PubChem兼容接口 import PubChem查询插件, requests

# requests 是同一个模块对象，保留旧测试/调用者的 requests.get 注入路径。
__all__ = ["PubChem查询插件", "requests"]
