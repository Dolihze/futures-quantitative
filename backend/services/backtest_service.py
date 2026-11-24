"""量化回测服务：从本地历史行情库（数据库管理里导入的 tick）取分钟 K 线。"""
from backend.services import kline_store

BACKTEST_PERIODS = kline_store.KLINE_PERIODS


def fetch_backtest_bars(symbol, period):
    """取某合约某周期在本地库里的全部可得 K 线，返回 dict 列表，升序。

    合约没导入时抛 ApiError(404) 并提示去「数据库管理」导入。聚合结果带缓存，库文件变化后自动失效。
    """
    return kline_store.fetch_bars(symbol, period)
