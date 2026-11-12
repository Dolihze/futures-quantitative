#!/usr/bin/env python3
"""
CTP 实盘 / 仿真登录服务（基于 vnpy + vnpy_ctp）

职责：
  1. 读取各期货公司的 CTP 接入参数（data/ctp_brokers.json，可被 ctp_brokers.local.json 覆盖/追加）
  2. 用用户输入的账号、密码连接 CTP 交易 / 行情前置，完成「终端认证 + 登录」
  3. 登录成功后保持会话，对外提供资金、持仓快照
  4. 退出登录 / 重新登录时释放旧会话

约束：
  * 同一时间只保留一个 CTP 会话（单用户桌面应用）。重新登录会先关闭旧会话。
  * 密码只在连接时传给 CTP 接口，不写日志、不落盘、不保存在本模块里。
  * vnpy 在函数内延迟导入，未安装 vnpy 时后端其它功能不受影响。
"""
import atexit
import json
import os
import threading
import time

# 登录等待时间（秒）
LOGIN_TIMEOUT = 20
# 登录成功后等待首次资金回报的时间（秒），超时不算登录失败
FIRST_ACCOUNT_WAIT = 6

GATEWAY_NAME = "CTP"

_broker_configs = {}      # broker value -> CTP 参数
_lock = threading.Lock()  # 保护 _session 的创建 / 销毁
_session = None           # 当前 CTP 会话


# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------

REQUIRED_FIELDS = ("broker_id", "td_address", "md_address")


def load_configs(paths):
    """加载 CTP 接入参数。paths 中靠后的文件会覆盖 / 追加前面的同名配置。

    文件格式：{ "<broker value>": { "name", "broker_id", "td_address", "md_address",
                                     "app_id", "auth_code", "environment" } }
    以 "_" 开头的键（如 "_说明"）会被忽略。
    """
    configs = {}
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"[CTP] 读取配置失败 {path}: {e}")
            continue
        for key, cfg in data.items():
            if key.startswith("_") or not isinstance(cfg, dict):
                continue
            configs[key] = cfg
        print(f"[CTP] 已加载配置 {path}")
    _broker_configs.clear()
    _broker_configs.update(configs)
    print(f"[CTP] 已配置的期货公司: {sorted(_broker_configs) or '无'}")


def get_config(broker):
    """返回某个期货公司的 CTP 参数，未配置或参数不完整返回 None。"""
    cfg = _broker_configs.get(broker)
    if not cfg:
        return None
    if any(not str(cfg.get(k, "")).strip() for k in REQUIRED_FIELDS):
        return None
    return cfg


# ----------------------------------------------------------------------------
# 会话
# ----------------------------------------------------------------------------

class _Session:
    def __init__(self, broker, username, engine):
        self.broker = broker
        self.username = username
        self.engine = engine
        self.done = threading.Event()   # 交易端登录出结果（成功或失败）
        self.td_connected = False       # 已连上交易前置
        self.td_logged_in = False
        self.error = ""                 # 交易端失败原因
        self.logs = []                  # 最近日志（仅用于排障，不含密码）
        self.contracts_ready = False    # 合约信息已查询完成（登录后异步查询，下单 / 订阅前必须就绪）
        self.subscribed = set()         # 已订阅行情的 vt_symbol
        self.order_errors = {}          # vt_orderid -> 柜台拒单 / 撤单失败原因
        self.last_error = ("", 0.0)     # (最近一条委托 / 撤单错误日志, 时间戳)
        self.reverse_tasks = {}         # task_id -> 反手任务（先平仓，平仓全部成交后再反向开仓）
        self.reverse_lock = threading.Lock()   # 事件线程与 HTTP 线程都会改任务状态

    def on_log(self, event):
        msg = str(getattr(event.data, "msg", "") or "")
        self.logs.append(msg)
        del self.logs[:-30]
        print(f"[CTP] {msg}")

        if "交易服务器连接成功" in msg:
            self.td_connected = True
        elif "交易服务器登录成功" in msg:
            self.td_logged_in = True
            self.done.set()
        elif "交易服务器登录失败" in msg or "交易服务器授权验证失败" in msg:
            self.error = msg
            self.done.set()
        elif "合约信息查询成功" in msg:
            self.contracts_ready = True
        elif msg.startswith(("交易委托失败", "交易撤单失败", "委托请求发送失败", "请选择开平方向")) \
                or ("委托 " in msg and "状态更新" in msg):
            # 柜台拒单：详细原因只通过日志返回，记下来，下单接口 / 委托列表可以回显给用户
            self.last_error = (msg, time.time())


