"""交易复盘：解析期货公司导出的交易记录 Excel，并生成累计平仓盈亏曲线。

只依赖 pandas / openpyxl / xlrd，不依赖 Flask，便于单独测试。

口径：
  - 曲线 Y 轴 = 累计平仓盈亏（可选扣除手续费）。
  - Excel 中有“平仓盈亏”列时直接使用；没有则按“合约 + 先进先出”自行配对开平仓计算。
  - 交易品种 = 合约代码去掉交割月份后的品种代码（FU2611 -> FU）。
"""
from __future__ import annotations

import io
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------
# 列名别名（全部转成小写、去空白后比较）
# ---------------------------------------------------------------------------
COLUMN_ALIASES: dict[str, list[str]] = {
    "datetime": ["成交时间", "交易时间", "时间", "日期时间", "委托时间", "datetime", "time"],
    "date": ["成交日期", "实际成交日期", "交易日期", "交易日", "日期", "date", "tradingday"],
    "symbol": ["合约", "合约代码", "合约名称", "品种", "品种合约", "instrument", "symbol", "contract"],
    "direction": ["买卖", "买/卖", "买卖方向", "方向", "buy/sell", "direction", "side"],
    "offset": ["开平", "开/平", "开平仓", "开平标志", "offset", "openclose"],
    "price": ["成交价", "成交价格", "价格", "成交均价", "price"],
    "volume": ["手数", "成交量", "成交手数", "数量", "volume", "qty", "lots"],
    "fee": ["手续费", "费用", "交易费用", "commission", "fee"],
    "pnl": ["平仓盈亏", "盈亏", "实现盈亏", "平仓盈亏(盯市)", "closeprofit", "realizedpnl", "pnl", "profit"],
    # 成交序号：同一时刻的多笔成交靠它还原先后顺序
    "seq": ["成交序号", "序号", "流水号", "tradeid"],
}

# 结算单里逐笔成交的 sheet 名（列：合约、成交序号、成交时间、买/卖、投机/套保/套利、成交价、手数、成交额、
# 开/平、手续费、平仓盈亏、实际成交日期）。命中后优先使用；其余名字的表按“表头能识别”兜底。
DETAIL_SHEET_NAMES = ["成交明细", "成交明细表", "成交记录", "transactionrecord"]

# 一个合约一手对应的交易单位（吨 / 手…），用于没有“平仓盈亏”列时自行计算。
# 未收录的品种按 10 处理，并在结果的 warnings 里提示。
CONTRACT_MULTIPLIER: dict[str, int] = {
    # 上期所
    "CU": 5, "AL": 5, "ZN": 5, "PB": 5, "NI": 1, "SN": 1, "AU": 1000, "AG": 15,
    "RB": 10, "HC": 10, "SS": 5, "FU": 10, "BU": 10, "RU": 10, "SP": 10, "NR": 10,
    "LU": 10, "BC": 5, "AO": 20, "SC": 1000,
    # 大商所
    "A": 10, "B": 10, "M": 10, "Y": 10, "P": 10, "C": 10, "CS": 10, "JD": 10, "L": 5,
    "V": 5, "PP": 5, "EB": 5, "EG": 10, "PG": 20, "I": 100, "J": 100, "JM": 60, "LH": 16,
    "RR": 10, "FB": 10, "BB": 500,
    # 郑商所
    "CF": 5, "SR": 10, "TA": 5, "MA": 10, "FG": 20, "RM": 10, "OI": 10, "ZC": 100,
    "SA": 20, "UR": 20, "PF": 5, "AP": 10, "CJ": 5, "PK": 5, "SF": 5, "SM": 5,
    "CY": 5, "WH": 20, "PM": 50, "RI": 20, "LR": 20, "JR": 20, "RS": 10, "SH": 30, "PX": 5,
    # 中金所（点值）
    "IF": 300, "IH": 300, "IC": 200, "IM": 200, "TS": 20000, "TF": 10000, "T": 10000, "TL": 10000,
}
DEFAULT_MULTIPLIER = 10


class ReviewParseError(ValueError):
    """Excel 无法识别时抛出，message 可直接展示给用户。"""


def _norm(text) -> str:
    return re.sub(r"\s+", "", str(text)).lower()


def product_code(symbol: str) -> str:
    """FU2611 -> FU；fu2611 -> FU；沪铜2601 -> 沪铜；SHFE.fu2611 -> FU。"""
    s = str(symbol).strip()
    if "." in s:
        s = s.split(".")[-1]
    m = re.match(r"^([A-Za-z\u4e00-\u9fa5]+)", s)
    code = m.group(1) if m else s
    return code.upper() if code.isascii() else code


# ---------------------------------------------------------------------------
# 读取 Excel
# ---------------------------------------------------------------------------
def _find_header_row(raw: pd.DataFrame) -> tuple[int, dict[str, int]]:
    """在前 30 行里找“命中已知列名最多”的一行作为表头（很多导出文件顶部带标题/账户信息）。"""
    best_row, best_map = -1, {}
    for i in range(min(30, len(raw))):
        mapping: dict[str, int] = {}
        for col_idx, cell in enumerate(raw.iloc[i].tolist()):
            if pd.isna(cell):
                continue
            n = _norm(cell)
            for field_name, aliases in COLUMN_ALIASES.items():
                if field_name in mapping:
                    continue
                if n in [_norm(a) for a in aliases]:
                    mapping[field_name] = col_idx
                    break
        if len(mapping) > len(best_map):
            best_row, best_map = i, mapping
    return best_row, best_map


_TIME_ONLY = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")

