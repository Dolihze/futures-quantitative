"""量化监控跟单引擎的单元测试：python -m pytest tests/test_copy_trading.py -q

用 FakeCtp 替换 ctp_service，不依赖真实 CTP / 网络，覆盖：
手数计算、开平分类、配置校验、品种白名单 / 信号延迟、平仓防多平、去重、基线过滤、模拟模式、实盘下单与撤单。"""
import os
import sys
import time
import types
import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import copy_trading as ct  # noqa: E402


# ----------------------------------------------------------------------------
# 假的 ctp_service
# ----------------------------------------------------------------------------

class FakeContract:
    def __init__(self, min_volume=1, max_volume=500):
        self.min_volume = min_volume
        self.max_volume = max_volume


class FakeCtp:
    def __init__(self):
        self.monitor_ok = True
        self.trade_ok = True
        self.my_bal = 100000.0
        self.src_bal = 100000.0
        self.contract = FakeContract()
        self.positions = {}              # (vt_symbol, side) -> (volume, frozen)
        self.price = (3500.0, "")
        self.sent = []                   # send_limit_order 调用记录
        self.send_result = None          # 覆盖返回值
        self.orders = {}                 # vt_orderid -> dict
        self.cancelled = []

    # 连接状态
    def monitor_connected(self): return self.monitor_ok
    def is_connected(self): return self.trade_ok
    def my_balance(self): return self.my_bal
    def monitor_balance(self): return self.src_bal
    def my_contract(self, vt): return self.contract

    def my_position_volume(self, vt, side): return self.positions.get((vt, side), (0, 0))[0]
    def my_available_close(self, vt, side):
        v, f = self.positions.get((vt, side), (0, 0))
        return max(v - f, 0)
    def follow_price(self, vt, action, mode): return self.price

    def send_limit_order(self, vt, action, price, volume):
        self.sent.append((vt, action, price, volume))
        if self.send_result is not None:
            return self.send_result
        oid = f"CTP.{len(self.sent)}"
        self.orders[oid] = {"vt_orderid": oid, "active": False, "traded": volume, "status": "全部成交"}
        return {"success": True, "message": "委托已提交", "vt_orderids": [oid], "orders": []}

    def my_order(self, oid): return self.orders.get(oid)
    def my_cancel(self, oid):
        self.cancelled.append(oid)
        o = self.orders.get(oid)
        if o and o["active"]:
            o["active"] = False
            o["status"] = "已撤销"
        return True


@pytest.fixture
def fake(monkeypatch):
    f = FakeCtp()
    for name in ("monitor_connected", "is_connected", "my_balance", "monitor_balance", "my_contract",
                 "my_position_volume", "my_available_close", "follow_price",
                 "send_limit_order", "my_order", "my_cancel"):
        monkeypatch.setattr(ct.ctp_service, name, getattr(f, name))
    return f


def make_engine(fake, **overrides):
    e = ct.CopyEngine()
    cfg = {"simulate": False, "size_mode": "multiple", "multiplier": 1, "signal_max_delay": 0,
           "order_timeout": 0}
    cfg.update(overrides)
    res = e.start(cfg)
    assert res["success"], res
    return e


def trade(tid="T1", symbol="rb2610", offset="开", direction="多", volume=2, price=3500.0, ts=None):
    off = types.SimpleNamespace(value=offset)
    dr = types.SimpleNamespace(value=direction)
    return types.SimpleNamespace(
        vt_tradeid=tid, tradeid=tid, vt_orderid="SRC.1", vt_symbol=f"{symbol}.SHFE", symbol=symbol,
        offset=off, direction=dr, price=price, volume=volume,
        datetime=ts if ts is not None else datetime.datetime.now())


def feed(e, **kw):
    """送入一笔源成交并等工作线程处理完。"""
    e.on_source_trade(None, trade(**kw))
    deadline = time.time() + 3
    while time.time() < deadline:
        if e._q.empty():
            time.sleep(0.15)   # 让工作线程跑完 _handle
            return
        time.sleep(0.02)


# ----------------------------------------------------------------------------
# 纯函数
# ----------------------------------------------------------------------------

def test_classify():
    assert ct.classify("开", "多") == "open_long"
    assert ct.classify("开", "空") == "open_short"
    assert ct.classify("平", "多") == "close_short"      # 买入平仓 = 平空
    assert ct.classify("平今", "空") == "close_long"     # 卖出平仓 = 平多
    assert ct.classify("平昨", "空") == "close_long"
    assert ct.classify("", "多") is None
    assert ct.classify("未知", "多") is None


