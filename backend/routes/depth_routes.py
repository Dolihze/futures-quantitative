"""深度行情：历史 tick CSV -> K 线 / 足迹图 / 历史盘口，以及 depth_files 文件夹管理。"""
import os

from flask import Blueprint, jsonify, request

from backend.core import depth_market
from backend.errors import ApiError, bad_request, not_found, wrap_errors
from backend.services import depth_archive as archive
from backend.services import depth_service as svc

bp = Blueprint('depth', __name__)


def parse_ticks(content, filename):
    """解析一份 tick CSV 并放进缓存，返回 (depthId, TickData)。解析失败抛 ApiError(400)。"""
    try:
        td = depth_market.parse(content, filename)
    except depth_market.DepthParseError as e:
        raise bad_request(str(e))
    except Exception as e:
        print(f"[Depth] 解析失败: {e}")
        import traceback
        traceback.print_exc()
        raise bad_request(f"解析失败：{e}")
    return svc.cache_ticks(td), td


def depth_analyze_to_response(content, filename):
    """解析一份 tick CSV，放进缓存，返回 JSON（上传和从文件夹选择共用）。"""
    depth_id, td = parse_ticks(content, filename)
    data = depth_market.summary(td)
    data.update({"success": True, "depthId": depth_id, "filename": filename})
    return jsonify(data)


def _depth_get(depth_id):
    """取缓存里的 tick 数据；失效抛 ApiError(410)。"""
    td = svc.get_cached(depth_id)
    if td is None:
        raise ApiError("数据已失效（后端重启或缓存被清理），请重新选择文件", 410, expired=True)
    return td


def _file_path_or_error(name, *, missing_hint=''):
    """校验文件名并确认文件存在，返回真实路径；否则抛 ApiError。"""
    path = svc.safe_depth_path(name)
    if path is None:
        raise bad_request("文件名不合法")
    if not os.path.isfile(path):
        raise not_found(f"文件「{name}」不存在，可能已被移动或删除{missing_hint}", fileMissing=True)
    return path


