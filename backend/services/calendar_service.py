"""交易日历：哪些日子是交易日（已剔除周末和法定节假日）。

数据源：新浪财经交易日历，经 akshare 的 tool_trade_date_hist_sina() 取得（需联网）。
期货日盘的休市日与它一致；节假日前的夜盘是否开放属于数据内容，不在这里判断。

缓存：拉到的日历写进 BASE_DIR/.trading_calendar.json（含拉取时间）。
- 缓存 CACHE_TTL 内直接用，不联网；
- 过期后联网刷新，刷新失败（断网 / 接口变动）就继续用旧缓存，并标记 stale=True；
- 既没有缓存又拉取失败：返回 None，调用方降级（不判断缺失交易日），不让整个页面报错。
进程内另有一层内存缓存，避免每次请求都读文件。
"""
import json
import os
import threading
import time

from backend import config

CACHE_NAME = '.trading_calendar.json'
CACHE_TTL = 24 * 3600        # 日历一天内不会变，一天刷新一次足够
MIN_PLAUSIBLE_DAYS = 1000    # 拉回来的日历少于这个数视为异常（真实有 8000+ 个），不覆盖缓存

RETRY_AFTER = 300            # 联网失败后至少隔这么久再试，免得页面每次刷新都卡在超时上

_lock = threading.Lock()
_mem = None                  # {'days': [...], 'fetchedAt': float}
_last_fail = 0.0             # 上次联网失败的时间


def cache_path():
    return os.environ.get('TRADING_CALENDAR_FILE') or os.path.join(config.BASE_DIR, CACHE_NAME)


def _fetch():
    """联网取全部交易日，升序 'YYYY-MM-DD' 列表。失败抛异常。"""
    import akshare as ak   # 延迟导入：只有真要联网时才付出 akshare 的导入开销
    df = ak.tool_trade_date_hist_sina()
    days = sorted({str(d)[:10] for d in df['trade_date']})
    if len(days) < MIN_PLAUSIBLE_DAYS:
        raise ValueError(f"交易日历数据异常（只有 {len(days)} 天）")
    return days


def _read_cache():
    try:
        with open(cache_path(), encoding='utf-8') as f:
            data = json.load(f)
        days, at = data['days'], float(data['fetchedAt'])
        if isinstance(days, list) and days:
            return {'days': days, 'fetchedAt': at}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _write_cache(data):
    path = cache_path()
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        print(f"[Calendar] 写缓存失败: {e}")


def load(force=False):
    """返回 {'days': [...], 'fetchedAt': 秒, 'stale': bool}，完全拿不到时返回 None。

    force=True 忽略缓存有效期强制联网刷新（失败仍回退到旧缓存）。
    """
    global _mem, _last_fail
    with _lock:
        data = _mem or _read_cache()
        now = time.time()
        fresh = data is not None and now - data['fetchedAt'] < CACHE_TTL
        if fresh and not force:
            _mem = data
            return {**data, 'stale': False}
        if not force and now - _last_fail < RETRY_AFTER:   # 刚失败过：不再重试，直接用旧缓存
            _mem = data
            return None if data is None else {**data, 'stale': True}
        try:
            new = {'days': _fetch(), 'fetchedAt': now}
        except Exception as e:
            _last_fail = now
            print(f"[Calendar] 拉取交易日历失败: {e}")
            if data is None:
                return None
            _mem = data
            return {**data, 'stale': True}
        _last_fail = 0.0
        _write_cache(new)
        _mem = new
        return {**new, 'stale': False}


def cached():
    """只读本地缓存，绝不联网（页面列表这类要快的路径用）：{'days','fetchedAt','stale'} 或 None。
    没有缓存或缓存过期时，会在后台线程里刷新，下次请求就是新的。"""
    global _mem
    with _lock:
        data = _mem or _read_cache()
        if data is not None:
            _mem = data
    if data is None:
        refresh_in_background()
        return None
    stale = time.time() - data['fetchedAt'] >= CACHE_TTL
    if stale:
        refresh_in_background()
    return {**data, 'stale': stale}


_bg = None


def refresh_in_background():
    """后台联网刷新一次（已有刷新在跑或刚失败过就什么也不做）。"""
    global _bg
    if _bg is not None and _bg.is_alive():
        return
    if time.time() - _last_fail < RETRY_AFTER:
        return
    _bg = threading.Thread(target=load, kwargs={'force': True}, daemon=True, name='calendar-refresh')
    _bg.start()


def trading_days(start, end):
    """[start, end]（含，'YYYY-MM-DD'）内的交易日；本地没有日历缓存返回 None（不联网，见 cached）。
    日历只覆盖到某个年底：end 超出日历范围的部分无法判断，不会被当成交易日。"""
    cal = cached()
    if cal is None:
        return None
    return [d for d in cal['days'] if start <= d <= end]


def missing_days(imported):
    """已导入日期列表 -> 其起止范围内「是交易日但没导入」的日期（升序）。日历不可用返回 None。"""
    if not imported:
        return []
    days = sorted(set(imported))
    want = trading_days(days[0], days[-1])
    if want is None:
        return None
    have = set(days)
    return [d for d in want if d not in have]


def reset_memory():
    """清掉进程内缓存（测试用）。"""
    global _mem, _last_fail
    with _lock:
        _mem = None
        _last_fail = 0.0
