"""仅在显式优化环境检查依赖，不把预留插件当已启用功能。"""

import importlib
import pytest

pytestmark = pytest.mark.optimization


@pytest.mark.parametrize("module", ["torch", "gpytorch", "botorch"])
def test_优化依赖可导入(module):
    assert importlib.import_module(module)
