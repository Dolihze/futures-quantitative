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
    'time': ['time', 'datetime', 'timestamp', 'date_time', 'tradetime', 'tradingtime', 'trading_time',
             '时间', '日期时间', '成交时间'],
    'price': ['current', 'last', 'lastprice', 'last_price', 'price', 'close', '最新价', '现价', '当前价'],
    'open': ['open', 'openprice', '开盘价', '今开'],
    'high': ['high', 'highprice', 'highestprice', '最高价', '最高'],
    'low': ['low', 'lowprice', 'lowestprice', '最低价', '最低'],
    'volume': ['volume', 'vol', '成交量', '总量'],
    'money': ['money', 'turnover', 'amount', '成交额', '成交金额'],
    'position': ['position', 'openinterest', 'open_interest', 'oi', '持仓量', '持仓'],
    'symbol': ['symbol', 'code', 'instrument', 'instrumentid', 'instrument_id', '合约', '合约代码'],
    'name': ['name', '名称', '合约名称'],
    # 每笔成交性质：多开 / 空开 / 多平 / 空平 / 双开 / 双平 / 多换 / 空换
    'bs': ['bs', 'bstype', 'direction', 'tradetype', '成交性质', '性质', '方向', '开平'],
}

# 成交性质 -> 简称。K 线聚合时统计每根 K 线里各类成交的笔数 / 手数。
# 识别方式：文字里同时含「多/空/双」+「开/平/换」；也兼容 BO/SO/BC/SC 这类英文缩写。
_BS_CODES = {'BO': '多开', 'SO': '空开', 'BC': '多平', 'SC': '空平', 'BE': '多换', 'SE': '空换',
             'DO': '双开', 'DC': '双平'}


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
    bs: np.ndarray = None     # 每笔成交性质（'多开' / '空开' / '多平' / '空平' ...，object 数组；没有 BS 列时为 None）
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


def _parse_time(series: pd.Series) -> pd.Series:
    """把 time 列解析为 datetime64。无法解析的行为 NaT，由调用方丢弃。

    支持：
    - 纯数字 YYYYMMDDHHMMSSmmm（17 位）/ 14 位 / 12 位；
    - 带分隔符的字符串，且【同一列允许混合格式】：'2026-9-17 8:59'（Excel 另存的不补零、不带秒）、
      '2026-9-17 8:59:03'、'2026/9/17 21:00:01'、'2026-09-17 09:00:00.500' 等。
      pandas 默认按第一行推断格式，其余行会变 NaT 被误丢，所以必须用 format='mixed'。
    """
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
        try:
            parsed = pd.to_datetime(s[rest], format='mixed', errors='coerce')
        except (TypeError, ValueError):   # 老版本 pandas 没有 format='mixed'
            parsed = pd.to_datetime(s[rest], errors='coerce')
        out.loc[rest] = parsed.astype('datetime64[ns]')
    return out


def _trading_day(dt: pd.Series) -> pd.Series:
    """交易日：>= 20:00 的夜盘算下一个自然日；落在周六/周日的再顺延到周一。"""
    shifted = dt + pd.to_timedelta((dt.dt.hour >= 20).astype(int), unit='D')
    dow = shifted.dt.dayofweek  # 周六 5、周日 6
    shifted = shifted + pd.to_timedelta(np.where(dow == 5, 2, np.where(dow == 6, 1, 0)), unit='D')
    return shifted.dt.strftime('%Y-%m-%d')


def _normalize_bs(series: pd.Series) -> np.ndarray:
    """把成交性质列规范成 '多开' / '空开' / '多平' / '空平' / '双开' / '双平' / '多换' / '空换'；认不出的置空串。"""
    out = []
    for raw in series.astype(str).str.strip():
        v = ''
        up = raw.upper()
        if up in _BS_CODES:
            v = _BS_CODES[up]
        else:
            side = next((c for c in '多空双' if c in raw), '')
            act = next((c for c in '开平换' if c in raw), '')
            if side and act:
                v = side + act
        out.append(v)
    return np.array(out, dtype=object)


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(',', '').str.strip(), errors='coerce')


