"""交易复盘解析/曲线的单元测试：python -m pytest tests -q（或 python tests/test_review.py）。

用合成的 Excel 覆盖两种常见导出：
  A. 有“平仓盈亏”列，且表头上面有标题/账户信息行；
  B. 没有“平仓盈亏”列，需要按先进先出自行配对。
期望值都是手算的。
"""
import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import review  # noqa: E402


def make_xlsx(rows, header, title_rows=0, ext="xlsx") -> bytes:
    buf = io.BytesIO()
    data = [[None] * len(header) for _ in range(title_rows)]
    if title_rows:
        data[0][0] = "成交明细查询"
        if title_rows > 1:
            data[1][0] = "资金账号：12345678"
    data.append(header)
    data.extend(rows)
    pd.DataFrame(data).to_excel(buf, header=False, index=False, engine="openpyxl")
    return buf.getvalue()


# ---- A: 有平仓盈亏列 + 顶部标题行 ------------------------------------------
HEADER_A = ["成交时间", "合约", "买卖", "开平", "成交价", "手数", "手续费", "平仓盈亏"]
ROWS_A = [
    ["2026-10-20 09:01:00", "FU2611", "买", "开", 2900, 2, 5.0, None],
    ["2026-10-20 10:30:00", "FU2611", "卖", "平", 2920, 2, 5.0, 400.0],   # +400
    ["2026-10-21 09:05:00", "rb2610", "卖", "开", 3300, 1, 3.0, None],
    ["2026-10-21 14:00:00", "rb2610", "买", "平", 3320, 1, 3.0, -200.0],  # -200
    ["2026-10-22 09:10:00", "FU2611", "买", "开", 2950, 1, 2.5, None],
    ["2026-10-22 11:00:00", "FU2611", "卖", "平", 2940, 1, 2.5, -100.0],  # -100
    ["合计", None, None, None, None, 7, 21.0, 100.0],                      # 汇总行必须被忽略
]


def test_header_detection_and_columns():
    df, warnings = review.read_trades(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "a.xlsx")
    assert len(df) == 6, "合计行应被丢弃"
    assert set(df["product"]) == {"FU", "RB"}
    assert df["pnl"].notna().any()
    assert not any("忽略" in w for w in warnings), "合计行 / 空行静默丢弃，不再提示丢了几行"


def test_curve_with_pnl_column():
    res = review.analyze(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "a.xlsx")
    assert res.products == ["FU", "RB"]
    c = review.build_curve(res.records, include_fee=False)
    assert c["stats"]["totalPnl"] == 100.0                  # 400 - 200 - 100
    assert c["stats"]["closeCount"] == 3 and c["stats"]["winCount"] == 1 and c["stats"]["lossCount"] == 2
    assert c["stats"]["winRate"] == 33.33
    assert c["points"][0][1] == 0.0
    assert [p[1] for p in c["points"]][-1] == 100.0


def test_fee_is_charged_on_every_fill():
    res = review.analyze(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "a.xlsx")
    c = review.build_curve(res.records, include_fee=True)
    # 手续费 5+5+3+3+2.5+2.5 = 21，开平两边都收
    assert c["stats"]["totalFee"] == 21.0
    assert c["stats"]["totalPnl"] == 79.0                   # 100 - 21


def test_filter_by_product_and_time():
    res = review.analyze(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "a.xlsx")
    fu = review.build_curve(res.records, products=["FU"], include_fee=False)
    assert fu["stats"]["totalPnl"] == 300.0                 # 400 - 100
    day = review.build_curve(res.records, start="2026-10-21", end="2026-10-21", include_fee=False)
    assert day["stats"]["totalPnl"] == -200.0, "只给日期时应包含当天整天"
    # 这一天有 rb 的一次开仓 + 一次平仓。“开/平只统计平”之后，曲线上的笔数只算平仓：1 笔（以前按成交笔数算是 2）
    assert day["trades"] == 1
    none = review.build_curve(res.records, products=["FU"], start="2026-11-01", include_fee=False)
    assert none["points"] == [] and none["stats"]["totalPnl"] == 0.0


def test_break_even_close_is_counted_but_not_win_or_loss():
    # 回归：盈亏恰好为 0 的平仓也是一笔平仓，不能因为 pnl==0 被当成开仓而漏计
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数", "平仓盈亏"]
    rows = [
        ["2026-10-20 09:00:00", "FU2611", "买", "开", 2900, 1, None],
        ["2026-10-20 10:00:00", "FU2611", "卖", "平", 2900, 1, 0.0],      # 持平
        ["2026-10-20 11:00:00", "FU2611", "买", "开", 2900, 1, None],
        ["2026-10-20 12:00:00", "FU2611", "卖", "平", 2910, 1, 100.0],    # 盈利
    ]
    s = review.build_curve(review.analyze(make_xlsx(rows, header), "f.xlsx").records, include_fee=False)["stats"]
    assert s["closeCount"] == 2, "持平的平仓也要计入平仓笔数"
    assert s["winCount"] == 1 and s["lossCount"] == 0
    assert s["winRate"] == 100.0, "胜率不把持平算作负"


def test_break_even_close_with_pairing():
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数"]
    rows = [["2026-10-20 09:00:00", "FU2611", "买", "开", 2900, 1],
            ["2026-10-20 10:00:00", "FU2611", "卖", "平", 2900, 1]]
    s = review.build_curve(review.analyze(make_xlsx(rows, header), "g.xlsx").records, include_fee=False)["stats"]
    assert s["closeCount"] == 1 and s["winCount"] == 0 and s["lossCount"] == 0 and s["winRate"] == 0.0


def test_max_profit_loss_when_one_side_missing():
    # 回归：全是亏损时，“单笔最大盈利”不能显示成负数（把最小亏损当成最大盈利）
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数", "平仓盈亏"]
    rows = [["2026-10-20 09:00:00", "FU2611", "买", "开", 2900, 1, None],
            ["2026-10-20 10:00:00", "FU2611", "卖", "平", 2890, 1, -100.0],
            ["2026-10-20 11:00:00", "FU2611", "买", "开", 2900, 1, None],
            ["2026-10-20 12:00:00", "FU2611", "卖", "平", 2880, 1, -200.0]]
    s = review.build_curve(review.analyze(make_xlsx(rows, header), "h.xlsx").records, include_fee=False)["stats"]
    assert s["maxProfit"] == 0.0 and s["maxLoss"] == -200.0
    assert s["winRate"] == 0.0 and s["lossCount"] == 2


def test_max_drawdown():
    res = review.analyze(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "a.xlsx")
    c = review.build_curve(res.records, include_fee=False)
    # 累计：0 -> 400 -> 200 -> 100，从峰值 400 回撤到 100 = 300
    assert c["stats"]["maxDrawdown"] == 300.0


