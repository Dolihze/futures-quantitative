"""量化监控：跟单引擎。

数据流：被监控账号（ctp_service 的只读监控会话）产生成交回报 -> on_source_trade()
        -> 入队 -> 工作线程按配置计算手数 / 价格 / 风控 -> 通过【主会话】发出限价委托
        -> 追踪委托，超时未成交则撤单（并记录），全部过程写入跟单记录。

安全原则（涉及真实资金）：
  * 默认关闭；必须显式 start()，且 start() 之后才产生的成交才会被跟随（启动时记录基线）。
  * 监控账号只读，本模块永远只通过主会话下单。
  * 任何拿不准的情况（行情缺失、合约未就绪、手数算出 0、风控命中、信号过期）一律放弃并留痕，
    绝不"猜"一个价格或手数去下单。
  * 平仓类信号只平主账号【实际持有】的手数，绝不会因为多平而反向开仓。
  * 同一笔源成交（vt_tradeid）只处理一次。
"""
import math
import threading
import time
import queue
import collections

import ctp_service

# 手数模式
SIZE_RATIO = "ratio"     # 按资金比例：源手数 × (我的权益 / 源权益) × multiplier
SIZE_MULTIPLE = "multiple"  # 固定倍数：源手数 × multiplier
SIZE_FIXED = "fixed"     # 固定手数：每笔成交固定跟 fixed_volume 手
SIZE_MODES = (SIZE_RATIO, SIZE_MULTIPLE, SIZE_FIXED)

# 价格模式（后端只有限价单）
PRICE_MODES = ("counter", "last", "market")

# 跟单记录状态
ST_SUBMITTED = "已委托"
ST_FILLED = "已成交"
ST_PARTIAL = "部分成交"
ST_CANCELLED = "已撤单"
ST_REJECTED = "已拒绝"
ST_SKIPPED = "已跳过"
ST_SIMULATED = "模拟"
ST_FAILED = "失败"

MAX_RECORDS = 500
MAX_LOGS = 300

DEFAULT_CONFIG = {
    "size_mode": SIZE_RATIO,
    "multiplier": 1.0,          # ratio / multiple 模式的倍率
    "fixed_volume": 1,          # fixed 模式的每笔手数
    "price_mode": "counter",
    "order_timeout": 5.0,       # 委托超过该秒数未全部成交则撤单（0 = 不撤）
    "simulate": True,           # 模拟模式：只记录"本应下单"，不真正下单。默认开，防止误触真单
    "max_order_volume": 5,      # 单笔跟单最大手数（0 = 不限）
    "max_position": 10,         # 单合约（多空合计）最大持仓手数（0 = 不限）
    "symbol_whitelist": [],     # 品种白名单（合约代码前缀字母，如 ["rb", "ag"]），空 = 全部
    "daily_loss_limit": 0.0,    # 当日最大亏损（元，正数），权益较启动时回撤超过即熔断；0 = 不启用
    "max_follow_count": 0,      # 当日最多跟单次数（0 = 不限）
    "signal_max_delay": 3.0,    # 信号延迟超过该秒数则丢弃（0 = 不限）
}


def _product_of(symbol):
    """rb2610 -> rb（合约代码里的字母前缀，转小写）。"""
    letters = []
    for ch in symbol:
        if ch.isalpha():
            letters.append(ch)
        else:
            break
    return "".join(letters).lower()