def _diff_cumulative(values: np.ndarray, days: np.ndarray, first_is_partial: bool = False):
    """把【当日累计】序列按交易日差分成增量（向量化）。

    - 交易日内回退（< 前值）视为重置，把当前值本身当增量。
    - 每个交易日第一笔：默认增量 = 累计值本身（文件从开盘开始截取时成立）。
      first_is_partial=True 时，【整个文件】最开头那一笔增量记 0：文件是中途截取的，
      第一行的累计值包含了文件之前的成交，不能算进这根 K 线（否则首根 K 线成交量会虚高几万手）。
      后面的交易日仍按「开盘第一笔 = 累计值」处理，因为那是真正的开盘。
    """
    v = np.nan_to_num(values.astype(float), nan=0.0)
    prev = np.concatenate(([0.0], v[:-1]))
    # 交易日切换处，前值清零
    new_day = np.concatenate(([True], days[1:] != days[:-1]))
    prev = np.where(new_day, 0.0, prev)
    inc = np.where(v >= prev, v - prev, v)
    if first_is_partial and len(inc):
        inc[0] = 0.0
    return inc


def _starts_mid_session(dt: pd.Series, cum_vol: np.ndarray) -> bool:
    """文件是否从交易时段中途开始（此时第一行的累计成交量包含了文件之前的成交，不能算进首根 K 线）。

    只有同时满足两个条件才判定为中途截取：
    1. 第一笔 tick 的累计成交量 > 0，且远大于后续相邻两笔的最大增量（> 20 倍）——
       真正从开盘开始的文件，首笔累计值和后面几笔的增量是同一量级；
    2. 第一笔的时间不是「开盘后的头几分钟」。日盘 09:00 / 夜盘 21:00 / 09:30(金融) 之后 2 分钟内，
       首笔累计值可能就是集合竞价撮合量，属于正常开盘，不算中途。
    例：首笔 08:59、累计 71845，而后面每笔增量只有几十到一百多手——说明文件是从夜盘 / 集合竞价
    之后截取的，首笔 71845 手是之前成交的累计，判定为中途，首笔增量记 0。
    """
    if len(cum_vol) < 3 or not np.isfinite(cum_vol[0]) or cum_vol[0] <= 0:
        return False
    d = np.diff(np.nan_to_num(cum_vol[:2000]))
    d = d[d > 0]
    if len(d) == 0:
        return False
    if not cum_vol[0] > d.max() * 20:
        return False
    t = dt.iloc[0]
    minutes = t.hour * 60 + t.minute
    # 开盘后 2 分钟内：日盘 09:00 / 夜盘 21:00 / 股指期货 09:30 / 国债 09:15，首笔累计值多半就是开盘撮合量
    open_minutes = (9 * 60, 9 * 60 + 15, 9 * 60 + 30, 21 * 60)
    if any(0 <= minutes - m <= 2 for m in open_minutes):
        return False
    return True


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

    # 累计值 -> 增量。如果整列单调不减就是累计值；若频繁回退（>= 5% 的行）更像是单笔增量，直接使用并提示。
    # 文件从盘中截取时第一笔的成交量按 0 处理（不提示用户，见 _diff_cumulative）
    partial_start = _starts_mid_session(dt, cum_vol)
    vol_inc = _diff_cumulative(cum_vol, days, first_is_partial=partial_start)
    drops = int((np.diff(np.nan_to_num(cum_vol)) < 0).sum())
    # 每个交易日开始都会合法回退一次，所以阈值以“交易日数 + 5% 行数”为准
    if len(cum_vol) > 50 and drops > len(set(days)) + len(cum_vol) * 0.05:
        warnings.append('成交量不是单调递增，疑似单笔增量而非当日累计，已按增量直接使用')
        vol_inc = np.nan_to_num(cum_vol)
    money_inc = _diff_cumulative(cum_money, days, first_is_partial=partial_start) if cum_money.any() \
        else np.zeros(len(df))

    levels = _detect_levels(columns)
    ask_p, ask_v, bid_p, bid_v = [], [], [], []
    for ap, av, bp, bv in levels:
        ask_p.append(_to_num(df[ap]).to_numpy(dtype=float))
        ask_v.append(_to_num(df[av]).to_numpy(dtype=float))
        bid_p.append(_to_num(df[bp]).to_numpy(dtype=float))
        bid_v.append(_to_num(df[bv]).to_numpy(dtype=float))
    if not levels:
        warnings.append('没有识别到盘口列（a1_p / a1_v / b1_p / b1_v ...），只能看 K 线')

    c_bs = _find_col(columns, 'bs')
    bs = _normalize_bs(df[c_bs]) if c_bs else None

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
        bs=bs,
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
def _group_ticks(td: TickData, period: int, day: str = None):
    """把 tick 分配到 K 线：返回 (idx, keys, labels)。

    idx：参与聚合的 tick 序号（按 day 过滤后）；keys：每个 tick 所属 K 线的组号（与 idx 等长）；
    labels：组号 -> K 线时间文字。build_kline 和 build_footprint 共用，保证两者的 K 线完全一致。
    """
    if period not in PERIODS:
        raise ValueError(f'不支持的周期：{period}，可选 {PERIODS}')
    mask = np.ones(td.count, dtype=bool) if not day else (td.day == day)
    idx = np.nonzero(mask)[0]
    if len(idx) == 0:
        return idx, np.array([], dtype=np.int64), []

    ts = td.ts[idx]
    days = td.day[idx]
    if period == 1440:
        # 日线的 key 是交易日字符串；用 factorize 保持出现顺序
        codes, uniques = pd.factorize(days)
        labels = [str(u) for u in uniques]
    else:
        step = period * 60_000
        bucket = (ts // step) * step
        # 同一个 bucket 内如果跨交易日（理论上只会出现在 60 分钟线跨夜盘边界），按 (交易日, bucket) 分开
        key_df = pd.DataFrame({'d': days, 'b': bucket})
        codes, uniques = pd.factorize(pd.MultiIndex.from_frame(key_df))
        labels = [fmt_ts(u[1])[:16] for u in uniques]
    return idx, codes, labels


def _clean_list(values: np.ndarray) -> list:
    """一整列数值 -> JSON 友好的 python 值列表，和逐个调用 _clean 的结果完全一致（但快得多）。

    NaN -> None；整数值（且绝对值 < 1e15）-> int；其余 round(x, 6)。
    """
    a = np.asarray(values, dtype=float)
    nan = np.isnan(a)
    is_int = (~nan) & (a == np.floor(a)) & (np.abs(a) < 1e15)
    ints = np.where(is_int, a, 0.0).astype(np.int64).tolist()
    nan_l, int_l, raw = nan.tolist(), is_int.tolist(), a.tolist()
    # 小数用内置 round，不能用 np.round：两者在恰好落在舍入边界的数上结果不同
    # （如 0.1234575：内置 round -> 0.123457，np.round -> 0.123458），换了会悄悄改变输出的数值
    return [None if nan_l[i] else (ints[i] if int_l[i] else round(raw[i], 6)) for i in range(len(raw))]


def build_kline(td: TickData, period: int = 1, day: str = None) -> dict:
    """由 tick 聚合 K 线。

    period：分钟数（1 / 5 / 15 / 30 / 60）或 1440（日线）。
    day：只取某个交易日（YYYY-MM-DD）；None = 全部交易日（日线时建议 None）。

    K 线的时间边界按“日历分钟”向下取整（9:00:00~9:00:59 -> 09:00）；5 分钟以上按
    自然整点对齐（9:00、9:05 …）。夜盘不特殊处理，同一个交易日里按真实时间连续排列。
    每根 bar 额外带 first/last tick 序号（ti0 / ti1），前端可据此联动盘口。

    实现是整列向量化：先用 pandas groupby 一次性算出每根 K 线的各项统计，再把每一列整体转成 python 列表、
    按列拼成 bar 字典；不再逐根逐字段取值。结果与旧的逐根组装版本逐字段、逐类型一致
    （tests/kline_reference.py 保留了旧实现作对照）。
    """
    idx, keys, labels = _group_ticks(td, period, day)
    if len(idx) == 0:
        return {'bars': [], 'period': period}

    vol = td.vol[idx]
    # 每个 tick 属于第几根 K 线（keys 是 0..n-1 连续的组号，按出现顺序编号）；bar 按组号升序，和 groupby(sort=True) 一致
    g = pd.DataFrame({
        'k': keys, 'p': td.price[idx], 'v': vol, 'm': td.money[idx], 'pos': td.position[idx],
        'i': idx, 'ts': td.ts[idx], 'day': td.day[idx],
    })
    grp = g.groupby('k', sort=True)
    first = grp.first()
    last = grp.last()
    agg = grp.agg(high=('p', 'max'), low=('p', 'min'), volume=('v', 'sum'), money=('m', 'sum'))
    sizes = grp.size()
    bar_keys = agg.index.to_numpy()

    # 每根 K 线里各类成交性质的手数：{'多开': 手数, ...}（没有 BS 列就不带 bs 字段，bs 为 None）
    bs_col = None
    if td.bs is not None:
        bg = pd.DataFrame({'k': keys, 'bs': td.bs[idx], 'v': vol})
        bg = bg[bg['bs'] != '']
        # 一次 groupby 搞定所有 K 线，不再每根单独算。sort=True：每根 K 线里 bs 的键按成交性质文字排序，
        # 和旧实现（逐根 sub.groupby('bs')，默认排序）的键顺序一致，JSON 输出逐字节相同
        per = bg.groupby(['k', 'bs'], sort=True)['v'].sum()
        by_bar = {}
        for (k, name), v in zip(per.index.tolist(), _clean_list(per.to_numpy())):
            by_bar.setdefault(k, {})[name] = v
        bs_col = [by_bar.get(k, {}) for k in bar_keys.tolist()]

    n = len(bar_keys)
    cols = {
        'time': [labels[k] for k in bar_keys.tolist()],
        'day': first['day'].tolist(),
        'open': _clean_list(first['p'].to_numpy()),
        'high': _clean_list(agg['high'].to_numpy()),
        'low': _clean_list(agg['low'].to_numpy()),
        'close': _clean_list(last['p'].to_numpy()),
        'volume': _clean_list(agg['volume'].to_numpy()),
        'money': _clean_list(agg['money'].to_numpy()),
        'position': _clean_list(last['pos'].to_numpy()),
        'ts0': first['ts'].astype(np.int64).tolist(),
        'ts1': last['ts'].astype(np.int64).tolist(),
        'ti0': first['i'].astype(np.int64).tolist(),
        'ti1': last['i'].astype(np.int64).tolist(),
        'ticks': sizes.astype(np.int64).tolist(),
        'bs': bs_col if bs_col is not None else [None] * n,
    }
    names = list(cols)
    bars = [dict(zip(names, row)) for row in zip(*cols.values())]
    return {'bars': bars, 'period': period}

# ---------------------------------------------------------------------------
# 足迹图：每根 K 线内每个价位的主动买 / 主动卖成交量 + 大单
# ---------------------------------------------------------------------------
DEFAULT_BIG_ORDER = 100   # 大单阈值默认值（手）：单笔 tick 的成交量增量 >= 它就算大单

# 成交性质 -> 主动方向。买方主动：多开（买入开多）、空平（买入平空）；
# 卖方主动：空开（卖出开空）、多平（卖出平多）。其余（双开 / 双平 / 多换 / 空换 / 认不出）方向不明，计入「中性」
_BUY_BS = ('多开', '空平')
_SELL_BS = ('空开', '多平')


def _side_of(bs: np.ndarray) -> np.ndarray:
    """成交性质 -> 方向：1 = 买方主动，-1 = 卖方主动，0 = 方向不明。"""
    side = np.zeros(len(bs), dtype=np.int8)
    side[np.isin(bs, _BUY_BS)] = 1
    side[np.isin(bs, _SELL_BS)] = -1
    return side


def build_footprint(td: TickData, period: int = 1, day: str = None, big_order: int = DEFAULT_BIG_ORDER) -> dict:
    """足迹图数据：K 线（同 build_kline）+ 每根 K 线里每个价位的买 / 卖 / 中性成交量 + 大单列表。

    - 一笔 tick 的成交量增量整笔算在它的最新价上（tick 只有一个最新价，半秒内跨价位的成交无法拆开，是近似）。
    - 每个价位：buy = 买方主动手数，sell = 卖方主动手数，neutral = 方向不明手数。
    - 大单：成交量增量 >= big_order 的单笔 tick；返回所在 K 线序号、价位、手数、方向、tick 序号。
      阈值只影响大单列表，不影响价位成交量，所以前端调阈值时不需要重新取价位数据（但这里仍支持传参，方便单独取）。
    - 没有 BS 列的数据无法判断方向：抛 ValueError，由接口返回可读提示。
    """
    if td.bs is None:
        raise ValueError('这个文件没有成交性质（BS）列，无法区分买卖方向，不能生成足迹图')
    if big_order < 1:
        raise ValueError('大单阈值必须 >= 1 手')

    kl = build_kline(td, period, day)
    bars = kl['bars']
    if not bars:
        return {'bars': [], 'period': period, 'bigOrders': [], 'bigOrder': big_order, 'tickSize': None}

    # 与 build_kline 用同一套分组：keys 的组号就是 bars 的序号（groupby sort=True 且组号从 0 连续递增）
    idx, bi_arr, _ = _group_ticks(td, period, day)
    price = td.price[idx]
    vol = td.vol[idx]
    side = _side_of(td.bs[idx])

    # 价位用整数 * 价格最小变动单位换算，避免浮点 key 不一致：这里直接用四舍五入到 1e-6 的价格作为 key
    df = pd.DataFrame({
        'b': bi_arr,
        'p': np.round(price, 6),
        'buy': np.where(side == 1, vol, 0.0),
        'sell': np.where(side == -1, vol, 0.0),
        'neu': np.where(side == 0, vol, 0.0),
    })
    agg = df.groupby(['b', 'p'], sort=True).sum()

    levels_by_bar = {}
    for (b, p), row in agg.iterrows():
        levels_by_bar.setdefault(int(b), []).append({
            'price': _clean(p), 'buy': _clean(row['buy']), 'sell': _clean(row['sell']), 'neutral': _clean(row['neu']),
        })

    for bi, b in enumerate(bars):
        b['levels'] = levels_by_bar.get(bi, [])   # 价位按价格从低到高

    # 大单：增量 >= 阈值的单笔 tick
    big_mask = vol >= big_order
    big = []
    for j in np.nonzero(big_mask)[0]:
        ti = int(idx[j])
        big.append({
            'bar': int(bi_arr[j]), 'index': ti,
            'price': _clean(price[j]), 'volume': _clean(vol[j]),
            'side': int(side[j]), 'bs': str(td.bs[ti]) or None,
            'time': fmt_ts(td.ts[ti], with_ms=False),
        })

    # 最小价位间隔（足迹图每格的高度）：取所有出现过的价位相邻差的最小值
    prices = np.unique(np.round(price, 6))
    tick_size = None
    if len(prices) >= 2:
        diffs = np.diff(prices)
        diffs = diffs[diffs > 1e-9]
        if len(diffs):
            tick_size = _clean(diffs.min())

    return {'bars': bars, 'period': period, 'bigOrders': big, 'bigOrder': big_order, 'tickSize': tick_size}


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
        'bs': str(td.bs[i]) if td.bs is not None and td.bs[i] else None,   # 这一笔的成交性质（多开 / 空平 ...）
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
        'hasBs': td.bs is not None,
        'warnings': td.warnings,
    }


