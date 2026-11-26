"""量化回测：本地已导入合约、K 线、策略列表、总览与单策略回测。

回测对象是「数据库管理 → 历史行情数据管理」里已导入的具体合约（如 fu2611），K 线由库内 tick 聚合而来，
不再访问在线行情接口。合约没导入时返回 404 并提示去导入。
"""
from flask import Blueprint, jsonify, request

from backend.core import backtest_engine, recent_store
from backend.errors import bad_request, not_found, wrap_errors
from backend.services import backtest_service, kline_store

bp = Blueprint('backtest', __name__)


def _backtest_params():
    """symbol（本地库里的合约代码）、days、lots，返回 (symbol, days, lots)。

    参数不合法时直接抛 ApiError(400)，由统一处理器返回 `参数错误：...`。
    合约是否已导入由取 K 线时判断（未导入返回 404 + 导入提示）。
    """
    symbol = (request.args.get('symbol') or '').strip()
    if not symbol:
        raise bad_request('参数错误：请先选择合约（需要先在「数据库管理」导入该合约的 tick 数据）')
    try:
        days = int(request.args.get('days', 30))
        lots = int(request.args.get('lots', backtest_engine.DEFAULT_LOTS))
        if days <= 0 or lots <= 0:
            raise ValueError('days 和 lots 必须大于 0')
    except ValueError as e:
        raise bad_request(f'参数错误：{e}')
    return symbol, days, lots


def _recent_symbols(data):
    """最近手动选过的合约（最新在前，最多 3 个），只保留现在库里还在的：合约被删后不能再出现在下拉里。"""
    existing = {c['symbol'] for c in data}
    return [s for s in recent_store.recent(recent_store.KIND_BACKTEST_SYMBOL) if s in existing]


@bp.route('/api/backtest/contracts')
def backtest_contracts():
    """可回测的合约：本地历史行情库里已导入的合约，附带数据覆盖的交易日范围。

    recent：最近手动选过的合约（最新在前，最多 3 个，入库保存）。
    default：进页面时默认加载的合约 = 最近使用的第一个；没有使用记录（或都已被删除）时退回库里的第一个。
    """
    data = kline_store.list_contracts()
    for c in data:
        c['label'] = backtest_engine.contract_name(c['symbol'])
    recent = _recent_symbols(data)
    default = recent[0] if recent else (data[0]['symbol'] if data else '')
    return jsonify({'success': True, 'default': default, 'recent': recent, 'data': data})


@bp.route('/api/backtest/recent-symbol', methods=['POST'])
def backtest_recent_symbol():
    """记一次「手动选择合约」：把它放到最近使用的最前面（最多保留 3 个），返回最新的列表。

    只接受本地库里存在的合约；记录失败（数据库异常）不算错误，只是这次没记上，不影响回测。
    """
    body = request.get_json(silent=True) or {}
    symbol = str(body.get('symbol') or '').strip()
    if not symbol:
        raise bad_request('参数错误：缺少合约 symbol')
    data = kline_store.list_contracts()
    match = next((c['symbol'] for c in data if c['symbol'].lower() == symbol.lower()), None)
    if match is None:
        raise not_found(f'本地行情库里没有合约「{symbol}」', fileMissing=True)
    recent_store.touch(recent_store.KIND_BACKTEST_SYMBOL, match)
    return jsonify({'success': True, 'recent': _recent_symbols(data)})


@bp.route('/api/backtest/kline')
@wrap_errors('获取数据失败', log_tag='[API]', sep=': ', log_prefix='获取K线数据失败')
def get_kline_data():
    """获取某合约在本地库里的 K 线数据。参数：symbol、period、days"""
    symbol, days, _ = _backtest_params()
    period = request.args.get('period', '1')
    if period not in backtest_service.BACKTEST_PERIODS:
        raise bad_request(f'不支持的周期：{period}')
    bars = backtest_engine.slice_recent_days(backtest_service.fetch_backtest_bars(symbol, period), days)
    if not bars:
        raise not_found('未获取到数据')
    return jsonify({'success': True, 'data': bars, 'symbol': symbol,
                    'symbolName': backtest_engine.contract_name(symbol), 'count': len(bars)})


