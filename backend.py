#!/usr/bin/env python3
"""
Flask Backend as Tauri Sidecar
用于 Tauri 2.x 架构,作为独立进程运行
"""
from flask import Flask, request, jsonify, session
from flask_cors import CORS
import json
import os
import sys
import uuid
from collections import OrderedDict

import review  # 交易复盘：Excel 解析与盈亏曲线（review.py）

# 配置 Flask 应用
app = Flask(__name__)
app.secret_key = os.urandom(24)

# 启用 CORS 支持（允许 Tauri WebView 访问）
CORS(app, supports_credentials=True, origins=[
    'tauri://localhost',
    'https://tauri.localhost',
    'http://localhost:5173',
    'http://127.0.0.1:5173'
])

# 动态获取基础路径（兼容开发模式和打包模式）
def get_base_dir():
    """获取可执行文件所在目录"""
    if getattr(sys, 'frozen', False):
        # 打包后运行（PyInstaller）
        return os.path.dirname(sys.executable)
    else:
        # 开发模式
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()


def find_data_file(*parts):
    """按优先级查找数据文件：PyInstaller 内置资源 > exe 同级目录 > 当前工作目录向上查找（开发模式）"""
    candidates = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(os.path.join(meipass, *parts))
    candidates.append(os.path.join(BASE_DIR, *parts))
    # 开发模式下 sidecar 位于 src-tauri/target/debug，向上回溯查找项目根目录的 data
    cur = BASE_DIR
    for _ in range(5):
        candidates.append(os.path.join(cur, *parts))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    candidates.append(os.path.join(os.getcwd(), *parts))
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


# 加载期货公司数据
BROKER_DATA_PATH = find_data_file('data', 'brokers.json')
print(f"[Backend] 基础路径: {BASE_DIR}")
print(f"[Backend] 数据文件路径: {BROKER_DATA_PATH}")

try:
    with open(BROKER_DATA_PATH, 'r', encoding='utf-8') as f:
        BROKER_GROUPS = json.load(f)
    print(f"[Backend] 成功加载 {len(BROKER_GROUPS)} 个期货公司组")
except FileNotFoundError:
    print(f"[Backend] 警告：数据文件未找到: {BROKER_DATA_PATH}")
    BROKER_GROUPS = {}
except Exception as e:
    print(f"[Backend] 警告：加载数据文件失败: {e}")
    BROKER_GROUPS = {}

# 模拟账户数据
USERS = {
    "admin": {"password": "123456", "broker": "ctp"},
    "test":  {"password": "test123", "broker": "simnow"},
}


@app.route('/api/brokers')
def get_brokers():
    """提供期货公司列表数据"""
    return jsonify(BROKER_GROUPS)


