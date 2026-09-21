"""干净根、旧结果投毒和同一控制器重复运行的隔离回归。"""

import pandas as pd
import pytest

from 核心系统.流程控制器 import 创建颅骨透明化筛选流程控制器

pytestmark = pytest.mark.integration
标识 = "补充数据2_规则筛选统一记录"


def test_干净根只生成一份canonical统一记录(seethrough2):
    root = seethrough2.项目根目录
    run = seethrough2.运行目录()
    assert (run / "筛选结果" / f"{标识}.csv").is_file()
    assert not (run / "模型结果" / f"{标识}.csv").exists()
    assert not (run / "中间结果/补充数据2_规则筛选记录.csv").exists()
    assert not (root / "数据/筛选结果").exists()
    assert not (root / "数据/中间结果").exists()
    assert len(seethrough2.读取中间结果("补充数据2_统一候选记录")) == 1619
    assert seethrough2.读取中间结果("补充数据2_结构映射结果")["候选编号"].nunique() == 41


def test_重复运行不读取legacy和前次run的错误结果(isolated_paper_root, seethrough2):
    controller = 创建颅骨透明化筛选流程控制器(isolated_paper_root)
    manager = controller.数据管理器
    stale = pd.DataFrame({"过期结果": ["不得读取"]})
    manager.保存筛选结果(标识, stale)
    manager.保存最终结果(标识, stale)
    manager.保存中间结果("仅旧目录存在", stale)
    manager.保存中间结果("补充数据3_统一候选基础记录", stale)
    first = controller.执行补充数据2规则筛选流程()
    manager.保存筛选结果(标识, stale)  # 故意损坏前一轮，仅限临时根。
    second = controller.执行补充数据2规则筛选流程()
    assert first["run_id"] != second["run_id"]
    assert [second[k] for k in ("清理后真实候选数", "数值初筛通过数", "自动规则最终剩余数", "论文最终10恢复数")] == [1619, 41, 20, 10]
    assert second["动物模型记录数"] == 20
    pd.testing.assert_frame_equal(manager.读取筛选结果(标识), seethrough2.读取筛选结果(标识))
    with pytest.raises(FileNotFoundError):
        manager.读取中间结果("仅旧目录存在")
    assert second["run_id"] in second["报告路径"]
    assert manager.导出结果目录.parent == manager.运行目录()


def test_共享fixture只读且各次读取独立(seethrough2):
    first = seethrough2.读取筛选结果(标识)
    first.loc[0, "候选编号"] = "修改副本"
    assert seethrough2.读取筛选结果(标识).loc[0, "候选编号"] != "修改副本"
    with pytest.raises(AssertionError, match="共享只读运行"):
        seethrough2.保存筛选结果(标识, first)
