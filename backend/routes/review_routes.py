"""交易复盘：上传 / 选择交易记录、账户总览、盈亏曲线、单日明细、单日 K 线。"""
import os
import traceback

import pandas as pd
from flask import Blueprint, jsonify, request

from backend.core import review
from backend.errors import ApiError, bad_request, not_found
from backend.services import kline_store
from backend.services import review_service as svc

bp = Blueprint('review', __name__)


def analyze_to_response(content, filename):
    """解析一份交易记录，放进缓存，返回给前端的 JSON（上传和从文件夹选择共用，前端不用区分来源）。

    解析失败抛 ApiError(400)。
    """
    try:
        result = review.analyze(content, filename)
    except review.ReviewParseError as e:
        raise bad_request(str(e))
    except Exception as e:  # 解析库的意外错误：不要把 500 抛给用户，给出可读提示
        print(f"[Review] 解析失败: {e}")
        traceback.print_exc()
        raise bad_request(f"解析失败：{e}")

    review_id = svc.cache_records(result.records)
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


def _file_path_or_error(name, *, missing_hint=''):
    """校验文件名并确认文件存在，返回真实路径；否则抛 ApiError。"""
    path = svc.safe_review_path(name)
    if path is None:
        raise bad_request("文件名不合法")
    if not os.path.isfile(path):
        raise not_found(f"文件「{name}」不存在，可能已被移动或删除{missing_hint}", fileMissing=True)
    return path