# 结算单里的「实际成交日期」是**交易日**，不是成交真正发生的日历日期：
# 夜盘（前一天晚上 21:00 起）的成交，日期也写成它所属的那个交易日。例如交易日 10-16 的所有行都标 10-16，
# 但 21:00~23:00 那批实际发生在 10-15 晚上，其余（凌晨 00:00~03:00、09:00~15:00）才是 10-16 当天。
# 如果直接把表里的“日期 + 时间”当成真实时间，夜盘会被当成发生在交易日当天的晚上，既排序错（排到当天白天之后），
# 也会被后面的“夜盘属于下一个交易日”再加一天，凭空多出一个根本没有数据的交易日（已复现：多出 10-17）。
# 所以读文件时就把它还原成真实发生的时刻：晚上（>= NIGHT_RESTORE_HOUR）的成交日期往前挪一天。
# 之后排序、合并、画图一律用这个真实时刻，不再各自猜日期的含义。
NIGHT_RESTORE_HOUR = 20


def _restore_real_time(t: pd.Series) -> pd.Series:
    """表里标的是交易日；把晚上（>= 20:00）的夜盘成交还原成前一天的真实日期。凌晨和白天保持不变。"""
    is_night = t.notna() & (t.dt.hour >= NIGHT_RESTORE_HOUR)
    return t.where(~is_night, t - pd.Timedelta(days=1))


def _to_datetime(series: pd.Series) -> pd.Series:
    """宽松解析时间：Excel 里可能是 datetime 对象，也可能是字符串；解析不了的变成 NaT（如“合计”行）。"""
    # Excel 单元格里已经是 datetime 的直接用；其余转字符串逐个解析（format="mixed" 避免 pandas 的推断告警）
    return pd.to_datetime(series, errors="coerce", format="mixed")


def _parse_time(dt_col: pd.Series | None, date_col: pd.Series | None) -> pd.Series:
    """统一得到成交时间。

    支持三种常见布局：
      1. 只有一列完整的“成交时间”（2026-10-20 09:01:00）；
      2. 只有“日期”列；
      3. “成交日期”+“成交时间”两列，时间部分只有 HH:MM:SS，需要拼起来。
    """
    if dt_col is None:
        return _to_datetime(date_col.astype(str).str.strip())
    if date_col is not None:
        texts = dt_col.dropna().astype(str).str.strip()
        # 时间列里的有效值全是 HH:MM[:SS]，说明日期在另一列
        valid = texts[texts.ne("") & texts.ne("nan")]
        if len(valid) and valid.map(lambda s: bool(_TIME_ONLY.match(s))).mean() > 0.5:
            joined = date_col.astype(str).str.strip().str.slice(0, 10) + " " + dt_col.astype(str).str.strip()
            return _to_datetime(joined)
    return _to_datetime(dt_col)


def _load_sheets(file_bytes: bytes, filename: str) -> dict[str, pd.DataFrame]:
    """读出文件里的所有工作表（csv 只有一张）。键是 sheet 名，值是不带表头的原始 DataFrame。"""
    name = filename.lower()
    try:
        if name.endswith(".csv"):
            try:
                raw = pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=object, encoding="utf-8-sig")
            except UnicodeDecodeError:
                raw = pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=object, encoding="gbk")
            return {"": raw}
        return pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=object, sheet_name=None)
    except Exception as e:  # 文件损坏、格式不对、被加密等
        # pandas/openpyxl 的原始报错是英文技术描述，对用户没有帮助；原因写到后端日志里便于排查
        print(f"[Review] 读取文件失败: {type(e).__name__}: {e}")
        raise ReviewParseError(
            "无法读取文件：请确认它是未损坏、未加密的 .xlsx / .xls / .csv 文件"
            "（如果是从软件里导出的，可以先用 Excel 打开再另存为 .xlsx）"
        ) from e


def _missing_fields(cols: dict[str, int]) -> list[str]:
    """表头里还缺哪些必需的列（用于判断这张表能不能用，以及给用户的提示）。"""
    has_time = "datetime" in cols or "date" in cols
    missing = [] if has_time else ["成交时间"]
    missing += [label for key, label in
                (("symbol", "合约"), ("direction", "买卖方向"), ("price", "成交价"), ("volume", "手数"))
                if key not in cols]
    return missing


def _pick_sheet(sheets: dict[str, pd.DataFrame]):
    """从所有工作表里选出要解析的那一张。

    优先级：
      1. 名称属于“成交明细”一类（DETAIL_SHEET_NAMES）且表头能识别的表；
      2. 其余表里，第一张表头能识别（必需列齐全）的表。
    返回 (raw, sheet_name, header_row, cols)。
    """
    candidates = []
    for name, raw in sheets.items():
        if raw is None or raw.empty:
            continue
        header_row, cols = _find_header_row(raw)
        candidates.append((name, raw, header_row, cols))

    if not candidates:
        raise ReviewParseError("文件是空的")

    detail_names = {_norm(n) for n in DETAIL_SHEET_NAMES}
    ordered = sorted(candidates, key=lambda c: 0 if _norm(c[0]) in detail_names else 1)  # 稳定排序，其余保持原顺序
    for name, raw, header_row, cols in ordered:
        if header_row >= 0 and not _missing_fields(cols):
            return raw, name, header_row, cols

    # 没有一张表能用：报错时给出“最接近的那张表”的信息，方便用户对照
    name, raw, header_row, cols = max(ordered, key=lambda c: len(c[3]))
    found = "、".join(str(raw.iloc[header_row, i]) for i in cols.values()) if header_row >= 0 and cols else "无"
    where = f"（工作表「{name}」）" if name and len(sheets) > 1 else ""
    raise ReviewParseError(f"没有识别到必需的列：{'、'.join(_missing_fields(cols))}。已识别的列{where}：{found}")


