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


atexit.register(logout)
