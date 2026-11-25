"""全量行情压缩包批量导入：从「YYYYMM / YYYYMMDD / 合约.zip」嵌套压缩包里挑出指定品种的全部合约 CSV。

压缩包结构（每一层既可能是文件夹，也可能是同名 zip）：

    全量数据.zip
    └── 202611/                  月份，YYYYMM
        ├── 20261102/            交易日，YYYYMMDD（文件夹，或 20261102.zip）
        │   ├── fu2611.zip       某个合约当天的数据，里面是一份 CSV
        │   ├── fu2701.zip
        │   └── rb2610.zip       其他品种，忽略
        └── 20261103/ ...

只处理文件名为「<品种><数字>.zip」（如 fu2611.zip）的成员；CSV 的格式、改名规则（合约名_YYYYMMDD.csv）
和单文件导入完全一致，直接复用 depth_market.canonical_name。
"""
import io
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile

from backend.core import depth_market
from backend.services import depth_service as svc

# 防 zip 炸弹：单个合约 CSV 解压后的上限；嵌套 zip（月/日这一层）本身解压后的上限
MAX_CSV_BYTES = 500 * 1024 * 1024
MAX_NESTED_ZIP_BYTES = 2 * 1024 * 1024 * 1024
MAX_DEPTH = 6   # 嵌套层数上限，防止循环 / 恶意套娃

_MONTH_RE = re.compile(r'^\d{6}$')
_DAY_RE = re.compile(r'^\d{8}$')

OVERWRITE_MODES = ('skip', 'overwrite')


class ArchiveError(Exception):
    """压缩包整体无法处理（不是 zip、损坏、没有找到数据等）。"""


def normalize_product(product):
    """品种代码规范化：只留字母，小写。非法返回空串。"""
    p = (product or '').strip().lower()
    return p if re.fullmatch(r'[a-z]{1,4}', p) else ''


def normalize_products(products):
    """品种列表规范化：接受列表或逗号 / 空白分隔的字符串，去重保序；任一项非法抛 ArchiveError。"""
    if isinstance(products, str):
        products = [products]
    out = []
    for item in products or []:
        for raw in re.split(r'[,\s，、]+', item or ''):   # 每一项也可能是逗号分隔的多个品种
            if not raw:
                continue
            p = normalize_product(raw)
            if not p:
                raise ArchiveError(f'品种代码不合法：{raw}')
            if p not in out:
                out.append(p)
    return out


def contract_pattern(products):
    """匹配「品种+数字」合约文件名（不含扩展名），如 fu2611；品种后必须直接跟数字，避免 fu 误匹配 fut2611。
    products 可以是单个品种字符串，也可以是列表（多个品种合成一个正则，压缩包只需扫描一遍）。"""
    if isinstance(products, str):
        products = [products]
    alts = '|'.join(re.escape(p) for p in products)
    return re.compile(rf'^(?:{alts})\d{{3,4}}$', re.IGNORECASE)


