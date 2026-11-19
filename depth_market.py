"""深度行情：历史 tick CSV 解析、K 线聚合、历史盘口查询。

输入是下载的历史 tick CSV（常见列：symbol, code, name, time, open, current, high, low,
volume, money, position, a1_p, a1_v, b1_p, b1_v ... a5_*, b5_*）。

约定：
- time 为 YYYYMMDDHHMMSSmmm（17 位）；也兼容 14 位、12 位、以及 "2026-05-29 21:00:00.500" 这类字符串。
- volume / money 是【当日累计值】：按交易日分组后差分得到每笔 tick 的增量（交易日内数值回退视为重置）。
- 夜盘（>= 20:00）和周末归属下一个交易日，与 review.py 的 trading_day 规则一致。
- 盘口档位自适应：CSV 里有几档（a{n}_p / a{n}_v / b{n}_p / b{n}_v）就解析几档，最多 5 档。
"""
import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


class DepthParseError(Exception):
    """CSV 格式不对 / 缺必要列：message 直接展示给用户。"""


# K 线周期（分钟）。1440 = 日线（按交易日聚合）
PERIODS = (1, 5, 15, 30, 60, 1440)
MAX_LEVELS = 5

# 必要列的别名（小写比较）。键是内部名
COLUMN_ALIASES = {
    'time': ['time', 'datetime', 'timestamp', 'date_time', 'tradetime', '时间', '日期时间'],
    'price': ['current', 'last', 'lastprice', 'last_price', 'price', 'close', '最新价', '现价', '当前价'],
    'open': ['open', 'openprice', '开盘价', '今开'],
    'high': ['high', 'highprice', 'highestprice', '最高价', '最高'],
    'low': ['low', 'lowprice', 'lowestprice', '最低价', '最低'],
    'volume': ['volume', 'vol', '成交量', '总量'],
    'money': ['money', 'turnover', 'amount', '成交额', '成交金额'],
    'position': ['position', 'openinterest', 'open_interest', 'oi', '持仓量', '持仓'],
    'symbol': ['symbol', 'code', 'instrument', 'instrumentid', '合约', '合约代码'],
    'name': ['name', '名称', '合约名称'],
}


@dataclass
class TickData:
    """解析后的 tick 数据（全部是等长 numpy 数组，按时间升序）。"""
    ts: np.ndarray            # 毫秒时间戳（int64，北京时间当作 UTC 存，只用于排序/展示，不做时区换算）
    price: np.ndarray         # 最新价
    vol: np.ndarray           # 每笔成交量增量
    cum_vol: np.ndarray       # 当日累计成交量（原值）
    money: np.ndarray         # 每笔成交额增量
    position: np.ndarray      # 持仓量
    day: np.ndarray           # 交易日 'YYYY-MM-DD'（object 数组）
    ask_p: list = field(default_factory=list)   # 每档一个数组：[a1_p, a2_p, ...]
    ask_v: list = field(default_factory=list)
    bid_p: list = field(default_factory=list)
    bid_v: list = field(default_factory=list)
    symbol: str = ''
    name: str = ''
    days: list = field(default_factory=list)    # 升序交易日列表
    warnings: list = field(default_factory=list)

    @property
    def levels(self):
        return len(self.ask_p)

    @property
    def count(self):
        return int(len(self.ts))


# ---------------------------------------------------------------------------
# 读取与列识别
# ---------------------------------------------------------------------------
def _read_csv(content: bytes) -> pd.DataFrame:
    last_err = None
    for enc in ('utf-8-sig', 'gbk'):
        try:
            # dtype=object：time 这类 17 位整数不能被当成 float 吃掉精度
            return pd.read_csv(io.BytesIO(content), dtype=object, encoding=enc)
        except UnicodeDecodeError as e:
            last_err = e
        except pd.errors.EmptyDataError:
            raise DepthParseError('文件是空的')
        except Exception as e:
            raise DepthParseError(f'无法读取 CSV：{e}')
    raise DepthParseError(f'无法识别文件编码（需要 UTF-8 或 GBK）：{last_err}')


def _norm(s) -> str:
    return re.sub(r'\s+', '', str(s)).lower()


def _find_col(columns: dict, key: str):
    """columns: {规范化列名: 原列名}"""
    for alias in COLUMN_ALIASES[key]:
        if alias in columns:
            return columns[alias]
    return None


