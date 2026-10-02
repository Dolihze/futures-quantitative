from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import webview
import threading
import json
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 加载期货公司数据
BROKER_DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'brokers.json')
with open(BROKER_DATA_PATH, 'r', encoding='utf-8') as f:
    BROKER_GROUPS = json.load(f)

# 模拟账户数据（实际项目中应对接数据库）
USERS = {
    "admin": {"password": "123456", "broker": "ctp"},
    "test":  {"password": "test123", "broker": "simnow"},
}


@app.route('/api/brokers')
def get_brokers():
    """提供期货公司列表数据"""
    return jsonify(BROKER_GROUPS)


@app.route('/login', methods=['GET'])
def login_page():
    """渲染登录页面"""
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    """处理登录请求"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    broker   = data.get('broker', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "请输入账号和密码"}), 400

    # ====== 暂时放开账号密码验证，方便开发首页，后续恢复 ======
    session['logged_in'] = True
    session['username']  = username
    session['broker']    = broker
    return jsonify({"success": True, "message": "登录成功"})
    # ==============================================================


@app.route('/debug-login')
def debug_login():
    """调试模式：跳过登录验证，直接进入首页"""
    session['logged_in'] = True
    session['username']  = '管理员'
    session['broker']    = ''
    return redirect(url_for('home'))


@app.route('/')
def home():
    """首页 - 需要登录才能访问"""
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))
    return render_template('home.html', username=session.get('username', ''))


@app.route('/trading')
def trading():
    """交易页面 - 需要登录才能访问"""
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))
    return render_template('trading.html', username=session.get('username', ''))


@app.route('/backtest')
def backtest():
    """回测页面 - 需要登录才能访问"""
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))
    return render_template('backtest.html', username=session.get('username', ''))


@app.route('/api/backtest/kline')
def get_kline_data():
    """获取K线数据API"""
    from datetime import datetime, timedelta
    import akshare as ak
    import pandas as pd
    
    try:
        # 获取前端传入的参数
        symbol = request.args.get('symbol', 'FU2611')
        period = request.args.get('period', '1')
        days = int(request.args.get('days', 30))
        
        print(f"[API] 请求参数: symbol={symbol}, period={period}, days={days}")
        print(f"[API] 开始调用 akshare.futures_zh_minute_sina...")
        
        # 使用akshare获取期货分钟级别数据
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        
        print(f"[API] akshare 返回数据类型: {type(df)}")
        print(f"[API] akshare 返回数据条数: {len(df) if df is not None else 0}")
        
        if df is not None and not df.empty:
            print(f"[API] 数据列名: {df.columns.tolist()}")
            print(f"[API] 前5行数据:\n{df.head()}")
            
            # 根据days过滤数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 确保datetime列是datetime类型
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df[df['datetime'] >= start_date]
            
            # 数据格式转换
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
            
            print(f"[API] 成功返回 {len(data)} 条数据")
            return jsonify({
                'success': True,
                'data': data,
                'symbol': symbol,
                'count': len(data)
            })
        else:
            print(f"[API] 未获取到数据")
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
            'error': error_detail  # 开发期间返回详细错误信息
        }), 500


@app.route('/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({"success": True})


@app.route('/api/quant-login', methods=['POST'])
def quant_login():
    """处理量化账号登录请求 - 后台自动登录"""
    from vnpy_ctp import CtpGateway
    from vnpy.trader.engine import MainEngine
    from vnpy.trader.setting import SETTINGS
    
    # 中信建投账号配置
    # ⚠️ 安全警告：建议迁移到环境变量或加密存储
    QUANT_CONFIG = {
        "account": "30522730",
        "password": "Lx031260",  # 登录密码
        "trade_password": "031260",  # 交易密码
        "brokerid": "9999",  # 中信建投brokerid，需确认
        "td_address": "tcp://180.168.146.187:10130",  # 中信建投交易服务器地址，需确认
        "md_address": "tcp://180.168.146.187:10131",  # 中信建投行情服务器地址，需确认
        "auth_code": "",  # 认证码，需申请
        "user_product_info": ""  # 用户产品信息
    }
    
    try:
        # 创建主引擎
        main_engine = MainEngine()
        
        # 添加CTP网关
        main_engine.add_gateway(CtpGateway)
        
        # 配置CTP连接参数
        setting = {
            "用户名": QUANT_CONFIG["account"],
            "密码": QUANT_CONFIG["password"],
            "经纪商代码": QUANT_CONFIG["brokerid"],
            "交易服务器": QUANT_CONFIG["td_address"],
            "行情服务器": QUANT_CONFIG["md_address"],
            "产品名称": QUANT_CONFIG["user_product_info"],
            "授权编码": QUANT_CONFIG["auth_code"],
            "产品信息": ""
        }
        
        # 连接CTP
        main_engine.connect(setting, "CTP")
        
        # 等待连接（实际应该使用回调）
        import time
        time.sleep(2)
        
        # 检查连接状态
        # 这里简化处理，实际应该检查网关的连接状态
        print(f"量化账号登录请求: account={QUANT_CONFIG['account']}")
        
        return jsonify({
            "success": True,
            "message": "登录成功",
            "data": {
                "account": QUANT_CONFIG["account"],
                "balance": 0.00,
                "available": 0.00,
                "frozen": 0.00
            }
        })
        
    except Exception as e:
        print(f"量化登录失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"登录失败: {str(e)}"
        }), 500


def start_flask():
    """在后台线程启动 Flask 服务器"""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)


def start_app():
    """启动桌面应用"""
    # 在后台线程启动 Flask
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # 创建可缩放的桌面窗口
    window = webview.create_window(
        title='期货量化交易系统',
        url='http://127.0.0.1:5000/login',
        maximized=True,  # 默认最大化，保留标题栏和边框
        resizable=True,
        min_size=(420, 600)
    )

    # 启动 webview（这会阻塞主线程）
    webview.start()


if __name__ == '__main__':
    start_app()
