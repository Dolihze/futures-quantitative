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
import ctp_service  # CTP 实盘 / 仿真登录、资金持仓（ctp_service.py）
import credential_store  # 「记住账号」凭据存储，DPAPI 加密（credential_store.py）

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

# CTP 接入参数：data/ctp_brokers.json（入库，仅含公开的 SimNow）
# + data/ctp_brokers.local.json（不入库，放真实期货公司参数，同名覆盖）
ctp_service.load_configs([
    find_data_file('data', 'ctp_brokers.json'),
    find_data_file('data', 'ctp_brokers.local.json'),
])


@app.route('/api/brokers')
def get_brokers():
    """提供期货公司列表数据"""
    return jsonify(BROKER_GROUPS)


@app.route('/api/login', methods=['POST'])
def login():
    """期货账号登录：通过 CTP 完成终端认证 + 登录，成功后保存会话"""
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', '')).strip()
    broker   = str(data.get('broker', '')).strip()

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
    session['username']  = username
    session['broker']    = broker

    # 「记住账号」：只在登录成功后才保存（避免存下输错的密码）；取消勾选则清除旧记录
    password_saved = False
    if data.get('remember'):
        password_saved = credential_store.save(broker, username, password)
    else:
        credential_store.clear()

    return jsonify({"success": True, "message": "登录成功", "data": result.get("data"),
                    "password_saved": password_saved})


@app.route('/api/credentials', methods=['GET'])
def get_credentials():
    """读取「记住账号」保存的凭据，用于登录页预填；没有记录返回 saved=false"""
    cred = credential_store.load()
    if not cred:
        return jsonify({"saved": False})
    return jsonify({"saved": True, **cred})


@app.route('/api/credentials', methods=['DELETE'])
def delete_credentials():
    """清除已保存的凭据"""
    credential_store.clear()
    return jsonify({"success": True})


@app.route('/api/account')
def get_account():
    """当前登录账号的资金、持仓快照（来自 CTP 会话）"""
    snap = ctp_service.snapshot()
    if snap is None:
        return jsonify({"success": False, "connected": False, "message": "未连接期货账户或连接已断开"})
    return jsonify({"success": True, "connected": True, "data": snap})


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
# 解析后的交易记录放在内存缓存里（reviewId 是临时的，sidecar 重启即失效）。
# 最多保留最近 5 份，避免反复切换文件导致内存无限增长。
REVIEW_CACHE = OrderedDict()
REVIEW_CACHE_MAX = 5
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB

# 导入过的交易记录文件保存在这个文件夹里（开发模式 = 项目根目录，打包后 = 可执行文件同级目录），
# 之后可以直接在界面上选择、切换分析，不必每次重新找文件。里面是个人交易数据，已加入 .gitignore。
# 环境变量 REVIEW_FILES_DIR 可以改位置（测试用）。
REVIEW_FILES_DIRNAME = 'review_files'
REVIEW_EXTS = ('.xlsx', '.xls', '.csv')


def review_files_dir():
    return os.environ.get('REVIEW_FILES_DIR') or os.path.join(BASE_DIR, REVIEW_FILES_DIRNAME)


def safe_review_path(name):
    """把界面传来的文件名换成 review_files 里的真实路径；名字不合法（含路径、越出文件夹）返回 None。"""
    if not name or name != os.path.basename(name) or name in ('.', '..'):
        return None
    if not name.lower().endswith(REVIEW_EXTS):
        return None
    root = os.path.realpath(review_files_dir())
    path = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(path) != root:
        return None
    return path


def analyze_to_response(content, filename):
    """解析一份交易记录，放进缓存，返回给前端的 JSON（上传和从文件夹选择共用，前端不用区分来源）。"""
    try:
        result = review.analyze(content, filename)
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
        "filename": filename,
        "products": result.products,
        "start": result.start,
        "end": result.end,
        "tradeCount": int(len(result.records)),
        "hasFee": result.has_fee,
        "days": result.days,
        "warnings": result.warnings,
    })


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"success": False, "message": "文件过大，请上传 20MB 以内的文件"}), 413


# /api/ 下的 404、405、500 也统一返回 JSON + message。Flask 默认返回 HTML 页面，前端读不到 message，
# 界面就只剩一句笼统的“xx失败”，看不出原因（比如后端是没重启的旧版本，缺少新接口时会返回 405）。
def _api_error(status, message):
    return jsonify({"success": False, "message": message}), status


@app.errorhandler(404)
def api_not_found(e):
    if request.path.startswith('/api/'):
        return _api_error(404, f"接口 {request.path} 不存在，可能是后端版本过旧，请重启后端")
    return e


@app.errorhandler(405)
def api_method_not_allowed(e):
    if request.path.startswith('/api/'):
        return _api_error(405, f"后端不支持 {request.method} {request.path}，可能是后端版本过旧，请重启后端")
    return e


@app.errorhandler(500)
def api_server_error(e):
    if request.path.startswith('/api/'):
        print(f"[Backend] 500 {request.method} {request.path}: {e}")
        return _api_error(500, "服务器内部错误，详细原因见后端日志")
    return e