def validate_config(raw):
    """校验并规整配置。返回 (config, error)。不信任前端。"""
    cfg = dict(DEFAULT_CONFIG)
    raw = raw or {}

    def num(key, lo=0.0, hi=None, allow_zero=True):
        v = raw.get(key, cfg[key])
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{key} 必须是数字")
        if not math.isfinite(v) or v < lo or (hi is not None and v > hi) or (not allow_zero and v == 0):
            raise ValueError(f"{key} 超出允许范围")
        return v

    try:
        mode = str(raw.get("size_mode", cfg["size_mode"]))
        if mode not in SIZE_MODES:
            raise ValueError("手数模式不正确")
        cfg["size_mode"] = mode

        cfg["multiplier"] = num("multiplier", 0.0, 100.0, allow_zero=False)
        fv = num("fixed_volume", 0.0, 10000.0, allow_zero=False)
        if fv != int(fv):
            raise ValueError("固定手数必须是整数")
        cfg["fixed_volume"] = int(fv)

        pm = str(raw.get("price_mode", cfg["price_mode"]))
        if pm not in PRICE_MODES:
            raise ValueError("价格模式不正确")
        cfg["price_mode"] = pm

        cfg["order_timeout"] = num("order_timeout", 0.0, 3600.0)
        cfg["simulate"] = bool(raw.get("simulate", cfg["simulate"]))

        for k in ("max_order_volume", "max_position", "max_follow_count"):
            v = num(k, 0.0, 100000.0)
            if v != int(v):
                raise ValueError(f"{k} 必须是整数")
            cfg[k] = int(v)

        cfg["daily_loss_limit"] = num("daily_loss_limit", 0.0, 1e12)
        cfg["signal_max_delay"] = num("signal_max_delay", 0.0, 3600.0)

        wl = raw.get("symbol_whitelist", cfg["symbol_whitelist"])
        if isinstance(wl, str):
            wl = [x for x in wl.replace("，", ",").replace(" ", ",").split(",")]
        cfg["symbol_whitelist"] = sorted({str(x).strip().lower() for x in (wl or []) if str(x).strip()})
    except ValueError as e:
        return None, str(e)
    return cfg, ""


def compute_volume(cfg, src_volume, my_balance, src_balance, remainder=0.0):
    """计算跟单手数。返回 (手数 int, 新的取整余量 float, 说明)。

    取整规则：向下取整，但把被舍掉的小数累积进 remainder，下一笔一并计入——
    这样长期来看跟单总量不会因为每笔都被向下取整而系统性偏小。"""
    if cfg["size_mode"] == SIZE_FIXED:
        return int(cfg["fixed_volume"]), 0.0, f"固定 {cfg['fixed_volume']} 手"

    if cfg["size_mode"] == SIZE_MULTIPLE:
        raw = src_volume * cfg["multiplier"]
        note = f"{src_volume:g} × 倍数 {cfg['multiplier']:g}"
    else:
        if not my_balance or not src_balance or my_balance <= 0 or src_balance <= 0:
            return 0, remainder, "权益数据不可用，无法按资金比例计算"
        ratio = my_balance / src_balance
        raw = src_volume * ratio * cfg["multiplier"]
        note = f"{src_volume:g} × 权益比 {ratio:.4f} × 倍率 {cfg['multiplier']:g}"

    total = raw + remainder
    vol = int(math.floor(total + 1e-9))
    return vol, max(total - vol, 0.0), f"{note} = {raw:.3f}（含余量 {remainder:.3f}）→ {vol} 手"


def classify(trade_offset, trade_direction):
    """把源成交的 (开平, 买卖方向) 转成 action。

    trade_offset: vnpy Offset.value（开 / 平 / 平今 / 平昨）；trade_direction: 多 / 空（买入 / 卖出方向）。
    返回 action（open_long / open_short / close_long / close_short）或 None。"""
    is_open = trade_offset == "开"
    is_close = trade_offset in ("平", "平今", "平昨")
    if not (is_open or is_close):
        return None
    if is_open:
        return "open_long" if trade_direction == "多" else "open_short"
    # 买入平仓 = 平空；卖出平仓 = 平多
    return "close_short" if trade_direction == "多" else "close_long"


