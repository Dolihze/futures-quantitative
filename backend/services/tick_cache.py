"""统一的 tick 解析缓存：深度行情、回测、交易复盘共用。

此前有两套互不相通的缓存：深度行情按随机 depthId 缓存（3 份，不检测文件变化），回测 / 复盘按合约缓存
（2 份）。同一个合约会被各解析一遍、内存里放两份。现在合并成一套：

- 合约缓存：键 = 合约代码，带文件签名（该合约所有文件的 名称 / 大小 / 修改时间）。导入 / 删除 / 覆盖后签名变化，
  下次取用自动重新解析；深度行情、回测、复盘取同一合约只解析一次、内存里只有一份。
- 句柄缓存：depthId -> TickData。深度行情页拿 depthId 反复请求 K 线 / 足迹 / 盘口 / tick。
  打开合约时 depthId 指向合约缓存里的同一个 TickData 对象（不复制）；
  打开单个文件（没有合约归属）时 depthId 指向它自己的 TickData。
- 淘汰按【内存预算】而不是个数：所有被缓存的 TickData（按对象去重）估算占用之和超过预算时，
  从最久没用的开始淘汰。一个 12 个文件的合约解析后约 35~50MB（实测），默认预算 768MB 大约能留 15~20 个。
  正在被使用的最新一份永远不会被淘汰（即使它自己就超过预算），避免刚打开就失效。
"""
import os
import threading
import uuid

import numpy as np

DEFAULT_BUDGET_MB = 768
BUDGET_ENV = 'TICK_CACHE_MB'


def budget_bytes():
    """内存预算（字节）。环境变量 TICK_CACHE_MB 可调（机器内存小时调低）。"""
    try:
        mb = float(os.environ.get(BUDGET_ENV, '') or DEFAULT_BUDGET_MB)
    except ValueError:
        mb = DEFAULT_BUDGET_MB
    return int(max(mb, 1) * 1024 * 1024)


def estimate_bytes(td):
    """TickData 占用内存的估算（字节）：数组本身 + object 数组里字符串的开销（取偏保守的每个 56 字节）。"""
    n = 0
    for v in vars(td).values():
        if isinstance(v, np.ndarray):
            n += v.nbytes + (len(v) * 56 if v.dtype == object else 0)
        elif isinstance(v, list):
            n += sum(a.nbytes for a in v if isinstance(a, np.ndarray))
    return n


_lock = threading.RLock()
# 合约缓存：symbol -> {"sig": 签名, "td": TickData, "used": 最近使用序号}
_CONTRACTS = {}
# 句柄缓存：depthId -> {"td": TickData, "symbol": 合约或 None, "used": 最近使用序号}
_HANDLES = {}
# 分钟 K 线缓存：(symbol, period) -> (签名, bars)；bars 很小，只按条数限制
_BARS = {}
BARS_MAX = 40
_clock = 0   # 单调递增的「最近使用」序号，每次取用 / 登记都 +1，比时间戳可靠（不会重复）


def _tick():
    global _clock
    _clock += 1
    return _clock


def _by_td():
    """按 TickData 对象去重后的所有缓存项：[{td, used(该对象最近一次被用的序号), contracts[...], handles[...]}]。
    合约缓存和句柄可能指向同一个对象（打开合约时），它们是一份内存，淘汰时一起走。"""
    groups = {}
    for sym, e in _CONTRACTS.items():
        g = groups.setdefault(id(e["td"]), {"td": e["td"], "used": 0, "contracts": [], "handles": []})
        g["used"] = max(g["used"], e["used"])
        g["contracts"].append(sym)
    for h, e in _HANDLES.items():
        g = groups.setdefault(id(e["td"]), {"td": e["td"], "used": 0, "contracts": [], "handles": []})
        g["used"] = max(g["used"], e["used"])
        g["handles"].append(h)
    return list(groups.values())


def used_bytes():
    with _lock:
        return sum(estimate_bytes(g["td"]) for g in _by_td())


def _evict():
    """超预算时按「最久没用」淘汰，直到不超预算。最近使用的那一份永远保留（即使它自己就超预算），
    避免刚打开 / 刚解析完就失效。淘汰一份 TickData 时，指向它的合约缓存和句柄一起删除。"""
    budget = budget_bytes()
    while True:
        groups = _by_td()
        if len(groups) <= 1 or sum(estimate_bytes(g["td"]) for g in groups) <= budget:
            return
        victim = min(groups, key=lambda g: g["used"])
        for sym in victim["contracts"]:
            _CONTRACTS.pop(sym, None)
            for k in [k for k in _BARS if k[0] == sym]:   # 该合约的 K 线很小，留着不占内存，但数据来源已丢，保持一致一并清掉
                _BARS.pop(k, None)
            for k in [k for k in _DAY_BARS if k[0] == sym]:
                _DAY_BARS.pop(k, None)
        for h in victim["handles"]:
            _HANDLES.pop(h, None)