@app.route('/api/review/upload', methods=['POST'])
def review_upload():
    """上传交易记录 Excel：先解析，解析成功后保存到 review_files 文件夹，返回可选品种和数据时间范围。

    文件名按“文件夹里是否已有同名文件”判断唯一性（Windows 下不区分大小写）：
    已有同名文件且没有带 overwrite=1 时返回 409 + exists:true，什么都不做（不解析、不保存），
    由界面弹窗让用户确认；用户确认后带 overwrite=1 重新上传，才会覆盖。
    """
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({"success": False, "message": "请选择要上传的文件"}), 400
    if not f.filename.lower().endswith(REVIEW_EXTS):
        return jsonify({"success": False, "message": "仅支持 .xlsx / .xls / .csv 文件"}), 400

    # 有的浏览器 / WebView 会在文件名里带路径，只取最后的文件名；取完还不合法（比如全是点）就拒绝
    name = os.path.basename(f.filename.replace('\\', '/'))
    path = safe_review_path(name)
    if path is None:
        return jsonify({"success": False, "message": "文件名不合法"}), 400
    overwrite = request.form.get('overwrite') == '1'
    if os.path.exists(path) and not overwrite:
        return jsonify({"success": False, "exists": True, "name": os.path.basename(path),
                        "message": f"「{os.path.basename(path)}」已存在，是否覆盖？"}), 409

    content = f.read()
    resp = analyze_to_response(content, name)
    response, status = resp if isinstance(resp, tuple) else (resp, 200)
    if status != 200:
        return resp          # 解析失败的文件不保存，已有的同名旧文件也不会被它覆盖

    # 保存失败（磁盘只读、没有权限等）不影响本次分析，只在警告里告诉用户。
    # 先写临时文件再替换：写到一半失败时不会把原来的好文件弄坏
    data = response.get_json()
    tmp = path + '.uploading'
    try:
        os.makedirs(review_files_dir(), exist_ok=True)
        with open(tmp, 'wb') as out:
            out.write(content)
        os.replace(tmp, path)
        data["saved"] = True
        data["overwritten"] = overwrite
    except OSError as e:
        print(f"[Review] 保存到 {review_files_dir()} 失败: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        data["saved"] = False
        data["warnings"] = list(data.get("warnings", [])) + [f"文件没能保存到「{REVIEW_FILES_DIRNAME}」文件夹：{e}"]
    return jsonify(data)


@app.route('/api/review/files')
def review_files():
    """列出 review_files 文件夹里的交易记录文件（最近修改的在前）。文件夹不存在时返回空列表。"""
    root = review_files_dir()
    files = []
    if os.path.isdir(root):
        for name in os.listdir(root):
            path = os.path.join(root, name)
            # 跳过临时文件（Excel 打开文件时会生成 ~$ 开头的锁文件）、子文件夹和不支持的类型
            if name.startswith(('~$', '.')) or not os.path.isfile(path) or not name.lower().endswith(REVIEW_EXTS):
                continue
            st = os.stat(path)
            files.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
    files.sort(key=lambda x: (-x["mtime"], x["name"]))
    return jsonify({"success": True, "dir": REVIEW_FILES_DIRNAME, "files": files})


@app.route('/api/review/files', methods=['DELETE'])
def review_file_delete():
    """删除 review_files 文件夹里的一个文件。

    参数（JSON）：name（文件名，不含路径）。只删磁盘上的文件：已经解析进内存、正在分析的数据不受影响。
    """
    name = (request.get_json(silent=True) or {}).get('name', '')
    path = safe_review_path(name)
    if path is None:
        return jsonify({"success": False, "message": "文件名不合法"}), 400
    if not os.path.isfile(path):
        return jsonify({"success": False, "fileMissing": True, "message": f"文件「{name}」不存在，可能已被移动或删除"}), 404
    try:
        os.remove(path)
    except OSError as e:      # 文件被 Excel 等程序占用时 Windows 会拒绝删除
        return jsonify({"success": False, "message": f"删除失败：{e}（文件可能正被其它程序打开）"}), 400
    return jsonify({"success": True, "name": name})


@app.route('/api/review/open', methods=['POST'])
def review_open():
    """选择 review_files 文件夹里已有的文件进行分析，返回结构和上传接口完全一致。

    参数（JSON）：name（文件名，不含路径）。
    """
    name = (request.get_json(silent=True) or {}).get('name', '')
    path = safe_review_path(name)
    if path is None:
        return jsonify({"success": False, "message": "文件名不合法"}), 400
    if not os.path.isfile(path):
        return jsonify({"success": False, "fileMissing": True, "message": f"文件「{name}」不存在，可能已被移动或删除，请刷新列表"}), 404
    try:
        with open(path, 'rb') as fh:
            content = fh.read()
    except OSError as e:
        return jsonify({"success": False, "message": f"读取文件失败：{e}"}), 400
    return analyze_to_response(content, name)


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


@app.route('/api/review/day-trades')
def review_day_trades():
    """某个交易日的所有交易（开仓、平仓配好对），按合约分组。

    参数：reviewId（必填）、day（YYYY-MM-DD，交易日，必填）、products（逗号分隔，空=全部）。
    """
    review_id = request.args.get('reviewId', '')
    records = REVIEW_CACHE.get(review_id)
    if records is None:
        return jsonify({"success": False, "expired": True,
                        "message": "交易记录已失效（应用重启过），请重新上传文件"}), 404
    day = request.args.get('day', '')
    if not day:
        return jsonify({"success": False, "message": "请选择交易日"}), 400
    products = [p for p in request.args.get('products', '').split(',') if p]
    try:
        result = review.build_day_trades(records, day, products or None)
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "message": f"参数错误：{e}"}), 400
    return jsonify({"success": True, **result})


