# 量化回测功能使用说明

## 功能概述

量化回测由两个页面组成：

- 回测对象是**各常见期货品种的主连**（上期所、能源中心、大商所、郑商所、中金所共约 65 个品种），在总览页右上角的下拉框选择，**默认燃料油主连**。选择会同步到地址栏，进入详情再返回不会丢。
- **策略总览**（`/backtest`）：以卡片展示每个量化策略在所选时间范围（7/30/60/90 天）内的**胜率**、**盈亏比**、**模拟盈亏**、交易笔数、最大回撤和缩略净值曲线，点击卡片进入详情。
- **策略详情**（`/backtest/:策略id`）：
  - 核心统计：胜率、盈亏比、总盈亏、收益率、最大回撤、盈利因子、连胜连亏、多空分别统计等；
  - K 线图上的买卖成交点：三角形为开仓（尖朝上=多头，尖朝下=空头），圆点为平仓，虚线连接开仓与平仓（红=盈利、绿=亏损）；
  - 盈利曲线：每笔交易平仓后的累计盈亏；
  - 成交明细表：每笔的开平仓时间/价格、手数、止盈止损价、平仓原因、持仓 K 线数、盈亏、账户权益；点击一行会把 K 线定位到该笔交易。

回测在 Python 后端（`backtest_engine.py`）里执行，前端只负责展示。

## 统计口径

- 初始资金 10000 元，每笔 5 手（URL 参数 `lots` 可调），**不含手续费与滑点**。
- 同一时刻只持一个仓位；以信号 K 线的收盘价开仓；之后逐根 K 线检查止盈止损，同一根 K 线同时触及两者时按止损处理（保守）；数据结束仍有持仓按最后收盘价强制平仓。
- **胜率** = 盈利笔数 / 总笔数。
- **盈亏比** = 平均盈利 / 平均亏损（没有亏损单时显示 `∞`）。
- **盈利因子** = 总盈利 / 总亏损。
- 数据来源于新浪财经（akshare）。新浪每个周期只提供最近约 1023 根 K 线（5 分钟线约 3 周），因此 30/60/90 天在短周期策略下实际可用数据可能不足所选天数，时间范围以数据中最后一根 K 线为基准往前推。

## 已有策略

| id | 名称 | 周期 | 说明 |
| --- | --- | --- | --- |
| `reversal` | 反转信号 | 5 分钟 | 日盘 09:00-09:15 / 夜盘 21:00-21:15 内，指标出现红柱做多、绿柱做空，每个时段最多开一单，止盈止损各 10 跳 |

## 新增策略

在 `backtest_engine.py` 里写一个函数并用 `@register` 注册，首页会自动出现新卡片，无需改前端：

```python
@register(id="my_strategy", name="我的策略", description="一句话说明", category="趋势", period="5")
def strategy_my(bars, ctx):
    # bars: [{time, open, high, low, close, volume}, ...]；ctx: symbol / tick_size / multiplier
    # 返回与 bars 等长的列表：想在这根 K 线收盘开仓就给 Signal，否则 None
    signals = [None] * len(bars)
    ...
    signals[i] = Signal("long", take_profit=距离, stop_loss=距离, reason="触发原因")
    return signals
```

`backtest_engine.py` 里已提供 `sma / ema / ma / hhv / llv / ref / rsi` 等指标函数。修改后请运行 `python -m pytest tests/test_backtest_engine.py -q`，并执行 `npm run backend:build` 重新打包 sidecar。

## 接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/backtest/strategies` | 策略列表 |
| `GET /api/backtest/products` | 可回测的品种（主连）列表与默认品种 |
| `GET /api/backtest/overview?product&days&lots` | 首页：所选品种上所有策略的统计与缩略净值曲线（`product` 默认 `FU`） |
| `GET /api/backtest/run?strategy&product&days&lots` | 详情：K 线、逐笔成交、净值曲线、完整统计 |
| `GET /api/backtest/kline?product&period&days` | 原始 K 线 |

## 使用方法

```bash
pip install -r requirements.txt
npm install
npm run dev
```

首次运行或修改 `backend.py` / `backtest_engine.py` 后，需先执行 `npm run backend:build` 重新打包 sidecar。登录后在首页点击"量化回测"即可进入策略总览。

## 注意事项

1. 确保网络连接正常；首页首次加载要取 K 线并回测所有策略，可能需要几秒钟（后端对 K 线缓存 5 分钟）。
2. 品种目录、最小变动价位和合约乘数维护在 `backtest_engine.py` 的 `_CATALOG` 里（新浪主连代码 = 品种代码 + `0`，如 `FU0`、`RB0`，已逐个核对能取到数据；最小变动价位已用价格数据交叉校验）。要增删品种改这一处即可，下拉框和接口自动跟随。动力煤 ZC 已停止交易，不收录。
3. 主连是新浪拼接的连续行情，换月处价格可能有跳空，回测时会被当作一次正常的价格变动。
4. 策略和品种要匹配：例如「反转信号」只在 09:00-09:15 / 21:00-21:15 开仓，股指、国债期货 09:30 开盘且没有夜盘，所以在这些品种上不会产生交易，卡片上会提示。

## 后续开发计划

- [ ] 增加更多策略（均线交叉、布林突破、RSI 反转等）
- [ ] 手续费与滑点参数
- [ ] 自定义时间区间
- [ ] 按品种分别设置手数、品种级手续费
