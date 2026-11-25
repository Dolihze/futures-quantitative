"""build_kline 的【参照实现】：逐根组装版本的原样拷贝（改成向量化之前的实现）。

向量化版本（backend/core/depth_market.build_kline）必须和它逐根、逐字段、逐类型完全一致；
对照测试在 test_depth_market.py（test_kline_vectorized_matches_reference_*）。
这份代码故意保持原样、不要优化：它的作用是当「标准答案」。
"""
import numpy as np
import pandas as pd

from backend.core.depth_market import _clean, _group_ticks


def build_kline_reference(td, period=1, day=None):
    idx, keys, labels = _group_ticks(td, period, day)
    if len(idx) == 0:
        return {'bars': [], 'period': period}

    ts = td.ts[idx]
    price = td.price[idx]
    vol = td.vol[idx]
    money = td.money[idx]
    pos = td.position[idx]
    days = td.day[idx]

    g = pd.DataFrame({
        'k': keys, 'p': price, 'v': vol, 'm': money, 'pos': pos, 'i': idx, 'ts': ts, 'day': days,
    })
    grp = g.groupby('k', sort=True)
    first = grp.first()
    last = grp.last()
    agg = grp.agg(high=('p', 'max'), low=('p', 'min'), volume=('v', 'sum'), money=('m', 'sum'))
    sizes = grp.size()

    bs_by_bar = None
    if td.bs is not None:
        bg = pd.DataFrame({'k': keys, 'bs': td.bs[idx], 'v': vol})
        bg = bg[bg['bs'] != '']
        bs_by_bar = {k: sub.groupby('bs')['v'].sum().to_dict() for k, sub in bg.groupby('k')}

    bars = []
    for k in agg.index:
        bar_bs = None
        if bs_by_bar is not None:
            bar_bs = {name: _clean(v) for name, v in bs_by_bar.get(k, {}).items()}
        bars.append({
            'time': labels[k],
            'day': first.at[k, 'day'],
            'open': _clean(first.at[k, 'p']),
            'high': _clean(agg.at[k, 'high']),
            'low': _clean(agg.at[k, 'low']),
            'close': _clean(last.at[k, 'p']),
            'volume': _clean(agg.at[k, 'volume']),
            'money': _clean(agg.at[k, 'money']),
            'position': _clean(last.at[k, 'pos']),
            'ts0': int(first.at[k, 'ts']),
            'ts1': int(last.at[k, 'ts']),
            'ti0': int(first.at[k, 'i']),
            'ti1': int(last.at[k, 'i']),
            'ticks': int(sizes.at[k]),
            'bs': bar_bs,
        })
    return {'bars': bars, 'period': period}