def _import_vnpy():
    """延迟导入 vnpy，返回 (MainEngine, CtpGateway, EVENT_LOG)。"""
    from vnpy.trader.setting import SETTINGS
    # 关闭 vnpy 自带的 loguru 文件日志：每次登录都会新建 MainEngine，避免重复添加日志输出；
    # 日志由本模块通过 EVENT_LOG 统一处理。必须在创建 MainEngine 之前设置。
    SETTINGS["log.active"] = False

    from vnpy.trader.engine import MainEngine
    from vnpy.trader.event import EVENT_LOG
    from vnpy_ctp import CtpGateway
    return MainEngine, CtpGateway, EVENT_LOG


def _close_session(session):
    if not session:
        return
    try:
        session.engine.close()
    except Exception as e:  # noqa: BLE001
        print(f"[CTP] 关闭会话时出错: {e}")


def _fail(message):
    return {"success": False, "message": message}


# 常见 CTP 错误码 -> 用户可读说明（未收录的保留原始信息）
_ERROR_HINTS = {
    "3": "账号或密码错误",
    "4": "账号或密码错误，或该账号未激活 / 不在当前环境",
    "7": "账号或密码错误",
    "63": "终端认证失败：App ID 或认证码（auth_code）不正确",
    "68": "终端认证失败：该账号不允许使用此终端（需期货公司开通）",
    "75": "账号或密码错误（连续输错可能被临时锁定）",
    "81": "该账号需要先修改初始密码（请用期货公司官方客户端修改后再登录）",
}


def _friendly_error(raw):
    """把网关日志 '交易服务器登录失败，代码：4，信息：CTP:用户不活跃' 转成可读提示。"""
    import re
    m = re.search(r"代码：(\d+)，信息：(.*)$", raw)
    if not m:
        return raw
    code, info = m.group(1), m.group(2).strip()
    hint = _ERROR_HINTS.get(code)
    stage = "终端认证失败" if "授权验证失败" in raw else "登录失败"
    return f"{hint}（{info}）" if hint else f"{stage}：{info}（代码 {code}）"


def login(broker, username, password):
    """连接 CTP 并登录，返回 {"success", "message", "data"?}。阻塞至多 LOGIN_TIMEOUT 秒。"""
    global _session

    cfg = get_config(broker)
    if not cfg:
        return _fail("该期货公司暂未开通实盘接入（缺少 CTP 前置地址等参数），请联系管理员配置")

    try:
        MainEngine, CtpGateway, EVENT_LOG = _import_vnpy()
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"[CTP] 导入 vnpy 失败:\n{traceback.format_exc()}")
        # 不能一律说“未安装”：打包后缺依赖、DLL 加载失败、版本不兼容等都会走到这里，
        # 把真实异常带给界面，才能定位问题
        kind = "未安装 CTP 接口组件（vnpy / vnpy_ctp）" if isinstance(e, ModuleNotFoundError) \
            else "CTP 接口组件加载失败"
        return _fail(f"{kind}：{type(e).__name__}: {e}")

    with _lock:
        # 先关闭旧会话（重新登录 / 切换账号）
        _close_session(_session)
        _session = None

        engine = MainEngine()
        session = _Session(broker, username, engine)
        engine.event_engine.register(EVENT_LOG, session.on_log)
        # 反手任务靠委托状态推送推进：平仓全部成交 -> 开仓；被撤 / 被拒 -> 取消
        from vnpy.trader.event import EVENT_ORDER
        engine.event_engine.register(EVENT_ORDER, lambda event, _s=session: _on_order_event(_s, event))
        engine.add_gateway(CtpGateway, GATEWAY_NAME)

        setting = {
            "用户名": username,
            "密码": password,
            "经纪商代码": str(cfg["broker_id"]).strip(),
            "交易服务器": str(cfg["td_address"]).strip(),
            "行情服务器": str(cfg["md_address"]).strip(),
            "产品名称": str(cfg.get("app_id", "")).strip(),
            "授权编码": str(cfg.get("auth_code", "")).strip(),
            "柜台环境": cfg.get("environment", "实盘"),
        }
        print(f"[CTP] 开始登录 broker={broker} user={username} "
              f"td={setting['交易服务器']} md={setting['行情服务器']}")

        try:
            engine.connect(setting, GATEWAY_NAME)
        except Exception as e:  # noqa: BLE001
            print(f"[CTP] 连接异常: {e}")
            _close_session(session)
            return _fail(f"连接 CTP 失败：{e}")

        session.done.wait(LOGIN_TIMEOUT)

        if not session.td_logged_in:
            _close_session(session)
            if session.error:
                return _fail(_friendly_error(session.error))
            if not session.td_connected:
                return _fail(f"无法连接交易服务器（{setting['交易服务器']}），"
                             "请检查网络，或确认该环境当前是否在服务时间内")
            return _fail("登录超时，期货公司未返回登录结果，请稍后重试")

        _session = session

    # 首次资金回报由网关定时查询触发（约 2 秒一次），这里尽量等一下，拿不到也不算失败
    deadline = time.time() + FIRST_ACCOUNT_WAIT
    while time.time() < deadline and not engine.get_all_accounts():
        time.sleep(0.3)

    return {"success": True, "message": "登录成功", "data": snapshot()}


