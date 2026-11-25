"""本地历史行情库 -> 分钟 K 线。

数据来源是「数据库管理 / 历史行情数据管理」维护的 depth_files 里的 tick CSV（见 depth_service）。
回测与交易复盘都从这里取 K 线，不再访问任何在线行情接口。

约定（沿用原先在线分钟线的格式，前端不用改）：
- 返回 dict 列表，升序：{time, open, high, low, close, volume}，time 为 'YYYY-MM-DD HH:MM:SS'。
- time 是这根 K 线的【结束时间】：1 分钟线 09:00~09:01 的那根标 09:01，5 分钟线 09:00~09:05 标 09:05。
  （depth_market.build_kline 的 time 是开始时间，这里统一 +周期 换成结束时间。）
- 支持周期：1 / 5 / 15 / 30 / 60 分钟。
"""
import re
from datetime import datetime, timedelta

from backend.core import depth_market
from backend.errors import bad_request, not_found
from backend.services import depth_service, tick_cache

KLINE_PERIODS = ('1', '5', '15', '30', '60')

# 合约 tick 的解析缓存和分钟 K 线缓存都在 services/tick_cache.py（和深度行情共用，同一合约只解析一次，按内存预算淘汰）。
# 缓存签名 = 该合约所有文件的 (名称, 大小, mtime_ns)，导入 / 删除 / 覆盖文件后自动失效。
IMPORT_HINT = '请先到「数据库管理 → 历史行情数据管理」导入该合约的 tick 数据'


def normalize_symbol(symbol):
    """'SHFE.fu2611' / 'FU2611' -> 'fu2611'（库里按小写去掉交易所前缀比较）。"""
    return str(symbol or '').strip().split('.')[-1].lower()


def _find_contract(symbol):
    """在库里按不区分大小写、去交易所前缀的方式找合约，返回 scan() 里的合约 dict 或 None。"""
    key = normalize_symbol(symbol)
    contracts, _ = depth_service.scan()
    for c in contracts:
        if normalize_symbol(c['symbol']) == key:
            return c
    return None


def list_contracts():
    """库里已导入的合约（回测页下拉用）：[{symbol, name, days, dayCount, start, end, tickCount}]。"""
    contracts, _ = depth_service.scan()
    out = [{
        'symbol': c['symbol'], 'name': c['name'],
        'dayCount': c['dayCount'], 'start': c['start'], 'end': c['end'],
        'tickCount': c['tickCount'],
    } for c in contracts]
    out.sort(key=lambda x: x['symbol'].lower())
    return out


def _load_ticks(contract):
    """解析并合并该合约的所有文件，走统一缓存（和深度行情共用）。"""
    try:
        td, _ = depth_service.load_contract(contract)
    except (depth_market.DepthParseError, OSError) as e:
        raise bad_request(str(e))
    return td


def _end_time(start_label, period):
    """K 线开始时间 'YYYY-MM-DD HH:MM' + 周期分钟 -> 结束时间 'YYYY-MM-DD HH:MM:00'。"""
    t = datetime.strptime(start_label[:16], '%Y-%m-%d %H:%M') + timedelta(minutes=period)
    return t.strftime('%Y-%m-%d %H:%M:%S')


def fetch_bars(symbol, period):
    """取某合约某周期在本地库里的全部 K 线（升序，time 为结束时间）。

    合约没导入 / 没有可用数据时抛 ApiError(404)，提示去数据库管理导入；不会访问网络。
    """
    period = str(period)
    if period not in KLINE_PERIODS:
        raise bad_request(f'不支持的周期：{period}')
    contract = _find_contract(symbol)
    if contract is None:
        raise not_found(f'本地行情库里没有合约「{symbol}」的数据，{IMPORT_HINT}', fileMissing=True)

    sig = depth_service.contract_signature(contract)
    hit = tick_cache.get_bars(contract['symbol'], period, sig)
    if hit is not None:
        return hit

    td = _load_ticks(contract)
    res = depth_market.build_kline(td, int(period))
    bars = []
    for b in res['bars']:
        if b['open'] is None or b['close'] is None:
            continue
        bars.append({
            'time': _end_time(b['time'], int(period)),
            'open': float(b['open']), 'high': float(b['high']), 'low': float(b['low']), 'close': float(b['close']),
            'volume': int(b['volume'] or 0),
        })
    bars.sort(key=lambda x: x['time'])
    tick_cache.put_bars(contract['symbol'], period, sig, bars)
    return bars


def clear_cache():
    """清空所有 tick / K 线缓存（测试用）。"""
    tick_cache.clear()


def product_of(symbol):
    """合约代码 -> 品种代码：fu2611 -> FU（用于取最小变动价位 / 合约乘数）。"""
    return re.sub(r'\d+', '', normalize_symbol(symbol)).upper()
