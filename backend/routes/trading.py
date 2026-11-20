"""实盘交易：合约、行情、委托、持仓、成交、反手。"""
from flask import Blueprint, jsonify, request

from backend.core import ctp_service

bp = Blueprint('trading', __name__)


@bp.route('/api/contracts')
def get_contracts():
    """可交易的期货合约列表（登录后由 CTP 异步查询，刚登录时可能还没就绪）"""
    items, err = ctp_service.list_contracts()
    if items is None:
        return jsonify({"success": False, "message": err})
    return jsonify({"success": True, "data": items})


@bp.route('/api/quote')
def get_quote():
    """订阅并返回合约最新行情：?symbol=ag2612.SHFE"""
    vt_symbol = request.args.get('symbol', '').strip()
    if not vt_symbol:
        return jsonify({"success": False, "message": "缺少合约代码"}), 400
    quote, err = ctp_service.get_quote(vt_symbol)
    if quote is None:
        return jsonify({"success": False, "message": err})
    return jsonify({"success": True, "data": quote})


@bp.route('/api/order', methods=['POST'])
def place_order():
    """限价下单：{symbol: "ag2612.SHFE", action: open_long|open_short|close_long|close_short, price, volume}"""
    data = request.get_json(silent=True) or {}
    vt_symbol = str(data.get('symbol', '')).strip()
    action = str(data.get('action', '')).strip()
    if not vt_symbol or not action:
        return jsonify({"success": False, "message": "缺少合约或操作类型"}), 400
    result = ctp_service.send_limit_order(vt_symbol, action, data.get('price'), data.get('volume'))
    return jsonify(result)


@bp.route('/api/orders')
def get_orders():
    """当前会话的委托列表（最新的在前）"""
    items, err = ctp_service.list_orders()
    if items is None:
        return jsonify({"success": False, "message": err})
    return jsonify({"success": True, "data": items})


@bp.route('/api/positions')
def get_positions():
    """当前会话的持仓列表（含今昨仓、开仓均价、按最新价算的浮动盈亏）"""
    items, err = ctp_service.list_positions()
    if items is None:
        return jsonify({"success": False, "message": err})
    return jsonify({"success": True, "data": items})


@bp.route('/api/trades')
def get_trades():
    """当前会话的成交明细（最新的在前）"""
    items, err = ctp_service.list_trades()
    if items is None:
        return jsonify({"success": False, "message": err})
    return jsonify({"success": True, "data": items})


@bp.route('/api/reverse', methods=['POST'])
def start_reverse():
    """反手：{symbol, fromSide: "多"|"空", closePrice, openPrice, volume}。先平仓，平仓全部成交后再反向开仓"""
    data = request.get_json(silent=True) or {}
    vt_symbol = str(data.get('symbol', '')).strip()
    from_side = str(data.get('fromSide', '')).strip()
    if not vt_symbol or not from_side:
        return jsonify({"success": False, "message": "缺少合约或持仓方向"}), 400
    return jsonify(ctp_service.start_reverse(
        vt_symbol, from_side, data.get('closePrice'), data.get('openPrice'), data.get('volume')))


@bp.route('/api/reverse/cancel', methods=['POST'])
def cancel_reverse():
    """取消等待中的反手任务：{taskId}"""
    data = request.get_json(silent=True) or {}
    task_id = str(data.get('taskId', '')).strip()
    if not task_id:
        return jsonify({"success": False, "message": "缺少任务编号"}), 400
    return jsonify(ctp_service.cancel_reverse(task_id))


@bp.route('/api/reverse/tasks')
def get_reverse_tasks():
    """反手任务列表（含等待 / 已开仓 / 已取消 / 开仓失败）"""
    return jsonify({"success": True, "data": ctp_service.list_reverse_tasks()})


@bp.route('/api/order/cancel', methods=['POST'])
def cancel_order():
    """撤单：{orderId: "CTP.1_2_3"}"""
    data = request.get_json(silent=True) or {}
    order_id = str(data.get('orderId', '')).strip()
    if not order_id:
        return jsonify({"success": False, "message": "缺少委托号"}), 400
    return jsonify(ctp_service.cancel_order(order_id))