# ---------------------------------------------------------------------------
# 多文件合并：同一个合约的多个 CSV（比如每个交易日一个文件）合成一条时间线
# ---------------------------------------------------------------------------
def merge(parts: list) -> TickData:
    """把同一合约的多份 TickData 按时间合并。

    重要：成交量增量（vol）是每个文件【单独】差分得到的，这里只拼接已经算好的数组，
    绝不能先拼 cum_vol 再差分——每个文件的首笔处理（盘中截取判断、交易日开盘重置）是文件内的事，
    合在一起差分会把相邻文件的首尾错误地相减。

    重叠处理：两个文件覆盖了同一个交易日时（比如重复下载、一个是全天一个是片段），
    同一交易日只保留 tick 数更多的那个文件的数据，并在 warnings 里提示，避免同一天的 K 线成交量翻倍。
    """
    if not parts:
        raise DepthParseError('没有可合并的数据')
    if len(parts) == 1:
        return parts[0]

    # 每个交易日只取一个来源：tick 最多的文件；并列取靠前的（调用方按文件名排序，结果稳定）
    best = {}
    for pi, p in enumerate(parts):
        for d, n in zip(*np.unique(p.day.astype(str), return_counts=True)):
            if d not in best or n > best[d][1]:
                best[d] = (pi, int(n))
    warnings = []
    for p in parts:
        warnings.extend(p.warnings)
    dup_days = sorted({d for pi, p in enumerate(parts) for d in set(p.day.astype(str)) if best[d][0] != pi})
    if dup_days:
        warnings.append(f'{len(dup_days)} 个交易日在多个文件里重复出现（{dup_days[0]}'
                        f'{"…" if len(dup_days) > 1 else ""}），每个交易日只保留 tick 最多的那个文件的数据')

    keep = []   # 每个文件保留的 tick 掩码
    for pi, p in enumerate(parts):
        keep.append(np.array([best[str(d)][0] == pi for d in p.day], dtype=bool))

    levels = min(p.levels for p in parts)
    if len({p.levels for p in parts}) > 1:
        warnings.append(f'各文件的盘口档数不一致，合并后只保留 {levels} 档')
    has_bs = all(p.bs is not None for p in parts)
    if not has_bs and any(p.bs is not None for p in parts):
        warnings.append('部分文件没有 BS 列，合并后无法生成足迹图')

    def cat(getter):
        return np.concatenate([getter(p)[k] for p, k in zip(parts, keep)])

    ts = cat(lambda p: p.ts)
    order = np.argsort(ts, kind='stable')   # 稳定排序：时间相同的 tick 保持「文件顺序 + 文件内顺序」

    def srt(a):
        return a[order]

    merged = TickData(
        ts=srt(ts),
        price=srt(cat(lambda p: p.price)),
        vol=srt(cat(lambda p: p.vol)),
        cum_vol=srt(cat(lambda p: p.cum_vol)),
        money=srt(cat(lambda p: p.money)),
        position=srt(cat(lambda p: p.position)),
        day=srt(cat(lambda p: p.day)),
        bs=srt(np.concatenate([p.bs[k] for p, k in zip(parts, keep)])) if has_bs else None,
        ask_p=[srt(np.concatenate([p.ask_p[n][k] for p, k in zip(parts, keep)])) for n in range(levels)],
        ask_v=[srt(np.concatenate([p.ask_v[n][k] for p, k in zip(parts, keep)])) for n in range(levels)],
        bid_p=[srt(np.concatenate([p.bid_p[n][k] for p, k in zip(parts, keep)])) for n in range(levels)],
        bid_v=[srt(np.concatenate([p.bid_v[n][k] for p, k in zip(parts, keep)])) for n in range(levels)],
        symbol=parts[0].symbol,
        name=next((p.name for p in parts if p.name), ''),
        warnings=warnings,
    )
    merged.days = sorted(set(merged.day.tolist()))
    return merged


