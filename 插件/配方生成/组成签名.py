"""质量组成公共纯契约；绝对投料必须先经过组装换算。"""

from math import isclose, isfinite


def 质量分数组成签名(组成):
    """接受显式 (稳定成分 ID, 质量分数)，校验后按 ID 排序，保留10位。"""
    项们 = []
    try:
        for 编号, 分数 in 组成:
            if not isinstance(编号, str) or not 编号.strip():
                raise ValueError("需要非空稳定成分ID")
            if isinstance(分数, bool):
                raise ValueError("质量分数不能是布尔值")
            数 = float(分数)
            if not isfinite(数) or 数 <= 0:
                raise ValueError("质量分数必须有限且为正")
            项们.append((编号, 数))
    except (TypeError, OverflowError) as e:
        raise ValueError("质量分数组成格式无效") from e
    if (not 项们 or len({i for i, _ in 项们}) != len(项们)
            or not isclose(sum(f for _, f in 项们), 1, abs_tol=1e-6, rel_tol=0)):
        raise ValueError("规范化质量组成必须ID唯一、分数之和约等于1")
    return tuple(sorted((i, round(f, 10)) for i, f in 项们))


def 搜索定义质量签名(定义):
    """仅接受原始质量分数搜索定义；拒绝 g/mL/mol 等单位。"""
    if any(x.get("单位") != "质量分数" for x in 定义["组分"]):
        raise ValueError("搜索定义签名仅接受质量分数单位")
    return 质量分数组成签名((x["物质编号"], x["用量"]) for x in 定义["组分"])


def 已组装配方质量签名(配方):
    """取组装后计算的质量分数，适用于分数或绝对投料输入。"""
    return 质量分数组成签名((x["成分键"], x["质量分数"]) for x in 配方["成分"])