def _clean_parts(name):
    """压缩包成员路径 -> 去掉空段 / 当前目录的分段列表；含 .. 或绝对路径的返回 None（zip-slip 防护）。"""
    norm = name.replace('\\', '/')
    if norm.startswith('/') or re.match(r'^[A-Za-z]:', norm):
        return None
    parts = [p for p in norm.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        return None
    return parts


def _is_junk(parts):
    return any(p.startswith('__MACOSX') or p == '.DS_Store' or p.startswith('._') for p in parts)


def _read_member(zf, info, limit):
    """读取 zip 成员内容，超过 limit 抛 ArchiveError（按实际读取量判断，不信任头部声明的大小）。"""
    if info.file_size > limit:
        raise ArchiveError(f'「{info.filename}」解压后超过 {limit // 1024 // 1024}MB，已拒绝')
    with zf.open(info) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise ArchiveError(f'「{info.filename}」解压后超过 {limit // 1024 // 1024}MB，已拒绝')
    return data


def _extract_csv(inner_bytes, member_label):
    """合约 zip（fu2611.zip）的内容 -> (csv 字节, csv 原文件名)。里面应当只有一份 CSV。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(inner_bytes))
    except zipfile.BadZipFile:
        raise ArchiveError(f'「{member_label}」不是有效的 zip 文件')
    with zf:
        csvs = []
        for info in zf.infolist():
            parts = _clean_parts(info.filename)
            if info.is_dir() or not parts or _is_junk(parts):
                continue
            if parts[-1].lower().endswith('.csv'):
                csvs.append((info, parts[-1]))
        if not csvs:
            raise ArchiveError(f'「{member_label}」里没有 CSV 文件')
        # 正常只会有一份；万一有多份，取最大的那份（其余多半是说明文件）
        info, csv_name = max(csvs, key=lambda x: x[0].file_size)
        return _read_member(zf, info, MAX_CSV_BYTES), csv_name


def _walk(zf, depth, pattern, label_prefix):
    """遍历一个 zip，逐个产出命中的合约成员 (label, 合约 zip 字节)。

    label 形如「202611/20261102/fu2611.zip」，用于结果展示。月 / 日这一层如果本身被打成了 zip
    （如 202611.zip、20261102.zip），解开继续往里找；解开的内层只存在于内存，用完即释放。
    """
    infos = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = _clean_parts(info.filename)
        if not parts or _is_junk(parts):
            continue
        stem, ext = os.path.splitext(parts[-1])
        if ext.lower() != '.zip':
            continue
        infos.append(('/'.join(label_prefix + parts), parts, stem, info))
    infos.sort(key=lambda x: x[0])   # YYYYMM/YYYYMMDD 字典序即时间序

    for label, parts, stem, info in infos:
        if pattern.match(stem):
            yield label, _read_member(zf, info, MAX_NESTED_ZIP_BYTES)
        elif (_MONTH_RE.match(stem) or _DAY_RE.match(stem)) and depth < MAX_DEPTH:
            data = _read_member(zf, info, MAX_NESTED_ZIP_BYTES)
            try:
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                continue
            del data
            with inner:
                yield from _walk(inner, depth + 1, pattern, label_prefix + parts[:-1] + [stem])


def _count_hits(zf, depth, pattern):
    """只数命中的合约成员个数（不读取合约 zip 内容），用于进度条的总数。
    月 / 日层是 zip 时需要解开才能数，所以这一步对「全是文件夹」的压缩包几乎瞬间完成。"""
    n = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = _clean_parts(info.filename)
        if not parts or _is_junk(parts):
            continue
        stem, ext = os.path.splitext(parts[-1])
        if ext.lower() != '.zip':
            continue
        if pattern.match(stem):
            n += 1
        elif (_MONTH_RE.match(stem) or _DAY_RE.match(stem)) and depth < MAX_DEPTH:
            try:
                inner = zipfile.ZipFile(io.BytesIO(_read_member(zf, info, MAX_NESTED_ZIP_BYTES)))
            except zipfile.BadZipFile:
                continue
            with inner:
                n += _count_hits(inner, depth + 1, pattern)
    return n


def import_archive(archive_path, products, on_exists='skip', progress=None):
    """把压缩包里指定品种（可多个）的所有合约数据导入 depth_files。

    progress(done, total, label)：可选回调；total 先通过一次快速扫描得到，之后每处理完一份回调一次。
    返回 dict：
        products（规范化后的品种列表）, matched（命中的合约文件数）, imported / overwritten / skipped / failed（计数）,
        perProduct（每个品种命中的文件数，没命中的为 0）,
        contracts（涉及的合约代码，排序）, items（逐个结果：label / status / name / message）
    压缩包整体无法打开或所选品种一个合约都没找到，抛 ArchiveError。
    """
    products = normalize_products(products)
    if not products:
        raise ArchiveError('请选择有效的品种')
    if on_exists not in OVERWRITE_MODES:
        on_exists = 'skip'
    pattern = contract_pattern(products)
    # 合约文件名 -> 品种：用最长的前缀匹配（如同时选 a 和 ag 时，ag2612 属于 ag 而不是 a）
    by_len = sorted(products, key=len, reverse=True)
    per_product = {p: 0 for p in products}

    def product_of_label(label):
        stem = os.path.splitext(label.rsplit('/', 1)[-1])[0].lower()
        return next((p for p in by_len if re.fullmatch(rf'{re.escape(p)}\d{{3,4}}', stem)), '')
    root = svc.depth_files_dir()

    try:
        outer = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile:
        raise ArchiveError('不是有效的 zip 压缩文件（暂只支持 .zip）')

    items = []
    counts = {'imported': 0, 'overwritten': 0, 'skipped': 0, 'failed': 0}
    contracts = set()
    seen_names = set()   # 本次导入中已处理的目标文件名：同一天出现重复成员时只取第一份

    def add(label, status, name='', message='', symbol=''):
        items.append({'label': label, 'status': status, 'name': name, 'message': message, 'symbol': symbol})

    with outer:
        matched = 0
        try:
            total = _count_hits(outer, 0, pattern)
            if total == 0:
                names = '、'.join(products)
                raise ArchiveError(
                    f'压缩包里没有找到品种「{names}」的合约数据（应为 YYYYMM/YYYYMMDD/品种+数字.zip 结构，如 {products[0]}2611.zip）')
            if progress:
                progress(0, total, '')
            hits = _walk(outer, 0, pattern, [])
            for label, inner_bytes in hits:
                matched += 1
                owner = product_of_label(label)
                if owner:
                    per_product[owner] += 1
                if progress:
                    progress(matched - 1, total, label)
                try:
                    csv_bytes, csv_name = _extract_csv(inner_bytes, label)
                    meta = depth_market.peek_meta(csv_bytes, csv_name)
                    name = depth_market.canonical_name(csv_bytes, csv_name, '.csv')
                except depth_market.DepthParseError as e:
                    counts['failed'] += 1
                    add(label, 'failed', message=str(e))
                    continue
                except ArchiveError as e:
                    counts['failed'] += 1
                    add(label, 'failed', message=str(e))
                    continue
                except Exception as e:  # noqa: BLE001
                    counts['failed'] += 1
                    add(label, 'failed', message=f'读取失败：{e}')
                    continue

                symbol = str(meta['symbol'])
                path = svc.safe_depth_path(name)
                if path is None:
                    counts['failed'] += 1
                    add(label, 'failed', name, f'文件名不合法：{name}')
                    continue
                if name in seen_names:
                    counts['skipped'] += 1
                    add(label, 'skipped', name, '压缩包内重复的数据，已忽略', symbol)
                    continue
                seen_names.add(name)

                existed = os.path.exists(path)
                if existed and on_exists != 'overwrite':
                    counts['skipped'] += 1
                    add(label, 'skipped', name, '已存在，已跳过', symbol)
                    contracts.add(symbol)
                    continue

                tmp = path + '.uploading'
                try:
                    os.makedirs(root, exist_ok=True)
                    with open(tmp, 'wb') as out:
                        out.write(csv_bytes)
                    os.replace(tmp, path)
                except OSError as e:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    counts['failed'] += 1
                    add(label, 'failed', name, f'保存失败：{e}', symbol)
                    continue
                if existed:
                    counts['overwritten'] += 1
                    add(label, 'overwritten', name, '已覆盖', symbol)
                else:
                    counts['imported'] += 1
                    add(label, 'imported', name, '', symbol)
                contracts.add(symbol)
        except zipfile.BadZipFile as e:
            raise ArchiveError(f'压缩包已损坏：{e}')

    if progress:
        progress(matched, total, '')
    return {'products': products, 'perProduct': per_product, 'matched': matched,
            'contracts': sorted(contracts), 'items': items, **counts}


# ---------------------------------------------------------------------------
# 后台任务：上传后立即返回 taskId，导入在线程里跑，前端轮询进度
# ---------------------------------------------------------------------------
_TASKS = {}            # taskId -> dict（见 start_task）
_TASKS_LOCK = threading.Lock()
_TASKS_KEEP = 20       # 只保留最近的任务记录


def _prune_tasks():
    finished = [k for k, v in _TASKS.items() if v['status'] != 'running']   # dict 保持插入顺序，最旧的在前
    for k in finished[:max(0, len(finished) - _TASKS_KEEP)]:
        _TASKS.pop(k, None)


def start_task(archive_path, products, on_exists, original_name):
    """启动后台导入，返回 taskId。products 须已规范化；archive_path 导入结束后由任务线程删除。"""
    task_id = uuid.uuid4().hex
    task = {'id': task_id, 'status': 'running', 'products': list(products), 'originalName': original_name,
            'done': 0, 'total': 0, 'current': '', 'message': '', 'result': None, 'startedAt': time.time()}
    with _TASKS_LOCK:
        _prune_tasks()
        _TASKS[task_id] = task

    def on_progress(done, total, label):
        task['done'], task['total'], task['current'] = done, total, label

    def run():
        try:
            task['result'] = import_archive(archive_path, products, on_exists, on_progress)
            task['done'] = task['total']
            task['status'] = 'done'
        except ArchiveError as e:
            task['status'], task['message'] = 'error', str(e)
        except Exception as e:  # noqa: BLE001
            print(f"[Depth] 批量导入失败: {e}")
            task['status'], task['message'] = 'error', f'批量导入失败：{e}'
        finally:
            try:
                os.remove(archive_path)
            except OSError:
                pass

    threading.Thread(target=run, name=f'depth-archive-{task_id[:6]}', daemon=True).start()
    return task_id


def get_task(task_id):
    return _TASKS.get(task_id or '')


def latest_task():
    """最近的任务：有运行中的优先返回它，否则返回最后启动的那个（供页面重新进入 / 应用重载后恢复进度）。"""
    with _TASKS_LOCK:
        tasks = list(_TASKS.values())
    running = [t for t in tasks if t['status'] == 'running']
    if running:
        return running[-1]
    return tasks[-1] if tasks else None


def has_running_task():
    return any(t['status'] == 'running' for t in _TASKS.values())


def save_upload_to_temp(file_storage):
    """把上传的压缩包流式写到临时文件（不整体读入内存），返回临时文件路径；调用方负责删除。"""
    fd, path = tempfile.mkstemp(prefix='depth_archive_', suffix='.zip')
    try:
        with os.fdopen(fd, 'wb') as out:
            shutil.copyfileobj(file_storage.stream, out, length=1024 * 1024)
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path
