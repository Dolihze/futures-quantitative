"""交易复盘：上传 / 选择交易记录、账户总览、盈亏曲线、单日明细、单日 K 线。"""
import os
import traceback

import pandas as pd
from flask import Blueprint, jsonify, request

from backend.core import review
from backend.errors import ApiError, bad_request, not_found
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
    """某个合约在某个交易日的 K 线（夜盘 + 日盘），尽量用最细的周期。

    数据来自新浪（akshare 的 futures_zh_minute_sina）。这个接口没有日期参数，每个周期只返回最近 1023 根，
    所以周期越长回溯越远：1 分钟约 3 个交易日、5 分钟约 3 周、15 分钟约 2.5 个月、30 分钟约 4 个月、60 分钟约 8 个月。
    这里按 1 → 5 → 15 → 30 → 60 分钟的顺序找，用第一个“完整覆盖这个交易日”的周期；
    1 分钟取不到时自动降级，并在返回里用 period 告诉前端实际用了几分钟线。
    某个周期里这一天只有后半段（最早那天被截断）算不完整，继续试更长的周期；全都不完整时用其中最细的那个并标 partial。
    参数：symbol（合约代码，如 FU2611）、day（YYYY-MM-DD，交易日）。
    """
    import akshare as ak

    symbol = request.args.get('symbol', '').strip()
    day = request.args.get('day', '').strip()
    if not symbol or not day:
        raise bad_request("缺少合约或交易日")
    try:
        target = pd.to_datetime(day).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        raise bad_request(f"日期格式不对：{day}")
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
            raise ApiError(f"获取 {code} 的 K 线失败：{last_error}", 502)
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