def canonical_name(content: bytes, filename: str = '', ext: str = '.csv', meta: dict = None) -> str:
    """读取文件内部数据（合约代码 + 交易日），返回规范文件名「合约名_YYYYMMDD.csv」。

    日期取文件内的【交易日】（夜盘归下一交易日，与图表一致）；一个文件含多个交易日时写成
    「合约名_YYYYMMDD-YYYYMMDD.csv」（最早-最晚）。解析失败抛 DepthParseError。
    调用方已经算过 peek_meta 时通过 meta 传入，避免把同一份内容再解析一遍。
    """
    if meta is None:
        meta = peek_meta(content, filename)
    days = meta['days']
    first = days[0].replace('-', '')
    last = days[-1].replace('-', '')
    date_part = first if first == last else f'{first}-{last}'
    symbol = re.sub(r'[\\/:*?"<>|\s]+', '', str(meta['symbol'])) or '未知合约'
    return f'{symbol}_{date_part}{ext}'


def peek_meta(content: bytes, filename: str = '') -> dict:
    """只读文件的合约代码 / 交易日 / tick 数 / 时间范围，不做完整解析（给「数据库管理」的合约索引用）。

    和 parse 用同一套列识别和时间解析，所以结论一致；但跳过成交量差分、盘口、BS 等较重的步骤。
    无法识别的文件抛 DepthParseError。
    """
    df = _read_csv(content)
    if df.empty:
        raise DepthParseError('文件里没有数据行')
    columns = {_norm(c): c for c in df.columns}
    c_time = _find_col(columns, 'time')
    c_price = _find_col(columns, 'price')
    if c_time is None or c_price is None:
        raise DepthParseError('缺少时间或最新价列')
    dt = _parse_time(df[c_time])
    ok = dt.notna() & (_to_num(df[c_price]) > 0)
    if not ok.any():
        raise DepthParseError('没有可用的 tick')
    dt = dt[ok].reset_index(drop=True)
    days = _trading_day(dt)
    c_sym = _find_col(columns, 'symbol')
    c_name = _find_col(columns, 'name')
    symbol = str(df[c_sym].iloc[0]).strip() if c_sym else ''
    if not symbol:
        symbol = re.sub(r'\.[^.]+$', '', filename or '') or '未知合约'
    return {
        'symbol': symbol,
        'name': str(df[c_name].iloc[0]).strip() if c_name else '',
        'tickCount': int(ok.sum()),
        'days': sorted(set(days.tolist())),
        'start': fmt_ts(int(dt.min().value // 1_000_000), True),
        'end': fmt_ts(int(dt.max().value // 1_000_000), True),
        'hasBs': _find_col(columns, 'bs') is not None,
        'levels': len(_detect_levels(columns)),
    }