@bp.route('/api/backtest/strategies')
def backtest_strategies():
    """已注册的量化策略列表（不含回测结果）"""
    return jsonify({'success': True, 'data': backtest_engine.list_strategies()})


@bp.route('/api/backtest/overview')
def backtest_overview():
    """首页：对所有策略在最近 days 天内回测，返回每个策略的胜率、盈亏比、总盈亏和缩略净值曲线。

    参数：symbol（本地库里的合约代码）、days（默认 30）、lots（默认 5）。
    每个策略使用它自己声明的 K 线周期；某个策略失败不影响其它策略，失败原因放在该策略的 error 字段里。
    合约本身没导入时整体返回 404（所有策略都没数据，逐个报错没有意义）。
    """
    symbol, days, lots = _backtest_params()
    # 先探测合约是否在库里：没导入就直接 404 + 导入提示，而不是 N 张一模一样的错误卡片
    backtest_service.fetch_backtest_bars(symbol, backtest_service.BACKTEST_PERIODS[0])

    items = []
    for sdef in backtest_engine.sorted_strategies():   # 新创建的策略排最前（按创建日期由新到旧）
        info = {'id': sdef.id, 'name': sdef.name, 'description': sdef.description,
                'category': sdef.category, 'period': sdef.period, 'managed': sdef.managed,
                'created': sdef.created}
        try:
            all_bars = backtest_service.fetch_backtest_bars(symbol, sdef.period)
            bars = backtest_engine.slice_recent_days(all_bars, days)
            if not bars:
                raise ValueError('未获取到K线数据')
            result = backtest_engine.run_backtest(bars, sdef.id, symbol, lots)
            info.update(stats=result['stats'], equity=result['equity'], error=None,
                        coverage=backtest_engine.data_coverage(all_bars, days))
        except Exception as e:   # 单个策略失败不影响其它策略：错误写进该策略的 error 字段，而不是整个接口失败
            print(f"[Backtest] 策略 {sdef.id} 回测失败: {e}")
            info.update(stats=None, equity=[], error=str(getattr(e, 'message', e)), coverage=None)
        items.append(info)
    # 页面级可选范围：各策略可得天数的最大值决定上限（短周期策略数据少，用各自实际可得的全部数据）
    avail = max((i['coverage']['availableDays'] for i in items if i.get('coverage')), default=0)
    return jsonify({'success': True, 'symbol': symbol,
                    'symbolName': backtest_engine.contract_name(symbol),
                    'days': days, 'lots': lots, 'availableDays': avail, 'data': items})


@bp.route('/api/backtest/run')
@wrap_errors('回测失败', log_tag='[Backtest]')
def backtest_run():
    """详情页：回测单个策略，返回 K 线、成交明细（含买卖点）、净值曲线和完整统计。

    参数：strategy（策略 id）、symbol、days、lots。
    """
    strategy = request.args.get('strategy', '').strip()
    if strategy not in backtest_engine.STRATEGIES:
        raise not_found(f'未知策略：{strategy}')
    symbol, days, lots = _backtest_params()
    sdef = backtest_engine.STRATEGIES[strategy]
    all_bars = backtest_service.fetch_backtest_bars(symbol, sdef.period)
    bars = backtest_engine.slice_recent_days(all_bars, days)
    if not bars:
        raise not_found('未获取到K线数据')
    result = backtest_engine.run_backtest(bars, strategy, symbol, lots)
    result.update(success=True, days=days, period=sdef.period, kline=bars,
                  symbolName=backtest_engine.contract_name(symbol),
                  coverage=backtest_engine.data_coverage(all_bars, days))
    return jsonify(result)