def _detect_levels(columns: dict):
    """识别盘口列：支持 a1_p / a1_v / b1_p / b1_v，以及 ask1_price / bid1_volume / askprice1 / bidvolume1 等写法。
    返回 [(ask_p, ask_v, bid_p, bid_v), ...]（每档一组原列名），缺任何一列的档位及其之后的档位都丢弃。"""
    def pick(side, n, kind):
        s_long = 'ask' if side == 'a' else 'bid'
        p_long = 'price' if kind == 'p' else 'volume'
        k_alt = 'vol' if kind == 'v' else 'price'
        names = [
            f'{side}{n}_{kind}', f'{side}{n}{kind}',
            f'{s_long}{n}_{p_long}', f'{s_long}{n}{p_long}', f'{s_long}{p_long}{n}', f'{s_long}_{p_long}_{n}',
            f'{s_long}{n}_{k_alt}', f'{s_long}{k_alt}{n}',
        ]
        if side == 'a':
            names += [f'卖{n}价' if kind == 'p' else f'卖{n}量']
        else:
            names += [f'买{n}价' if kind == 'p' else f'买{n}量']
        for nm in names:
            if nm in columns:
                return columns[nm]
        return None

    levels = []
    for n in range(1, MAX_LEVELS + 1):
        cols = (pick('a', n, 'p'), pick('a', n, 'v'), pick('b', n, 'p'), pick('b', n, 'v'))
        if any(c is None for c in cols):
            break
        levels.append(cols)
    return levels


def _parse_time(series: pd.Series) -> np.ndarray:
    """把 time 列解析为毫秒时间戳（int64，北京时间按 UTC 存）。无法解析的行返回 iNaT 标记 -> 由调用方丢弃。"""
    s = series.astype(str).str.strip()
    # 纯数字（可能带 .0 后缀，比如被 Excel 另存过）
    digits = s.str.replace(r'\.0+$', '', regex=True)
    is_num = digits.str.fullmatch(r'\d{12,17}')
    out = pd.Series(pd.NaT, index=s.index, dtype='datetime64[ns]')

    if is_num.any():
        d = digits[is_num]
        # 按位数补齐成 17 位：YYYYMMDDHHMMSSmmm；12 位 = 到分钟，14 位 = 到秒
        d = d.str.ljust(17, '0')
        out.loc[is_num] = pd.to_datetime(d, format='%Y%m%d%H%M%S%f', errors='coerce')
    rest = ~is_num
    if rest.any():
        out.loc[rest] = pd.to_datetime(s[rest], errors='coerce')
    # 转毫秒；NaT -> 最小值（后面按 isna 过滤）
    return out


def _trading_day(dt: pd.Series) -> pd.Series:
    """交易日：>= 20:00 的夜盘算下一个自然日；落在周六/周日的再顺延到周一。"""
    shifted = dt + pd.to_timedelta((dt.dt.hour >= 20).astype(int), unit='D')
    dow = shifted.dt.dayofweek  # 周六 5、周日 6
    shifted = shifted + pd.to_timedelta(np.where(dow == 5, 2, np.where(dow == 6, 1, 0)), unit='D')
    return shifted.dt.strftime('%Y-%m-%d')


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(',', '').str.strip(), errors='coerce')


def _diff_cumulative(values: np.ndarray, days: np.ndarray):
    """把【当日累计】序列按交易日差分成增量（向量化）。
    每个交易日第一笔：增量 = 累计值本身；交易日内回退（< 前值）视为重置，把当前值本身当增量。"""
    v = np.nan_to_num(values.astype(float), nan=0.0)
    prev = np.concatenate(([0.0], v[:-1]))
    # 交易日切换处，前值清零
    new_day = np.concatenate(([True], days[1:] != days[:-1]))
    prev = np.where(new_day, 0.0, prev)
    return np.where(v >= prev, v - prev, v)


