"""量化回测服务：新浪 K 线获取与短时缓存。"""
import time

# 新浪 K 线按 (合约, 周期) 缓存几分钟：首页一次要对所有策略回测，详情页又会再取一次，不必每次都请求网络。
BACKTEST_KLINE_CACHE = {}
BACKTEST_KLINE_TTL = 300  # 秒
BACKTEST_PERIODS = ('1', '5', '15', '30', '60')


def fetch_backtest_bars(symbol, period):
    """取某合约某周期的全部可得 K 线（新浪每个周期只给最近约 1023 根）。返回 dict 列表，升序。"""
    import akshare as ak
    import pandas as pd

    key = (symbol, period)
    cached = BACKTEST_KLINE_CACHE.get(key)
    if cached and time.time() - cached[0] < BACKTEST_KLINE_TTL:
        return cached[1]
    df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
    if df is None or df.empty:
        return []
    df = df.copy()
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')
    bars = [{
        'time': r.datetime.strftime('%Y-%m-%d %H:%M:%S'),
        'open': float(r.open), 'high': float(r.high), 'low': float(r.low), 'close': float(r.close),
        'volume': int(r.volume) if hasattr(r, 'volume') else 0,
    } for r in df.itertuples(index=False)]
    BACKTEST_KLINE_CACHE[key] = (time.time(), bars)
    return bars
