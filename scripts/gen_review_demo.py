"""生成「交易复盘」的调试用假数据 -> 后端的复盘文件夹（与你正常导入的 Excel 同一目录）。

用法：
    python scripts/gen_review_demo.py                 # 生成 4 个月的数据，每月一个文件
    python scripts/gen_review_demo.py --months 6      # 改月数
    python scripts/gen_review_demo.py --seed 7        # 换一组随机数据
    python scripts/gen_review_demo.py --clean         # 只删除之前生成的假数据文件，不生成
    python scripts/gen_review_demo.py --out some_dir  # 只写到指定目录

文件名统一以 DEMO_ 开头（DEMO_交易明细_2026-07.xlsx），--clean 只删这个前缀，不会碰你真正导入的文件。

写到哪里：后端的复盘文件夹是「它的 exe 所在目录/review_files」。默认写入当前存在的这些位置，并逐个打印出来，
每个目录里你自己导入的文件也会列出来，方便确认写对了地方：
    npm run dev             -> src-tauri/target/debug/backend-dist/review_files
    tauri build             -> src-tauri/target/release/backend-dist/review_files
都找不到时（还没运行过 npm run dev），请先运行一次，或用 --out 指定目录。
安装版不在仓库里，请用 --out 指定安装目录下的 backend-dist/review_files。
直接 `python backend/app.py` 读的是项目根目录的 review_files/，这里不会写它；需要的话用 --out review_files。
这些目录都在 .gitignore 里（src-tauri/target/、review_files/），不会被提交。

格式与期货公司结算单的「成交明细」一致（见 backend/core/review.py 的 COLUMN_ALIASES / DETAIL_SHEET_NAMES）：
  - 多个工作表：「资金状况」（无关，用来测试选表逻辑）+「成交明细」（真正被解析）
  - 成交明细顶部有标题 / 客户号 / 统计区间，表头在后面，末尾有「合计」行
  - 夜盘（21:00-23:00）的「实际成交日期」写的是它所属的交易日（不是真实日历日），和真实结算单一致
  - 同一时刻的多笔平仓（用来测试合并为一笔）
以上都是故意设计的边界情况，不是纯随机。
"""
import argparse
import calendar
import datetime as dt
import os
import random
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = "DEMO_交易明细_"

# 成交明细表头：与真实结算单一致（带换行），review.py 会去空白后匹配别名
HEADER = ["合约", "成交序号", "成交时间", "买/卖", "投机（一\n般）/套保/\n套利", "成交价", "手数", "成交额",
          "开/平", "手续费", "平仓盈亏", "实际成交日\n期"]

# 品种：(合约, 起始价, 合约乘数, 最小变动价位, 单手手续费(开/平各收), 日波动幅度(价格的比例), 昼夜是否有夜盘)
PRODUCTS = [
    ("FU2701", 2900.0, 10, 1.0, 2.5, 0.011, True),
    ("rb2701", 3300.0, 10, 1.0, 2.0, 0.009, True),
    ("cu2612", 78000.0, 5, 10.0, 6.0, 0.007, True),
    ("ag2612", 8050.0, 15, 1.0, 3.0, 0.012, True),
    ("IF2612", 3900.0, 300, 0.2, 23.0, 0.010, False),   # 中金所无夜盘
]

# 单笔交易的最大手数：按「一手的合约价值」限制，避免 IF（一手约 117 万）一笔就盈亏上万、把曲线带偏。
# 其余品种一手价值在 3~12 万，不限制。
MAX_LOTS = {"IF2612": 1, "cu2612": 3}


# 后端的「复盘文件夹」是它的 exe 所在目录下的 review_files（backend/config.py 的 BASE_DIR）。
# `npm run dev` 时 Tauri 把 src-tauri/backend-dist 复制到 src-tauri/target/debug/backend-dist 再启动 exe，
# 所以实际读写的是下面这个目录；`tauri build` 的 release 同理。
# 不写项目根目录的 review_files/：只有直接 `python backend/app.py` 才会读它，日常用不到，写了只会多出一个没人读的目录
# （要这样用，请自己指定 --out 或环境变量 REVIEW_FILES_DIR）。
def candidate_dirs():
    return [
        ("npm run dev (debug)", os.path.join(ROOT, "src-tauri", "target", "debug", "backend-dist", "review_files")),
        ("tauri build (release)", os.path.join(ROOT, "src-tauri", "target", "release", "backend-dist", "review_files")),
    ]


def target_dirs(out=None):
    """要写入的目录列表：--out > 环境变量 REVIEW_FILES_DIR > 自动探测。

    自动探测：只写「你确实运行过的」那种后端——它的 backend-dist 目录已经存在才写，不会凭空创建目录。
    一个都找不到时返回空列表，由调用方提示先运行一次 `npm run dev`。
    """
    if out:
        return [("--out", out)]
    env = os.environ.get("REVIEW_FILES_DIR")
    if env:
        return [("REVIEW_FILES_DIR", env)]
    return [(label, path) for label, path in candidate_dirs() if os.path.isdir(os.path.dirname(path))]