# ---------------------------------------------------------------------------
# 解析入口
# ---------------------------------------------------------------------------
def parse(content: bytes, filename: str = '') -> TickData:
    df = _read_csv(content)
    if df.empty:
        raise DepthParseError('文件里没有数据行')
    columns = {_norm(c): c for c in df.columns}

    c_time = _find_col(columns, 'time')
    c_price = _find_col(columns, 'price')
    if c_time is None:
        raise DepthParseError('找不到时间列（需要 time / datetime 等）。当前列：' + ', '.join(map(str, df.columns[:15])))
    if c_price is None:
        raise DepthParseError('找不到最新价列（需要 current / last / price 等）。当前列：' + ', '.join(map(str, df.columns[:15])))

    warnings = []
    dt = _parse_time(df[c_time])
    price = _to_num(df[c_price])
    ok = dt.notna() & price.notna() & (price > 0)
    dropped = int((~ok).sum())
    if dropped:
        warnings.append(f'{dropped} 行时间或价格无效，已忽略')
    if not ok.any():
        raise DepthParseError('没有可用的 tick：时间或最新价全部无法解析')

    df = df.loc[ok].reset_index(drop=True)
    dt = dt.loc[ok].reset_index(drop=True)
    price = price.loc[ok].reset_index(drop=True)

    # 按时间稳定排序（同毫秒的多笔保持文件原顺序）
    order = np.argsort(dt.values, kind='stable')
    if not np.array_equal(order, np.arange(len(order))):
        df = df.iloc[order].reset_index(drop=True)
        dt = dt.iloc[order].reset_index(drop=True)
        price = price.iloc[order].reset_index(drop=True)
        warnings.append('文件里的 tick 不是按时间排序的，已重新排序')

    days = _trading_day(dt).to_numpy(dtype=object)

    def num_col(key, default=0.0):
        c = _find_col(columns, key)
        if c is None:
            return None
        return _to_num(df[c]).to_numpy(dtype=float)

    cum_vol = num_col('volume')
    if cum_vol is None:
        warnings.append('没有成交量列，K 线成交量显示为 0')
        cum_vol = np.zeros(len(df))
    cum_money = num_col('money')
    if cum_money is None:
        cum_money = np.zeros(len(df))
    position = num_col('position')
    if position is None:
        position = np.full(len(df), np.nan)

    # 累计值 -> 增量。如果整列单调不减就是累计值；若频繁回退（>= 5% 的行）更像是单笔增量，直接使用并提示
    vol_inc = _diff_cumulative(cum_vol, days)
    drops = int((np.diff(np.nan_to_num(cum_vol)) < 0).sum())
    # 每个交易日开始都会合法回退一次，所以阈值以“交易日数 + 5% 行数”为准
    if len(cum_vol) > 50 and drops > len(set(days)) + len(cum_vol) * 0.05:
        warnings.append('成交量不是单调递增，疑似单笔增量而非当日累计，已按增量直接使用')
        vol_inc = np.nan_to_num(cum_vol)
    money_inc = _diff_cumulative(cum_money, days) if cum_money.any() else np.zeros(len(df))

    levels = _detect_levels(columns)
    ask_p, ask_v, bid_p, bid_v = [], [], [], []
    for ap, av, bp, bv in levels:
        ask_p.append(_to_num(df[ap]).to_numpy(dtype=float))
        ask_v.append(_to_num(df[av]).to_numpy(dtype=float))
        bid_p.append(_to_num(df[bp]).to_numpy(dtype=float))
        bid_v.append(_to_num(df[bv]).to_numpy(dtype=float))
    if not levels:
        warnings.append('没有识别到盘口列（a1_p / a1_v / b1_p / b1_v ...），只能看 K 线')

    c_sym = _find_col(columns, 'symbol')
    c_name = _find_col(columns, 'name')
    symbol = str(df[c_sym].iloc[0]).strip() if c_sym else ''
    name = str(df[c_name].iloc[0]).strip() if c_name else ''
    if not symbol:
        symbol = re.sub(r'\.[^.]+$', '', filename or '') or '未知合约'
    if len(set(df[c_sym].astype(str))) > 1 if c_sym else False:
        warnings.append('文件里有多个合约的 tick，K 线会混在一起；建议每个文件只放一个合约')

    return TickData(
        ts=(dt.astype('int64') // 1_000_000).to_numpy(dtype=np.int64),
        price=price.to_numpy(dtype=float),
        vol=vol_inc,
        cum_vol=cum_vol,
        money=money_inc,
        position=position,
        day=days,
        ask_p=ask_p, ask_v=ask_v, bid_p=bid_p, bid_v=bid_v,
        symbol=symbol,
        name=name,
        days=sorted(set(days.tolist())),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def fmt_ts(ms: int, with_ms=False) -> str:
    t = pd.Timestamp(int(ms), unit='ms')
    return t.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if with_ms else t.strftime('%Y-%m-%d %H:%M:%S')


def _clean(x):
    """numpy 标量 -> JSON 友好的 python 值；NaN -> None。"""
    if x is None:
        return None
    f = float(x)
    if f != f:
        return None
    return int(f) if f.is_integer() and abs(f) < 1e15 else round(f, 6)


# ---------------------------------------------------------------------------
# K 线聚合
# ---------------------------------------------------------------------------
def build_kline(td: TickData, period: int = 1, day: str = None) -> dict:
    """由 tick 聚合 K 线。

    period：分钟数（1 / 5 / 15 / 30 / 60）或 1440（日线）。
    day：只取某个交易日（YYYY-MM-DD）；None = 全部交易日（日线时建议 None）。

    K 线的时间边界按“日历分钟”向下取整（9:00:00~9:00:59 -> 09:00）；5 分钟以上按
    自然整点对齐（9:00、9:05 …）。夜盘不特殊处理，同一个交易日里按真实时间连续排列。
    每根 bar 额外带 first/last tick 序号（ti0 / ti1），前端可据此联动盘口。
    """
    if period not in PERIODS:
        raise ValueError(f'不支持的周期：{period}，可选 {PERIODS}')
    mask = np.ones(td.count, dtype=bool) if not day else (td.day == day)
    idx = np.nonzero(mask)[0]
    if len(idx) == 0:
        return {'bars': [], 'period': period}

    ts = td.ts[idx]
    price = td.price[idx]
    vol = td.vol[idx]
    money = td.money[idx]
    pos = td.position[idx]
    days = td.day[idx]

    if period == 1440:
        key_days = days
        # 日线的 key 是交易日字符串；用 factorize 保持出现顺序
        codes, uniques = pd.factorize(key_days)
        keys = codes
        labels = [str(u) for u in uniques]
    else:
        step = period * 60_000
        bucket = (ts // step) * step
        # 同一个 bucket 内如果跨交易日（理论上只会出现在 60 分钟线跨夜盘边界），按 (交易日, bucket) 分开
        key_df = pd.DataFrame({'d': days, 'b': bucket})
        codes, uniques = pd.factorize(pd.MultiIndex.from_frame(key_df))
        keys = codes
        labels = [fmt_ts(u[1])[:16] for u in uniques]

    # 逐组聚合（用 pandas groupby，tick 数量几十万量级也很快）
    g = pd.DataFrame({
        'k': keys, 'p': price, 'v': vol, 'm': money, 'pos': pos, 'i': idx, 'ts': ts, 'day': days,
    })
    grp = g.groupby('k', sort=True)
    first = grp.first()
    last = grp.last()
    agg = grp.agg(high=('p', 'max'), low=('p', 'min'), volume=('v', 'sum'), money=('m', 'sum'))
    sizes = grp.size()

    bars = []
    for k in agg.index:
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
        })
    return {'bars': bars, 'period': period}


# ---------------------------------------------------------------------------
# 历史盘口
# ---------------------------------------------------------------------------
def _tick_book(td: TickData, i: int) -> dict:
    asks = [{'level': n + 1, 'price': _clean(td.ask_p[n][i]), 'volume': _clean(td.ask_v[n][i])}
            for n in range(td.levels)]
    bids = [{'level': n + 1, 'price': _clean(td.bid_p[n][i]), 'volume': _clean(td.bid_v[n][i])}
            for n in range(td.levels)]
    return {
        'index': int(i),
        'ts': int(td.ts[i]),
        'time': fmt_ts(td.ts[i], with_ms=True),
        'day': str(td.day[i]),
        'price': _clean(td.price[i]),
        'volume': _clean(td.vol[i]),
        'cumVolume': _clean(td.cum_vol[i]),
        'position': _clean(td.position[i]),
        # 卖盘从远到近排列（卖5在上、卖1在下），买盘从近到远（买1在上），符合盘口显示习惯
        'asks': asks,
        'bids': bids,
    }


def find_tick_index(td: TickData, ts: int = None, index: int = None) -> int:
    """按毫秒时间戳（取 <= ts 的最近一笔，早于首笔则取首笔）或 tick 序号定位。"""
    if index is not None:
        return int(min(max(index, 0), td.count - 1))
    pos = int(np.searchsorted(td.ts, ts, side='right')) - 1
    return int(min(max(pos, 0), td.count - 1))


def book_at(td: TickData, ts: int = None, index: int = None) -> dict:
    return _tick_book(td, find_tick_index(td, ts, index))


def ticks_range(td: TickData, start_index: int, count: int = 200) -> list:
    """返回从 start_index 开始的 count 笔 tick（含盘口），用于前端回放预取。"""
    start = int(min(max(start_index, 0), max(td.count - 1, 0)))
    end = int(min(start + max(count, 1), td.count))
    return [_tick_book(td, i) for i in range(start, end)]


def summary(td: TickData) -> dict:
    return {
        'symbol': td.symbol,
        'name': td.name,
        'tickCount': td.count,
        'levels': td.levels,
        'days': td.days,
        'start': fmt_ts(td.ts[0], True),
        'end': fmt_ts(td.ts[-1], True),
        'warnings': td.warnings,
    }