def logout():
    """关闭当前 CTP 会话（没有会话也安全）。"""
    global _session
    with _lock:
        _close_session(_session)
        _session = None


def is_connected():
    s = _session
    if not s:
        return False
    try:
        return bool(s.engine.get_gateway(GATEWAY_NAME).td_api.login_status)
    except Exception:  # noqa: BLE001
        return False


def current_user():
    """当前 CTP 会话对应的 (broker, username)，没有会话返回 None。"""
    s = _session
    return (s.broker, s.username) if s else None


def snapshot():
    """当前会话的资金、持仓快照；没有可用会话返回 None。"""
    s = _session
    if not s or not is_connected():
        return None

    accounts = s.engine.get_all_accounts()
    account = None
    if accounts:
        a = accounts[0]
        account = {
            "account": a.accountid,
            "balance": a.balance,
            "available": a.available,
            "frozen": a.frozen,
        }

    positions = []
    profit = 0.0
    for p in s.engine.get_all_positions():
        if not p.volume:
            continue
        profit += p.pnl
        positions.append({
            "symbol": p.symbol,
            "exchange": p.exchange.value,
            "direction": p.direction.value,
            "volume": p.volume,
            "yd_volume": p.yd_volume,
            "frozen": p.frozen,
            "price": p.price,
            "pnl": p.pnl,
        })

    return {
        "broker": s.broker,
        "username": s.username,
        "account": account,          # 首次资金回报到达前为 None
        "positions": positions,
        "position_profit": profit,   # 持仓盈亏合计
    }


# ----------------------------------------------------------------------------
# 交易：合约、行情、限价下单、撤单、委托与成交
# ----------------------------------------------------------------------------

# 下单后等待柜台首次应答（拒单 / 排队）的时间（秒）
ORDER_ACK_WAIT = 1.5
# 价格校验的浮点容差
_EPS = 1e-6


def _ready_session():
    """返回可交易的会话；未登录 / 连接断开 / 合约未就绪时返回 (None, 原因)。"""
    s = _session
    if not s or not is_connected():
        return None, "未连接期货账户或连接已断开，请重新登录"
    if not s.contracts_ready:
        return None, "合约信息正在加载，请稍后几秒再试"
    return s, ""


def _contract_dict(c):
    return {
        "vt_symbol": c.vt_symbol,
        "symbol": c.symbol,
        "exchange": c.exchange.value,
        "name": c.name,
        "size": c.size,
        "pricetick": c.pricetick,
        "min_volume": c.min_volume,
        "max_volume": c.max_volume,
    }


def list_contracts():
    """返回当前账号可交易的期货合约列表。(contracts, error)"""
    s, err = _ready_session()
    if not s:
        return None, err

    from vnpy.trader.constant import Product
    items = [_contract_dict(c) for c in s.engine.get_all_contracts() if c.product == Product.FUTURES]
    # 先按品种前缀（字母部分）、再按合约代码排序，同一品种的不同月份排在一起
    items.sort(key=lambda c: (c["exchange"], "".join(ch for ch in c["symbol"] if ch.isalpha()), c["symbol"]))
    return items, ""


def _subscribe(s, contract):
    """订阅行情（同一合约只订阅一次）。"""
    if contract.vt_symbol in s.subscribed:
        return
    from vnpy.trader.object import SubscribeRequest
    s.engine.subscribe(SubscribeRequest(symbol=contract.symbol, exchange=contract.exchange), GATEWAY_NAME)
    s.subscribed.add(contract.vt_symbol)