def read_trades(file_bytes: bytes, filename: str = "") -> tuple[pd.DataFrame, list[str]]:
    """把 Excel/CSV 读成统一结构的 DataFrame。

    返回 (df, warnings)。df 列：time, symbol, product, direction(买/卖), offset(开/平/平今/平昨),
    price, volume, fee, pnl（pnl 为 NaN 表示文件里没有该列）。
    """
    warnings: list[str] = []
    sheets = _load_sheets(file_bytes, filename)
    raw, sheet_name, header_row, cols = _pick_sheet(sheets)
    if len(sheets) > 1:
        warnings.append(f"已读取工作表「{sheet_name}」")

    body = raw.iloc[header_row + 1:].reset_index(drop=True)

    def col(key):
        return body.iloc[:, cols[key]] if key in cols else None

    time = _restore_real_time(_parse_time(col("datetime") if "datetime" in cols else None,
                                          col("date") if "date" in cols else None))

    df = pd.DataFrame({
        "time": time,
        "symbol": col("symbol").astype(str).str.strip(),
        "direction": col("direction").astype(str).str.strip(),
        "price": pd.to_numeric(col("price"), errors="coerce"),
        "volume": pd.to_numeric(col("volume"), errors="coerce"),
    })
    df["offset"] = col("offset").astype(str).str.strip() if "offset" in cols else ""
    df["fee"] = pd.to_numeric(col("fee"), errors="coerce").fillna(0.0) if "fee" in cols else 0.0
    df["pnl"] = pd.to_numeric(col("pnl"), errors="coerce") if "pnl" in cols else float("nan")
    # 成交序号：同一时刻的多笔成交靠它还原先后顺序（可能是 "00012345" 这样的文本）
    df["seq"] = pd.to_numeric(col("seq"), errors="coerce") if "seq" in cols else float("nan")

    # 丢掉汇总行 / 空行：时间、合约、手数任一缺失
    before = len(df)
    df = df.dropna(subset=["time", "volume"])
    df = df[df["symbol"].ne("") & df["symbol"].ne("nan")]
    df = df[df["volume"] > 0]
    dropped = before - len(df)
    if dropped:
        warnings.append(f"已忽略 {dropped} 行无法识别的数据（空行、合计行等）")
    if df.empty:
        raise ReviewParseError("没有读取到有效的成交记录")
    # 曲线按“成交时间”聚合、按时间排列：如果所有记录都只有日期（时间全是 00:00:00），同一天的成交分不出先后，
    # 按成交时间合并会把不相干的成交并成一笔（已发生过：14 笔被并成 6 笔且没有任何提示）。
    # 与其给出看似正常但数字不对的结果，不如明确拒绝，并告诉用户要导出带成交时间的“成交明细”。
    if (df["time"] == df["time"].dt.normalize()).all():
        raise ReviewParseError(
            "文件里只有日期，没有具体的成交时间，无法按成交时间生成曲线。"
            "请导入带「成交时间」列的「成交明细」工作表（例如 21:30:05 这样的时分秒）。"
        )

    df["product"] = df["symbol"].map(product_code)
    df["direction"] = df["direction"].map(_norm_direction)
    df["offset"] = df["offset"].map(_norm_offset)
    df = _sort_by_session(df)
    if "pnl" not in cols:
        warnings.append("文件中没有“平仓盈亏”列，已按先进先出自行配对开平仓计算（仅供参考）")
    return df, warnings


# ---------------------------------------------------------------------------
# 按交易时段排序
# ---------------------------------------------------------------------------
# 排序要和横轴的顺序完全一致，累计盈亏才是沿着图从左到右累加的：
#   交易日 → 夜盘 → 早盘一 → 早盘二 → 午盘 → 下一个交易日 → ……
# 注意这和“按真实时间排序”不一样：10-15 晚上 22:30 的夜盘属于 10-16 交易日，要排在 10-15 白天的成交**之后**
# （10-15 的白天先于它发生），但它在轴上属于 10-16 的夜盘段、排在 10-16 白天之前。所以排序键是
# (交易日, 时段, 时间, 序号)，交易日和时段的判断用的就是横轴那套（trading_day / session_of），不再各写一遍。
def _sort_by_session(df: pd.DataFrame) -> pd.DataFrame:
    keyed = df.assign(
        _day=df["time"].map(trading_day),
        _sess=df["time"].map(session_of),
    )
    keyed = keyed.sort_values(["_day", "_sess", "time", "seq"], kind="stable", na_position="last")
    return keyed.drop(columns=["_day", "_sess"]).reset_index(drop=True)


def _norm_direction(v: str) -> str:
    s = _norm(v)
    if s in ("买", "买入", "buy", "b", "多", "long") or s.startswith("买"):
        return "买"
    if s in ("卖", "卖出", "sell", "s", "空", "short") or s.startswith("卖"):
        return "卖"
    return s


def _norm_offset(v: str) -> str:
    s = _norm(v)
    if s in ("", "nan", "none"):
        return ""
    if "平" in s or s in ("close", "closetoday", "closeyesterday", "c"):
        return "平"
    if "开" in s or s in ("open", "o"):
        return "开"
    return s


