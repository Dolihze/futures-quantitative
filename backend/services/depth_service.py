"""深度行情服务：depth_files 文件夹管理、tick 解析缓存、按合约分组的文件索引。"""
import os
import uuid
from collections import OrderedDict

from backend import config
from backend.core import depth_market

# 解析后的 tick 数据放在内存缓存里（depthId 临时，sidecar 重启即失效），只留最近 3 份（tick 数据较大）。
DEPTH_CACHE = OrderedDict()
DEPTH_CACHE_MAX = 3

# 导入过的 tick CSV 保存在这个文件夹（位置规则同 review_files，已加入 .gitignore）；环境变量 DEPTH_FILES_DIR 可改（测试用）
DEPTH_FILES_DIRNAME = 'depth_files'
DEPTH_EXTS = ('.csv',)
DEPTH_MAX_UPLOAD = 500 * 1024 * 1024   # tick 文件很大，单个上限 500MB

# 每个文件的元数据要读一遍 CSV 才知道，大文件很慢，缓存到内存，按 (大小, 修改时间) 判断是否失效。
_DEPTH_META_CACHE = {}   # name -> ((size, mtime_ns), meta | {"error": str})


def depth_files_dir():
    return os.environ.get('DEPTH_FILES_DIR') or os.path.join(config.BASE_DIR, DEPTH_FILES_DIRNAME)


def safe_depth_path(name):
    """文件名 -> depth_files 里的真实路径；名字不合法返回 None（规则同 safe_review_path）。"""
    if not name or name != os.path.basename(name) or name in ('.', '..'):
        return None
    if not name.lower().endswith(DEPTH_EXTS):
        return None
    root = os.path.realpath(depth_files_dir())
    path = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(path) != root:
        return None
    return path


def is_depth_file(root, name):
    path = os.path.join(root, name)
    return not (name.startswith(('~$', '.')) or not os.path.isfile(path) or not name.lower().endswith(DEPTH_EXTS))


def cache_ticks(td):
    """把解析结果放进缓存，返回 depthId，并淘汰最旧的。"""
    depth_id = uuid.uuid4().hex
    DEPTH_CACHE[depth_id] = td
    while len(DEPTH_CACHE) > DEPTH_CACHE_MAX:
        DEPTH_CACHE.popitem(last=False)
    return depth_id


def get_cached(depth_id):
    """取缓存里的 tick 数据；不存在返回 None。命中时刷新 LRU 顺序。"""
    td = DEPTH_CACHE.get(depth_id or '')
    if td is not None:
        DEPTH_CACHE.move_to_end(depth_id)
    return td


def list_files():
    root = depth_files_dir()
    files = []
    if os.path.isdir(root):
        for name in os.listdir(root):
            if not is_depth_file(root, name):
                continue
            st = os.stat(os.path.join(root, name))
            files.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
    files.sort(key=lambda x: (-x["mtime"], x["name"]))
    return files


def file_meta(name, path):
    st = os.stat(path)
    sig = (st.st_size, st.st_mtime_ns)
    hit = _DEPTH_META_CACHE.get(name)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        with open(path, 'rb') as fh:
            meta = depth_market.peek_meta(fh.read(), name)
    except depth_market.DepthParseError as e:
        meta = {"error": str(e)}
    except Exception as e:
        meta = {"error": f"读取失败：{e}"}
    _DEPTH_META_CACHE[name] = (sig, meta)
    return meta


def scan():
    """扫描 depth_files：返回 (按合约分组的列表, 无法识别的文件列表)。合约按「最近导入的文件」倒序。"""
    root = depth_files_dir()
    groups, bad = {}, []
    if not os.path.isdir(root):
        return [], []
    alive = set()
    for name in sorted(os.listdir(root)):
        if not is_depth_file(root, name):
            continue
        path = os.path.join(root, name)
        alive.add(name)
        st = os.stat(path)
        meta = file_meta(name, path)
        if "error" in meta:
            bad.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime), "error": meta["error"]})
            continue
        g = groups.setdefault(meta["symbol"], {"symbol": meta["symbol"], "name": "", "files": []})
        g["name"] = g["name"] or meta["name"]
        g["files"].append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime),
                           "tickCount": meta["tickCount"], "days": meta["days"],
                           "start": meta["start"], "end": meta["end"], "hasBs": meta["hasBs"]})
    for gone in set(_DEPTH_META_CACHE) - alive:   # 文件被删了，清掉缓存
        _DEPTH_META_CACHE.pop(gone, None)

    out = []
    for g in groups.values():
        fs = g["files"]
        days = sorted({d for f in fs for d in f["days"]})
        out.append({
            "symbol": g["symbol"], "name": g["name"],
            "fileCount": len(fs), "files": sorted(fs, key=lambda f: f["start"]),
            "tickCount": sum(f["tickCount"] for f in fs),
            "days": days, "dayCount": len(days),
            "start": min(f["start"] for f in fs), "end": max(f["end"] for f in fs),
            "hasBs": all(f["hasBs"] for f in fs),
            "mtime": max(f["mtime"] for f in fs),
            "size": sum(f["size"] for f in fs),
        })
    out.sort(key=lambda g: (-g["mtime"], g["symbol"]))
    bad.sort(key=lambda x: (-x["mtime"], x["name"]))
    return out, bad
