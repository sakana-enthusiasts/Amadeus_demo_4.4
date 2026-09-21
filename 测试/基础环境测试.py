"""独立环境与工程骨架的基础测试。"""

import importlib
import pkgutil
import sqlite3
from pathlib import Path

import numpy
import openpyxl
import pandas
import rdkit
import requests
import streamlit


项目根目录 = Path(__file__).resolve().parents[1]


def test_指定依赖可导入() -> None:
    assert all((numpy, pandas, openpyxl, rdkit, streamlit, requests))


def test_sqlite可用() -> None:
    with sqlite3.connect(":memory:") as 连接:
        连接.execute("CREATE TABLE 环境验证 (标识 INTEGER)")
        连接.execute("INSERT INTO 环境验证 VALUES (1)")
        assert 连接.execute("SELECT COUNT(*) FROM 环境验证").fetchone() == (1,)


def test_核心接口与页面模块可导入() -> None:
    模块列表 = [
        "核心系统.流程控制器",
        "核心系统.插件管理器",
        "核心系统.数据校验器",
        "核心系统.数据格式定义",
        "核心系统.数据管理接口",
        "核心系统.日志与错误记录管理器",
        "插件.插件接口",
        "软件界面.主界面",
    ]
    for 模块名 in 模块列表:
        assert importlib.import_module(模块名)


def test_所有插件模块可导入() -> None:
    import 插件

    插件模块 = [模块.name for 模块 in pkgutil.walk_packages(插件.__path__, "插件.")]
    assert 插件模块
    for 模块名 in 插件模块:
        assert importlib.import_module(模块名)


def test_论文原始数据目录存在且由接口保护() -> None:
    原始数据目录 = 项目根目录 / "数据" / "论文原始数据"
    assert 原始数据目录.is_dir()
    from 核心系统.数据管理接口 import 文件数据访问管理器

    管理器 = 文件数据访问管理器(项目根目录)
    try:
        管理器.确认目标可写入(原始数据目录 / "不应写入.xlsx")
    except PermissionError:
        return
    raise AssertionError("论文原始数据目录未受到写入保护")