def get_quote(vt_symbol):
    """订阅并返回合约的最新行情。(quote, error)

    刚订阅时行情还没推送，quote 里的价格字段为 None，前端下一次轮询即可拿到。"""
    s, err = _ready_session()
    if not s:
        return None, err
    contract = s.engine.get_contract(vt_symbol)
    if not contract:
        return None, f"合约不存在：{vt_symbol}"

    _subscribe(s, contract)

    tick = s.engine.get_tick(vt_symbol)
    quote = {
        "vt_symbol": vt_symbol,
        "name": contract.name,
        "pricetick": contract.pricetick,
        "last_price": None, "bid_price": None, "ask_price": None,
        "limit_up": None, "limit_down": None, "pre_close": None, "time": None,
    }
    if tick:
        def pos(v):  # CTP 无效价格会被置 0，当作“没有”；同时把浮点误差（如 7187.400000000001）规整到最小变动价位
            return _round_to_tick(v, contract.pricetick) if v else None
        quote.update({
            "last_price": pos(tick.last_price),
            "bid_price": pos(tick.bid_price_1),
            "ask_price": pos(tick.ask_price_1),
            "limit_up": pos(tick.limit_up),
            "limit_down": pos(tick.limit_down),
            "pre_close": pos(tick.pre_close),
            "time": tick.datetime.strftime("%H:%M:%S") if tick.datetime else None,
        })
    return quote, ""


def _round_to_tick(price, tick):
    """把价格规整到最小变动价位的整数倍，并去掉浮点误差。

    CTP 推送的涨跌停价是按“昨结算价 × 比例”算出来的，常带 7187.400000000001 这样的尾巴；
    按最小变动价位四舍五入后，再按价位的小数位数取整，显示和后续比较都干净。"""
    if not tick or tick <= 0:
        return price
    n = round(price / tick)
    # 价位小数位数：0.2 -> 1，0.02 -> 2，1 -> 0，0.5 -> 1
    s = f"{tick:.10f}".rstrip("0").rstrip(".")
    decimals = len(s.split(".")[1]) if "." in s else 0
    return round(n * tick, decimals)


def _is_tick_multiple(price, tick):
    if not tick:
        return True
    n = round(price / tick)
    return abs(price - n * tick) < _EPS * max(1.0, abs(price))


def _wait_order_ack(s, vt_orderids, since):
    """等柜台对委托的首次应答；返回 (状态列表, 拒单原因)。"""
    from vnpy.trader.constant import Status
    deadline = time.time() + ORDER_ACK_WAIT
    while time.time() < deadline:
        orders = [s.engine.get_order(i) for i in vt_orderids]
        # 只要还有委托停在“提交中”就继续等；全部离开该状态即视为已应答
        if all(o and o.status != Status.SUBMITTING for o in orders):
            break
        time.sleep(0.1)

    orders = [s.engine.get_order(i) for i in vt_orderids]
    reason = ""
    msg, ts = s.last_error
    if ts >= since:
        reason = msg
    return orders, reason


def _check_order_params(s, contract, price, volume):
    """校验限价、手数。通过返回 (price, volume, "")；不通过返回 (None, None, 原因)。

    所有下单入口（普通限价单、反手的平仓 / 开仓）都必须走这里，不信任前端。"""
    import math
    try:
        price = float(price)
        raw_volume = float(volume)
    except (TypeError, ValueError):
        return None, None, "价格或手数格式不正确"
    # NaN / inf 会让后面的比较全部失效，必须先挡掉
    if not math.isfinite(price) or not math.isfinite(raw_volume):
        return None, None, "价格或手数格式不正确"
    # 手数必须本身就是整数：1.5 不能被悄悄截断成 1 手去下单
    if raw_volume != int(raw_volume):
        return None, None, "手数必须是整数"
    volume = int(raw_volume)

    if volume < max(1, int(contract.min_volume or 1)):
        return None, None, "手数必须是正整数"
    if contract.max_volume and volume > contract.max_volume:
        return None, None, f"单笔最大 {int(contract.max_volume)} 手"
    if price <= 0:
        return None, None, "限价必须大于 0"
    if not _is_tick_multiple(price, contract.pricetick):
        return None, None, f"价格必须是最小变动价位 {contract.pricetick:g} 的整数倍"

    # 涨跌停校验：拿得到就校验，拿不到（行情还没推送）不拦，交给柜台判断
    _subscribe(s, contract)
    tick = s.engine.get_tick(contract.vt_symbol)
    if tick:
        if tick.limit_up and price > tick.limit_up + _EPS:
            return None, None, f"价格高于涨停价 {tick.limit_up:g}"
        if tick.limit_down and price < tick.limit_down - _EPS:
            return None, None, f"价格低于跌停价 {tick.limit_down:g}"
    return price, volume, ""