# ---------------------------------------------------------------------------
# 配对计算（当文件没有“平仓盈亏”列时）
# ---------------------------------------------------------------------------
def compute_pnl_by_pairing(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, list[str]]:
    """按合约先进先出配对开/平仓，返回 (每行的平仓盈亏, 每行是否为平仓, 提示)。开仓行盈亏为 0。

    平仓的方向是“反向”：买平 = 平空仓，卖平 = 平多仓。
    没有“开平”列时，按持仓方向推断：与当前持仓相反的成交视为平仓。
    """
    warnings: list[str] = []
    pnl = pd.Series(0.0, index=df.index)
    closes = pd.Series(False, index=df.index)
    long_q: dict[str, deque] = defaultdict(deque)   # symbol -> deque[[price, lots]]
    short_q: dict[str, deque] = defaultdict(deque)
    unknown_mult: set[str] = set()
    has_offset = (df["offset"] != "").any()

    for idx, row in df.iterrows():
        sym, price, lots, d = row["symbol"], float(row["price"]), float(row["volume"]), row["direction"]
        mult = CONTRACT_MULTIPLIER.get(row["product"])
        if mult is None:
            mult = DEFAULT_MULTIPLIER
            unknown_mult.add(row["product"])

        if has_offset:
            is_close = row["offset"] == "平"
        else:
            is_close = (d == "买" and bool(short_q[sym])) or (d == "卖" and bool(long_q[sym]))

        if not is_close:
            (long_q if d == "买" else short_q)[sym].append([price, lots])
            continue

        closes.at[idx] = True
        queue = short_q[sym] if d == "买" else long_q[sym]
        remaining, realized = lots, 0.0
        while remaining > 1e-9 and queue:
            open_price, open_lots = queue[0]
            matched = min(remaining, open_lots)
            if d == "买":   # 买平空：开空价 - 平仓价
                realized += (open_price - price) * matched * mult
            else:           # 卖平多：平仓价 - 开多价
                realized += (price - open_price) * matched * mult
            remaining -= matched
            queue[0][1] -= matched
            if queue[0][1] <= 1e-9:
                queue.popleft()
        if remaining > 1e-9:
            warnings.append(f"{sym} 有 {remaining:g} 手平仓找不到对应开仓（可能开仓在所选文件之前），这部分盈亏未计入")
        pnl.at[idx] = realized

    if unknown_mult:
        warnings.append(f"品种 {'、'.join(sorted(unknown_mult))} 未收录合约乘数，按 {DEFAULT_MULTIPLIER} 计算，盈亏金额可能不准")
    # 同一条提示可能重复出现，去重并保持顺序
    return pnl, closes, list(dict.fromkeys(warnings))


# ---------------------------------------------------------------------------
# 对外：汇总 + 曲线
# ---------------------------------------------------------------------------
@dataclass
class ReviewResult:
    records: pd.DataFrame
    products: list[str]
    start: str
    end: str
    warnings: list[str] = field(default_factory=list)
    # 文件里是否有手续费数据。没有时前端应禁用“扣除手续费”，而不是让它看起来生效了
    has_fee: bool = True
    # 文件里有成交的全部交易日（升序，YYYY-MM-DD）：当天 K 线视图的日期选择用
    days: list[str] = field(default_factory=list)


def analyze(file_bytes: bytes, filename: str = "") -> ReviewResult:
    """解析文件并给每笔成交补上 pnl（平仓盈亏），用于后续按条件筛选。"""
    df, warnings = read_trades(file_bytes, filename)
    if df["pnl"].isna().all():
        df["pnl"], df["is_close"], w = compute_pnl_by_pairing(df)
        warnings += w
    else:
        # 有平仓盈亏列：开仓行通常为空，按 0 处理
        df["pnl"] = df["pnl"].fillna(0.0)
        if (df["offset"] != "").any():
            # 有“开平”列：以它为准，这样盈亏恰好为 0 的平仓也能被算作一笔平仓
            df["is_close"] = df["offset"] == "平"
        else:
            # 没有“开平”列：只能认为有盈亏的行是平仓
            df["is_close"] = df["pnl"] != 0
    products = sorted(df["product"].unique().tolist())
    return ReviewResult(
        records=df,
        products=products,
        # 数据的起止给前端的日期选择器用，所以是**交易日**（和 Excel 的日期列一致）。
        # 不能给真实时间：夜盘还原到前一天后，最早的“日期”会变成 Excel 里根本不存在的那一天（10-14），
        # 选择器里就会出现一个文件里没有的日期
        start=df["time"].map(trading_day).min().strftime("%Y-%m-%d %H:%M:%S"),
        end=df["time"].map(trading_day).max().strftime("%Y-%m-%d %H:%M:%S"),
        warnings=list(dict.fromkeys(warnings)),
        has_fee=bool((df["fee"] != 0).any()),
        days=sorted(df["time"].map(trading_day).dt.strftime("%Y-%m-%d").unique().tolist()),
    )


