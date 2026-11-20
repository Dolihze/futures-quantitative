"""交易复盘服务：review_files 文件夹管理、解析结果内存缓存、多文件合并。

不依赖 Flask 请求对象，路由层负责把异常/结果转成 HTTP 响应。
"""
import os
import uuid
from collections import OrderedDict

from backend import config
from backend.core import review

# 解析后的交易记录放在内存缓存里（reviewId 是临时的，sidecar 重启即失效）。
# 最多保留最近 5 份，避免反复切换文件导致内存无限增长。
REVIEW_CACHE = OrderedDict()
REVIEW_CACHE_MAX = 5

# 导入过的交易记录文件保存在这个文件夹里（开发模式 = 项目根目录，打包后 = 可执行文件同级目录）。
# 里面是个人交易数据，已加入 .gitignore。环境变量 REVIEW_FILES_DIR 可以改位置（测试用）。
REVIEW_FILES_DIRNAME = 'review_files'
REVIEW_EXTS = ('.xlsx', '.xls', '.csv')

_REVIEW_META_CACHE = {}   # name -> ((size, mtime_ns), meta | {"error": str})
_REVIEW_ALL_CACHE = {"sig": None, "id": None, "warnings": [], "skipped": [], "fileCount": 0}


def review_files_dir():
    return os.environ.get('REVIEW_FILES_DIR') or os.path.join(config.BASE_DIR, REVIEW_FILES_DIRNAME)


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


def is_review_file(root, name):
    """跳过 Excel 锁文件（~$ 开头）、隐藏文件、子文件夹和不支持的类型。"""
    path = os.path.join(root, name)
    return not (name.startswith(('~$', '.')) or not os.path.isfile(path) or not name.lower().endswith(REVIEW_EXTS))


def cache_records(records):
    """把解析结果放进缓存，返回 reviewId，并淘汰最旧的。"""
    review_id = uuid.uuid4().hex
    REVIEW_CACHE[review_id] = records
    while len(REVIEW_CACHE) > REVIEW_CACHE_MAX:
        REVIEW_CACHE.popitem(last=False)
    return review_id


def list_files():
    """review_files 里的文件列表（最近修改的在前）。文件夹不存在时返回空列表。"""
    root = review_files_dir()
    files = []
    if os.path.isdir(root):
        for name in os.listdir(root):
            if not is_review_file(root, name):
                continue
            st = os.stat(os.path.join(root, name))
            files.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
    files.sort(key=lambda x: (-x["mtime"], x["name"]))
    return files


def file_meta(name, path):
    """交易记录文件的元信息（品种 / 交易日 / 成交手数），按 (大小, 修改时间) 缓存，文件没变不再重读。"""
    st = os.stat(path)
    sig = (st.st_size, st.st_mtime_ns)
    hit = _REVIEW_META_CACHE.get(name)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        with open(path, 'rb') as fh:
            r = review.analyze(fh.read(), name)
        meta = {"products": r.products, "days": r.days, "tradeCount": int(len(r.records)),
                "start": r.start, "end": r.end, "hasFee": r.has_fee}
    except review.ReviewParseError as e:
        meta = {"error": str(e)}
    except Exception as e:
        meta = {"error": f"读取失败：{e}"}
    _REVIEW_META_CACHE[name] = (sig, meta)
    return meta


def list_files_detail():
    """文件列表 + 每个文件的元信息（数据库管理用）。解析不了的文件带 error 字段。"""
    root = review_files_dir()
    files = []
    if os.path.isdir(root):
        alive = set()
        for name in os.listdir(root):
            if not is_review_file(root, name):
                continue
            path = os.path.join(root, name)
            alive.add(name)
            st = os.stat(path)
            item = {"name": name, "size": st.st_size, "mtime": int(st.st_mtime)}
            item.update(file_meta(name, path))
            files.append(item)
        for gone in set(_REVIEW_META_CACHE) - alive:
            _REVIEW_META_CACHE.pop(gone, None)
    files.sort(key=lambda x: (-x["mtime"], x["name"]))
    return files


def all_records():
    """合并 review_files 里所有能解析的文件 -> (reviewId, warnings, skipped, fileCount)。

    文件集合（名字 + 大小 + 修改时间）没变就复用上次的合并结果；变了（导入 / 删除 / 覆盖）才重新解析。
    合并结果放进 REVIEW_CACHE，所以 reviewId 可以直接给 /api/review/curve、/day-trades 用。
    """
    root = review_files_dir()
    entries = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if not is_review_file(root, name):
                continue
            path = os.path.join(root, name)
            st = os.stat(path)
            entries.append((name, path, st.st_size, st.st_mtime_ns))
    sig = tuple((n, s, m) for n, _p, s, m in entries)
    c = _REVIEW_ALL_CACHE
    if c["sig"] == sig and c["id"] in REVIEW_CACHE:
        REVIEW_CACHE.move_to_end(c["id"])
        return c["id"], c["warnings"], c["skipped"], c["fileCount"]

    parts, warnings, skipped = [], [], []
    for name, path, _s, _m in entries:
        try:
            with open(path, 'rb') as fh:
                r = review.analyze(fh.read(), name)
            parts.append(r.records)
            warnings += [f"{name}：{w}" for w in r.warnings]
        except review.ReviewParseError as e:
            skipped.append({"name": name, "error": str(e)})
        except Exception as e:
            skipped.append({"name": name, "error": f"读取失败：{e}"})
    merged = review.merge_records(parts)
    review_id = cache_records(merged)
    _REVIEW_ALL_CACHE.update(sig=sig, id=review_id, warnings=warnings, skipped=skipped, fileCount=len(parts))
    return review_id, warnings, skipped, len(parts)