ACTIONS = ("open_long", "open_short", "close_long", "close_short")


def send_limit_order(vt_symbol, action, price, volume):
    """限价下单。action: open_long 买多开仓 / open_short 卖空开仓 / close_long 平多 / close_short 平空。

    返回 {"success", "message", "orders": [...]}。所有参数都在服务端重新校验，不信任前端。"""
    s, err = _ready_session()
    if not s:
        return _fail(err)

    contract = s.engine.get_contract(vt_symbol)
    if not contract:
        return _fail(f"合约不存在：{vt_symbol}")
    if action not in ACTIONS:
        return _fail("不支持的操作类型")

    price, volume, err = _check_order_params(s, contract, price, volume)
    if err:
        return _fail(err)
    return _place(s, contract, action, price, volume)


def _place(s, contract, action, price, volume):
    """把已校验过的限价单发给柜台（平仓会按持仓拆成平今 / 平昨）。

    返回 {"success", "message", "orders", "vt_orderids"}；vt_orderids 是实际发出的委托号，反手要用。"""
    from vnpy.trader.constant import Direction, Offset, OrderType, Status
    from vnpy.trader.object import OrderRequest

    is_open = action.startswith("open")
    # 买多 / 平空 → 买入；卖空 / 平多 → 卖出
    direction = Direction.LONG if action in ("open_long", "close_short") else Direction.SHORT
    req = OrderRequest(
        symbol=contract.symbol, exchange=contract.exchange, direction=direction,
        type=OrderType.LIMIT, volume=volume, price=price,
        offset=Offset.OPEN if is_open else Offset.CLOSE,
        reference="futures-quantitative",
    )

    # ---- 平仓：上期所 / 能源中心要拆成平今 + 平昨，并按已冻结仓位计算可平量 ----
    converter = s.engine.get_converter(GATEWAY_NAME)
    if is_open:
        reqs = [req]
    else:
        if not converter:
            return _fail("没有可平的持仓")
        reqs = converter.convert_order_request(req, lock=False, net=False)
        if not reqs:
            side = "多单" if action == "close_long" else "空单"
            return _fail(f"可平{side}不足（可能已有挂单占用了仓位），请检查持仓和委托")

    since = time.time()
    vt_orderids = []
    for r in reqs:
        vt_orderid = s.engine.send_order(r, GATEWAY_NAME)
        if not vt_orderid:
            # 网关没发出去：已经发出的部分不撤，如实告诉用户
            break
        vt_orderids.append(vt_orderid)
        if converter:
            converter.update_order_request(r, vt_orderid)

    if not vt_orderids:
        return _fail(_last_error_since(s, since) or "委托发送失败")

    orders, reason = _wait_order_ack(s, vt_orderids, since)
    result = [_order_dict(o) for o in orders if o]
    partial = len(vt_orderids) < len(reqs)

    rejected = [o for o in orders if o and o.status == Status.REJECTED]
    if rejected and len(rejected) == len(orders):
        return {"success": False, "message": reason or "委托被柜台拒绝", "orders": result,
                "vt_orderids": vt_orderids, "partial": partial}

    msg = "委托已提交"
    if len(vt_orderids) > 1:
        msg = f"委托已提交（已自动拆分为 {len(vt_orderids)} 笔：平今 / 平昨）"
    if partial:
        msg += "；部分委托未能发出，请核对委托列表"
    return {"success": True, "message": msg, "orders": result,
            "vt_orderids": vt_orderids, "partial": partial}


def _last_error_since(s, since):
    msg, ts = s.last_error
    return msg if ts >= since else ""


_STATUS_TEXT = {
    "提交中": "提交中", "未成交": "未成交", "部分成交": "部分成交",
    "全部成交": "全部成交", "已撤销": "已撤销", "拒单": "已拒绝",
}


def _status_text(order):
    return _STATUS_TEXT.get(order.status.value, order.status.value)


def _order_dict(o):
    return {
        "vt_orderid": o.vt_orderid,
        "vt_symbol": o.vt_symbol,
        "symbol": o.symbol,
        "direction": o.direction.value if o.direction else "",
        "offset": o.offset.value if o.offset else "",
        "price": o.price,
        "volume": o.volume,
        "traded": o.traded,
        "status": _status_text(o),
        "active": o.is_active(),
        "time": o.datetime.strftime("%H:%M:%S") if o.datetime else "",
    }