def build_curve(records: pd.DataFrame, products: list[str] | None = None,
                start: str | None = None, end: str | None = None,
                include_fee: bool = True) -> dict:
    """按品种、时间范围筛选并生成累计盈亏曲线及统计。

    曲线点 = 每笔“产生平仓盈亏的成交”之后的累计值；起点补一个 0，方便看出从哪里开始。
    手续费开仓、平仓都产生，所以扣费时按每笔成交扣，而不只在平仓行扣。
    """
    df = records
    if products:
        df = df[df["product"].isin(products)]
    # 时间范围按**交易日**筛选，和 Excel 里「实际成交日期」是同一个语义。
    # 不能按真实时间筛：交易日 10-16 的夜盘真实发生在 10-15 晚上，按真实时间选“10-16 到 10-16”会漏掉它，
    # 少算这部分盈亏，和 Excel 里按 10-16 汇总的数字对不上（已复现：漏了 22:30 那笔 +200）。
    # 日期选择器只给到日，所以两端都按日期比较；非法日期仍抛 ValueError（接口返回 400）。
    if start or end:
        tday = df["time"].map(trading_day)
        if start:
            df = df[tday >= pd.to_datetime(start).normalize()]
            tday = tday.loc[df.index]
        if end:
            df = df[tday <= pd.to_datetime(end).normalize()]

    if df.empty:
        return {"points": [], "xs": [], "segments": [], "details": [], "stats": _empty_stats(), "trades": 0, "openMarks": []}
    df = _sort_by_session(df)

    # 曲线上只有“平”：开仓行不产生盈亏，也不算一笔成交。
    # 但开仓同样要付手续费，真实盈亏必须扣掉。开仓手续费记在“同一合约之后的第一笔平仓”上（那一刻才实现盈亏），
    # 这样曲线不会在最后凭空掉下去一截；后面没有平仓的开仓（仍持仓），其手续费计入最后一笔。
    df = df.assign(fee_charge=_attribute_fees(df))
    closes = df[df["is_close"]]
    if closes.empty:
        return {"points": [], "xs": [], "segments": [], "details": [], "stats": _empty_stats(), "trades": 0, "openOnly": True, "openMarks": []}

    trades = _merge_same_time(closes)
    # 开仓成交（同样按“时间+合约+买卖”合并）。它们不进 points/stats，只作为 openMarks 交给前端画在曲线上：
    # 开仓不产生盈亏，所以开仓那一刻曲线保持水平，直到平仓才动。
    opens = df[~df["is_close"]]
    open_trades = _merge_same_time(opens.assign(pnl=0.0, fee_charge=0.0)) if not opens.empty else opens
    fee_used = trades["fee_charge"] if include_fee else 0.0
    delta = trades["pnl"] - fee_used
    cum = delta.cumsum()

    # 起点（累计盈亏 0）放在第一笔平仓“之前一秒”，而不是和它同一时刻。
    # 同一时刻的话，两个点横坐标相同，鼠标悬停在这个位置永远只会命中起点，第一笔成交的信息就看不到了（已验证）。
    # 夜盘到凌晨 02:30，第一笔恰好在 00:00:00 时减一秒是前一天的 23:59:59，作为“之前”同样成立。
    first_time = trades["time"].iloc[0]
    start_time = first_time - pd.Timedelta(seconds=1)
    points = [[start_time.strftime("%Y-%m-%d %H:%M:%S"), 0.0]]
    points += [[t.strftime("%Y-%m-%d %H:%M:%S"), round(float(v), 2)] for t, v in zip(trades["time"], cum)]
    # 横坐标：固定的四个交易时段（夜盘 → 早盘一 → 早盘二 → 午盘），与 points 一一对应。
    # 起点不按时间映射：它的坐标固定在第一笔的左边，保证严格不重叠（第一笔恰好在轴的最左端时也是），
    # 否则鼠标悬停在第一笔的位置只会命中起点。整条轴整体右移 AXIS_PAD 给起点留位置。
    # 轴要覆盖开仓所在的交易日，所以把开仓时间也一起交给 session_axis；前 n 个是平仓，其后是开仓
    n_close = len(trades)
    open_times = list(open_trades["time"]) if len(open_trades) else []
    all_xs, segments = session_axis(list(trades["time"]) + open_times)
    trade_xs, open_xs = all_xs[:n_close], all_xs[n_close:]
    xs = [round(trade_xs[0] - START_POINT_OFFSET, 3)] + [round(x, 3) for x in trade_xs]
    # 平移的基准是“整条轴的最左端”（第一段的起点），而不是第一个点：点落在段内偏右的位置是正常的，
    # 如果按点平移，第一笔在夜盘 21:30 时整条轴会被向左拉，夜盘的起点 21:00 就跑到负坐标去了（已发现）。
    # 起点（第一笔左边 START_POINT_OFFSET）万一超出轴的最左端（第一笔恰好在 21:00:00），靠 AXIS_PAD 的留白容纳。
    shift = AXIS_PAD - segments[0]["x0"]
    xs = [round(x + shift, 3) for x in xs]
    open_xs = [round(x + shift, 3) for x in open_xs]
    for sg in segments:
        sg["x0"] = round(sg["x0"] + shift, 3)
        sg["x1"] = round(sg["x1"] + shift, 3)

    wins, losses = int((trades["pnl"] > 0).sum()), int((trades["pnl"] < 0).sum())
    peak = cum.cummax().clip(lower=0)
    max_dd = float((peak - cum).max()) if len(cum) else 0.0
    total_fee = float(df["fee"].sum())   # 手续费合计：所有成交（开+平）的手续费
    stats = {
        "totalPnl": round(float(cum.iloc[-1]), 2),
        "grossPnl": round(float(trades["pnl"].sum()), 2),
        "totalFee": round(total_fee, 2),
        # 平仓笔数 = 合并后的平仓笔数（成交时间相同的合并为一笔），包含盈亏恰好为 0 的平仓；
        # 胜率只在盈利/亏损的平仓里算（持平不算胜也不算负）
        "closeCount": int(len(trades)),
        "winCount": wins,
        "lossCount": losses,
        "winRate": round(wins / (wins + losses) * 100, 2) if (wins + losses) else 0.0,
        "maxDrawdown": round(max_dd, 2),
        # 没有盈利（亏损）的平仓时，单笔最大盈利（亏损）记 0，而不是把亏损（盈利）当成最大盈利（亏损）
        "maxProfit": round(float(trades["pnl"].max()), 2) if wins else 0.0,
        "maxLoss": round(float(trades["pnl"].min()), 2) if losses else 0.0,
    }
    # 与 points 一一对应的逐笔说明（第 0 个是人为补的“起点 0”，没有成交，用 None）。
    details = [None] + [
        {
            "time": t.strftime("%Y-%m-%d %H:%M:%S"), "symbol": str(sym), "direction": str(d),
            "lots": _num(lots), "price": _num(price), "pnl": round(float(p), 2),
            "fee": round(float(f), 2), "fills": int(n), "isClose": True,
        }
        for t, sym, d, lots, price, p, f, n in zip(trades["time"], trades["symbol"], trades["direction"],
                                                   trades["volume"], trades["price"], trades["pnl"],
                                                   trades["fee_charge"], trades["fills"])
    ]
    # 开仓标记：与 points 无关，单独成列，前端按横坐标把它们插进曲线（y = 此前最近一个平仓点的累计值）
    open_marks = [
        {
            "time": t.strftime("%Y-%m-%d %H:%M:%S"), "x": x, "symbol": str(sym), "direction": str(d),
            "lots": _num(lots), "price": _num(price), "fills": int(n),
        }
        for x, t, sym, d, lots, price, n in zip(open_xs, open_trades["time"], open_trades["symbol"],
                                                open_trades["direction"], open_trades["volume"],
                                                open_trades["price"], open_trades["fills"])
    ] if len(open_trades) else []
    return {"points": points, "xs": xs, "segments": segments, "details": details, "stats": stats,
            "trades": int(len(trades)), "openMarks": open_marks}


