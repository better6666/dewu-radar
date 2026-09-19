# -*- coding: utf-8 -*-
"""平台 adapter 注册表。按调研结果逐个接入可用的进货平台。"""
from __future__ import annotations

from typing import List

from .base import PlatformAdapter


def get_adapters() -> List[PlatformAdapter]:
    """返回可用的进货平台 adapter 列表。"""
    adapters: List[PlatformAdapter] = []
    # 逐个接入（按调研可行性），失败的平台静默跳过
    for factory in _factories():
        try:
            adapters.append(factory())
        except Exception:  # noqa: BLE001
            continue
    return adapters


# 平台 adapter 工厂列表（按调研结果填充）
def _factories():
    from .suning import SuningAdapter
    return [SuningAdapter]