# ----------------------------------------------------------------------------
# 反手：先平掉现有持仓，平仓【全部成交】后才反向开同样手数
#
# 为什么不一次把平仓和开仓都发出去：限价平仓可能迟迟不成交，而反向开仓若先成交，
# 账户就会同时持有多空双向仓位（多占一份保证金，也违背“反手”的意图）。
# 所以反手是一个有状态的任务：平仓成交才开仓；平仓被撤 / 被拒 / 只成交一部分就被撤，任务取消，不开仓。
# ----------------------------------------------------------------------------

REVERSE_WAITING = "waiting"      # 平仓已发出，等待全部成交
REVERSE_OPENED = "opened"        # 平仓已全部成交，反向开仓已发出
REVERSE_CANCELLED = "cancelled"  # 任务取消（平仓被撤 / 被拒 / 用户取消），没有开反向仓
REVERSE_FAILED = "failed"        # 平仓已成交，但反向开仓发送失败（需要用户手动处理）

_REVERSE_FINAL = (REVERSE_OPENED, REVERSE_CANCELLED, REVERSE_FAILED)


def _reverse_dict(t):
    return {k: t[k] for k in ("task_id", "vt_symbol", "symbol", "name", "from_side", "to_side", "volume",
                              "close_price", "open_price", "state", "message", "created", "open_orderids")}


def _advance_reverse_tasks(s, only_orderid=None):
    """检查等待中的反手任务：平仓全部成交 -> 触发开仓；有一笔被撤 / 被拒 -> 取消任务。

    事件线程（委托状态推送）和 HTTP 线程（刚发出平仓后补判一次，防止事件比任务登记还早到）都会调用，
    所以全程加锁，并且【先改状态、后开仓】，保证同一个任务绝不会触发两次开仓。
    only_orderid 不为空时只处理包含该委托的任务。"""
    from vnpy.trader.constant import Status
    todo = []

    with s.reverse_lock:
        for t in s.reverse_tasks.values():
            if t["state"] != REVERSE_WAITING or not t["close_orderids"]:
                continue
            if only_orderid and only_orderid not in t["close_orderids"]:
                continue

            orders = [s.engine.get_order(i) for i in t["close_orderids"]]
            if any(o is None for o in orders):
                continue
            closed = sum(o.traded for o in orders)

            if any(o.status in (Status.CANCELLED, Status.REJECTED) for o in orders):
                # 平仓有一笔没做成：不开反向仓，并把已平的手数如实告诉用户
                t["state"] = REVERSE_CANCELLED
                t["message"] = (f"平仓委托被撤销或拒绝，已取消反手，未开反向仓。"
                                f"已平 {closed:g} / {t['volume']} 手，请核对持仓。")
            elif all(o.status == Status.ALLTRADED for o in orders):
                t["state"] = REVERSE_OPENED
                t["message"] = "平仓已全部成交，正在发出反向开仓…"
                todo.append(t)

    for t in todo:
        # 不能在事件线程里下单：_place 会等柜台应答，而应答也要靠这个事件线程分发，会互相卡死
        threading.Thread(target=_run_reverse_open, args=(s, t), daemon=True).start()


def _on_order_event(s, event):
    """委托状态推送（运行在 vnpy 事件线程，不能阻塞）。"""
    _advance_reverse_tasks(s, only_orderid=event.data.vt_orderid)


def _run_reverse_open(s, t):
    contract = s.engine.get_contract(t["vt_symbol"])
    action = "open_long" if t["to_side"] == "多" else "open_short"
    if not contract:
        res = _fail("合约不存在")
    else:
        # 开仓价同样要过校验（行情可能在等平仓期间已经变化，比如价格已超出涨跌停）
        price, volume, err = _check_order_params(s, contract, t["open_price"], t["volume"])
        res = _fail(err) if err else _place(s, contract, action, price, volume)

    with s.reverse_lock:
        if res["success"]:
            t["open_orderids"] = res.get("vt_orderids", [])
            t["message"] = "平仓已成交，反向开仓委托已提交"
        else:
            t["state"] = REVERSE_FAILED
            t["message"] = f"平仓已全部成交，但反向开仓失败：{res['message']}。请手动开仓。"


