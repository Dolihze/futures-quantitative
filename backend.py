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


@app.route('/api/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({"success": True})


@app.route('/api/quant-login', methods=['POST'])
def quant_login():
    """处理量化账号登录请求"""
    # 调试模式：暂时跳过实际登录
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
