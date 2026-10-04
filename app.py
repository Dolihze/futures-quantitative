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
    """获取K线数据API - 使用tushare获取真实数据"""
    from datetime import datetime, timedelta
    import tushare as ts
    import pandas as pd
    
    # tushare token配置 - 请替换为你自己的token
    # 在 https://tushare.pro 注册后获取
    TUSHARE_TOKEN = ''  # TODO: 请填入你的tushare token
    
    try:
        # 检查token是否配置
        if not TUSHARE_TOKEN:
            error_msg = '请先配置tushare token！在app.py中搜索TUSHARE_TOKEN并填入你的token'
            print(f"[API] 错误: {error_msg}")
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400
        
        # 初始化tushare
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        
        # 获取前端传入的参数
        symbol = request.args.get('symbol', 'FU2611')
        period = request.args.get('period', '1')
        days = int(request.args.get('days', 30))
        
        print(f"[API] 请求参数: symbol={symbol}, period={period}, days={days}")
        print(f"[API] 开始调用 tushare.ft_mins...")
        
        # 转换合约代码格式：FU2611 -> FU2611.SHF
        ts_symbol = convert_to_tushare_symbol(symbol)
        print(f"[API] 转换后的tushare合约代码: {ts_symbol}")
        
        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 格式化日期为tushare格式 (YYYY-MM-DD HH:MM:SS)
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"[API] 日期范围: {start_date_str} ~ {end_date_str}")
        
        # 使用tushare获取期货分钟级别数据
        # ft_mins: 期货分钟级别行情数据
        df = pro.ft_mins(
            ts_code=ts_symbol,
            freq=f'{period}min',
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        print(f"[API] tushare 返回数据类型: {type(df)}")
        print(f"[API] tushare 返回数据条数: {len(df) if df is not None else 0}")
        
        if df is not None and not df.empty:
            print(f"[API] 数据列名: {df.columns.tolist()}")
            print(f"[API] 前5行数据:\n{df.head()}")
            
            # 按时间正序排列（tushare默认是倒序）
            df = df.sort_values('trade_time', ascending=True).reset_index(drop=True)
            
            # 数据格式转换
            data = []
            for _, row in df.iterrows():
                # tushare的trade_time格式: '2026-10-04 10:30:00'
                data.append({
                    'time': row['trade_time'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['vol']) if 'vol' in row else 0
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
                'message': '未获取到数据，请检查合约代码是否正确或tushare权限是否足够'
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


def convert_to_tushare_symbol(symbol):
    """
    转换合约代码为tushare格式
    例如: FU2611 -> FU2611.SHF (上期所)
    """
    # 交易所映射规则
    exchange_map = {
        # 上海期货交易所 (SHF)
        'FU': 'SHF',  # 燃料油
        'RB': 'SHF',  # 螺纹钢
        'CU': 'SHF',  # 铜
        'AL': 'SHF',  # 铝
        'AU': 'SHF',  # 黄金
        'AG': 'SHF',  # 白银
        'ZN': 'SHF',  # 锌
        'PB': 'SHF',  # 铅
        'NI': 'SHF',  # 镍
        'SN': 'SHF',  # 锡
        'SS': 'SHF',  # 不锈钢
        'BU': 'SHF',  # 沥青
        'RU': 'SHF',  # 天然橡胶
        'SP': 'SHF',  # 纸浆
        
        # 大连商品交易所 (DCE)
        'M': 'DCE',   # 豆粕
        'Y': 'DCE',   # 豆油
        'I': 'DCE',   # 铁矿石
        'JM': 'DCE',  # 焦煤
        'J': 'DCE',   # 焦炭
        'A': 'DCE',   # 豆一
        'B': 'DCE',   # 豆二
        'C': 'DCE',   # 玉米
        'CS': 'DCE',  # 玉米淀粉
        'L': 'DCE',   # 聚乙烯
        'V': 'DCE',   # 聚氯乙烯
        'PP': 'DCE',  # 聚丙烯
        'EB': 'DCE',  # 苯乙烯
        'EG': 'DCE',  # 乙二醇
        'PG': 'DCE',  # 液化石油气
        
        # 郑州商品交易所 (CZC)
        'CF': 'CZC',  # 棉花
        'SR': 'CZC',  # 白糖
        'TA': 'CZC',  # PTA
        'OI': 'CZC',  # 菜籽油
        'RM': 'CZC',  # 菜籽粕
        'MA': 'CZC',  # 甲醇
        'FG': 'CZC',  # 玻璃
        'SA': 'CZC',  # 纯碱
        'SF': 'CZC',  # 硅铁
        'SM': 'CZC',  # 锰硅
        'AP': 'CZC',  # 苹果
        'CJ': 'CZC',  # 红枣
        'PK': 'CZC',  # 花生
        
        # 中国金融期货交易所 (CFX)
        'IF': 'CFX',  # 沪深300股指期货
        'IC': 'CFX',  # 中证500股指期货
        'IH': 'CFX',  # 上证50股指期货
        'T': 'CFX',   # 10年期国债期货
        'TF': 'CFX',  # 5年期国债期货
        'TS': 'CFX',  # 2年期国债期货
    }
    
    # 提取品种代码（去掉数字部分）
    variety_code = ''.join([c for c in symbol if c.isalpha()])
    
    # 获取对应的交易所代码
    exchange = exchange_map.get(variety_code.upper(), 'SHF')  # 默认使用SHF
    
    return f"{symbol}.{exchange}"


def start_flask():
    """在后台线程启动 Flask 服务器"""
    # 添加启动完成标记
    import time
    from werkzeug.serving import make_server
    
    # 创建 Flask 服务器
    server = make_server('127.0.0.1', 5000, app)
    
    # 标记服务器已就绪
    global flask_ready
    flask_ready = True
    print("[启动] Flask 服务器已就绪")
    
    # 启动服务器
    server.serve_forever()


def start_app():
    """启动桌面应用"""
    import time
    
    # 全局标记
    global flask_ready
    flask_ready = False
    
    # 在后台线程启动 Flask
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # 等待 Flask 服务器完全启动
    print("[启动] 正在等待 Flask 服务器启动...")
    max_wait = 5  # 最多等待5秒
    wait_count = 0
    while not flask_ready and wait_count < max_wait * 10:
        time.sleep(0.1)
        wait_count += 1
    
    if flask_ready:
        print("[启动] Flask 服务器已就绪，创建桌面窗口...")
    else:
        print("[启动] 警告：Flask 服务器启动超时，尝试创建窗口...")
    
    # 额外等待一小段时间确保服务器完全就绪
    time.sleep(0.5)
    
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