@app.route('/api/login', methods=['POST'])
def login():
    """处理登录请求"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    broker   = data.get('broker', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "请输入账号和密码"}), 400

    # 调试模式：暂时跳过验证
    session['logged_in'] = True
    session['username']  = username
    session['broker']    = broker
    return jsonify({"success": True, "message": "登录成功"})


@app.route('/api/backtest/kline')
def get_kline_data():
    """获取K线数据API"""
    from datetime import datetime, timedelta
    import akshare as ak
    import pandas as pd
    
    try:
        symbol = request.args.get('symbol', 'FU2611')
        period = request.args.get('period', '1')
        days = int(request.args.get('days', 30))
        
        print(f"[API] 请求参数: symbol={symbol}, period={period}, days={days}")
        
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        
        if df is not None and not df.empty:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df[df['datetime'] >= start_date]
            
            data = []
            for _, row in df.iterrows():
                data.append({
                    'time': row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['volume']) if 'volume' in row else 0
                })
            
            return jsonify({
                'success': True,
                'data': data,
                'symbol': symbol,
                'count': len(data)
            })
        else:
            return jsonify({
                'success': False,
                'message': '未获取到数据'
            }), 404
            
    except Exception as e:
        print(f"[API] 获取K线数据失败: {str(e)}")
        import traceback
        error_detail = traceback.format_exc()
        print(f"[API] 详细错误信息:\n{error_detail}")
        return jsonify({
            'success': False,
            'message': f'获取数据失败: {str(e)}',
            'error': error_detail
        }), 500


# ---------------------------------------------------------------------------
# 交易复盘
# ---------------------------------------------------------------------------
# 上传的交易记录只保存在内存里（不落盘，属于个人交易数据）；sidecar 重启即清空。
# 最多保留最近 5 份，避免反复上传导致内存无限增长。
REVIEW_CACHE = OrderedDict()
REVIEW_CACHE_MAX = 5
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"success": False, "message": "文件过大，请上传 20MB 以内的文件"}), 413


@app.route('/api/review/upload', methods=['POST'])
def review_upload():
    """上传交易记录 Excel，解析后返回可选品种和数据时间范围。"""
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({"success": False, "message": "请选择要上传的文件"}), 400
    if not f.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        return jsonify({"success": False, "message": "仅支持 .xlsx / .xls / .csv 文件"}), 400

    try:
        result = review.analyze(f.read(), f.filename)
    except review.ReviewParseError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # 解析库的意外错误：不要把 500 抛给用户，给出可读提示
        print(f"[Review] 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"解析失败：{e}"}), 400

    review_id = uuid.uuid4().hex
    REVIEW_CACHE[review_id] = result.records
    while len(REVIEW_CACHE) > REVIEW_CACHE_MAX:
        REVIEW_CACHE.popitem(last=False)

    return jsonify({
        "success": True,
        "reviewId": review_id,
        "filename": f.filename,
        "products": result.products,
        "start": result.start,
        "end": result.end,
        "tradeCount": int(len(result.records)),
        "hasFee": result.has_fee,
        "warnings": result.warnings,
    })


@app.route('/api/review/curve')
def review_curve():
    """按品种 / 时间范围筛选，返回累计平仓盈亏曲线和统计。

    参数：reviewId（必填）、products（逗号分隔，空=全部）、start、end（YYYY-MM-DD[ HH:MM:SS]）、
    fee（1=扣除手续费，0=不扣，默认 1）。
    """
    review_id = request.args.get('reviewId', '')
    records = REVIEW_CACHE.get(review_id)
    if records is None:
        return jsonify({"success": False, "expired": True,
                        "message": "交易记录已失效（应用重启过），请重新上传文件"}), 404

    products = [p for p in request.args.get('products', '').split(',') if p]
    start = request.args.get('start') or None
    end = request.args.get('end') or None
    include_fee = request.args.get('fee', '1') != '0'
    try:
        curve = review.build_curve(records, products or None, start, end, include_fee)
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "message": f"参数错误：{e}"}), 400
    return jsonify({"success": True, **curve})


@app.route('/api/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({"success": True})


@app.route('/api/quant-login', methods=['POST'])
def quant_login():
    """处理量化账号登录请求"""
    # 调试模式：暂时跳过实际登录
    # TODO: 接入真实 CTP 登录（vnpy_ctp.CtpGateway + vnpy.trader.engine.MainEngine）。
    #   账号/密码/交易密码/brokerid/td_address/md_address/auth_code 应从环境变量或
    #   加密配置读取，不要写进源码。旧的参考实现见 git 历史中的 app.py（提交 ed08d7c）。
    print(f"[调试模式] 量化账号登录请求 - 跳过实际验证")
    
    return jsonify({
        "success": True,
        "message": "登录成功（调试模式）",
        "data": {
            "account": "30522730",
            "balance": 100000.00,
            "available": 80000.00,
            "frozen": 20000.00
        }
    })


if __name__ == '__main__':
    # Sidecar 模式：监听 5000 端口
    print("[Backend] Flask Sidecar 启动中...")
    print("[Backend] 监听地址: http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