# ---------------------------------------------------------------------------
# 横坐标：固定的四个交易时段
# ---------------------------------------------------------------------------
# 商品期货一个交易日的四个时段（分钟，从 0 点起算）。夜盘属于“下一个交易日”，所以排在最前面：
#   夜盘 21:00-23:00 → 早盘第一场 09:00-10:15 → 早盘第二场 10:30-11:30 → 午盘 13:30-15:00
# 横轴只画这四段，段与段首尾相接（休息时间不画），段宽与真实时长成正比，所以横轴仍然是“时间”。
# 每个出现过成交的交易日都画完整的四段（哪怕某一段没有成交），这样每天的轴长度一致、段的位置固定；
# 没有任何成交的交易日不画，否则一个月的文件会有几十个空段。
SESSIONS = [
    {"key": "night", "name": "夜盘", "start": 21 * 60, "end": 23 * 60},
    {"key": "am1", "name": "早盘（上）", "start": 9 * 60, "end": 10 * 60 + 15},
    {"key": "am2", "name": "早盘（下）", "start": 10 * 60 + 30, "end": 11 * 60 + 30},
    {"key": "pm", "name": "午盘", "start": 13 * 60 + 30, "end": 15 * 60},
]
SESSION_GAP_WIDTH = 14  # 相邻两段之间留的视觉间隔（分钟宽度，只是为了画分隔线、让两侧的时间标签各占一边，不代表时间）
START_POINT_OFFSET = 1.5  # “起点 0”放在第一笔左边这么远（分钟宽度），保证悬停时不会遮住第一笔
AXIS_PAD = 2.0            # 整条轴最左边留出的空白，给起点腾位置
NIGHT_HOUR = 20         # 这个钟点之后的成交属于夜盘（交易日算下一天）
NIGHT_TAIL_HOUR = 3     # 凌晨这个钟点之前的成交是夜盘的延续（有的品种夜盘到 01:00、02:30）；交易日就是当天
NIGHT_IDX, AM1_IDX, AM2_IDX, PM_IDX = 0, 1, 2, 3


def _minutes_of_day(t: pd.Timestamp) -> float:
    return t.hour * 60 + t.minute + t.second / 60


def trading_day(t: pd.Timestamp) -> pd.Timestamp:
    """成交所属的交易日：夜盘（20:00 之后）属于下一天；凌晨（夜盘延续）和白天属于当天。"""
    d = t.normalize()
    return d + pd.Timedelta(days=1) if t.hour >= NIGHT_HOUR else d


def session_of(t: pd.Timestamp) -> int:
    """成交落在哪个时段（返回 SESSIONS 的下标）。

    - 20:00 之后、或凌晨 03:00 之前：夜盘（夜盘可以延续到凌晨，跨午夜仍是同一个夜盘）；
    - 其余时间：在早盘一、早盘二、午盘里取距离最近的；落在时段内距离为 0。
      落在时段之外（集合竞价略早于开盘、撮合延迟略晚于收盘、两场之间的休息）时归入最近的时段——不丢点，
      位置只是贴到时段边界，悬停里显示的仍是真实的成交时间。两边一样远（如午休正中间）取后一个时段，
      因为这时最可能是下一场开盘前的集合竞价委托。
    """
    m = _minutes_of_day(t)
    if m >= NIGHT_HOUR * 60 or m < NIGHT_TAIL_HOUR * 60:
        return NIGHT_IDX
    best, best_d = AM1_IDX, None
    for i in (AM1_IDX, AM2_IDX, PM_IDX):
        s = SESSIONS[i]
        d = 0.0 if s["start"] <= m <= s["end"] else min(abs(m - s["start"]), abs(m - s["end"]))
        if best_d is None or d <= best_d:   # <=：距离相等时取后一个（循环顺序是先早盘一、最后午盘）
            best, best_d = i, d
    return best