@bp.route('/api/review/upload', methods=['POST'])
def review_upload():
    """上传交易记录 Excel：先解析，解析成功后保存到 review_files 文件夹，返回可选品种和数据时间范围。

    文件名按“文件夹里是否已有同名文件”判断唯一性（Windows 下不区分大小写）：
    已有同名文件且没有带 overwrite=1 时返回 409 + exists:true，什么都不做（不解析、不保存），
    由界面弹窗让用户确认；用户确认后带 overwrite=1 重新上传，才会覆盖。
    """
    f = request.files.get('file')
    if f is None or not f.filename:
        raise bad_request("请选择要上传的文件")
    if not f.filename.lower().endswith(svc.REVIEW_EXTS):
        raise bad_request("仅支持 .xlsx / .xls / .csv 文件")

    # 有的浏览器 / WebView 会在文件名里带路径，只取最后的文件名；取完还不合法（比如全是点）就拒绝
    name = os.path.basename(f.filename.replace('\\', '/'))
    path = svc.safe_review_path(name)
    if path is None:
        raise bad_request("文件名不合法")
    overwrite = request.form.get('overwrite') == '1'
    if os.path.exists(path) and not overwrite:
        existing = os.path.basename(path)
        raise ApiError(f"「{existing}」已存在，是否覆盖？", 409, exists=True, name=existing)

    content = f.read()
    # 解析失败会抛 ApiError：失败的文件不保存，已有的同名旧文件也不会被它覆盖
    data = analyze_to_response(content, name).get_json()

    # 保存失败（磁盘只读、没有权限等）不影响本次分析，只在警告里告诉用户。
    # 先写临时文件再替换：写到一半失败时不会把原来的好文件弄坏
    tmp = path + '.uploading'
    try:
        os.makedirs(svc.review_files_dir(), exist_ok=True)
        with open(tmp, 'wb') as out:
            out.write(content)
        os.replace(tmp, path)
        data["saved"] = True
        data["overwritten"] = overwrite
    except OSError as e:
        print(f"[Review] 保存到 {svc.review_files_dir()} 失败: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        data["saved"] = False
        data["warnings"] = list(data.get("warnings", [])) + [f"文件没能保存到「{svc.REVIEW_FILES_DIRNAME}」文件夹：{e}"]
    return jsonify(data)


@bp.route('/api/review/files')
def review_files():
    """列出 review_files 文件夹里的交易记录文件（最近修改的在前）。文件夹不存在时返回空列表。"""
    return jsonify({"success": True, "dir": svc.REVIEW_FILES_DIRNAME, "files": svc.list_files()})


@bp.route('/api/review/files/detail')
def review_files_detail():
    """交易记录文件列表 + 每个文件的元信息（数据库管理用）。解析不了的文件带 error 字段。"""
    return jsonify({"success": True, "dir": svc.REVIEW_FILES_DIRNAME, "files": svc.list_files_detail()})


@bp.route('/api/review/files', methods=['DELETE'])
def review_file_delete():
    """删除 review_files 文件夹里的一个文件。

    参数（JSON）：name（文件名，不含路径）。只删磁盘上的文件：已经解析进内存、正在分析的数据不受影响。
    """
    name = (request.get_json(silent=True) or {}).get('name', '')
    path = _file_path_or_error(name)
    try:
        os.remove(path)
    except OSError as e:      # 文件被 Excel 等程序占用时 Windows 会拒绝删除
        raise bad_request(f"删除失败：{e}（文件可能正被其它程序打开）")
    return jsonify({"success": True, "name": name})


@bp.route('/api/review/open', methods=['POST'])
def review_open():
    """选择 review_files 文件夹里已有的文件进行分析，返回结构和上传接口完全一致。

    参数（JSON）：name（文件名，不含路径）。
    """
    name = (request.get_json(silent=True) or {}).get('name', '')
    path = _file_path_or_error(name, missing_hint='，请刷新列表')
    try:
        with open(path, 'rb') as fh:
            content = fh.read()
    except OSError as e:
        raise bad_request(f"读取文件失败：{e}")
    return analyze_to_response(content, name)


@bp.route('/api/review/overview')
def review_overview():
    """账户整体概览：合并 review_files 里全部交易记录，按交易日 / 品种聚合。

    参数：fee（1=扣除手续费，0=不扣，默认 1）。start / end（YYYY-MM-DD，可选）：只统计这段交易日。
    返回的 reviewId 对应合并后的全部记录，可直接用于 /api/review/curve、/day-trades（单日详情）。
    """
    review_id, warnings, skipped, file_count = svc.all_records()
    records = svc.REVIEW_CACHE.get(review_id)
    include_fee = request.args.get('fee', '1') != '0'
    start = request.args.get('start') or None
    end = request.args.get('end') or None
    if records is None or records.empty:
        data = review.build_overview(None)
        data.update(success=True, reviewId=review_id, fileCount=file_count, skipped=skipped, warnings=warnings,
                    allStart="", allEnd="", hasFee=False)
        return jsonify(data)
    all_days = records["time"].map(review.trading_day)
    all_start, all_end = all_days.min().strftime('%Y-%m-%d'), all_days.max().strftime('%Y-%m-%d')
    df = records
    try:
        if start:
            df = df[all_days >= pd.to_datetime(start).normalize()]
            all_days = all_days.loc[df.index]
        if end:
            df = df[all_days <= pd.to_datetime(end).normalize()]
    except (ValueError, TypeError) as e:
        raise bad_request(f"参数错误：{e}")
    data = review.build_overview(df, include_fee)
    data.update(success=True, reviewId=review_id, fileCount=file_count, skipped=skipped, warnings=warnings,
                allStart=all_start, allEnd=all_end, hasFee=bool((records["fee"] != 0).any()))
    return jsonify(data)


def _get_records(review_id):
    """取缓存里的交易记录；失效（应用重启过）抛 ApiError(404, expired=True)。"""
    records = svc.REVIEW_CACHE.get(review_id)
    if records is None:
        raise not_found("交易记录已失效（应用重启过），请重新上传文件", expired=True)
    return records


@bp.route('/api/review/curve')
def review_curve():
    """按品种 / 时间范围筛选，返回累计平仓盈亏曲线和统计。

    参数：reviewId（必填）、products（逗号分隔，空=全部）、start、end（YYYY-MM-DD[ HH:MM:SS]）、
    fee（1=扣除手续费，0=不扣，默认 1）。
    """
    records = _get_records(request.args.get('reviewId', ''))

    products = [p for p in request.args.get('products', '').split(',') if p]
    start = request.args.get('start') or None
    end = request.args.get('end') or None
    include_fee = request.args.get('fee', '1') != '0'
    try:
        curve = review.build_curve(records, products or None, start, end, include_fee)
    except (ValueError, TypeError) as e:
        raise bad_request(f"参数错误：{e}")
    return jsonify({"success": True, **curve})


@bp.route('/api/review/day-trades')
def review_day_trades():
    """某个交易日的所有交易（开仓、平仓配好对），按合约分组。

    参数：reviewId（必填）、day（YYYY-MM-DD，交易日，必填）、products（逗号分隔，空=全部）。
    """
    records = _get_records(request.args.get('reviewId', ''))
    day = request.args.get('day', '')
    if not day:
        raise bad_request("请选择交易日")
    products = [p for p in request.args.get('products', '').split(',') if p]
    try:
        result = review.build_day_trades(records, day, products or None)
    except (ValueError, TypeError) as e:
        raise bad_request(f"参数错误：{e}")
    return jsonify({"success": True, **result})


@bp.route('/api/review/day-kline')
def review_day_kline():
    """某个合约在某个交易日的 K 线（夜盘 + 日盘），取自本地历史行情库（数据库管理里导入的 tick）。

    tick 可以聚合出任意周期，所以直接用最细的 1 分钟线；不再访问在线行情接口。
    本地库里没有这个合约、或这个合约没有覆盖这个交易日时不是错误：available=False，message 说明库内能提供的范围，
    提示用户去「数据库管理」导入对应数据。
    参数：symbol（合约代码，如 FU2611 / SHFE.fu2611）、day（YYYY-MM-DD，交易日）。
    """
    symbol = request.args.get('symbol', '').strip()
    day = request.args.get('day', '').strip()
    if not symbol or not day:
        raise bad_request("缺少合约或交易日")
    try:
        target = pd.to_datetime(day).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        raise bad_request(f"日期格式不对：{day}")
    code = kline_store.normalize_symbol(symbol)

    try:
        by_day, bars = kline_store.bars_by_day(code, '1')
    except ApiError as e:
        if e.status != 404:
            raise
        return jsonify({"success": True, "available": False, "data": [], "message": e.message})

    # 和成交用同一套“交易日”口径（夜盘 20:00 之后属于下一个交易日）：K 线已按交易日分好组并缓存，直接取这一天
    day_bars = by_day.get(target, [])
    if not day_bars:
        have = f"{bars[0]['time'][:10]} ~ {bars[-1]['time'][:10]}" if bars else '没有可用数据'
        return jsonify({"success": True, "available": False, "data": [],
                        "message": f"本地行情库里 {code} 没有 {target} 的数据（库内范围：{have}），"
                                   f"{kline_store.IMPORT_HINT}"})
    return jsonify({"success": True, "available": True, "symbol": code, "day": target,
                    "period": 1, "data": day_bars, "count": len(day_bars), "partial": False})