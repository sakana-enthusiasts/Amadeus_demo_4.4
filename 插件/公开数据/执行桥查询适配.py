"""执行桥显式联网阶段复用公开聚合入口，不创建第二条 Provider 流程。"""

from .公开证据聚合插件 import 公开证据聚合插件


class ExecutionEvidenceFetcher:
    def __init__(self, repository, context, resolver=None):
        self.repository = repository
        self.context = dict(context)
        self.resolver = resolver

    def __call__(self, identities):
        return 公开证据聚合插件().执行(self.context | {"公开候选": identities,
            "证据存储": self.repository, "证据选择器": self.resolver,
            "公开能力": ("properties",), "允许网络公开查询": True})