# ---- B: 没有平仓盈亏列，按先进先出配对 ---------------------------------------
HEADER_B = ["成交日期", "成交时间", "合约代码", "买卖方向", "开平标志", "成交价格", "成交量", "手续费"]
ROWS_B = [
    ["2026-10-20", "09:01:00", "FU2611", "买", "开仓", 2900, 2, 5.0],
    ["2026-10-20", "09:30:00", "FU2611", "买", "开仓", 2910, 1, 2.5],
    ["2026-10-20", "10:30:00", "FU2611", "卖", "平仓", 2930, 2, 5.0],   # 平2手：先平 2900 的 2 手
    ["2026-10-20", "11:00:00", "FU2611", "卖", "平今", 2900, 1, 2.5],   # 再平 2910 的 1 手
]


def test_pairing_fifo_and_multiplier():
    res = review.analyze(make_xlsx(ROWS_B, HEADER_B), "b.xlsx")
    assert any("没有“平仓盈亏”列" in w for w in res.warnings)
    c = review.build_curve(res.records, include_fee=False)
    # FU 乘数 10：(2930-2900)*2*10 = +600；(2900-2910)*1*10 = -100
    assert c["stats"]["grossPnl"] == 500.0
    assert c["stats"]["closeCount"] == 2 and c["stats"]["winCount"] == 1


def test_pairing_short_side_and_infer_offset():
    # 没有“开平”列：与当前持仓相反的成交视为平仓
    header = ["成交时间", "合约", "买卖", "成交价", "手数"]
    rows = [
        ["2026-10-20 09:00:00", "rb2610", "卖", 3300, 2],   # 开空
        ["2026-10-20 10:00:00", "rb2610", "买", 3280, 2],   # 买平：(3300-3280)*2*10 = +400
    ]
    res = review.analyze(make_xlsx(rows, header), "c.xlsx")
    assert review.build_curve(res.records, include_fee=False)["stats"]["grossPnl"] == 400.0


def test_unmatched_close_warns():
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数"]
    rows = [["2026-10-20 10:00:00", "FU2611", "卖", "平", 2900, 3]]
    res = review.analyze(make_xlsx(rows, header), "d.xlsx")
    assert any("找不到对应开仓" in w for w in res.warnings)


def test_unknown_product_multiplier_warns():
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数"]
    rows = [["2026-10-20 09:00:00", "ZZ2601", "买", "开", 100, 1],
            ["2026-10-20 10:00:00", "ZZ2601", "卖", "平", 110, 1]]
    res = review.analyze(make_xlsx(rows, header), "e.xlsx")
    assert any("ZZ" in w and "合约乘数" in w for w in res.warnings)


def test_bad_files_raise_readable_errors():
    for bad, name in ((b"not an excel file", "x.xlsx"),):
        try:
            review.read_trades(bad, name)
        except review.ReviewParseError as e:
            assert "无法读取" in str(e)
        else:
            raise AssertionError("应抛出 ReviewParseError")
    # 能读但没有必需列
    try:
        review.read_trades(make_xlsx([[1, 2]], ["foo", "bar"]), "y.xlsx")
    except review.ReviewParseError as e:
        assert "没有识别到必需的列" in str(e)
    else:
        raise AssertionError("应抛出 ReviewParseError")


def test_csv_gbk():
    csv = "成交时间,合约,买卖,开平,成交价,手数\n2026-10-20 09:00:00,FU2611,买,开,2900,1\n" \
          "2026-10-20 10:00:00,FU2611,卖,平,2910,1\n"
    res = review.analyze(csv.encode("gbk"), "z.csv")
    assert review.build_curve(res.records, include_fee=False)["stats"]["grossPnl"] == 100.0


def test_product_code():
    assert review.product_code("FU2611") == "FU"
    assert review.product_code("fu2611") == "FU"
    assert review.product_code("SHFE.fu2611") == "FU"
    assert review.product_code("沪铜2601") == "沪铜"


# ---- C: 结算单“成交明细”页：多 sheet、顶部有冗余信息、同一时刻多笔成交、夜盘 -------------------------
# 表头与实际导出一致（单元格里有换行：投机（一\n般）/套保/\n套利、实际成交日\n期）
HEADER_D = ["合约", "成交序号", "成交时间", "买/卖", "投机（一\n般）/套保/\n套利", "成交价", "手数", "成交额",
            "开/平", "手续费", "平仓盈亏", "实际成交日\n期"]
MULT = {"FU": 10, "rb": 10, "IF": 300}


def _row(seq, sym, t, side, oc, price, lots, fee, pnl=None, date=None):
    """一行成交明细。t 为 'HH:MM:SS'；date 为 'YYYY-MM-DD'（实际成交日期）。"""
    prod = "FU" if sym.startswith("FU") else "rb" if sym.startswith("rb") else "IF"
    # 成交额 = 价格 × 手数 × 合约乘数。价格/手数在“单元格类型”测试里可能是文本，先转成数字再算
    amount = float(price) * float(lots) * MULT[prod]
    return [sym, f"{seq:08d}", t, side, "投机", price, lots, amount, oc, fee, pnl, date]


