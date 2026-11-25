"""深度行情服务：depth_files 文件夹管理、tick 解析缓存、按合约分组的文件索引。

文件索引（合约 / 交易日 / tick 数 / 时间范围）分两级缓存，避免每次都把全部 CSV 读一遍：
1. 内存 _DEPTH_META_CACHE：进程内有效；
2. 磁盘 depth_files/.meta_index.json：跨重启有效。键是文件名，签名是 (大小, 修改时间)，
   签名没变就直接用索引里的结果，不读 CSV；文件新增 / 改动 / 删除后自动更新。
索引损坏或版本不符时丢弃并重建，不影响数据文件本身（索引只是缓存，CSV 才是数据）。
"""
import json
import os
import threading

from backend import config
from backend.core import depth_market
from backend.services import tick_cache

# 解析后的 tick 数据放在内存缓存里（depthId 临时，sidecar 重启即失效），只留最近 3 份（tick 数据较大）。

# 导入过的 tick CSV 保存在这个文件夹（位置规则同 review_files，已加入 .gitignore）；环境变量 DEPTH_FILES_DIR 可改（测试用）
DEPTH_FILES_DIRNAME = 'depth_files'
DEPTH_EXTS = ('.csv',)
DEPTH_MAX_UPLOAD = 500 * 1024 * 1024   # tick 文件很大，单个上限 500MB
DEPTH_MAX_ARCHIVE_UPLOAD = 10 * 1024 * 1024 * 1024   # 全量行情压缩包（含所有品种的多个月数据），上限 10GB

# 每个文件的元数据要读一遍 CSV 才知道，大文件很慢，缓存到内存，按 (大小, 修改时间) 判断是否失效。
_DEPTH_META_CACHE = {}   # name -> ((size, mtime_ns), meta | {"error": str})

# 磁盘索引：文件名以点开头，is_depth_file 会跳过它，不会被当成数据文件
META_INDEX_NAME = '.meta_index.json'
META_INDEX_VERSION = 1
_index_lock = threading.RLock()
_index_state = {"dir": None, "loaded": False, "dirty": False}   # dir：索引对应的目录，换目录（测试）后要重新加载


def depth_files_dir():
    return os.environ.get('DEPTH_FILES_DIR') or os.path.join(config.BASE_DIR, DEPTH_FILES_DIRNAME)


def _index_path():
    return os.path.join(depth_files_dir(), META_INDEX_NAME)


def _load_index():
    """把磁盘索引读进内存缓存（每个目录只读一次）。文件不存在 / 损坏 / 版本不符都当作空索引。"""
    root = os.path.realpath(depth_files_dir())
    with _index_lock:
        if _index_state["loaded"] and _index_state["dir"] == root:
            return
        _DEPTH_META_CACHE.clear()
        _index_state.update(dir=root, loaded=True, dirty=False)
        try:
            with open(_index_path(), 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if data.get("version") != META_INDEX_VERSION or not isinstance(data.get("files"), dict):
                return
            for name, ent in data["files"].items():
                sig, meta = ent.get("sig"), ent.get("meta")
                if isinstance(sig, list) and len(sig) == 2 and isinstance(meta, dict):
                    _DEPTH_META_CACHE[name] = ((int(sig[0]), int(sig[1])), meta)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError) as e:   # 损坏的 JSON、结构不对等：丢弃，按空索引重建
            print(f"[Depth] 元数据索引读取失败，将重建：{e}")
            _DEPTH_META_CACHE.clear()


def _save_index():
    """把内存缓存写回磁盘索引（原子替换）。只有变化过才写；写失败只打日志，不影响功能。"""
    with _index_lock:
        if not _index_state["dirty"]:
            return
        root = depth_files_dir()
        if not os.path.isdir(root):
            return
        files = {name: {"sig": [sig[0], sig[1]], "meta": meta} for name, (sig, meta) in _DEPTH_META_CACHE.items()}
        tmp = _index_path() + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({"version": META_INDEX_VERSION, "files": files}, fh, ensure_ascii=False)
            os.replace(tmp, _index_path())
            _index_state["dirty"] = False
        except OSError as e:
            print(f"[Depth] 元数据索引写入失败（不影响使用，下次启动会重新解析）：{e}")
            try:
                os.remove(tmp)
            except OSError:
                pass