@bp.route('/api/depth/upload', methods=['POST'])
def depth_upload():
    """上传 tick CSV：解析成功后保存到 depth_files。同名文件未带 overwrite=1 时返回 409 + exists:true（同复盘）。"""
    f = request.files.get('file')
    if f is None or not f.filename:
        raise bad_request("请选择要上传的文件")
    if not f.filename.lower().endswith(svc.DEPTH_EXTS):
        raise bad_request("仅支持 .csv 文件")
    orig_name = os.path.basename(f.filename.replace('\\', '/'))
    content = f.read()

    # 每次导入的文件名可能都一样（如 fu2701.csv），实际是不同日期的数据：
    # 先读文件内部的合约和交易日，改名为「合约名_YYYYMMDD.csv」再判断是否重名
    try:
        name = depth_market.canonical_name(content, orig_name, os.path.splitext(orig_name)[1].lower() or '.csv')
    except depth_market.DepthParseError as e:
        raise bad_request(str(e))
    except Exception as e:
        print(f"[Depth] 读取文件日期失败: {e}")
        raise bad_request(f"读取文件日期失败：{e}")
    path = svc.safe_depth_path(name)
    if path is None:
        raise bad_request(f"文件名不合法：{name}")
    overwrite = request.form.get('overwrite') == '1'
    if os.path.exists(path) and not overwrite:
        raise ApiError(f"「{name}」已存在，是否覆盖？", 409, exists=True, name=name, originalName=orig_name)

    data = depth_analyze_to_response(content, name).get_json()
    tmp = path + '.uploading'
    try:
        os.makedirs(svc.depth_files_dir(), exist_ok=True)
        with open(tmp, 'wb') as out:
            out.write(content)
        os.replace(tmp, path)
        data["saved"] = True
        data["overwritten"] = overwrite
        data["savedName"] = name
        data["originalName"] = orig_name
    except OSError as e:
        print(f"[Depth] 保存到 {svc.depth_files_dir()} 失败: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        data["saved"] = False
        data["warnings"] = list(data.get("warnings", [])) + [f"文件没能保存到「{svc.DEPTH_FILES_DIRNAME}」文件夹：{e}"]
    return jsonify(data)


@bp.route('/api/depth/upload-archive', methods=['POST'])
def depth_upload_archive():
    """批量导入：上传全量行情压缩包（YYYYMM/YYYYMMDD/合约.zip），只导入指定品种（可多个）的所有合约。

    表单字段：file（.zip）、product（品种代码，如 fu；多个品种重复传该字段，也兼容逗号分隔）、
    overwrite（1 = 已存在的同名文件直接覆盖，否则跳过）。
    每份合约数据的解析和改名（合约名_YYYYMMDD.csv）与单文件导入完全一致。
    压缩包很大，导入在后台线程里跑：本接口保存完上传就返回 taskId，前端用
    GET /api/depth/archive-task?id= 轮询进度和最终结果。
    """
    f = request.files.get('file')
    if f is None or not f.filename:
        raise bad_request("请选择要上传的压缩包")
    if not f.filename.lower().endswith('.zip'):
        raise bad_request("仅支持 .zip 压缩包")
    try:
        products = archive.normalize_products(request.form.getlist('product'))
    except archive.ArchiveError as e:
        raise bad_request(str(e))
    if not products:
        raise bad_request("请先选择品种")
    on_exists = 'overwrite' if request.form.get('overwrite') == '1' else 'skip'
    if archive.has_running_task():
        raise ApiError("已有一个批量导入正在进行，请等它完成后再导入", 409, busy=True)

    orig_name = os.path.basename(f.filename.replace('\\', '/'))
    tmp_path = archive.save_upload_to_temp(f)
    task_id = archive.start_task(tmp_path, products, on_exists, orig_name)   # 临时文件由任务线程负责删除
    return jsonify({"success": True, "taskId": task_id, "products": products, "originalName": orig_name})


@bp.route('/api/depth/archive-task')
def depth_archive_task():
    """批量导入任务的进度：status = running / done / error；done 时带 result（结构见 DepthArchiveResult）。

    不带 id 时返回最近的任务（有运行中的优先），没有任何任务返回 404 + noTask；页面重新进入时据此恢复进度。
    """
    task_id = request.args.get('id')
    task = archive.get_task(task_id) if task_id else archive.latest_task()
    if task is None:
        if not task_id:
            raise not_found("没有批量导入任务", noTask=True)
        raise not_found("导入任务不存在（后端可能已重启）", expired=True)
    result = task['result']
    if result is not None:
        result = {**result, "success": True, "originalName": task['originalName']}
    return jsonify({
        "success": True, "taskId": task['id'], "status": task['status'], "products": task['products'],
        "originalName": task['originalName'], "done": task['done'], "total": task['total'],
        "current": task['current'], "message": task['message'], "result": result,
    })


@bp.route('/api/depth/contracts')
def depth_contracts():
    """已导入的合约列表（按合约合并多个文件）+ 无法识别的文件。深度行情左侧列表和数据库管理共用。"""
    contracts, bad = svc.scan()
    return jsonify({"success": True, "dir": svc.DEPTH_FILES_DIRNAME, "contracts": contracts, "unrecognized": bad})


def _find_contract(symbol, message):
    contracts, _ = svc.scan()
    c = next((x for x in contracts if x["symbol"] == symbol), None)
    if c is None:
        raise not_found(message, fileMissing=True)
    return c


@bp.route('/api/depth/open-contract', methods=['POST'])
def depth_open_contract():
    """打开一个合约：把它的所有文件解析后按时间合并成一条时间线，返回结构同 /api/depth/open。"""
    symbol = (request.get_json(silent=True) or {}).get('symbol', '')
    c = _find_contract(symbol, f"合约「{symbol}」没有数据文件，可能已被删除，请刷新列表")
    parts = []
    for f in c["files"]:
        path = svc.safe_depth_path(f["name"])
        try:
            with open(path, 'rb') as fh:
                parts.append(depth_market.parse(fh.read(), f["name"]))
        except depth_market.DepthParseError as e:
            raise bad_request(f"{f['name']}：{e}")
        except OSError as e:
            raise bad_request(f"读取 {f['name']} 失败：{e}")
        except Exception as e:
            print(f"[Depth] 解析 {f['name']} 失败: {e}")
            raise bad_request(f"解析 {f['name']} 失败：{e}")
    try:
        td = depth_market.merge(parts)
    except Exception as e:
        print(f"[Depth] 合并 {symbol} 失败: {e}")
        raise bad_request(f"合并文件失败：{e}")

    depth_id = svc.cache_ticks(td)
    data = depth_market.summary(td)
    data.update({"success": True, "depthId": depth_id, "filename": symbol, "fileCount": len(parts)})
    return jsonify(data)


@bp.route('/api/depth/contracts', methods=['DELETE'])
def depth_contract_delete():
    """删除一个合约：删掉它名下的全部文件。返回删除了哪些、哪些失败。"""
    symbol = (request.get_json(silent=True) or {}).get('symbol', '')
    c = _find_contract(symbol, f"合约「{symbol}」没有数据文件")
    deleted, failed = [], []
    for f in c["files"]:
        path = svc.safe_depth_path(f["name"])
        try:
            os.remove(path)
            deleted.append(f["name"])
        except OSError as e:
            failed.append({"name": f["name"], "error": str(e)})
    if failed:
        raise bad_request(f"{len(failed)} 个文件删除失败（可能正被其它程序打开）：{failed[0]['name']}",
                          deleted=deleted, failed=failed)
    return jsonify({"success": True, "deleted": deleted})


@bp.route('/api/depth/files')
def depth_files():
    """列出 depth_files 文件夹里的 tick CSV（最近修改的在前）。"""
    return jsonify({"success": True, "dir": svc.DEPTH_FILES_DIRNAME, "files": svc.list_files()})


@bp.route('/api/depth/files', methods=['DELETE'])
def depth_file_delete():
    name = (request.get_json(silent=True) or {}).get('name', '')
    path = _file_path_or_error(name)
    try:
        os.remove(path)
    except OSError as e:
        raise bad_request(f"删除失败：{e}（文件可能正被其它程序打开）")
    return jsonify({"success": True, "name": name})


@bp.route('/api/depth/open', methods=['POST'])
def depth_open():
    """选择 depth_files 里已有的文件，返回结构和上传接口一致。"""
    name = (request.get_json(silent=True) or {}).get('name', '')
    path = _file_path_or_error(name, missing_hint='，请刷新列表')
    try:
        with open(path, 'rb') as fh:
            content = fh.read()
    except OSError as e:
        raise bad_request(f"读取文件失败：{e}")
    return depth_analyze_to_response(content, name)


@bp.route('/api/depth/kline')
@wrap_errors('生成 K 线失败', log_tag='[Depth]', log_prefix='聚合 K 线失败')
def depth_kline():
    """由 tick 聚合 K 线。参数：depthId、period（1/5/15/30/60/1440，默认 1）、day（交易日，可空=全部）。"""
    td = _depth_get(request.args.get('depthId'))
    try:
        period = int(request.args.get('period', 1))
        result = depth_market.build_kline(td, period, request.args.get('day') or None)
    except ValueError as e:
        raise bad_request(str(e))
    return jsonify({"success": True, **result})


@bp.route('/api/depth/footprint')
@wrap_errors('生成足迹图失败', log_tag='[Depth]', trace=True)
def depth_footprint():
    """足迹图数据：每根 K 线每个价位的买 / 卖 / 中性成交量 + 大单列表。

    参数：depthId、period（1/5/15/30/60/1440，默认 1）、day（交易日，可空）、bigOrder（大单阈值，手，默认 100）。
    没有 BS 列的文件无法区分买卖方向，返回 400 + 说明。
    """
    td = _depth_get(request.args.get('depthId'))
    try:
        period = int(request.args.get('period', 1))
        big_order = int(request.args.get('bigOrder', depth_market.DEFAULT_BIG_ORDER))
        result = depth_market.build_footprint(td, period, request.args.get('day') or None, big_order)
    except ValueError as e:
        raise bad_request(str(e))
    return jsonify({"success": True, **result})


@bp.route('/api/depth/book')
def depth_book():
    """某一时刻的历史盘口。参数：depthId，ts（毫秒时间戳，取不晚于它的最近一笔）或 index（tick 序号）。"""
    td = _depth_get(request.args.get('depthId'))
    try:
        ts = request.args.get('ts')
        index = request.args.get('index')
        if ts is None and index is None:
            raise bad_request("需要 ts 或 index 参数")
        book = depth_market.book_at(td, ts=int(ts) if ts is not None else None,
                                    index=int(index) if index is not None else None)
    except ValueError:
        raise bad_request("ts / index 必须是整数")
    return jsonify({"success": True, "levels": td.levels, **book})


@bp.route('/api/depth/ticks')
def depth_ticks():
    """一段连续的 tick（含盘口），用于回放预取。参数：depthId、start（起始序号）、count（默认 200，最多 1000）。"""
    td = _depth_get(request.args.get('depthId'))
    try:
        start = int(request.args.get('start', 0))
        count = min(max(int(request.args.get('count', 200)), 1), 1000)
    except ValueError:
        raise bad_request("start / count 必须是整数")
    return jsonify({"success": True, "levels": td.levels, "total": td.count,
                    "ticks": depth_market.ticks_range(td, start, count)})