def make_detail_sheet(rows, sheet="成交明细", other_first=True, title=True, extra_closed_sheet=True) -> bytes:
    """多 sheet 的结算单：除“成交明细”外，还有不相关的“资金状况”（默认排在最前）和旧的“平仓明细”。"""
    import openpyxl
    wb = openpyxl.Workbook()
    other = wb.active
    other.title = "资金状况"
    other.append(["期货结算单"])
    other.append(["项目", "金额"])
    other.append(["平仓盈亏", 12345.0])
    if extra_closed_sheet:   # 旧格式的表还在文件里：新逻辑不能再去读它
        old = wb.create_sheet("平仓明细")
        old.append(["合约", "成交序号", "买/卖", "成交价", "开仓价", "手数", "昨结算价", "平仓盈亏", "原成交序号", "实际成交日期"])
        old.append(["FU2611", "00000001", "卖", 2910, 2900, 1, 2905, 99999.0, "00000000", "2026-10-21"])
    s = wb.create_sheet(sheet)
    if title:
        s.append(["成交明细 Transaction Record"])
        s.append(["客户号 Client ID：88001234"])
        s.append(["统计区间：2026-10-21 ~ 2026-10-22"])
        s.append([])
    s.append(HEADER_D)
    for r in rows:
        s.append(r)
    s.append(["合计 Total", None, None, None, None, None, sum(float(r[6]) for r in rows), None, None,
              round(sum(float(r[9]) for r in rows), 2), sum(float(r[10] or 0) for r in rows), None])
    if not other_first:
        wb.move_sheet("资金状况", offset=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# 结算单里的「实际成交日期」是**交易日**，不是成交真正发生的日历日期：同一个交易日的所有行（夜盘、凌晨、白天）
# 都标同一个日期，夜盘（21:00~23:00）其实发生在前一天晚上，由 review._restore_real_time 还原。
# 所以这里夜盘和白天用同一个日期 D（交易日 10-22）；夜盘的真实时间是 10-21 晚上。
# 以前样本里把夜盘标成前一天（N=10-21），那是“日期是真实日历日期”的旧约定，和用户的 Excel 不一致。
D = "2026-10-22"   # 交易日（周四）。夜盘真实在 10-21 晚上，白天在 10-22
N = D              # 夜盘行标的日期与白天相同：都是交易日
ROWS_D = [
    # 开 6 手 FU，随后同一时刻（21:30:05）分 3 笔平掉：1+2+3 手 → 合并为 1 笔
    _row(1, "FU2611", "21:25:05", "买", "开", 2900, 6, 15.0, None, N),
    _row(2, "FU2611", "21:30:05", "卖", "平", 2910, 1, 2.5, 100.0, N),
    _row(3, "FU2611", "21:30:05", "卖", "平", 2912, 2, 5.0, 240.0, N),
    _row(4, "FU2611", "21:30:05", "卖", "平", 2914, 3, 7.5, 420.0, N),
    # 夜盘 rb：开空 21:05，22:10 买平
    _row(5, "rb2610", "21:05:00", "卖", "开", 3300, 2, 4.0, None, N),
    _row(6, "rb2610", "22:10:30", "买", "平", 3290, 2, 4.0, 200.0, N),
    # 次日 09:15:00，两个不同合约同一时刻平仓：不能合并成一笔
    _row(7, "IF2611", "09:00:00", "买", "开", 3900, 1, 25.0, None, D),
    _row(8, "FU2611", "09:01:00", "买", "开", 2900, 1, 2.5, None, D),
    _row(9, "IF2611", "09:15:00", "卖", "平", 3910, 1, 25.0, 3000.0, D),
    _row(10, "FU2611", "09:15:00", "卖", "平", 2895, 1, 2.5, -50.0, D),
    # 下午：亏损一笔
    _row(11, "rb2610", "13:40:00", "买", "开", 3290, 1, 2.0, None, D),
    _row(12, "rb2610", "14:30:00", "卖", "平", 3280, 1, 2.0, -100.0, D),
    # 只有开仓、没有平仓（仍持仓）：不进曲线，但手续费是真实成本
    _row(13, "FU2611", "14:50:00", "买", "开", 2905, 2, 5.0, None, D),
]
GROSS_D = 760.0 + 200.0 + 3000.0 - 50.0 - 100.0           # 3810
FEE_ALL_D = sum(r[9] for r in ROWS_D)                      # 102.0（开 + 平 全部手续费）


def test_detail_sheet_is_chosen_and_old_closed_sheet_is_ignored():
    # 文件里同时有“资金状况”“平仓明细”“成交明细”：只读“成交明细”（旧的平仓明细里放了 99999 的陷阱数据）
    df, w = review.read_trades(make_detail_sheet(ROWS_D), "s.xlsx")
    assert len(df) == 13 and set(df["product"]) == {"FU", "RB", "IF"}
    assert not any("已读取工作表" in x for x in w), "读了哪张工作表不再作为提示显示给用户"
    g = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)["stats"]["grossPnl"]
    assert g == GROSS_D, "读到了错误的工作表" if g != GROSS_D else ""


def test_detail_header_aliases_slash_forms_and_wrapped_cells():
    # “开/平”“买/卖”和带换行的表头都要能识别；成交额、投机/套保/套利等无关列被忽略
    df, _ = review.read_trades(make_detail_sheet(ROWS_D), "s.xlsx")
    assert set(df["offset"]) == {"开", "平"} and set(df["direction"]) == {"买", "卖"}
    assert df["fee"].sum() == FEE_ALL_D


def test_only_close_rows_are_on_the_curve():
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)
    assert c["trades"] == 5, "13 行里 6 行是开仓，7 行平仓合并后是 5 笔"
    assert len(c["points"]) == len(c["details"]) == 6          # 起点 + 5 笔
    assert all(d["isClose"] for d in c["details"][1:]), "曲线上不应有开仓"
    assert c["stats"]["closeCount"] == 5 and c["stats"]["winCount"] == 3 and c["stats"]["lossCount"] == 2


def test_same_time_same_contract_and_side_are_merged_with_weighted_price():
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)
    first = c["details"][1]
    assert first["time"] == "2026-10-21 21:30:05" and first["symbol"] == "FU2611" and first["direction"] == "卖"
    assert first["lots"] == 6 and first["fills"] == 3
    assert first["pnl"] == 760.0, "平仓盈亏相加：100+240+420"
    # 成交价按手数加权：(2910*1 + 2912*2 + 2914*3) / 6 = 2912.6667
    assert abs(first["price"] - (2910 * 1 + 2912 * 2 + 2914 * 3) / 6) < 1e-3


def test_same_time_but_different_contract_is_not_merged():
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)
    at_0915 = [d for d in c["details"][1:] if d["time"].endswith("09:15:00")]
    assert len(at_0915) == 2 and {d["symbol"] for d in at_0915} == {"IF2611", "FU2611"}
    assert all(d["fills"] == 1 for d in at_0915)


def test_same_time_different_direction_is_not_merged():
    rows = [
        _row(1, "FU2611", "09:00:00", "买", "开", 2900, 2, 5.0, None, D),
        _row(2, "FU2611", "09:00:00", "卖", "开", 2900, 2, 5.0, None, D),
        _row(3, "FU2611", "10:00:00", "卖", "平", 2910, 2, 5.0, 200.0, D),
        _row(4, "FU2611", "10:00:00", "买", "平", 2890, 2, 5.0, 200.0, D),   # 同一时刻、买卖相反的两笔平仓
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    assert c["trades"] == 2 and {d["direction"] for d in c["details"][1:]} == {"买", "卖"}


def test_totals_with_fee_deduct_open_and_close_fees():
    # 只统计“平”不能把开仓的手续费丢掉：曲线终点 = 平仓盈亏合计 - 全部（开+平）手续费
    r = review.analyze(make_detail_sheet(ROWS_D), "s.xlsx")
    gross = review.build_curve(r.records, include_fee=False)
    net = review.build_curve(r.records, include_fee=True)
    assert gross["stats"]["totalPnl"] == gross["points"][-1][1] == GROSS_D
    assert net["stats"]["totalPnl"] == net["points"][-1][1] == GROSS_D - FEE_ALL_D == 3708.0
    assert net["stats"]["totalFee"] == FEE_ALL_D == 102.0, "手续费合计包含开仓行"
    # 逐笔：每笔扣的手续费之和 = 全部手续费，并且曲线逐点等于“累计盈亏 - 累计手续费”
    assert round(sum(d["fee"] for d in net["details"][1:]), 2) == FEE_ALL_D


def test_open_fee_is_charged_at_the_next_close_of_the_same_contract():
    # FU 在 21:25 开仓付 15.0；它在 21:30:05 被平掉，那一笔（合并后）的手续费 = 平仓 15.0 + 开仓 15.0 = 30.0
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=True)
    assert c["details"][1]["fee"] == 30.0 and c["points"][1][1] == 760.0 - 30.0
    # rb 夜盘：开仓 4.0 + 平仓 4.0 = 8.0
    assert c["details"][2]["fee"] == 8.0