def session_axis(times: list[pd.Timestamp]) -> tuple[list[float], list[dict]]:
    """把一组按先后排好的时间点映射到“固定四段”的横坐标，并返回轴上的段列表。

    返回 (xs, segments)：
      xs[i]      第 i 个点的横坐标（单位：分钟）。点落在段内时与真实时间成正比；
                 落在段外（被归入最近的时段）时贴到该段的边界。
      segments   轴上所有的段，按先后顺序：
                 {"day": 交易日, "key", "name", "x0", "x1", "start", "end"}，start/end 是这段对应的真实起止时刻。
    """
    if not times:
        return [], []
    days = sorted({trading_day(t) for t in times})
    # 轴上的段 = 每个出现过成交的交易日 × 四个时段
    segments: list[dict] = []
    x = 0.0
    for d in days:
        for si, s in enumerate(SESSIONS):
            length = s["end"] - s["start"]
            # 夜盘的真实日期是交易日的前一天，其余时段是交易日当天
            base = d - pd.Timedelta(days=1) if s["key"] == "night" else d
            segments.append({
                "day": d.strftime("%Y-%m-%d"), "key": s["key"], "name": s["name"],
                "x0": round(x, 3), "x1": round(x + length, 3),
                "start": (base + pd.Timedelta(minutes=s["start"])).strftime("%Y-%m-%d %H:%M:%S"),
                "end": (base + pd.Timedelta(minutes=s["end"])).strftime("%Y-%m-%d %H:%M:%S"),
                "_si": si,
            })
            x += length + SESSION_GAP_WIDTH
    by_slot = {(sg["day"], sg["_si"]): sg for sg in segments}

    xs: list[float] = []
    for t in times:
        si = session_of(t)
        seg = by_slot[(trading_day(t).strftime("%Y-%m-%d"), si)]
        s = SESSIONS[si]
        m = _minutes_of_day(t)
        # 凌晨的夜盘延续（00:00~03:00）：真实分钟数要加上一整天，才能接在 23:00 之后
        if si == NIGHT_IDX and m < NIGHT_TAIL_HOUR * 60:
            m += 24 * 60
        offset = min(max(m - s["start"], 0.0), s["end"] - s["start"])
        xs.append(round(seg["x0"] + offset, 3))
    for sg in segments:
        sg.pop("_si")
    return xs, segments


def _attribute_fees(df: pd.DataFrame) -> pd.Series:
    """把每一行的手续费归到“曲线上的某一笔平仓”上，返回与 df 同索引的 Series（只有平仓行有值，其余为 0）。

    - 平仓行：自己的手续费；
    - 开仓行：记到同一合约、时间上之后的第一笔平仓；
    - 后面没有平仓的开仓（仍持仓）：记到最后一笔平仓（保证曲线终点 = 平仓盈亏 - 全部手续费）。
    要求 df 已按交易时段排好序。
    """
    charge = pd.Series(0.0, index=df.index)
    pending: dict[str, float] = defaultdict(float)   # 合约 -> 尚未归属的开仓手续费
    last_close_idx = None
    for idx, sym, is_close, fee in zip(df.index, df["symbol"], df["is_close"], df["fee"]):
        if is_close:
            charge.at[idx] += fee + pending.pop(sym, 0.0)
            last_close_idx = idx
        else:
            pending[sym] += fee
    leftover = sum(pending.values())
    if leftover and last_close_idx is not None:
        charge.at[last_close_idx] += leftover
    return charge


def _merge_same_time(closes: pd.DataFrame) -> pd.DataFrame:
    """成交时间相同的几笔平仓合并为一笔。

    合并键：成交时间 + 合约 + 买/卖。不同合约、或买卖方向不同的成交即使同一时刻也不合并——
    合并后要展示“合约、方向、手数、价格”，混在一起会没有意义。
    手数、平仓盈亏、手续费相加；成交价取按手数加权的均价；fills 记录合并了几笔成交。
    """
    work = closes.assign(_notional=closes["price"] * closes["volume"])
    keys = ["time", "symbol", "direction"]
    agg = work.groupby(keys, sort=False, as_index=False).agg(
        volume=("volume", "sum"), _notional=("_notional", "sum"), pnl=("pnl", "sum"),
        fee_charge=("fee_charge", "sum"), seq=("seq", "min"), fills=("volume", "size"),
        product=("product", "first"),
    )
    agg["price"] = agg["_notional"] / agg["volume"]
    agg = agg.drop(columns=["_notional"])
    # groupby(sort=False) 保持首次出现的顺序，而输入已按交易时段排好序，所以这里不需要再排
    return agg.reset_index(drop=True)


def _num(v: float):
    """手数/价格转成 JSON 里干净的数字：整数不带 .0。"""
    f = float(v)
    return int(f) if f.is_integer() else round(f, 4)


def _empty_stats() -> dict:
    return {"totalPnl": 0.0, "grossPnl": 0.0, "totalFee": 0.0, "closeCount": 0, "winCount": 0,
            "lossCount": 0, "winRate": 0.0, "maxDrawdown": 0.0, "maxProfit": 0.0, "maxLoss": 0.0}


