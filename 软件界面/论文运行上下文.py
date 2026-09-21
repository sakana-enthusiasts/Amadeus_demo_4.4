"""页面共享明确的论文运行编号；无新运行时保留旧结果浏览兼容。"""

import streamlit as st

from 核心系统.运行数据管理 import 运行数据管理器


def 读取论文运行(项目根目录, 补充表编号):
    管理器 = 运行数据管理器(项目根目录)
    run_id = st.session_state.get(f"补充数据{补充表编号}run_id")
    if run_id:
        管理器.激活运行(run_id)
    return 管理器