def test_still_open_position_fee_goes_to_the_last_trade():
    # 14:50 的 FU 开仓 2 手（手续费 5.0）后面没有平仓：计入最后一笔，终点才等于“平仓盈亏 - 全部手续费”
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=True)
    last = c["details"][-1]
    assert last["symbol"] == "rb2610" and last["fee"] == 2.0 + 2.0 + 5.0   # 自己平仓 2.0 + 13:40 开仓 2.0 + 仍持仓的 5.0


def test_night_session_is_ordered_before_next_morning_when_date_is_calendar_date():
    # 约定 A：实际成交日期 = 真实日历日期（周三夜盘记周三）。文件顺序故意打乱。
    rows = [ROWS_D[11], ROWS_D[3], ROWS_D[8], ROWS_D[5], ROWS_D[0], ROWS_D[1], ROWS_D[2], ROWS_D[4],
            ROWS_D[6], ROWS_D[7], ROWS_D[9], ROWS_D[10], ROWS_D[12]]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    times = [d["time"] for d in c["details"][1:]]
    assert times == sorted(times), times
    assert times[0].endswith("21:30:05") and times[-1].endswith("14:30:00"), "夜盘在最前，下午在最后"


def test_night_session_is_ordered_before_day_session_when_date_is_trading_day():
    # 约定 B：日期是“交易日”——周三晚上的夜盘记成周四。只按 (日期, 时间) 排会把夜盘排到当天日盘之后，顺序是错的。
    rows = [
        _row(1, "FU2611", "21:10:00", "买", "开", 2900, 1, 2.5, None, D),    # 周三夜盘，但日期记为交易日 周四
        _row(2, "FU2611", "21:40:00", "卖", "平", 2910, 1, 2.5, 100.0, D),
        _row(3, "FU2611", "09:10:00", "买", "开", 2910, 1, 2.5, None, D),
        _row(4, "FU2611", "10:30:00", "卖", "平", 2905, 1, 2.5, -50.0, D),
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    times = [d["time"][11:] for d in c["details"][1:]]
    assert times == ["21:40:00", "10:30:00"], "夜盘（21:40）必须排在同一交易日的日盘（10:30）之前"
    assert [p[1] for p in c["points"][1:]] == [100.0, 50.0]


def test_post_midnight_trades_stay_after_the_night_session_and_before_the_morning():
    rows = [
        _row(1, "FU2611", "21:10:00", "买", "开", 2900, 1, 2.5, None, N),
        _row(2, "FU2611", "23:10:00", "卖", "平", 2910, 1, 2.5, 100.0, N),
        _row(3, "FU2611", "00:30:00", "买", "开", 2910, 1, 2.5, None, D),    # 凌晨 00:30，真实日期已是周四
        _row(4, "FU2611", "01:20:00", "卖", "平", 2915, 1, 2.5, 50.0, D),
        _row(5, "FU2611", "09:15:00", "买", "开", 2915, 1, 2.5, None, D),
        _row(6, "FU2611", "09:50:00", "卖", "平", 2920, 1, 2.5, 50.0, D),
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    assert [d["time"][5:16] for d in c["details"][1:]] == ["10-21 23:10", "10-22 01:20", "10-22 09:50"]


def test_detail_filter_by_product_and_time_range_uses_merged_trades():
    r = review.analyze(make_detail_sheet(ROWS_D), "s.xlsx")
    fu = review.build_curve(r.records, ["FU"], include_fee=False)
    assert fu["stats"]["totalPnl"] == 760.0 - 50.0 and fu["trades"] == 2          # 合并后的 FU 2 笔
    # 时间范围按交易日筛选（和 Excel 的「实际成交日期」同一个语义）：D 这个交易日的夜盘（真实在前一天晚上）也属于它。
    # 以前按真实时间筛，选“D 到 D”会漏掉夜盘的两笔（+760、+200），总盈亏只有白天的 2850，和 Excel 里按这天汇总的数字对不上
    day = review.build_curve(r.records, start=D, end=D, include_fee=False)
    assert day["stats"]["totalPnl"] == GROSS_D == 3810.0 and day["trades"] == 5
    assert [d["time"][5:16] for d in day["details"][1:3]] == ["10-21 21:30", "10-21 22:10"], "夜盘（真实 10-21 晚上）包含在 10-22 交易日里"
    assert review.build_curve(r.records, start="2027-01-01")["points"] == []


def test_open_only_selection_returns_empty_curve_not_error():
    # 筛选出来全是开仓（比如只看一个还没平仓的品种）：没有可画的曲线，但不应报错
    rows = [_row(1, "FU2611", "09:00:00", "买", "开", 2900, 1, 2.5, None, D)]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records)
    assert c["points"] == [] and c["trades"] == 0 and c["details"] == []


def test_start_point_is_before_the_first_trade_not_on_top_of_it():
    # 回归：起点和第一笔同一时刻时，鼠标悬停在该位置只会命中起点，第一笔成交的信息永远看不到
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)
    start_t, first_t = c["points"][0][0], c["points"][1][0]
    assert c["points"][0][1] == 0.0
    assert start_t < first_t, (start_t, first_t)
    assert first_t == "2026-10-21 21:30:05" and start_t == "2026-10-21 21:30:04"
    # 所有点的时间戳互不相同（同一时刻的成交已合并），悬停才能分得清
    assert len({p[0] for p in c["points"]}) == len(c["points"]) or any(
        c["details"][i]["time"] == c["details"][i + 1]["time"] for i in range(1, len(c["details"]) - 1))