def remember_meta(name, path, meta, save=True):
    """导入时已经解析过文件内容，直接把 meta 记进索引，之后列表不用再读这个文件。
    批量导入传 save=False，整批结束后调一次 save_index()，避免每个文件都重写一遍整份索引。"""
    try:
        st = os.stat(path)
    except OSError:
        return
    _load_index()
    with _index_lock:
        _DEPTH_META_CACHE[name] = ((st.st_size, st.st_mtime_ns), meta)
        _index_state["dirty"] = True
    if save:
        _save_index()


def save_index():
    """把内存索引落盘（没有变化时什么都不写）。"""
    _save_index()


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


def cache_ticks(td, symbol=None):
    """把解析结果登记进统一缓存（services/tick_cache.py），返回 depthId。
    symbol 不为空：td 同时是该合约的缓存（见 load_contract），depthId 和合约缓存共用同一份内存。"""
    return tick_cache.new_handle(td, symbol)


def get_cached(depth_id):
    """按 depthId 取 tick 数据；不存在（被淘汰 / 后端重启 / 合约文件已变）返回 None。命中时刷新使用顺序。"""
    return tick_cache.get_handle(depth_id)


def contract_signature(contract):
    """合约所有文件的 (名称, 大小, mtime_ns) 签名：导入 / 删除 / 覆盖文件后变化，用来判断缓存是否过期。"""
    sig = []
    for f in contract['files']:
        path = safe_depth_path(f['name'])
        try:
            st = os.stat(path)
            sig.append((f['name'], st.st_size, st.st_mtime_ns))
        except (OSError, TypeError):
            sig.append((f['name'], -1, -1))
    return tuple(sorted(sig))


def load_contract(contract):
    """解析并合并该合约的所有文件，返回 (TickData, 文件个数)。带统一缓存：
    深度行情、回测、交易复盘取同一个合约只解析一次，内存里只有一份；文件变了自动重新解析。
    解析失败抛 depth_market.DepthParseError / OSError（带文件名的说明），由调用方转成对应的 HTTP 错误。"""
    symbol = contract['symbol']
    sig = contract_signature(contract)
    td = tick_cache.get_contract(symbol, sig)
    if td is not None:
        return td, len(contract['files'])
    parts = []
    for f in contract['files']:
        path = safe_depth_path(f['name'])
        try:
            with open(path, 'rb') as fh:
                parts.append(depth_market.parse(fh.read(), f['name']))
        except depth_market.DepthParseError as e:
            raise depth_market.DepthParseError(f"{f['name']}：{e}")
        except OSError as e:
            raise OSError(f"读取 {f['name']} 失败：{e}")
    td = depth_market.merge(parts)
    tick_cache.put_contract(symbol, sig, td)
    return td, len(parts)

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
    _load_index()
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
    with _index_lock:
        _DEPTH_META_CACHE[name] = (sig, meta)
        _index_state["dirty"] = True
    return meta


def scan():
    """扫描 depth_files：返回 (按合约分组的列表, 无法识别的文件列表)。合约按「最近导入的文件」倒序。"""
    root = depth_files_dir()
    groups, bad = {}, []
    if not os.path.isdir(root):
        return [], []
    _load_index()
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
    with _index_lock:
        gone_names = set(_DEPTH_META_CACHE) - alive
        for gone in gone_names:   # 文件被删了，清掉缓存
            _DEPTH_META_CACHE.pop(gone, None)
        if gone_names:
            _index_state["dirty"] = True
    _save_index()   # 有新增 / 改动 / 删除时一次性落盘；没变化什么都不写

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
