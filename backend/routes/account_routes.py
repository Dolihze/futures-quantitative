"""账号：期货公司列表、登录 / 退出、记住账号凭据、资金快照。"""
import json

from flask import Blueprint, jsonify, request, session

from backend import config
from backend.core import copy_trading, credential_store, ctp_service

bp = Blueprint('account', __name__)

# 期货公司列表。由 init() 在应用创建时加载，导入本模块本身没有副作用。
_broker_groups = {}


def load_broker_groups():
    path = config.find_data_file('data', 'brokers.json')
    print(f"[Backend] 数据文件路径: {path}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            groups = json.load(f)
        print(f"[Backend] 成功加载 {len(groups)} 个期货公司组")
        return groups
    except FileNotFoundError:
        print(f"[Backend] 警告：数据文件未找到: {path}")
    except Exception as e:
        print(f"[Backend] 警告：加载数据文件失败: {e}")
    return {}


def init():
    """加载期货公司列表和 CTP 接入参数。由 create_app() 调用。"""
    global _broker_groups
    _broker_groups = load_broker_groups()
    # CTP 接入参数：data/ctp_brokers.json（入库，仅含公开的 SimNow）
    # + data/ctp_brokers.local.json（不入库，放真实期货公司参数，同名覆盖）
    ctp_service.load_configs([
        config.find_data_file('data', 'ctp_brokers.json'),
        config.find_data_file('data', 'ctp_brokers.local.json'),
    ])


@bp.route('/api/brokers')
def get_brokers():
    """提供期货公司列表数据"""
    return jsonify(_broker_groups)


@bp.route('/api/login', methods=['POST'])
def login():
    """期货账号登录：通过 CTP 完成终端认证 + 登录，成功后保存会话"""
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', '')).strip()
    broker = str(data.get('broker', '')).strip()

    if not broker:
        return jsonify({"success": False, "message": "请选择期货公司"}), 400
    if not username or not password:
        return jsonify({"success": False, "message": "请输入账号和密码"}), 400

    # 密码只传给 CTP 接口，不写入 session / 日志
    result = ctp_service.login(broker, username, password)
    if not result.get("success"):
        session.clear()
        return jsonify({"success": False, "message": result.get("message", "登录失败")})

    session['logged_in'] = True
    session['username'] = username
    session['broker'] = broker

    # 「记住账号」：只在登录成功后才保存（避免存下输错的密码）；取消勾选则清除旧记录
    password_saved = False
    if data.get('remember'):
        password_saved = credential_store.save(broker, username, password)
    else:
        credential_store.clear()

    return jsonify({"success": True, "message": "登录成功", "data": result.get("data"),
                    "password_saved": password_saved})


@bp.route('/api/credentials', methods=['GET'])
def get_credentials():
    """读取「记住账号」保存的凭据，用于登录页预填；没有记录返回 saved=false"""
    cred = credential_store.load()
    if not cred:
        return jsonify({"saved": False})
    return jsonify({"saved": True, **cred})


@bp.route('/api/credentials', methods=['DELETE'])
def delete_credentials():
    """清除已保存的凭据"""
    credential_store.clear()
    return jsonify({"success": True})


@bp.route('/api/account')
def get_account():
    """当前登录账号的资金、持仓快照（来自 CTP 会话）"""
    snap = ctp_service.snapshot()
    if snap is None:
        return jsonify({"success": False, "connected": False, "message": "未连接期货账户或连接已断开"})
    return jsonify({"success": True, "connected": True, "data": snap})


@bp.route('/api/logout', methods=['POST'])
def logout():
    """退出登录：先停止跟单，再关闭 CTP 会话（含被监控账号）"""
    copy_trading.engine.stop("退出登录")
    ctp_service.monitor_logout()
    ctp_service.logout()
    session.clear()
    return jsonify({"success": True})


@bp.route('/api/quant-login', methods=['POST'])
def quant_login():
    """交易页「连接量化账号」：复用登录页建立的 CTP 会话，返回真实资金、持仓。

    不再使用写死的账号；没有真实会话（例如用调试模式进入）时返回失败。
    """
    snap = ctp_service.snapshot()
    if snap is None:
        return jsonify({
            "success": False,
            "message": "未登录期货账户或连接已断开，请退出后用期货账号重新登录（调试模式无真实账户）"
        })
    return jsonify({"success": True, "message": "连接成功", "data": snap})
