"""量化监控：登录被监控账号（只读会话）+ 跟单引擎。"""
import io
import time
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request
from openpyxl import Workbook
from openpyxl.styles import Font

from backend.core import copy_trading, credential_store, ctp_service

bp = Blueprint('monitor', __name__)

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
LOG_LEVEL_TEXT = {"info": "信息", "warn": "警告", "error": "错误"}

MONITOR_CRED_SLOT = "monitor"   # 被监控账号的凭据槽位（见 credential_store）


@bp.route('/api/monitor/login', methods=['POST'])
def monitor_login():
    """登录被监控账号（只读，不会用它下单）：{broker, username, password}"""
    data = request.get_json(silent=True) or {}
    broker = str(data.get('broker', '')).strip()
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', '')).strip()
    if not broker:
        return jsonify({"success": False, "message": "请选择期货公司"}), 400
    if not username or not password:
        return jsonify({"success": False, "message": "请输入被监控账号和密码"}), 400
    if copy_trading.engine.running:
        return jsonify({"success": False, "message": "跟单运行中，请先停止跟单再更换被监控账号"})
    result = ctp_service.monitor_login(broker, username, password,
                                       copy_trading.engine.on_source_trade)
    if result.get("success"):
        # 「记住账号密码」：只在登录成功后才保存（避免存下输错的密码）；取消勾选则清除旧记录。
        # 存在独立槽位，不影响登录页记住的交易账号
        password_saved = False
        if data.get('remember'):
            password_saved = credential_store.save(broker, username, password, slot=MONITOR_CRED_SLOT)
        else:
            credential_store.clear(slot=MONITOR_CRED_SLOT)
        result = {**result, "password_saved": password_saved}
    return jsonify(result)


@bp.route('/api/monitor/credentials', methods=['GET'])
def monitor_credentials():
    """读取量化监控「记住账号密码」保存的被监控账号，用于表单预填；没有记录返回 saved=false"""
    cred = credential_store.load(slot=MONITOR_CRED_SLOT)
    if not cred:
        return jsonify({"saved": False})
    return jsonify({"saved": True, **cred})


@bp.route('/api/monitor/logout', methods=['POST'])
def monitor_logout():
    """断开被监控账号（同时停止跟单）"""
    copy_trading.engine.stop("断开被监控账号")
    ctp_service.monitor_logout()
    return jsonify({"success": True})


@bp.route('/api/monitor/account')
def monitor_account():
    """被监控账号的权益与持仓"""
    snap = ctp_service.monitor_snapshot()
    if snap is None:
        return jsonify({"success": False, "message": "被监控账号未连接"})
    return jsonify({"success": True, "data": snap})


@bp.route('/api/monitor/status')
def monitor_status():
    """跟单引擎状态（含配置、连接状态、权益）"""
    return jsonify({"success": True, "data": copy_trading.engine.status()})


@bp.route('/api/monitor/records')
def monitor_records():
    """跟单记录与运行日志"""
    return jsonify({"success": True, "data": {
        "records": copy_trading.engine.get_records(),
        "logs": copy_trading.engine.get_logs(),
    }})


def build_logs_xlsx(logs):
    """把运行日志写成 Excel 字节流。引擎里的日志是「最新在前」，导出按时间正序（旧 -> 新），方便从头往下读。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "运行日志"
    ws.append(["时间", "级别", "内容"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for entry in reversed(logs):
        level = str(entry.get("level", ""))
        ws.append([str(entry.get("time", "")), LOG_LEVEL_TEXT.get(level, level), str(entry.get("msg", ""))])
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 8
    ws.column_dimensions["C"].width = 100
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@bp.route('/api/monitor/logs/export')
def monitor_logs_export():
    """导出运行日志为 Excel（.xlsx），时间正序"""
    data = build_logs_xlsx(copy_trading.engine.get_logs())
    filename = f"运行日志_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    # filename* 用 RFC 5987 编码，中文文件名在各浏览器 / WebView 里都不会乱码
    return Response(data, mimetype=XLSX_MIMETYPE, headers={
        "Content-Disposition": f"attachment; filename=monitor_logs.xlsx; filename*=UTF-8''{quote(filename)}",
    })


@bp.route('/api/monitor/start', methods=['POST'])
def monitor_start():
    """启动跟单：{config: {...}}。必须由前端二次确认后调用"""
    data = request.get_json(silent=True) or {}
    return jsonify(copy_trading.engine.start(data.get('config')))


@bp.route('/api/monitor/stop', methods=['POST'])
def monitor_stop():
    return jsonify(copy_trading.engine.stop())


@bp.route('/api/monitor/config', methods=['POST'])
def monitor_config():
    """运行中更新跟单配置（仅对之后的信号生效）"""
    data = request.get_json(silent=True) or {}
    return jsonify(copy_trading.engine.update_config(data.get('config')))


@bp.route('/api/monitor/config/save', methods=['POST'])
def monitor_config_save():
    """只保存跟单配置到本地（不启动跟单），下次打开软件时恢复"""
    data = request.get_json(silent=True) or {}
    return jsonify(copy_trading.engine.save_draft_config(data.get('config')))


@bp.route('/api/monitor/resume', methods=['POST'])
def monitor_resume():
    """人工解除断连造成的自动暂停"""
    return jsonify(copy_trading.engine.resume())
