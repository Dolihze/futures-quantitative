"""深度行情：历史 tick CSV -> K 线 / 足迹图 / 历史盘口，以及 depth_files 文件夹管理。"""
import os

from flask import Blueprint, jsonify, request

from backend.core import depth_market
from backend.errors import ApiError, bad_request, not_found, wrap_errors
from backend.services import depth_archive as archive
from backend.services import depth_service as svc
from backend.services import tick_store

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


def _depth_get(depth_id):
    """取缓存里的 tick 数据；失效抛 ApiError(410)。"""
    td = svc.get_cached(depth_id)
    if td is None:
        raise ApiError("数据已失效（后端重启或缓存被清理），请重新选择文件", 410, expired=True)
    return td


def _unit_or_error(name, *, missing_hint=''):
    """校验数据单元名并确认它在行情库里；否则抛 ApiError。返回单元名。"""
    if not name or name != os.path.basename(name.replace('\\', '/')):   # 含路径分隔符 / .. 的一律拒绝，不做「取文件名」式的宽容
        raise bad_request("名称不合法")
    n = svc.unit_name(name)
    if not n or tick_store.safe_store_path(svc.depth_files_dir(), n) is None:
        raise bad_request("名称不合法")
    if not svc.unit_exists(n):
        raise not_found(f"数据「{n}」不存在，可能已被删除{missing_hint}", fileMissing=True)
    return n


@bp.route('/api/depth/upload', methods=['POST'])
def depth_upload():
    """上传 tick CSV：解析一次后存进行情库（不保留 CSV）。数据已在库里且未带 overwrite=1 时返回 409 + exists:true。"""
    f = request.files.get('file')
    if f is None or not f.filename:
        raise bad_request("请选择要上传的文件")
    if not f.filename.lower().endswith(svc.DEPTH_EXTS):
        raise bad_request("仅支持 .csv 文件")
    orig_name = os.path.basename(f.filename.replace('\\', '/'))
    content = f.read()

    # 每次导入的文件名可能都一样（如 fu2701.csv），实际是不同日期的数据：
    # 先读文件内部的合约和交易日，得到规范名「合约名_YYYYMMDD」再判断是否已导入过
    try:
        meta = depth_market.peek_meta(content, orig_name)
        name = depth_market.canonical_name(content, orig_name, '.csv', meta)
    except depth_market.DepthParseError as e:
        raise bad_request(str(e))
    except Exception as e:
        print(f"[Depth] 读取文件日期失败: {e}")
        raise bad_request(f"读取文件日期失败：{e}")
    unit = svc.unit_name(name)
    if tick_store.safe_store_path(svc.depth_files_dir(), unit) is None:
        raise bad_request(f"名称不合法：{name}")
    overwrite = request.form.get('overwrite') == '1'
    if not overwrite:
        why = svc.already_imported(unit, str(meta['symbol']), meta['days'])
        if why:
            raise ApiError(f"{why}，是否覆盖？", 409, exists=True, name=unit, originalName=orig_name)

    depth_id, td = parse_ticks(content, name)
    data = depth_market.summary(td)
    data.update({"success": True, "depthId": depth_id, "filename": name})
    try:
        svc.save_unit(unit, td, source=orig_name)
        data["saved"] = True
        data["overwritten"] = overwrite
        data["savedName"] = unit
        data["originalName"] = orig_name
    except OSError as e:
        print(f"[Depth] 写入行情库 {svc.depth_files_dir()} 失败: {e}")
        data["saved"] = False
        data["warnings"] = list(data.get("warnings", [])) + [f"数据没能写入行情库：{e}"]
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
    """已导入的合约列表（按合约合并多个文件）+ 无法识别的文件。深度行情左侧列表和数据库管理共用。

    migration：以前版本导入的遗留 CSV 正在后台迁移进行情库时 running=true（列表里已迁移的数据陆续出现）。
    """
    contracts, bad = svc.scan()
    m = svc.migration_status()
    return jsonify({"success": True, "dir": svc.DEPTH_FILES_DIRNAME, "contracts": contracts, "unrecognized": bad,
                    "migration": {"running": m["running"], "total": m["total"], "done": m["done"],
                                  "current": m["current"], "pending": m["pending"]}})


def _find_contract(symbol, message):
    contracts, _ = svc.scan()
    c = next((x for x in contracts if x["symbol"] == symbol), None)
    if c is None:
        raise not_found(message, fileMissing=True)
    return c