def start_reverse(vt_symbol, from_side, close_price, open_price, volume):
    """反手：from_side 是现有持仓方向（'多' 或 '空'）。

    先按 close_price 平掉 volume 手；平仓全部成交后，按 open_price 反向开 volume 手。"""
    s, err = _ready_session()
    if not s:
        return _fail(err)

    contract = s.engine.get_contract(vt_symbol)
    if not contract:
        return _fail(f"合约不存在：{vt_symbol}")
    if from_side not in ("多", "空"):
        return _fail("反手方向不正确")

    # 两个价格、手数都先校验：不能平仓成功了才发现开仓价非法
    close_price, volume, err = _check_order_params(s, contract, close_price, volume)
    if err:
        return _fail(f"平仓价：{err}" if "价" in err else err)
    open_price, _, err = _check_order_params(s, contract, open_price, volume)
    if err:
        return _fail(f"开仓价：{err}" if "价" in err else err)

    # 同一合约、同一方向已有反手任务在等待时不允许重复发起（否则会重复平仓 / 重复开仓）
    with s.reverse_lock:
        for t in s.reverse_tasks.values():
            if t["state"] == REVERSE_WAITING and t["vt_symbol"] == vt_symbol and t["from_side"] == from_side:
                return _fail("该合约已有一笔反手在等待平仓成交，请先等待成交或取消")

    close_action = "close_long" if from_side == "多" else "close_short"
    to_side = "空" if from_side == "多" else "多"

    # 先登记任务、再发平仓：平仓若瞬间成交，事件可能比 _place 的返回还早到，
    # 那时任务必须已经存在，否则会漏掉触发
    task = {
        "task_id": f"R{int(time.time() * 1000)}",
        "vt_symbol": vt_symbol, "symbol": contract.symbol, "name": contract.name,
        "from_side": from_side, "to_side": to_side, "volume": volume,
        "close_price": close_price, "open_price": open_price,
        "state": REVERSE_WAITING, "message": "平仓已发出，等待全部成交后自动反向开仓",
        "created": time.strftime("%H:%M:%S"),
        "close_orderids": [], "open_orderids": [],
    }
    with s.reverse_lock:
        s.reverse_tasks[task["task_id"]] = task

    res = _place(s, contract, close_action, close_price, volume)
    if not res.get("vt_orderids"):
        with s.reverse_lock:
            s.reverse_tasks.pop(task["task_id"], None)
        return _fail(res["message"])

    with s.reverse_lock:
        task["close_orderids"] = res["vt_orderids"]
        if res.get("partial"):
            # 平仓只发出去一部分：数量对不上，任务无法保证“全部平掉才开仓”，直接取消更安全
            task["state"] = REVERSE_CANCELLED
            task["message"] = "平仓委托未能全部发出，已取消反手，未开反向仓。请核对委托和持仓。"
    if task["state"] == REVERSE_CANCELLED:
        return {"success": False, "message": task["message"], "task": _reverse_dict(task)}

    # 平仓可能在 close_orderids 登记之前就已成交 / 被拒（事件早到，当时没匹配上），这里补判一次
    _advance_reverse_tasks(s)

    if not res["success"]:
        # 平仓被柜台拒绝：上面的补判通常已经把任务置为取消并写了通用文案，这里改成带柜台真实原因的提示
        with s.reverse_lock:
            task["state"] = REVERSE_CANCELLED
            task["message"] = f"平仓被柜台拒绝，已取消反手，未开反向仓：{res['message']}"
        return {"success": False, "message": task["message"], "task": _reverse_dict(task)}

    return {"success": True, "message": "反手已发起：先平仓，全部成交后自动反向开仓",
            "task": _reverse_dict(task), "orders": res.get("orders", [])}


def cancel_reverse(task_id):
    """取消等待中的反手任务，并撤掉还没成交的平仓委托。已成交的平仓不会回滚。"""
    s, err = _ready_session()
    if not s:
        return _fail(err)
    with s.reverse_lock:
        t = s.reverse_tasks.get(task_id)
        if not t:
            return _fail("反手任务不存在")
        if t["state"] != REVERSE_WAITING:
            return _fail("该反手任务已结束，无法取消")
        # 先改状态：之后即使平仓恰好全部成交，也不会再触发开仓
        t["state"] = REVERSE_CANCELLED
        t["message"] = "已手动取消反手，未开反向仓"
        close_orderids = list(t["close_orderids"])

    for vt_orderid in close_orderids:
        o = s.engine.get_order(vt_orderid)
        if o and o.is_active():
            s.engine.cancel_order(o.create_cancel_request(), GATEWAY_NAME)
    return {"success": True, "message": "已取消反手，并已撤销未成交的平仓委托（已成交的部分不会回滚）"}