@app.route('/api/review/day-kline')
def review_day_kline():
    """某个合约在某个交易日的 K 线（夜盘 + 日盘），尽量用最细的周期。

    数据来自新浪（akshare 的 futures_zh_minute_sina）。这个接口没有日期参数，每个周期只返回最近 1023 根，
    所以周期越长回溯越远：1 分钟约 3 个交易日、5 分钟约 3 周、15 分钟约 2.5 个月、30 分钟约 4 个月、60 分钟约 8 个月。
    这里按 1 → 5 → 15 → 30 → 60 分钟的顺序找，用第一个“完整覆盖这个交易日”的周期；
    1 分钟取不到时自动降级，并在返回里用 period 告诉前端实际用了几分钟线。
    某个周期里这一天只有后半段（最早那天被截断）算不完整，继续试更长的周期；全都不完整时用其中最细的那个并标 partial。
    参数：symbol（合约代码，如 FU2611）、day（YYYY-MM-DD，交易日）。
    """
    import akshare as ak
    import pandas as pd

    symbol = request.args.get('symbol', '').strip()
    day = request.args.get('day', '').strip()
    if not symbol or not day:
        return jsonify({"success": False, "message": "缺少合约或交易日"}), 400
    try:
        target = pd.to_datetime(day).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": f"日期格式不对：{day}"}), 400
    # 新浪要的是不带交易所前缀的合约代码（SHFE.fu2611 -> fu2611）
    code = symbol.split('.')[-1]

    best = None              # (period, day_df)：完整覆盖这一天的最细周期；没有的话是“找到这一天但开头被截断”的最细周期
    complete = False         # best 是否完整覆盖了这一天
    ranges = []              # 每个周期实际能取到的范围，取不到时写进提示
    last_error = None
    for period in ('1', '5', '15', '30', '60'):
        try:
            df = ak.futures_zh_minute_sina(symbol=code, period=period)
        except Exception as e:
            last_error = e
            print(f"[Review] 获取 K 线失败 {code} {period}分钟: {e}")
            continue
        if df is None or df.empty:
            continue
        df = df.copy()
        df['datetime'] = pd.to_datetime(df['datetime'])
        have_from, have_to = df['datetime'].min(), df['datetime'].max()
        ranges.append(f"{period}分钟 {have_from:%m-%d} ~ {have_to:%m-%d}")
        # 和成交用同一套“交易日”口径：夜盘（20:00 之后）属于下一个交易日
        tday = df['datetime'].map(review.trading_day).dt.strftime('%Y-%m-%d')
        day_df = df[tday == target]
        if day_df.empty:
            continue
        # 这一天的第一根就是整份数据的第一根：说明开头可能被截断（更早的部分没有取到）
        if day_df['datetime'].min() == have_from:
            if best is None:
                best = (period, day_df)
            continue
        best, complete = (period, day_df), True
        break

    if best is None:
        if last_error is not None and not ranges:
            return jsonify({"success": False, "message": f"获取 {code} 的 K 线失败：{last_error}"}), 502
        detail = '；'.join(ranges) if ranges else '没有取到任何数据（合约可能已退市，或新浪暂无数据）'
        return jsonify({"success": True, "available": False, "data": [],
                        "message": f"取不到 {code} 在 {target} 的 K 线。新浪能提供的范围：{detail}"})

    period, day_df = best
    data = [{
        'time': r.datetime.strftime('%Y-%m-%d %H:%M:%S'),
        'open': float(r.open), 'high': float(r.high), 'low': float(r.low), 'close': float(r.close),
        'volume': int(r.volume),
    } for r in day_df.itertuples(index=False)]
    return jsonify({"success": True, "available": True, "symbol": code, "day": target,
                    "period": int(period), "data": data, "count": len(data), "partial": not complete})


@app.route('/api/logout', methods=['POST'])
def logout():
    """退出登录：同时关闭 CTP 会话"""
    ctp_service.logout()
    session.clear()
    return jsonify({"success": True})


@app.route('/api/quant-login', methods=['POST'])
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


if __name__ == '__main__':
    # Sidecar 模式：监听 5000 端口
    print("[Backend] Flask Sidecar 启动中...")
    print("[Backend] 监听地址: http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