# ---------------------------------------------------------------------------
# 当天 K 线复盘：把每一笔开仓和平仓配成一笔“交易”
# ---------------------------------------------------------------------------
def pair_trades(df: pd.DataFrame) -> list[dict]:
    """按合约先进先出，把开仓和平仓配成一笔笔交易（一笔平仓可能对应多笔开仓，会拆开）。

    要求 df 已按交易时段排好序，且带有 is_close / pnl 列（analyze 已处理）。
    平仓方向与持仓相反：买平 = 平空仓，卖平 = 平多仓。
    每笔交易的盈亏：文件里有“平仓盈亏”时，按手数把平仓行的盈亏分摊到它对应的各笔开仓上
    （这样和资金曲线、Excel 的汇总一致）；否则按价差 × 合约乘数 × 手数计算。
    没有找到对应开仓的平仓（开仓在文件之前）：open_time 为 None，盈亏仍取平仓行的值。
    """
    long_q: dict[str, deque] = defaultdict(deque)    # 合约 -> deque[[开仓时间, 价格, 剩余手数, 费用]]
    short_q: dict[str, deque] = defaultdict(deque)
    trades: list[dict] = []
    has_file_pnl = bool((df["pnl"] != 0).any())

    for row in df.itertuples(index=False):
        sym, lots, price, d, t = row.symbol, float(row.volume), float(row.price), row.direction, row.time
        mult = CONTRACT_MULTIPLIER.get(row.product, DEFAULT_MULTIPLIER)
        if not row.is_close:
            (long_q if d == "买" else short_q)[sym].append([t, price, lots])
            continue

        # 买平 = 平空仓（队列是 short_q），卖平 = 平多仓
        queue = short_q[sym] if d == "买" else long_q[sym]
        side = "空" if d == "买" else "多"
        remaining, total_lots = lots, lots
        while remaining > 1e-9:
            if queue:
                o_time, o_price, o_lots = queue[0]
                matched = min(remaining, o_lots)
                queue[0][2] -= matched
                if queue[0][2] <= 1e-9:
                    queue.popleft()
            else:
                o_time, o_price, matched = None, None, remaining   # 找不到对应开仓
            if has_file_pnl:
                pnl = float(row.pnl) * matched / total_lots
            elif o_price is not None:
                pnl = ((o_price - price) if side == "空" else (price - o_price)) * matched * mult
            else:
                pnl = 0.0
            trades.append({
                "symbol": str(sym), "side": side, "lots": matched,
                "openTime": o_time, "openPrice": o_price, "closeTime": t, "closePrice": price, "pnl": pnl,
            })
            remaining -= matched
    return trades


def merge_paired_trades(trades: list[dict]) -> list[dict]:
    """把配对后“开仓时间、平仓时间、合约、方向都相同”的交易合并成一条，对应资金曲线的 _merge_same_time。

    先进先出会把同一时刻的几笔成交拆成几条（例如同一时刻分三笔平 1+2+3 手，或一笔平仓吃掉同一时刻的几笔开仓），
    它们在 K 线上落在同一根 K 线，开仓点、平仓点和连线会叠在一起，悬停也只能看到最上面一条。
    合并后：手数、盈亏相加；开仓价、平仓价取按手数加权的均价；fills 记录合并了几条。
    开仓时间为 None（找不到对应开仓）的按平仓时间合并。保持首次出现的顺序。
    """
    merged: dict[tuple, dict] = {}
    for tr in trades:
        key = (tr["symbol"], tr["side"], tr["openTime"], tr["closeTime"])
        m = merged.get(key)
        if m is None:
            merged[key] = {**tr, "fills": 1,
                           "_open_notional": (tr["openPrice"] or 0.0) * tr["lots"],
                           "_close_notional": tr["closePrice"] * tr["lots"]}
            continue
        m["lots"] += tr["lots"]
        m["pnl"] += tr["pnl"]
        m["fills"] += 1
        m["_open_notional"] += (tr["openPrice"] or 0.0) * tr["lots"]
        m["_close_notional"] += tr["closePrice"] * tr["lots"]
    out = []
    for m in merged.values():
        m["closePrice"] = m.pop("_close_notional") / m["lots"]
        open_notional = m.pop("_open_notional")
        m["openPrice"] = None if m["openTime"] is None else open_notional / m["lots"]
        out.append(m)
    return out


def build_day_trades(records: pd.DataFrame, day: str, products: list[str] | None = None) -> dict:
    """某个交易日的所有交易（按合约分组），用于在 K 线上标注。

    配对使用文件里的全部记录（隔夜持仓的开仓在前一个交易日），再取“开仓或平仓落在这个交易日”的交易。
    返回 {"day", "symbols": [{"symbol", "trades": [...]}], "days": [文件里有成交的全部交易日]}。
    """
    df = records
    if products:
        df = df[df["product"].isin(products)]
    df = _sort_by_session(df)
    tday = df["time"].map(trading_day).dt.strftime("%Y-%m-%d")
    days = sorted(tday.unique().tolist())
    target = pd.to_datetime(day).strftime("%Y-%m-%d")   # 非法日期抛 ValueError（接口返回 400）

    def fmt(t):
        return None if t is None else t.strftime("%Y-%m-%d %H:%M:%S")

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for tr in merge_paired_trades(pair_trades(df)):
        in_day = lambda t: t is not None and trading_day(t).strftime("%Y-%m-%d") == target
        if not (in_day(tr["openTime"]) or in_day(tr["closeTime"])):
            continue
        by_symbol[tr["symbol"]].append({
            "side": tr["side"], "lots": _num(tr["lots"]),
            # 合并后的均价保留两位小数（期货最小变动价位最多到 0.01 的量级，再多位数只是均价的除不尽）
            "openTime": fmt(tr["openTime"]),
            "openPrice": None if tr["openPrice"] is None else _num(round(tr["openPrice"], 2)),
            "closeTime": fmt(tr["closeTime"]), "closePrice": _num(round(tr["closePrice"], 2)),
            "pnl": round(tr["pnl"], 2), "fills": tr["fills"],
            # 开仓 / 平仓是否落在这个交易日：不在当天的那一端画不到当天的 K 线上
            "openInDay": in_day(tr["openTime"]), "closeInDay": in_day(tr["closeTime"]),
        })
    symbols = [{"symbol": s, "trades": ts} for s, ts in sorted(by_symbol.items())]
    return {"day": target, "days": days, "symbols": symbols}