class CopyEngine:
    def __init__(self):
        self._lock = threading.RLock()
        self.config = dict(DEFAULT_CONFIG)
        self.running = False
        self.paused_reason = ""          # 非空 = 因风控 / 断连被自动暂停
        self.started_at = 0.0
        self.baseline_ts = 0.0           # 只跟 baseline_ts 之后到达的成交
        self.start_my_balance = None     # 启动时我的权益（每日亏损熔断基准）
        self.follow_count = 0            # 本次运行已发起的跟单次数
        self.seen = set()                # 已处理过的源 vt_tradeid
        self.remainders = collections.defaultdict(float)   # (vt_symbol, action) -> 取整余量
        self.records = collections.deque(maxlen=MAX_RECORDS)   # 最新在左
        self.logs = collections.deque(maxlen=MAX_LOGS)
        self._seq = 0
        self._q = queue.Queue()
        self._worker = None
        self._watch = None
        self._stop_evt = threading.Event()

    # ------------------------------------------------------------------ 日志 / 记录
    def log(self, msg, level="info"):
        entry = {"time": time.strftime("%H:%M:%S"), "level": level, "msg": msg}
        with self._lock:
            self.logs.appendleft(entry)
        print(f"[Copy] {msg}")

    def _new_record(self, **kw):
        with self._lock:
            self._seq += 1
            rec = {"id": self._seq, "time": time.strftime("%H:%M:%S"),
                   "symbol": "", "src_action": "", "src_volume": 0, "src_price": 0,
                   "action": "", "volume": 0, "price": None, "status": "", "message": "",
                   "vt_orderids": [], "traded": 0}
            rec.update(kw)
            self.records.appendleft(rec)
            return rec

    # ------------------------------------------------------------------ 启停
    def start(self, config):
        cfg, err = validate_config(config)
        if err:
            return {"success": False, "message": f"配置不正确：{err}"}
        if not ctp_service.monitor_connected():
            return {"success": False, "message": "请先登录被监控账号"}
        if not cfg["simulate"] and not ctp_service.is_connected():
            return {"success": False, "message": "当前交易账号未连接，无法实盘跟单（可先开启模拟模式）"}
        with self._lock:
            if self.running:
                return {"success": False, "message": "跟单已在运行"}
            self.config = cfg
            self.running = True
            self.paused_reason = ""
            self.started_at = time.time()
            self.baseline_ts = self.started_at     # 基线：此刻之前的成交一律不跟
            self.start_my_balance = ctp_service.my_balance()
            self.follow_count = 0
            self.remainders.clear()
            # 每次运行用全新的停止事件：旧线程只认旧事件，绝不会被新一轮 start() 复活
            self._stop_evt = threading.Event()
            # 清空启动前可能残留在队列里的信号
            try:
                while True:
                    self._q.get_nowait()
            except queue.Empty:
                pass
        self._worker = threading.Thread(target=self._run, args=(self._stop_evt,), daemon=True, name="copy-worker")
        self._worker.start()
        self._watch = threading.Thread(target=self._watchdog, args=(self._stop_evt,), daemon=True, name="copy-watch")
        self._watch.start()
        mode = "【模拟】" if cfg["simulate"] else "【实盘】"
        self.log(f"跟单已启动 {mode}，只跟随此刻之后的新成交", "warn")
        return {"success": True, "message": "跟单已启动" + ("（模拟模式，不会真实下单）" if cfg["simulate"] else "")}

    def stop(self, reason="用户停止"):
        with self._lock:
            was = self.running
            self.running = False
            self._stop_evt.set()
        if was:
            self.log(f"跟单已停止：{reason}", "warn")
        return {"success": True, "message": "跟单已停止"}

    def update_config(self, config):
        """运行中改配置（仅对之后的信号生效）。"""
        cfg, err = validate_config(config)
        if err:
            return {"success": False, "message": f"配置不正确：{err}"}
        with self._lock:
            # 不允许在运行中悄悄把模拟切成实盘：必须停止后重新启动（让用户重新确认）
            if self.running and self.config["simulate"] and not cfg["simulate"]:
                return {"success": False, "message": "运行中不能从模拟切换为实盘，请先停止再启动"}
            self.config = cfg
        self.log("跟单配置已更新", "info")
        return {"success": True, "message": "配置已更新"}

    def resume(self):
        """人工确认后，解除风控 / 断连造成的自动暂停。"""
        with self._lock:
            if not self.running:
                return {"success": False, "message": "跟单未运行"}
            if not self.paused_reason:
                return {"success": True, "message": "当前没有暂停"}
            self.paused_reason = ""
            # 恢复时重置基线：暂停期间的成交不补跟
            self.baseline_ts = time.time()
        self.log("已手动恢复跟单（暂停期间的成交不补跟）", "warn")
        return {"success": True, "message": "已恢复"}

    def _pause(self, reason):
        with self._lock:
            if self.paused_reason:
                return
            self.paused_reason = reason
        self.log(f"跟单已自动暂停：{reason}", "error")

    # ------------------------------------------------------------------ 信号入口
    def on_source_trade(self, session, trade):
        """监控会话的成交回报（vnpy 事件线程，只做轻量入队）。"""
        recv = time.time()
        with self._lock:
            if not self.running:
                return
            tid = getattr(trade, "vt_tradeid", None) or f"{trade.vt_orderid}:{trade.tradeid}"
            if tid in self.seen:
                return
            self.seen.add(tid)
            # 防止集合无限增长（一次运行里几万笔成交不现实，这里只是兜底）
            if len(self.seen) > 50000:
                self.seen = set(list(self.seen)[-20000:])
            # 基线过滤：CTP 登录 / 重连时会把当日历史成交回放一遍，不能跟
            if recv < self.baseline_ts:
                return
            dt = getattr(trade, "datetime", None)
            trade_ts = dt.timestamp() if dt else None
        self._q.put({
            "tid": tid,
            "vt_symbol": trade.vt_symbol,
            "symbol": trade.symbol,
            "offset": trade.offset.value if trade.offset else "",
            "direction": trade.direction.value if trade.direction else "",
            "price": trade.price,
            "volume": trade.volume,
            "recv": recv,
            "trade_ts": trade_ts,
        })

    # ------------------------------------------------------------------ 工作线程
    def _run(self, stop_evt):
        while not stop_evt.is_set():
            try:
                sig = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if not self.running:
                continue
            try:
                self._handle(sig)
            except Exception as e:  # noqa: BLE001  一个信号出错不能让整个跟单线程退出
                import traceback
                self.log(f"处理信号异常：{type(e).__name__}: {e}", "error")
                print(traceback.format_exc())

    def _skip(self, sig, action, message, status=ST_SKIPPED, volume=0, price=None, level="warn"):
        rec = self._new_record(
            symbol=sig["symbol"], src_action=f"{sig['offset']}{sig['direction']}",
            src_volume=sig["volume"], src_price=sig["price"], action=action or "",
            volume=volume, price=price, status=status, message=message)
        self.log(f"{sig['symbol']} {sig['offset']}{sig['direction']} {sig['volume']:g}手：{message}", level)
        return rec

    def _handle(self, sig):
        with self._lock:
            cfg = dict(self.config)
            paused = self.paused_reason

        action = classify(sig["offset"], sig["direction"])
        if not action:
            self._skip(sig, None, f"无法识别的开平标志「{sig['offset']}」")
            return

        if paused:
            self._skip(sig, action, f"跟单已暂停（{paused}），信号丢弃")
            return

        # ---- 信号延迟 ----
        if cfg["signal_max_delay"] > 0:
            ref = sig["trade_ts"] or sig["recv"]
            delay = time.time() - ref
            if delay > cfg["signal_max_delay"]:
                self._skip(sig, action, f"信号延迟 {delay:.1f}s 超过上限 {cfg['signal_max_delay']:g}s，已丢弃")
                return

        # ---- 白名单 ----
        if cfg["symbol_whitelist"] and _product_of(sig["symbol"]) not in cfg["symbol_whitelist"]:
            self._skip(sig, action, "不在品种白名单内")
            return

        # ---- 每日亏损熔断 / 最大跟单次数（只拦新开仓；平仓永远放行，避免风控把人困在仓位里）----
        is_open = action.startswith("open")
        if is_open and cfg["daily_loss_limit"] > 0 and self.start_my_balance:
            bal = ctp_service.my_balance()
            if bal is not None and self.start_my_balance - bal >= cfg["daily_loss_limit"]:
                self._pause(f"当日亏损 {self.start_my_balance - bal:.0f} 元已达熔断线 {cfg['daily_loss_limit']:g} 元")
                self._skip(sig, action, "触发每日亏损熔断，跟单已暂停（平仓信号仍会处理）", level="error")
                return
        if is_open and cfg["max_follow_count"] > 0 and self.follow_count >= cfg["max_follow_count"]:
            self._skip(sig, action, f"已达最大跟单次数 {cfg['max_follow_count']}")
            return

        # ---- 合约 ----
        contract = ctp_service.my_contract(sig["vt_symbol"])
        if not cfg["simulate"] and not contract:
            self._skip(sig, action, "当前交易账号查不到该合约（未就绪或不可交易）")
            return

        # ---- 手数 ----
        vt = sig["vt_symbol"]
        key = (vt, action)
        my_bal = ctp_service.my_balance()
        src_bal = ctp_service.monitor_balance()
        with self._lock:
            rem = self.remainders[key]
        vol, new_rem, note = compute_volume(cfg, sig["volume"], my_bal, src_bal, rem)
        with self._lock:
            self.remainders[key] = new_rem

        if not is_open:
            # 平仓：只平我实际持有的，绝不多平（多平会变成开反向仓）
            side = "多" if action == "close_long" else "空"
            avail = ctp_service.my_available_close(vt, side)
            held = ctp_service.my_position_volume(vt, side)
            if held <= 0:
                self._skip(sig, action, f"我方没有该合约的{side}单可平（{note}）")
                return
            if vol > avail:
                note += f"；可平仅 {avail} 手，已下调"
                vol = avail
            if vol <= 0:
                self._skip(sig, action, f"可平手数为 0（持仓 {held} 手，可能已被挂单冻结）")
                return

        if vol <= 0:
            self._skip(sig, action, f"计算手数为 0，已跳过（{note}）；余量已累积到下次")
            return

        # ---- 单笔上限 / 最大持仓 ----
        if cfg["max_order_volume"] > 0 and vol > cfg["max_order_volume"]:
            note += f"；超过单笔上限 {cfg['max_order_volume']}，已下调"
            vol = cfg["max_order_volume"]
        if is_open and cfg["max_position"] > 0:
            cur = ctp_service.my_symbol_volume(vt)
            room = cfg["max_position"] - cur
            if room <= 0:
                self._skip(sig, action, f"{sig['symbol']} 持仓 {cur} 手已达上限 {cfg['max_position']}", volume=vol)
                return
            if vol > room:
                note += f"；持仓上限剩余 {room} 手，已下调"
                vol = room

        # 合约的最小 / 最大手数
        if contract:
            if contract.max_volume and vol > contract.max_volume:
                vol = int(contract.max_volume)
            if vol < max(1, int(contract.min_volume or 1)):
                self._skip(sig, action, f"低于合约最小手数（{note}）")
                return

        # ---- 价格 ----
        price, perr = ctp_service.follow_price(vt, action, cfg["price_mode"])
        if price is None:
            self._skip(sig, action, f"取不到下单价格：{perr}", volume=vol)
            return

        # ---- 模拟模式 ----
        if cfg["simulate"]:
            with self._lock:
                self.follow_count += 1
            self._new_record(symbol=sig["symbol"], src_action=f"{sig['offset']}{sig['direction']}",
                             src_volume=sig["volume"], src_price=sig["price"], action=action,
                             volume=vol, price=price, status=ST_SIMULATED,
                             message=f"模拟：本应{_ACTION_TEXT[action]} {vol} 手 @ {price:g}（{note}）")
            self.log(f"[模拟] {sig['symbol']} {_ACTION_TEXT[action]} {vol} 手 @ {price:g}（{note}）", "info")
            return

        # ---- 真实下单（只走主会话）----
        res = ctp_service.send_limit_order(vt, action, price, vol)
        with self._lock:
            self.follow_count += 1
        ids = res.get("vt_orderids") or []
        if not res.get("success"):
            self._new_record(symbol=sig["symbol"], src_action=f"{sig['offset']}{sig['direction']}",
                             src_volume=sig["volume"], src_price=sig["price"], action=action,
                             volume=vol, price=price, status=ST_REJECTED if ids else ST_FAILED,
                             message=res.get("message", "下单失败"), vt_orderids=ids)
            self.log(f"{sig['symbol']} {_ACTION_TEXT[action]} {vol} 手 @ {price:g} 失败：{res.get('message')}", "error")
            return

        rec = self._new_record(symbol=sig["symbol"], src_action=f"{sig['offset']}{sig['direction']}",
                               src_volume=sig["volume"], src_price=sig["price"], action=action,
                               volume=vol, price=price, status=ST_SUBMITTED,
                               message=f"{res.get('message', '')}（{note}）", vt_orderids=ids)
        self.log(f"{sig['symbol']} {_ACTION_TEXT[action]} {vol} 手 @ {price:g} 已委托", "info")
        threading.Thread(target=self._track, args=(rec, ids, cfg["order_timeout"]), daemon=True).start()

    # ------------------------------------------------------------------ 委托追踪
    def _track(self, rec, ids, timeout):
        """等委托结束；超时仍未全部成交就撤单。"""
        deadline = time.time() + timeout if timeout > 0 else None
        cancelled = False
        while True:
            orders = [ctp_service.my_order(i) for i in ids]
            orders = [o for o in orders if o]
            if orders and all(not o["active"] for o in orders):
                break
            if deadline and time.time() >= deadline and not cancelled:
                for i in ids:
                    ctp_service.my_cancel(i)
                cancelled = True
                self.log(f"{rec['symbol']} 委托超过 {timeout:g}s 未全部成交，已撤单", "warn")
            if not self.running and not deadline:
                return
            if cancelled and time.time() > (deadline or 0) + 10:
                break   # 撤单后 10 秒还没结束，不再死等，用当前状态记录
            time.sleep(0.3)

        orders = [ctp_service.my_order(i) for i in ids]
        orders = [o for o in orders if o]
        traded = sum(o["traded"] for o in orders)
        with self._lock:
            rec["traded"] = traded
            if traded >= rec["volume"]:
                rec["status"] = ST_FILLED
            elif traded > 0:
                rec["status"] = ST_PARTIAL if not cancelled else ST_CANCELLED
                rec["message"] += f"；成交 {traded:g}/{rec['volume']} 手后撤单" if cancelled else ""
            elif any(o["status"] == "已拒绝" for o in orders):
                rec["status"] = ST_REJECTED
            else:
                rec["status"] = ST_CANCELLED

    # ------------------------------------------------------------------ 看门狗
    def _watchdog(self, stop_evt):
        """监控账号 / 交易账号断连时自动暂停；两边都恢复也【不】自动继续（避免漏单后悄悄接着跟，导致仓位错位）。"""
        while not stop_evt.wait(2.0):
            if not self.running:
                return
            if not ctp_service.monitor_connected():
                self._pause("被监控账号连接已断开")
            elif not self.config["simulate"] and not ctp_service.is_connected():
                self._pause("当前交易账号连接已断开")

    # ------------------------------------------------------------------ 状态
    def status(self):
        with self._lock:
            cfg = dict(self.config)
            return {
                "running": self.running,
                "paused_reason": self.paused_reason,
                "started_at": self.started_at,
                "follow_count": self.follow_count,
                "config": cfg,
                "monitor_connected": ctp_service.monitor_connected(),
                "trade_connected": ctp_service.is_connected(),
                "my_balance": ctp_service.my_balance(),
                "src_balance": ctp_service.monitor_balance(),
                "start_my_balance": self.start_my_balance,
            }

    def get_records(self):
        with self._lock:
            return [dict(r) for r in self.records]

    def get_logs(self):
        with self._lock:
            return list(self.logs)


_ACTION_TEXT = {
    "open_long": "买多开仓", "open_short": "卖空开仓",
    "close_long": "卖出平多", "close_short": "买入平空",
}

engine = CopyEngine()