def test_compute_volume_modes():
    cfg = dict(ct.DEFAULT_CONFIG)
    cfg.update(size_mode="fixed", fixed_volume=3)
    assert ct.compute_volume(cfg, 10)[0] == 3

    cfg.update(size_mode="multiple", multiplier=0.5)
    assert ct.compute_volume(cfg, 4)[0] == 2


def test_compute_volume_remainder_accumulates():
    cfg = dict(ct.DEFAULT_CONFIG)
    cfg.update(size_mode="multiple", multiplier=0.4)
    rem, total = 0.0, 0
    for _ in range(5):                      # 5 笔 × 1 手 × 0.4 = 2.0 手
        v, rem, _ = ct.compute_volume(cfg, 1, rem)
        total += v
    assert total == 2                       # 余量累积，没有被系统性丢掉


def test_validate_config():
    assert ct.validate_config({})[1] == ""
    assert ct.validate_config({"size_mode": "x"})[1]
    assert ct.validate_config({"size_mode": "ratio"})[1]          # 资金比例模式已移除
    assert ct.validate_config({"multiplier": 0})[1]
    assert ct.validate_config({"multiplier": -1})[1]
    assert ct.validate_config({"multiplier": float("nan")})[1]
    assert ct.validate_config({"multiplier": "abc"})[1]
    assert ct.validate_config({"fixed_volume": 1.5})[1]
    assert ct.validate_config({"price_mode": "foo"})[1]
    assert ct.validate_config({"signal_max_delay": -1})[1]
    assert ct.validate_config({"simulate": 0})[0]["simulate"] is False
    cfg, _ = ct.validate_config({"symbol_whitelist": "RB, ag，  cu"})
    assert cfg["symbol_whitelist"] == ["ag", "cu", "rb"]
    # 默认是模拟模式，防止误触真单
    assert ct.validate_config({})[0]["simulate"] is True


# ----------------------------------------------------------------------------
# 启动条件
# ----------------------------------------------------------------------------

def test_start_requires_monitor_login(fake):
    fake.monitor_ok = False
    assert not ct.CopyEngine().start({"simulate": True})["success"]


def test_start_live_requires_trade_account(fake):
    fake.trade_ok = False
    assert not ct.CopyEngine().start({"simulate": False})["success"]
    assert ct.CopyEngine().start({"simulate": True})["success"]   # 模拟不要求


def test_cannot_switch_sim_to_live_while_running(fake):
    e = make_engine(fake, simulate=True)
    assert not e.update_config({"simulate": False})["success"]
    assert e.config["simulate"] is True
    e.stop()


# ----------------------------------------------------------------------------
# 信号流
# ----------------------------------------------------------------------------

def test_open_is_followed_live(fake):
    e = make_engine(fake)
    feed(e, offset="开", direction="多", volume=2)
    assert fake.sent == [("rb2610.SHFE", "open_long", 3500.0, 2)]
    assert e.get_records()[0]["status"] == ct.ST_FILLED
    e.stop()


def test_nothing_before_start_and_nothing_when_stopped(fake):
    e = ct.CopyEngine()
    e.on_source_trade(None, trade())              # 未启动
    assert e._q.empty()
    e = make_engine(fake)
    e.stop()
    e.on_source_trade(None, trade(tid="T9"))      # 已停止
    assert e._q.empty()


def test_dedupe_same_trade_only_once(fake):
    e = make_engine(fake)
    feed(e, tid="DUP")
    feed(e, tid="DUP")
    assert len(fake.sent) == 1
    e.stop()


def test_baseline_ignores_trades_received_before_start(fake):
    e = make_engine(fake)
    e.baseline_ts = time.time() + 100             # 模拟：信号收到时早于基线
    feed(e, tid="OLD")
    assert fake.sent == []
    assert e.get_records() == []
    e.stop()


def test_close_never_exceeds_my_position(fake):
    e = make_engine(fake)
    # 我方没有持仓：平仓信号必须跳过，不能变成反向开仓
    feed(e, tid="C1", offset="平", direction="空", volume=3)       # 卖出平多
    assert fake.sent == []
    assert e.get_records()[0]["status"] == ct.ST_SKIPPED

    # 我方只持有 1 手多：源平 3 手，只能平 1 手
    fake.positions[("rb2610.SHFE", "多")] = (1, 0)
    feed(e, tid="C2", offset="平", direction="空", volume=3)
    assert fake.sent == [("rb2610.SHFE", "close_long", 3500.0, 1)]
    e.stop()