def _reject_while_migrating():
    """遗留 CSV 还在迁移时，合约名下的数据可能只迁了一部分：打开 / 删除都会得到不完整的结果，先拒绝并说明。"""
    m = svc.migration_status()
    if m["running"]:
        raise ApiError(f"历史数据正在迁移进行情库（{m['done']}/{m['total']}），完成后才能打开或删除合约，请稍候", 409,
                       migrating=True)


@bp.route('/api/depth/open-contract', methods=['POST'])
def depth_open_contract():
    """打开一个合约：把它的所有文件解析后按时间合并成一条时间线，返回结构同 /api/depth/open。"""
    symbol = (request.get_json(silent=True) or {}).get('symbol', '')
    _reject_while_migrating()
    c = _find_contract(symbol, f"合约「{symbol}」没有数据文件，可能已被删除，请刷新列表")
    try:
        # 统一缓存：同一个合约（文件没变）不管是深度行情、回测还是复盘先打开的，都只解析一次
        td, file_count = svc.load_contract(c)
    except (depth_market.DepthParseError, OSError) as e:
        raise bad_request(str(e))
    except Exception as e:
        print(f"[Depth] 解析合约 {symbol} 失败: {e}")
        raise bad_request(f"解析合约 {symbol} 失败：{e}")

    depth_id = svc.cache_ticks(td, c["symbol"])
    data = depth_market.summary(td)
    data.update({"success": True, "depthId": depth_id, "filename": symbol, "fileCount": file_count})
    return jsonify(data)


@bp.route('/api/depth/contracts', methods=['DELETE'])
def depth_contract_delete():
    """删除一个合约：删掉它名下的全部文件。返回删除了哪些、哪些失败。"""
    symbol = (request.get_json(silent=True) or {}).get('symbol', '')
    _reject_while_migrating()
    c = _find_contract(symbol, f"合约「{symbol}」没有数据文件")
    deleted, failed = [], []
    for f in c["files"]:
        try:
            svc.remove_unit(f["name"])
            deleted.append(f["name"])
        except (OSError, tick_store.StoreError) as e:
            failed.append({"name": f["name"], "error": str(e)})
    if failed:
        raise bad_request(f"{len(failed)} 份数据删除失败（可能正被其它程序占用）：{failed[0]['name']}",
                          deleted=deleted, failed=failed)
    return jsonify({"success": True, "deleted": deleted})


@bp.route('/api/depth/files')
def depth_files():
    """列出行情库里的全部数据单元（最近导入的在前）。"""
    svc.scan()   # 顺便触发遗留 CSV 的后台迁移
    return jsonify({"success": True, "dir": svc.DEPTH_FILES_DIRNAME, "files": svc.list_files()})


@bp.route('/api/depth/files', methods=['DELETE'])
def depth_file_delete():
    name = (request.get_json(silent=True) or {}).get('name', '')
    unit = _unit_or_error(name)
    try:
        svc.remove_unit(unit)
    except (OSError, tick_store.StoreError) as e:
        raise bad_request(f"删除失败：{e}（文件可能正被其它程序占用）")
    return jsonify({"success": True, "name": unit})


@bp.route('/api/depth/unrecognized', methods=['DELETE'])
def depth_unrecognized_delete():
    """删除「无法识别的文件」：未能迁移进行情库、仍留在 depth_files 根目录的 CSV。只允许删这类文件，不会碰行情库。"""
    name = (request.get_json(silent=True) or {}).get('name', '')
    if not name or name != os.path.basename(name.replace('\\', '/')):
        raise bad_request("名称不合法")
    path = svc.safe_depth_path(name)
    if path is None:
        raise bad_request("名称不合法")
    if not os.path.isfile(path):
        raise not_found(f"文件「{name}」不存在，可能已被删除", fileMissing=True)
    try:
        os.remove(path)
    except OSError as e:
        raise bad_request(f"删除失败：{e}（文件可能正被其它程序占用）")
    return jsonify({"success": True, "name": name})


@bp.route('/api/depth/open', methods=['POST'])
def depth_open():
    """打开行情库里的一份数据单元，返回结构和上传接口一致。"""
    name = (request.get_json(silent=True) or {}).get('name', '')
    unit = _unit_or_error(name, missing_hint='，请刷新列表')
    try:
        td = tick_store.read_unit(svc.depth_files_dir(), unit)
    except (tick_store.StoreError, OSError) as e:
        raise bad_request(f"读取数据失败：{e}")
    depth_id = svc.cache_ticks(td)
    data = depth_market.summary(td)
    data.update({"success": True, "depthId": depth_id, "filename": unit})
    return jsonify(data)


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
