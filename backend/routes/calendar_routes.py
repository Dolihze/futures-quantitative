"""交易日历：某段日期内哪些是交易日 / 非交易日（周末 + 法定节假日）。"""
import datetime as dt

from flask import Blueprint, jsonify, request

from backend.errors import ApiError, bad_request
from backend.services import calendar_service as cal

bp = Blueprint('calendar', __name__)


def _parse_day(name):
    raw = (request.args.get(name) or '').strip()
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError:
        raise bad_request(f"{name} 需要 YYYY-MM-DD 格式的日期")


@bp.route('/api/calendar/trading-days')
def trading_days():
    """[start, end] 内的交易日与休市日（周末、法定节假日）。

    refresh=1 强制联网刷新交易日历；否则优先用本地缓存（一天内有效）。
    日历数据只覆盖到某个年底，end 超出的部分 covered=false，休市日不包含这一段。
    """
    start, end = _parse_day('start'), _parse_day('end')
    if start > end:
        raise bad_request("start 不能晚于 end")
    if (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days > 3660:
        raise bad_request("日期范围过长（最多 10 年）")

    data = cal.load(force=request.args.get('refresh') == '1')
    if data is None:
        raise ApiError("交易日历暂时不可用：本地没有缓存，联网获取也失败了，请检查网络后重试", 503)

    covered_to = data['days'][-1]
    trading = [d for d in data['days'] if start <= d <= end]
    have = set(trading)
    closed = []
    d, last = dt.date.fromisoformat(start), dt.date.fromisoformat(min(end, covered_to))
    while d <= last:
        s = d.isoformat()
        if s not in have:
            closed.append(s)
        d += dt.timedelta(days=1)
    return jsonify({'success': True, 'start': start, 'end': end, 'tradingDays': trading, 'closedDays': closed,
                    'coveredTo': covered_to, 'stale': data['stale'], 'fetchedAt': int(data['fetchedAt'])})