# ---------------------------------------------------------------------------
# 合约缓存
# ---------------------------------------------------------------------------
def _drop_contract(symbol):
    """删掉某合约的缓存，以及指向同一份 TickData 的句柄和它的 K 线缓存。"""
    e = _CONTRACTS.pop(symbol, None)
    if e is None:
        return
    for h in [h for h, x in _HANDLES.items() if x["td"] is e["td"]]:
        _HANDLES.pop(h, None)
    for k in [k for k in _BARS if k[0] == symbol]:
        _BARS.pop(k, None)
    for k in [k for k in _DAY_BARS if k[0] == symbol]:
        _DAY_BARS.pop(k, None)


def get_contract(symbol, sig):
    """取合约的 TickData；没有或文件签名变了返回 None（签名变了会连同旧句柄一起作废）。命中时标记为最近使用。"""
    with _lock:
        e = _CONTRACTS.get(symbol)
        if e is None:
            return None
        if e["sig"] != sig:
            _drop_contract(symbol)
            return None
        e["used"] = _tick()
        return e["td"]


def put_contract(symbol, sig, td):
    """缓存一个合约解析结果（同合约的旧数据被替换）。"""
    with _lock:
        _drop_contract(symbol)
        _CONTRACTS[symbol] = {"sig": sig, "td": td, "used": _tick()}
        _evict()


# ---------------------------------------------------------------------------
# 句柄（depthId）
# ---------------------------------------------------------------------------
def new_handle(td, symbol=None):
    """登记一个 TickData，返回 depthId。symbol 不为空表示它同时是该合约的缓存（调用方已 put_contract）。"""
    handle = uuid.uuid4().hex
    with _lock:
        _HANDLES[handle] = {"td": td, "symbol": symbol, "used": _tick()}
        _evict()
    return handle


def get_handle(handle):
    """按 depthId 取 TickData；不存在（被淘汰 / 后端重启 / 文件已变）返回 None。命中时标记为最近使用。"""
    with _lock:
        e = _HANDLES.get(handle or '')
        if e is None:
            return None
        now = _tick()
        e["used"] = now
        c = _CONTRACTS.get(e["symbol"])
        if c is not None and c["td"] is e["td"]:
            c["used"] = now   # 正在看的合约也算最近使用，别被淘汰
        return e["td"]


# ---------------------------------------------------------------------------
# K 线缓存（回测 / 复盘）
# ---------------------------------------------------------------------------
def get_bars(symbol, period, sig):
    with _lock:
        hit = _BARS.get((symbol, period))
        return hit[1] if hit and hit[0] == sig else None


def put_bars(symbol, period, sig, bars):
    with _lock:
        _BARS[(symbol, period)] = (sig, bars)
        while len(_BARS) > BARS_MAX:
            _BARS.pop(next(iter(_BARS)))


# 按交易日分好组的 K 线：(symbol, period) -> (签名, {交易日: [bar, ...]})。
# 和上面的 K 线缓存用同一个签名，文件变了一起失效；只是引用同一批 bar 字典，几乎不多占内存。
_DAY_BARS = {}


def get_day_bars(symbol, period, sig):
    with _lock:
        hit = _DAY_BARS.get((symbol, period))
        return hit[1] if hit and hit[0] == sig else None


def put_day_bars(symbol, period, sig, groups):
    with _lock:
        _DAY_BARS[(symbol, period)] = (sig, groups)
        while len(_DAY_BARS) > BARS_MAX:
            _DAY_BARS.pop(next(iter(_DAY_BARS)))


def clear():
    with _lock:
        _CONTRACTS.clear()
        _HANDLES.clear()
        _BARS.clear()
        _DAY_BARS.clear()


def stats():
    """调试 / 测试用：缓存里有哪些合约、句柄数、估算占用。"""
    with _lock:
        return {"contracts": sorted(_CONTRACTS), "handles": len(_HANDLES), "usedBytes": used_bytes(),
                "budgetBytes": budget_bytes()}