def test_start_point_is_still_before_a_trade_at_exactly_midnight():
    # 夜盘到凌晨 02:30：第一笔平仓恰好在 00:00:00 时，起点放在前一天 23:59:59，仍然严格早于它，悬停不会撞上
    rows = [
        _row(1, "FU2611", "23:50:00", "买", "开", 2900, 1, 2.5, None, N),
        _row(2, "FU2611", "00:00:00", "卖", "平", 2910, 1, 2.5, 100.0, D),
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    assert c["points"][0][0] == "2026-10-21 23:59:59" and c["points"][1][0] == "2026-10-22 00:00:00"


def test_file_with_only_dates_is_rejected_with_a_clear_message():
    # 所有时间都是 00:00:00（只有日期）：同一天的成交分不出先后，按成交时间合并会把不相干的成交并成一笔
    # （曾经 14 笔被静默并成 6 笔）。必须明确拒绝，而不是给出看似正常、实际不对的结果
    import datetime as dt
    rows = [
        _row(1, "FU2611", dt.time(0, 0, 0), "买", "开", 2900, 1, 2.5, None, N),
        _row(2, "FU2611", dt.time(0, 0, 0), "卖", "平", 2910, 1, 2.5, 100.0, N),
    ]
    try:
        review.analyze(make_detail_sheet(rows), "s.xlsx")
    except review.ReviewParseError as e:
        msg = str(e)
        assert "只有日期" in msg and "成交时间" in msg and "成交明细" in msg
    else:
        raise AssertionError("只有日期的文件应被拒绝")


def test_old_closed_positions_only_file_is_rejected_not_misread():
    # 只有“平仓明细”（没有成交时间、没有开/平列）的文件：以前会被静默读错，现在明确拒绝
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "平仓明细"
    wb.active.append(["合约", "成交序号", "买/卖", "成交价", "开仓价", "手数", "昨结算价", "平仓盈亏", "原成交序号", "实际成交日期"])
    for i in range(1, 5):
        wb.active.append(["FU2611", f"{i:08d}", "卖", 2910, 2900, 1, 2905, 100.0, "0", "2026-10-21"])
    buf = io.BytesIO()
    wb.save(buf)
    try:
        review.analyze(buf.getvalue(), "old.xlsx")
    except review.ReviewParseError as e:
        assert "成交明细" in str(e)
    else:
        raise AssertionError("只有平仓明细的文件应被拒绝")


# ---- 横坐标：固定的四个交易时段 --------------------------------------------------
# 夜盘 21:00-23:00 → 早盘一 09:00-10:15 → 早盘二 10:30-11:30 → 午盘 13:30-15:00
def _ts(s):
    return pd.Timestamp(s)


# ---- 「实际成交日期」是交易日：夜盘的日期要还原成前一天 --------------------------------
# 用户的 Excel：以 10-16 为例，当天所有行的日期都是 10-16，但 21:00~23:00 那批实际是 10-15 晚上，其余才是 10-16。
def _rows_user_excel():
    d15, d16 = "2026-10-15", "2026-10-16"
    return [
        _row(1, "FU2611", "21:30:00", "买", "开", 2900, 1, 2.5, None, d15),    # 交易日 10-15 的夜盘（真实 10-14 晚上）
        _row(2, "FU2611", "22:10:00", "卖", "平", 2910, 1, 2.5, 100.0, d15),
        _row(3, "FU2611", "09:30:00", "买", "开", 2910, 1, 2.5, None, d15),
        _row(4, "FU2611", "10:00:00", "卖", "平", 2920, 1, 2.5, 100.0, d15),
        _row(5, "FU2611", "21:20:00", "买", "开", 2920, 1, 2.5, None, d16),    # 交易日 10-16 的夜盘：Excel 标 10-16，真实是 10-15 晚上
        _row(6, "FU2611", "22:30:00", "卖", "平", 2930, 1, 2.5, 100.0, d16),
        _row(7, "FU2611", "09:20:00", "买", "开", 2930, 1, 2.5, None, d16),
        _row(8, "FU2611", "10:40:00", "卖", "平", 2940, 1, 2.5, 100.0, d16),
        _row(9, "FU2611", "14:00:00", "买", "开", 2940, 1, 2.5, None, d16),
        _row(10, "FU2611", "14:20:00", "卖", "平", 2950, 1, 2.5, 100.0, d16),
    ]


def test_restore_real_time_moves_only_the_evening_back_one_day():
    s = pd.Series(pd.to_datetime(["2026-10-16 21:00:00", "2026-10-16 22:30:00", "2026-10-16 23:59:59",
                                  "2026-10-16 20:00:00", "2026-10-16 19:59:59",
                                  "2026-10-16 00:30:00", "2026-10-16 09:20:00", "2026-10-16 14:20:00", None]))
    out = review._restore_real_time(s)
    assert [str(t)[:19] if pd.notna(t) else None for t in out] == [
        "2026-10-15 21:00:00", "2026-10-15 22:30:00", "2026-10-15 23:59:59",   # 晚上：往前挪一天
        "2026-10-15 20:00:00", "2026-10-16 19:59:59",                           # 20:00 是分界：20:00 挪，19:59:59 不挪
        "2026-10-16 00:30:00", "2026-10-16 09:20:00", "2026-10-16 14:20:00",   # 凌晨（夜盘延续）、白天：不变
        None,                                                                    # 空值保持空
    ]


def test_user_excel_night_session_is_restored_to_the_previous_evening():
    r = review.analyze(make_detail_sheet(_rows_user_excel()), "s.xlsx")
    times = {(row.symbol, row.volume, str(row.time)[:19]) for row in r.records.itertuples()}
    # Excel 里 10-16 的 21:20 / 22:30 其实是 10-15 晚上；白天的 09:20 / 10:40 / 14:20 仍是 10-16
    assert ("FU2611", 1, "2026-10-15 21:20:00") in times and ("FU2611", 1, "2026-10-15 22:30:00") in times
    assert ("FU2611", 1, "2026-10-16 09:20:00") in times and ("FU2611", 1, "2026-10-16 14:20:00") in times
    assert not any(t.startswith("2026-10-16 21:") or t.startswith("2026-10-16 22:") for _, _, t in times), "夜盘不能还留在 10-16"


def test_user_excel_does_not_invent_an_extra_trading_day():
    # 回归：夜盘被当成真实日历日期后又被“夜盘属于下一个交易日”加了一天，凭空多出一个没有数据的 10-17
    c = review.build_curve(review.analyze(make_detail_sheet(_rows_user_excel()), "s.xlsx").records, include_fee=False)
    days = sorted({s["day"] for s in c["segments"]})
    assert days == ["2026-10-15", "2026-10-16"], days
    night16 = next(s for s in c["segments"] if s["day"] == "2026-10-16" and s["key"] == "night")
    assert night16["start"] == "2026-10-15 21:00:00", "10-16 交易日的夜盘从 10-15 晚上 21:00 开始"
    assert night16["end"] == "2026-10-15 23:00:00"


def test_user_excel_each_trade_lands_in_the_right_trading_day_and_session():
    c = review.build_curve(review.analyze(make_detail_sheet(_rows_user_excel()), "s.xlsx").records, include_fee=False)
    where = {}
    for d, x in zip(c["details"][1:], c["xs"][1:]):
        seg = next(s for s in c["segments"] if s["x0"] - 1e-6 <= x <= s["x1"] + 1e-6)
        where[d["time"][5:16]] = (seg["day"], seg["name"])
    assert where == {
        "10-14 22:10": ("2026-10-15", "夜盘"),
        "10-15 10:00": ("2026-10-15", "早盘（上）"),
        "10-15 22:30": ("2026-10-16", "夜盘"),      # 10-16 交易日的夜盘，真实时间是 10-15 晚上
        "10-16 10:40": ("2026-10-16", "早盘（下）"),
        "10-16 14:20": ("2026-10-16", "午盘"),
    }, where


def test_user_excel_date_range_filter_uses_the_trading_day_like_the_excel_column():
    # 用户在界面上选“10-16”，心里想的是 Excel 日期列里的 10-16：它包含这个交易日的夜盘（真实在 10-15 晚上）
    r = review.analyze(make_detail_sheet(_rows_user_excel()), "s.xlsx")
    # 期望值由价格独立算出（每手 10）：(卖价 - 买价) × 手数 × 10
    d16 = review.build_curve(r.records, start="2026-10-16", end="2026-10-16", include_fee=False)
    assert [x["time"][5:16] for x in d16["details"][1:]] == ["10-15 22:30", "10-16 10:40", "10-16 14:20"]
    assert d16["stats"]["totalPnl"] == 100.0 + 100.0 + 100.0, "夜盘（2930-2920）+100 不能漏"
    d15 = review.build_curve(r.records, start="2026-10-15", end="2026-10-15", include_fee=False)
    assert [x["time"][5:16] for x in d15["details"][1:]] == ["10-14 22:10", "10-15 10:00"]
    assert d15["stats"]["totalPnl"] == (2910 - 2900) * 10 + (2920 - 2910) * 10
    # 两个交易日加起来 = 全部，没有重复也没有遗漏
    both = review.build_curve(r.records, start="2026-10-15", end="2026-10-16", include_fee=False)
    assert both["stats"]["totalPnl"] == d15["stats"]["totalPnl"] + d16["stats"]["totalPnl"] == 500.0
    # 选一天以外的范围：真实在 10-15 晚上但属于 10-16 的夜盘，不会因为“10-15”被算进 10-15
    assert review.build_curve(r.records, end="2026-10-14", include_fee=False)["points"] == []


def test_upload_start_end_are_trading_days_matching_the_excel_date_column():
    # 前端日期选择器用这两个值限定可选日期：必须是 Excel 里真实存在的日期（交易日），
    # 不能是夜盘还原后的 10-14（文件里没有这个日期）
    r = review.analyze(make_detail_sheet(_rows_user_excel()), "s.xlsx")
    assert r.start[:10] == "2026-10-15" and r.end[:10] == "2026-10-16", (r.start, r.end)


def test_user_excel_cumulative_curve_follows_the_axis_order_not_the_clock():
    # 累计盈亏要沿着图从左到右累加：10-15 的白天（10:00）先于 10-16 的夜盘（10-15 22:30），
    # 虽然按钟点 10-15 22:30 比 10-15 10:00 晚——它属于下一个交易日，排在后面
    c = review.build_curve(review.analyze(make_detail_sheet(_rows_user_excel()), "s.xlsx").records, include_fee=False)
    assert [d["time"][5:16] for d in c["details"][1:]] == ["10-14 22:10", "10-15 10:00", "10-15 22:30", "10-16 10:40", "10-16 14:20"]
    assert [p[1] for p in c["points"][1:]] == [100.0, 200.0, 300.0, 400.0, 500.0]
    assert c["xs"] == sorted(c["xs"]), "横轴从左到右，累计盈亏的顺序和它一致"


def test_user_excel_night_continuing_past_midnight_stays_in_order_even_if_rows_are_shuffled():
    # 夜盘延续到凌晨：Excel 里 22:30、23:20、00:40 都标同一个交易日 10-16。
    # 真实顺序是 10-15 22:30 → 10-15 23:20 → 10-16 00:40；按表里的“日期+钟点”排会把 00:40 排到最前面（顺序反了）
    d16 = "2026-10-16"
    rows = [
        _row(1, "FU2611", "00:40:00", "买", "开", 2910, 1, 2.5, None, d16),     # 故意把凌晨的行放在最前面
        _row(2, "FU2611", "00:50:00", "卖", "平", 2915, 1, 2.5, 50.0, d16),
        _row(3, "FU2611", "22:10:00", "买", "开", 2900, 1, 2.5, None, d16),
        _row(4, "FU2611", "22:30:00", "卖", "平", 2910, 1, 2.5, 100.0, d16),
        _row(5, "FU2611", "09:20:00", "买", "开", 2915, 1, 2.5, None, d16),
        _row(6, "FU2611", "09:50:00", "卖", "平", 2920, 1, 2.5, 50.0, d16),
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    assert [d["time"][5:16] for d in c["details"][1:]] == ["10-15 22:30", "10-16 00:50", "10-16 09:50"]
    assert [p[1] for p in c["points"][1:]] == [100.0, 150.0, 200.0]


def test_session_of_covers_all_four_sessions_and_boundaries():
    names = [s["name"] for s in review.SESSIONS]
    cases = {
        "2026-10-21 21:00:00": "夜盘", "2026-10-21 22:59:59": "夜盘",
        "2026-10-22 09:00:00": "早盘（上）", "2026-10-22 10:15:00": "早盘（上）",
        "2026-10-22 10:30:00": "早盘（下）", "2026-10-22 11:30:00": "早盘（下）",
        "2026-10-22 13:30:00": "午盘", "2026-10-22 15:00:00": "午盘",
    }
    for t, want in cases.items():
        assert names[review.session_of(_ts(t))] == want, (t, want)


def test_session_of_assigns_out_of_session_trades_to_the_nearest_session_without_dropping():
    names = [s["name"] for s in review.SESSIONS]
    cases = {
        "2026-10-22 08:59:00": "早盘（上）",   # 集合竞价，略早于开盘
        "2026-10-22 10:19:00": "早盘（上）",   # 两场之间的 15 分钟休息：离 10:15 更近
        "2026-10-22 10:28:00": "早盘（下）",   # 离 10:30 更近
        "2026-10-22 11:31:00": "早盘（下）",   # 收盘后撮合延迟
        "2026-10-22 12:30:00": "午盘",     # 午休正中间，两边一样远：取后一个
        "2026-10-22 15:05:00": "午盘",
        "2026-10-22 18:00:00": "午盘",     # 日盘结束后、夜盘开始前：跟前面的日盘走，不能被夜盘“抢走”
    }
    for t, want in cases.items():
        assert names[review.session_of(_ts(t))] == want, (t, want)


def test_night_session_extends_past_midnight_and_belongs_to_the_next_trading_day():
    # 周三晚 21:30 的夜盘属于周四的交易日；夜盘延续到凌晨（有的品种到 02:30），跨午夜仍是同一个夜盘、同一个交易日
    for t in ("2026-10-21 21:30:00", "2026-10-21 23:20:00", "2026-10-22 00:00:00", "2026-10-22 00:30:00", "2026-10-22 02:20:00"):
        assert review.SESSIONS[review.session_of(_ts(t))]["key"] == "night", t
        assert review.trading_day(_ts(t)) == _ts("2026-10-22"), t
    # 同一天白天不是夜盘
    assert review.trading_day(_ts("2026-10-22 09:15:00")) == _ts("2026-10-22")
    assert review.SESSIONS[review.session_of(_ts("2026-10-22 09:15:00"))]["key"] == "am1"


def test_session_axis_always_has_all_four_segments_per_trading_day_in_the_right_order():
    xs, segs = review.session_axis([_ts("2026-10-21 21:30:05"), _ts("2026-10-22 09:15:00"), _ts("2026-10-22 14:30:00")])
    assert [s["name"] for s in segs] == ["夜盘", "早盘（上）", "早盘（下）", "午盘"], "只有一个交易日：固定四段，哪怕早盘二没有成交"
    assert all(s["day"] == "2026-10-22" for s in segs)
    # 段宽 = 真实时长：夜盘 120、早盘一 75、早盘二 60、午盘 90；段与段之间留 SESSION_GAP_WIDTH
    assert [round(s["x1"] - s["x0"]) for s in segs] == [120, 75, 60, 90]
    for a, b in zip(segs, segs[1:]):
        assert abs(b["x0"] - a["x1"] - review.SESSION_GAP_WIDTH) < 1e-6
    # 段对应的真实起止时刻：夜盘从交易日的前一天 21:00 开始
    assert segs[0]["start"] == "2026-10-21 21:00:00" and segs[0]["end"] == "2026-10-21 23:00:00"
    assert segs[3]["start"] == "2026-10-22 13:30:00" and segs[3]["end"] == "2026-10-22 15:00:00"


def test_session_axis_places_points_proportionally_inside_their_segment():
    xs, segs = review.session_axis([_ts("2026-10-21 21:30:05"), _ts("2026-10-21 22:10:30"),
                                    _ts("2026-10-22 09:15:00"), _ts("2026-10-22 14:30:00")])
    night, am1, am2, pm = segs
    # 夜盘内部：21:30:05 比开盘 21:00 晚 30.083 分钟，22:10:30 晚 70.5 分钟
    assert abs((xs[0] - night["x0"]) - 30.0833) < 0.01 and abs((xs[1] - night["x0"]) - 70.5) < 0.01
    assert abs((xs[2] - am1["x0"]) - 15.0) < 1e-6        # 09:15 比 09:00 晚 15 分钟
    assert abs((xs[3] - pm["x0"]) - 60.0) < 1e-6         # 14:30 比 13:30 晚 60 分钟
    assert xs == sorted(xs), "先后顺序保持：夜盘 → 早盘 → 午盘"


def test_session_axis_out_of_session_trades_stick_to_the_segment_boundary_not_dropped():
    xs, segs = review.session_axis([_ts("2026-10-22 08:59:00"), _ts("2026-10-22 10:19:00"), _ts("2026-10-22 11:31:00"),
                                    _ts("2026-10-22 15:05:00")])
    am1, am2, pm = segs[1], segs[2], segs[3]
    assert len(xs) == 4, "一个点都不能丢"
    assert abs(xs[0] - am1["x0"]) < 1e-6, "08:59（开盘前）贴到早盘一的起点"
    assert abs(xs[1] - am1["x1"]) < 1e-6, "10:19（两场之间）贴到早盘一的终点"
    assert abs(xs[2] - am2["x1"]) < 1e-6, "11:31（收盘后）贴到早盘二的终点"
    assert abs(xs[3] - pm["x1"]) < 1e-6, "15:05（收盘后）贴到午盘的终点"


def test_session_axis_night_past_midnight_continues_after_23_00():
    xs, segs = review.session_axis([_ts("2026-10-26 22:40:00"), _ts("2026-10-26 23:20:00"),
                                    _ts("2026-10-27 00:00:00"), _ts("2026-10-27 00:30:00"), _ts("2026-10-27 09:40:00")])
    night = segs[0]
    assert night["start"] == "2026-10-26 21:00:00"
    # 夜盘段宽按 21:00-23:00 的 120 分钟画；23:00 之后的延续（23:20、00:00、00:30）超出了段，贴到段的终点
    assert abs(xs[0] - (night["x0"] + 100)) < 1e-6           # 22:40 比 21:00 晚 100 分钟
    assert all(abs(x - night["x1"]) < 1e-6 for x in xs[1:4]), "23:20 / 00:00 / 00:30 属于同一个夜盘，贴在夜盘末尾"
    assert xs[4] > night["x1"], "09:40 在早盘一，排在夜盘之后"


def test_session_axis_multiple_trading_days_each_gets_four_segments():
    xs, segs = review.session_axis([_ts("2026-10-12 09:30:00"), _ts("2026-10-13 10:40:00"), _ts("2026-10-14 13:40:00")])
    assert len(segs) == 12 and [s["day"] for s in segs[::4]] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert xs == sorted(xs)
    # 每个交易日的四段宽度一致，总轴长 = 3 天 × (345 分钟 + 4 个间隔) - 末尾多余的间隔
    assert abs(segs[-1]["x1"] - (3 * (120 + 75 + 60 + 90) + (12 - 1) * review.SESSION_GAP_WIDTH)) < 1e-6


def test_session_axis_empty_input():
    assert review.session_axis([]) == ([], [])


def test_curve_returns_session_x_aligned_with_points_and_segments_for_every_shape():
    r = review.analyze(make_detail_sheet(ROWS_D), "s.xlsx")
    c = review.build_curve(r.records, include_fee=False)
    assert len(c["xs"]) == len(c["points"]) == len(c["details"]) == 6, "xs 与 points、details 一一对应"
    assert c["xs"] == sorted(c["xs"])
    assert c["segments"][0]["x0"] == review.AXIS_PAD and "gaps" not in c, "整条轴从 AXIS_PAD 开始（段的起点，不是点的位置）；旧的 gaps 已删除"
    assert all(s["x0"] >= 0 for s in c["segments"]) and c["xs"][0] > 0, "不能出现负坐标"
    # 一个交易日（10-22）：固定四段，夜盘在最前
    assert [s["name"] for s in c["segments"]] == ["夜盘", "早盘（上）", "早盘（下）", "午盘"]
    assert c["segments"][0]["start"] == "2026-10-21 21:00:00", "夜盘从前一天 21:00 开始"
    # 所有点都落在某一段之内（包含边界）：不丢点
    for x in c["xs"][1:]:
        assert any(s["x0"] - 1e-6 <= x <= s["x1"] + 1e-6 for s in c["segments"]), x
    # 空结果也要带上同样的键，前端不能拿到 undefined
    for empty in (review.build_curve(r.records, start="2027-01-01"),
                  review.build_curve(review.analyze(make_detail_sheet(
                      [_row(1, "FU2611", "09:00:00", "买", "开", 2900, 1, 2.5, None, D)]), "o.xlsx").records)):
        assert empty["points"] == [] and empty["xs"] == [] and empty["segments"] == [] and empty["details"] == []


def test_start_point_never_overlaps_the_first_trade_even_at_the_very_start_of_the_axis():
    # 第一笔恰好在夜盘 21:00:00（整条轴的最左端）：起点仍然要严格在它左边，否则悬停永远只命中起点
    rows = [
        _row(1, "FU2611", "20:59:00", "买", "开", 2900, 1, 2.5, None, N),
        _row(2, "FU2611", "21:00:00", "卖", "平", 2910, 1, 2.5, 100.0, N),
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    assert c["xs"][0] < c["xs"][1], c["xs"]
    assert c["xs"][1] - c["xs"][0] >= review.START_POINT_OFFSET - 1e-6


def test_every_point_survives_compression_even_with_unusual_hours():
    # 回归：写死“21:00~23:00、09:00~11:30、13:30~15:00”会丢掉凌晨（夜盘到 02:30）和午休附近的成交。
    # 时段由数据推出，所以这些点都必须保留
    rows = [
        _row(1, "FU2611", "21:10:00", "买", "开", 2900, 1, 2.5, None, N),
        _row(2, "FU2611", "23:50:00", "卖", "平", 2910, 1, 2.5, 100.0, N),
        _row(3, "FU2611", "00:40:00", "买", "开", 2910, 1, 2.5, None, D),
        _row(4, "FU2611", "02:20:00", "卖", "平", 2915, 1, 2.5, 50.0, D),     # 夜盘延伸到凌晨 02:20
        _row(5, "FU2611", "12:10:00", "买", "开", 2915, 1, 2.5, None, D),
        _row(6, "FU2611", "12:50:00", "卖", "平", 2920, 1, 2.5, 50.0, D),     # 午休时段里的成交
    ]
    c = review.build_curve(review.analyze(make_detail_sheet(rows), "s.xlsx").records, include_fee=False)
    assert [d["time"][11:16] for d in c["details"][1:]] == ["23:50", "02:20", "12:50"], "凌晨和午休的成交不能丢"
    assert len(c["xs"]) == 4


def test_curve_details_align_with_points():
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)
    pts, det = c["points"], c["details"]
    assert len(det) == len(pts) == 6 and det[0] is None
    assert round(sum(d["pnl"] for d in det[1:]), 2) == pts[-1][1] == GROSS_D
    # 每笔都带悬停需要的基础信息：时间、合约、方向、手数、价格、盈亏、手续费
    for k in ("time", "symbol", "direction", "lots", "price", "pnl", "fee", "fills"):
        assert k in det[1], k


def test_detail_cell_types_numbers_dates_and_text():
    # 真实 Excel 里：时间可能是 time 对象、文本；日期可能是 date/datetime；价格、手数可能是文本
    import datetime as dt
    rows = [
        # 日期标的是交易日 10-22；夜盘 21:30:05 真实发生在 10-21 晚上。日期单元格是 date / datetime 对象时也要还原
        _row(1, "FU2611", dt.time(21, 25, 5), "买", "开", 2900, 1, 2.5, None, dt.date(2026, 10, 22)),
        _row(2, "FU2611", "21:30:05", "卖", "平", "2910", "1", 2.5, 100.0, dt.datetime(2026, 10, 22)),
    ]
    r = review.analyze(make_detail_sheet(rows), "s.xlsx")
    c = review.build_curve(r.records, include_fee=False)
    assert c["trades"] == 1 and c["stats"]["totalPnl"] == 100.0
    assert c["details"][1]["time"] == "2026-10-21 21:30:05"


def test_no_usable_sheet_error_names_the_closest_sheet():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "资金状况"
    wb.active.append(["项目", "金额"])
    s = wb.create_sheet("成交记录")
    s.append(["合约", "成交序号", "买/卖", "成交额"])   # 缺 成交价/手数/日期
    buf = io.BytesIO()
    wb.save(buf)
    try:
        review.read_trades(buf.getvalue(), "x.xlsx")
    except review.ReviewParseError as e:
        msg = str(e)
        assert "没有识别到必需的列" in msg and "成交记录" in msg and "合约" in msg
    else:
        raise AssertionError("应抛出 ReviewParseError")


def test_old_format_still_works_on_second_sheet():
    # 回归：任意一张表里有可识别的逐笔成交都能读到（旧的成交明细格式，非结算单）
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "说明"
    wb.active.append(["本文件由某某软件导出"])
    s = wb.create_sheet("成交明细")
    s.append(HEADER_A)
    for r in ROWS_A[:2]:
        s.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    r = review.analyze(buf.getvalue(), "old.xlsx")
    assert review.build_curve(r.records, include_fee=False)["stats"]["totalPnl"] == 400.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS ", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL ", t.__name__, "->", repr(e))
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


def test_curve_returns_open_marks_aligned_with_axis_and_not_in_points():
    # 开仓不进 points/details/stats，只作为 openMarks 返回，横坐标与平仓用同一条轴（xs 递增、落在某个段里）
    c = review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, include_fee=False)
    assert len(c["points"]) == len(c["details"]) == 6
    marks = c["openMarks"]
    assert [m["time"][5:19] for m in marks] == ["10-21 21:05:00", "10-21 21:25:05", "10-22 09:00:00",
                                                "10-22 09:01:00", "10-22 13:40:00", "10-22 14:50:00"]
    assert all(k in marks[0] for k in ("time", "x", "symbol", "direction", "lots", "price"))
    assert [m["x"] for m in marks] == sorted(m["x"] for m in marks)
    for m in marks:
        assert any(s["x0"] - 1e-6 <= m["x"] <= s["x1"] + 1e-6 for s in c["segments"]), m
    assert review.build_curve(review.analyze(make_detail_sheet(ROWS_D), "s.xlsx").records, start="2027-01-01")["openMarks"] == []