def test_close_respects_frozen_positions(fake):
    e = make_engine(fake)
    fake.positions[("rb2610.SHFE", "多")] = (2, 2)                  # 全被挂单冻结
    feed(e, tid="C1", offset="平", direction="空", volume=2)
    assert fake.sent == []
    e.stop()


def test_zero_volume_skipped(fake):
    e = make_engine(fake, multiplier=0.1)                            # 2 × 0.1 = 0.2 -> 0
    feed(e, tid="Z1", volume=2)
    assert fake.sent == []
    assert "手数为 0" in e.get_records()[0]["message"]
    e.stop()


def test_missing_price_skips_and_never_guesses(fake):
    fake.price = (None, "行情尚未到达")
    e = make_engine(fake)
    feed(e)
    assert fake.sent == []
    assert "价格" in e.get_records()[0]["message"]
    e.stop()


def test_missing_contract_skips_in_live(fake):
    fake.contract = None
    e = make_engine(fake)
    feed(e)
    assert fake.sent == []
    e.stop()


# ----------------------------------------------------------------------------
# 信号过滤：品种白名单 / 信号延迟
# ----------------------------------------------------------------------------

def test_whitelist(fake):
    e = make_engine(fake, symbol_whitelist="ag")
    feed(e, tid="W1", symbol="rb2610")
    assert fake.sent == []
    feed(e, tid="W2", symbol="ag2612")
    assert len(fake.sent) == 1
    e.stop()


def test_signal_delay_dropped(fake):
    e = make_engine(fake, signal_max_delay=3)
    old = datetime.datetime.now() - datetime.timedelta(seconds=30)
    feed(e, tid="D1", ts=old)
    assert fake.sent == []
    assert "延迟" in e.get_records()[0]["message"]
    e.stop()


def test_paused_drops_signals(fake):
    e = make_engine(fake)
    e._pause("测试暂停")
    feed(e, tid="X1")
    assert fake.sent == []
    e.resume()
    feed(e, tid="X2")
    assert len(fake.sent) == 1
    e.stop()


def test_watchdog_pauses_on_disconnect(fake):
    e = make_engine(fake)
    fake.monitor_ok = False
    deadline = time.time() + 5
    while time.time() < deadline and not e.paused_reason:
        time.sleep(0.1)
    assert "监控" in e.paused_reason
    e.stop()


# ----------------------------------------------------------------------------
# 模拟 & 下单结果
# ----------------------------------------------------------------------------

def test_simulate_never_sends(fake):
    e = make_engine(fake, simulate=True)
    feed(e, volume=2)
    assert fake.sent == []
    r = e.get_records()[0]
    assert r["status"] == ct.ST_SIMULATED and r["volume"] == 2
    e.stop()


def test_rejected_order_recorded(fake):
    fake.send_result = {"success": False, "message": "资金不足", "vt_orderids": []}
    e = make_engine(fake)
    feed(e)
    r = e.get_records()[0]
    assert r["status"] == ct.ST_FAILED and "资金不足" in r["message"]
    e.stop()


def test_timeout_cancels_unfilled_order(fake):
    def slow_send(vt, action, price, volume):
        fake.sent.append((vt, action, price, volume))
        fake.orders["CTP.S"] = {"vt_orderid": "CTP.S", "active": True, "traded": 0, "status": "未成交"}
        return {"success": True, "message": "委托已提交", "vt_orderids": ["CTP.S"]}
    fake.send_limit_order = slow_send
    ct.ctp_service.send_limit_order = slow_send
    e = make_engine(fake, order_timeout=0.5)
    feed(e)
    deadline = time.time() + 5
    while time.time() < deadline and e.get_records()[0]["status"] == ct.ST_SUBMITTED:
        time.sleep(0.1)
    assert fake.cancelled == ["CTP.S"]
    assert e.get_records()[0]["status"] == ct.ST_CANCELLED
    e.stop()


def test_stop_then_restart_gets_fresh_state(fake):
    e = make_engine(fake)
    feed(e, tid="A")
    e.stop()
    assert e.start({"simulate": False, "size_mode": "multiple", "signal_max_delay": 0})["success"]
    assert e.follow_count == 0
    feed(e, tid="B")
    assert len(fake.sent) == 2
    e.stop()