def list_reverse_tasks():
    s = _session
    if not s:
        return []
    with s.reverse_lock:
        tasks = sorted(s.reverse_tasks.values(), key=lambda t: t["task_id"], reverse=True)
        return [_reverse_dict(t) for t in tasks]


def list_positions():
    """当前会话的持仓列表。(positions, error)

    浮动盈亏 = (最新价 - 开仓均价) × 手数 × 合约乘数，空单取反；拿不到最新价时回落到 CTP 的持仓盈亏（按昨结算价算）。"""
    s = _session
    if not s or not is_connected():
        return None, "未连接期货账户或连接已断开"

    from vnpy.trader.constant import Direction
    items = []
    for p in s.engine.get_all_positions():
        if not p.volume:
            continue
        contract = s.engine.get_contract(p.vt_symbol)
        tick = s.engine.get_tick(p.vt_symbol)
        last = tick.last_price if tick and tick.last_price else None
        size = contract.size if contract else 0

        pnl, pnl_source = p.pnl, "ctp"
        if last and size and p.price:
            sign = 1 if p.direction == Direction.LONG else -1
            pnl, pnl_source = (last - p.price) * p.volume * size * sign, "live"

        yd = min(p.yd_volume or 0, p.volume)
        items.append({
            "vt_symbol": p.vt_symbol,
            "symbol": p.symbol,
            "name": contract.name if contract else p.symbol,
            "exchange": p.exchange.value,
            "direction": p.direction.value,        # 多 / 空
            "volume": p.volume,
            "yd_volume": yd,
            "td_volume": p.volume - yd,
            "frozen": p.frozen,
            "available": max(p.volume - p.frozen, 0),
            "price": p.price,                      # 开仓均价
            "last_price": last,
            "pnl": pnl,
            "pnl_source": pnl_source,              # live=按最新价实时算；ctp=柜台的持仓盈亏
        })
        # 持仓合约要有行情才能算实时盈亏
        if contract:
            _subscribe(s, contract)
    items.sort(key=lambda x: (x["symbol"], x["direction"]))
    return items, ""


def _trade_dict(t):
    return {
        "vt_tradeid": t.vt_tradeid,
        "vt_orderid": t.vt_orderid,
        "vt_symbol": t.vt_symbol,
        "symbol": t.symbol,
        "direction": t.direction.value if t.direction else "",
        "offset": t.offset.value if t.offset else "",
        "price": t.price,
        "volume": t.volume,
        "time": t.datetime.strftime("%H:%M:%S") if t.datetime else "",
    }


def list_trades():
    """当前会话的成交明细，最新的在前。(trades, error)"""
    s = _session
    if not s or not is_connected():
        return None, "未连接期货账户或连接已断开"
    trades = s.engine.get_all_trades()
    trades.sort(key=lambda t: (t.datetime.timestamp() if t.datetime else 0), reverse=True)
    return [_trade_dict(t) for t in trades], ""


def list_orders():
    """当前会话的委托列表，最新的在前。(orders, error)"""
    s = _session
    if not s or not is_connected():
        return None, "未连接期货账户或连接已断开"
    orders = s.engine.get_all_orders()
    orders.sort(key=lambda o: (o.datetime.timestamp() if o.datetime else 0), reverse=True)
    return [_order_dict(o) for o in orders], ""


def cancel_order(vt_orderid):
    """撤销一笔委托。"""
    from vnpy.trader.constant import Status
    s, err = _ready_session()
    if not s:
        return _fail(err)

    order = s.engine.get_order(vt_orderid)
    if not order:
        return _fail("委托不存在")
    if not order.is_active():
        return _fail(f"该委托状态为「{_status_text(order)}」，无法撤销")

    since = time.time()
    s.engine.cancel_order(order.create_cancel_request(), GATEWAY_NAME)

    deadline = time.time() + ORDER_ACK_WAIT
    while time.time() < deadline:
        cur = s.engine.get_order(vt_orderid)
        if cur and not cur.is_active():
            return {"success": True, "message": "撤单成功"}
        if _last_error_since(s, since):
            return _fail(_last_error_since(s, since))
        time.sleep(0.1)
    return {"success": True, "message": "撤单请求已发送，请稍后在委托列表确认"}


atexit.register(logout)