def trading_days(year, month):
    """当月的工作日（跳过周末；再随机空出几天当「没交易」，由调用方决定）。"""
    last = calendar.monthrange(year, month)[1]
    return [dt.date(year, month, d) for d in range(1, last + 1) if dt.date(year, month, d).weekday() < 5]


def _round_tick(price, tick):
    return round(round(price / tick) * tick, 4)


class Maker:
    """维护每个合约的「当前价」随机游走，并逐笔生成成交行。"""

    def __init__(self, rng):
        self.rng = rng
        self.price = {p[0]: p[1] for p in PRODUCTS}
        self.seq = 0
        self.rows = []     # 每项：(排序用真实时刻, 行)

    def _next_seq(self):
        self.seq += 1
        return f"{self.seq:08d}"

    def drift(self, spec):
        sym, _p0, _m, tick, _f, vol, _n = spec
        self.price[sym] = max(tick * 10, self.price[sym] * (1 + self.rng.gauss(0, vol / 6)))
        return self.price[sym]

    def trade(self, spec, trade_day, open_t, close_t, side, lots, win_bias, splits=1, night=False):
        """一笔完整交易：开仓一次，平仓可分 splits 笔、同一时刻成交（用来测试合并）。

        night=True 时 open_t / close_t 是 21:00-23:00 的时分秒，「实际成交日期」写 trade_day（交易日），
        而不是前一天的真实日期——这是结算单的真实口径。
        """
        sym, _p0, mult, tick, fee_per, vol, _n = spec
        r = self.rng
        entry = _round_tick(self.drift(spec), tick)
        # 盈亏方向偏置：win_bias>0 偏盈利；幅度约为日波动的 1/6（日内一笔的典型波动），并带少量大亏损（尾部）
        move = abs(r.gauss(0, entry * vol / 6))
        sign = 1 if r.random() < 0.5 + win_bias else -1
        if r.random() < 0.06:                       # 6% 概率一笔大亏（制造回撤）
            sign, move = -1, move * 3
        pnl_per_unit = sign * move
        exit_px = _round_tick(entry + (pnl_per_unit if side == "买" else -pnl_per_unit), tick)
        unit_pnl = (exit_px - entry) if side == "买" else (entry - exit_px)
        close_side = "卖" if side == "买" else "买"
        date_str = trade_day.strftime("%Y-%m-%d")

        # 开仓
        self.rows.append((self._mk_time(trade_day, open_t, night), [
            sym, self._next_seq(), open_t, side, "投机", entry, lots, round(entry * lots * mult, 2),
            "开", round(fee_per * lots, 2), None, date_str]))
        # 平仓：splits 笔同一时刻成交，手数拆开，价格略有差异（滑一两个 tick）
        remain, parts = lots, []
        for i in range(splits):
            n = remain if i == splits - 1 else max(1, remain // (splits - i))
            parts.append(n)
            remain -= n
        for n in parts:
            px = _round_tick(exit_px + r.choice((-1, 0, 0, 1)) * tick, tick) if splits > 1 else exit_px
            u = (px - entry) if side == "买" else (entry - px)
            self.rows.append((self._mk_time(trade_day, close_t, night), [
                sym, self._next_seq(), close_t, close_side, "投机", px, n, round(px * n * mult, 2),
                "平", round(fee_per * n, 2), round(u * n * mult, 2), date_str]))

    @staticmethod
    def _mk_time(trade_day, hms, night):
        h, m, s = map(int, hms.split(":"))
        real_day = trade_day - dt.timedelta(days=1) if night else trade_day
        if night and real_day.weekday() == 4 + 1:      # 周六：夜盘不会发生在周六，这里只是防御
            real_day -= dt.timedelta(days=1)
        return dt.datetime.combine(real_day, dt.time(h, m, s))


def _hms(r, lo, hi):
    """lo/hi 为 (时, 分)；返回区间内随机的 HH:MM:SS。"""
    a, b = lo[0] * 60 + lo[1], hi[0] * 60 + hi[1]
    mins = r.randint(a, b)
    return f"{mins // 60:02d}:{mins % 60:02d}:{r.randint(0, 59):02d}"


def _add_minutes(hms, minutes):
    h, m, s = map(int, hms.split(":"))
    t = h * 3600 + m * 60 + s + minutes * 60
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def make_month(year, month, rng, maker, idle_prob=0.18):
    """生成当月所有成交行。工作日里随机空出一部分当「没交易」。"""
    days = trading_days(year, month)
    for day in days:
        if rng.random() < idle_prob:
            continue
        # 这个交易日交易哪几个品种（1-3 个）
        for spec in rng.sample(PRODUCTS, rng.randint(1, 3)):
            has_night = spec[6]
            for _ in range(rng.randint(1, 3)):
                lots = min(rng.choice((1, 1, 2, 2, 3, 4, 6)), MAX_LOTS.get(spec[0], 99))
                side = rng.choice(("买", "卖"))
                bias = rng.uniform(-0.05, 0.08)       # 略偏盈利，曲线有起有伏而不是一路向下
                splits = rng.choice((1, 1, 1, 2, 3)) if lots >= 2 else 1
                if has_night and rng.random() < 0.25 and day.weekday() != 0:
                    # 夜盘：21:00-22:50 开，平仓晚 5-60 分钟；周一没有前一晚的夜盘（周日不开），所以排除
                    open_t = _hms(rng, (21, 0), (22, 30))
                    close_t = _add_minutes(open_t, rng.randint(5, 40))
                    maker.trade(spec, day, open_t, close_t, side, lots, bias, splits, night=True)
                else:
                    open_t = _hms(rng, (9, 0), (14, 20))
                    close_t = _add_minutes(open_t, rng.randint(2, 70))
                    # 不跨过 15:00 收盘
                    if close_t > "14:59:59":
                        close_t = "14:59:" + f"{rng.randint(0, 59):02d}"
                    maker.trade(spec, day, open_t, close_t, side, lots, bias, splits, night=False)


def write_workbook(path, rows, year, month):
    wb = openpyxl.Workbook()
    other = wb.active
    other.title = "资金状况"            # 排在最前、与成交无关：测试「选哪张表」的逻辑
    other.append(["期货结算单（调试用假数据）"])
    other.append(["项目", "金额"])
    other.append(["上日结存", 1000000.0])
    other.append(["平仓盈亏", 99999.0])  # 故意放一个很显眼、不该被当成成交盈亏的数字
    other.append(["手续费", 88888.0])

    s = wb.create_sheet("成交明细")
    last = calendar.monthrange(year, month)[1]
    s.append(["成交明细 Transaction Record（调试用假数据，非真实交易）"])
    s.append(["客户号 Client ID：DEMO0001"])
    s.append([f"统计区间：{year}-{month:02d}-01 ~ {year}-{month:02d}-{last:02d}"])
    s.append([])
    s.append(HEADER)
    total_fee = total_pnl = 0.0
    for _ts, row in rows:
        s.append(row)
        total_fee += row[9]
        total_pnl += row[10] or 0.0
    s.append(["合计 Total", None, None, None, None, None, None, None, None, round(total_fee, 2), round(total_pnl, 2), None])
    for col, width in zip("ABCDEFGHIJKL", (10, 11, 11, 7, 12, 10, 7, 14, 7, 10, 12, 13)):
        s.column_dimensions[col].width = width
    wb.save(path)


def months_back(count, today=None):
    """从上个月起往前数 count 个月，返回 [(year, month), ...]，从早到晚。"""
    today = today or dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(count):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return list(reversed(out))


def clean(directory):
    removed = []
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            if name.startswith(PREFIX) and name.lower().endswith((".xlsx", ".xls", ".csv")):
                os.remove(os.path.join(directory, name))
                removed.append(name)
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成交易复盘调试用假数据")
    ap.add_argument("--months", type=int, default=4, help="生成几个月（从上个月往前数），默认 4")
    ap.add_argument("--seed", type=int, default=2026, help="随机种子，相同种子生成相同数据，默认 2026")
    ap.add_argument("--out", default=None,
                    help="输出目录（只写这一处）。不指定时自动写入 npm run dev / tauri build 的后端数据目录，见脚本顶部说明")
    ap.add_argument("--clean", action="store_true", help="只删除之前生成的 DEMO_ 文件，不生成")
    args = ap.parse_args(argv)

    targets = target_dirs(args.out)
    if not targets:
        print("[demo] 没找到后端的数据目录：src-tauri/target/{debug,release}/backend-dist 都还不存在。\n"
              "[demo] 请先运行一次 `npm run dev`（会生成 debug 目录），或用 --out 指定目录。")
        return 1
    if args.clean:
        for label, directory in targets:
            removed = clean(directory)
            print(f"[demo] ({label}) {directory}")
            print(f"[demo]   已删除 {len(removed)} 个假数据文件" + (f"：{', '.join(removed)}" if removed else ""))
        return 0

    # 先把所有月份生成到内存，再写到每个目标目录：各处内容完全一致
    rng = random.Random(args.seed)
    maker = Maker(rng)
    months = []
    for year, month in months_back(args.months):
        maker.rows = []
        make_month(year, month, rng, maker)
        maker.rows.sort(key=lambda t: t[0])         # 按真实时刻排序（夜盘排在当天白天之前）
        months.append((year, month, list(maker.rows)))

    for label, out in targets:
        os.makedirs(out, exist_ok=True)
        removed = clean(out)       # 先清掉上次生成的，避免重复生成后文件越堆越多
        print(f"[demo] ({label}) {out}" + (f"  （已先清理上次生成的 {len(removed)} 个文件）" if removed else ""))
        for year, month, rows in months:
            path = os.path.join(out, f"{PREFIX}{year}-{month:02d}.xlsx")
            write_workbook(path, rows, year, month)
            print(f"[demo]   {os.path.basename(path)}：{len(rows)} 行")
        others = [n for n in os.listdir(out) if not n.startswith(PREFIX)]
        if others:
            print(f"[demo]   该目录里还有你自己导入的 {len(others)} 个文件，未改动：{', '.join(others)}")
    total_rows = sum(len(r) for _y, _m, r in months)
    print(f"[demo] 共 {len(months)} 个月、{total_rows} 行，已写入 {len(targets)} 个目录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
