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

    user = USERS.get(username)
    if user and user["password"] == password:
        session['logged_in'] = True
        session['username']  = username
        session['broker']    = broker
        return jsonify({"success": True, "message": "登录成功"})
    else:
        return jsonify({"success": False, "message": "账号或密码错误，请重新输入"}), 401


@app.route('/')
def index():
    """主页 - 需要登录才能访问"""
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))
    return render_template('index.html', username=session.get('username', ''))


@app.route('/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({"success": True})


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
