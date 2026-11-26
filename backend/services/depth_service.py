"""深度行情服务：行情库（见 tick_store）管理、按合约分组的台账、tick 解析缓存。

数据怎么存：
- 导入的 tick CSV 解析一次后存进行情库 depth_files/store/<合约>_<交易日>.npz（列式，打开时直接加载，不再解析 CSV）；
  原始 CSV 导入成功后不再保留。「哪些数据已经导入」由台账 depth_files/.ledger.json 回答（合约 / 交易日 / 导入时间 / 来源文件名）。
- 历史遗留：depth_files 根目录里以前导入的 CSV，首次扫描时自动迁移进行情库（解析成功才删除 CSV；
  解析失败的保留原处，在页面「无法识别的文件」里列出）。
- 内存里还有两层缓存：台账（进程内）、合约解析结果（services/tick_cache.py，深度行情 / 回测 / 复盘共用）。
"""
import os
import threading
import time

from backend import config
from backend.core import depth_market
from backend.services import calendar_service, tick_cache, tick_store

# 导入过的 tick 数据放在这个文件夹（位置规则同 review_files，已加入 .gitignore）；环境变量 DEPTH_FILES_DIR 可改（测试用）
DEPTH_FILES_DIRNAME = 'depth_files'
DEPTH_EXTS = ('.csv',)   # 可导入 / 可迁移的源文件类型
DEPTH_MAX_UPLOAD = 500 * 1024 * 1024   # tick 文件很大，单个上限 500MB
DEPTH_MAX_ARCHIVE_UPLOAD = 10 * 1024 * 1024 * 1024   # 全量行情压缩包（含所有品种的多个月数据），上限 10GB

_migrate_lock = threading.Lock()
MIGRATE_FLUSH_EVERY = 20   # 迁移时每处理这么多个文件把台账落盘一次


def depth_files_dir():
    return os.environ.get('DEPTH_FILES_DIR') or os.path.join(config.BASE_DIR, DEPTH_FILES_DIRNAME)


# ---------------------------------------------------------------------------
# 单元（行情库里的一份数据）
# ---------------------------------------------------------------------------
def unit_name(file_name):
    """规范文件名 / 单元名 -> 单元名（fu2611_20261102.csv -> fu2611_20261102）。"""
    return tick_store.unit_name(file_name)


def unit_exists(name):
    return tick_store.has_unit(depth_files_dir(), unit_name(name))


def already_imported(name, symbol, days):
    """这份数据（合约 + 交易日们）是不是已经在行情库里了。返回已覆盖的原因文字，没有则返回 ''。

    只比较单元名会漏：一份多日 CSV 的单元名是「合约_起日-止日」，之后再导入其中某一天的单日 CSV，名字不同，
    判不出重复，同一天会被存两份（合并时才丢掉重叠并给警告）。所以除了同名，还要看台账里该合约已覆盖的交易日：
    本次文件的每一个交易日都已被覆盖，就算重复。
    """
    base = depth_files_dir()
    n = unit_name(name)
    if tick_store.has_unit(base, n):
        return f'「{n}」已导入过'
    have = tick_store.covered_days(base, symbol)
    if days and all(d in have for d in days):
        d0, d1 = days[0], days[-1]
        return f'{symbol} 的 {d0 if d0 == d1 else d0 + " ~ " + d1} 已经导入过（包含在已有的数据里）'
    return ''


def save_unit(name, td, source='', save_ledger=True):
    """把解析好的 TickData 存进行情库并登记台账，返回台账 meta。批量导入传 save_ledger=False，整批后调 flush_ledger()。"""
    return tick_store.import_unit(depth_files_dir(), unit_name(name), td, source, save=save_ledger)


def flush_ledger():
    tick_store.flush(depth_files_dir())


def remove_unit(name):
    tick_store.remove_unit(depth_files_dir(), unit_name(name))


def safe_depth_path(name):
    """遗留 CSV：文件名 -> depth_files 根目录里的真实路径；名字不合法返回 None（迁移用）。"""
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


# ---------------------------------------------------------------------------
# 缓存（统一的 tick_cache）
# ---------------------------------------------------------------------------
def cache_ticks(td, symbol=None):
    """把解析结果登记进统一缓存（services/tick_cache.py），返回 depthId。
    symbol 不为空：td 同时是该合约的缓存（见 load_contract），depthId 和合约缓存共用同一份内存。"""
    return tick_cache.new_handle(td, symbol)


def get_cached(depth_id):
    """按 depthId 取 tick 数据；不存在（被淘汰 / 后端重启 / 合约数据已变）返回 None。命中时刷新使用顺序。"""
    return tick_cache.get_handle(depth_id)


def contract_signature(contract):
    """合约所有数据单元的 (名称, 大小, mtime_ns) 签名：导入 / 删除 / 覆盖后变化，用来判断缓存是否过期。"""
    base = depth_files_dir()
    return tuple(sorted(tick_store.signature(base, unit_name(f['name'])) for f in contract['files']))


def load_contract(contract):
    """从行情库加载并合并该合约的所有数据，返回 (TickData, 单元个数)。带统一缓存：
    深度行情、回测、交易复盘取同一个合约只加载一次，内存里只有一份；数据变了自动重新加载。
    加载失败抛 depth_market.DepthParseError / OSError（带单元名的说明），由调用方转成对应的 HTTP 错误。"""
    symbol = contract['symbol']
    sig = contract_signature(contract)
    td = tick_cache.get_contract(symbol, sig)
    if td is not None:
        return td, len(contract['files'])
    base = depth_files_dir()
    parts = []
    for f in contract['files']:
        n = unit_name(f['name'])
        try:
            parts.append(tick_store.read_unit(base, n))
        except tick_store.StoreError as e:
            raise depth_market.DepthParseError(f"{n}：{e}")
        except FileNotFoundError:
            raise OSError(f"{n} 已不在行情库中，请刷新列表")
        except OSError as e:
            raise OSError(f"读取 {n} 失败：{e}")
    td = depth_market.merge(parts)
    tick_cache.put_contract(symbol, sig, td)
    return td, len(parts)


# ---------------------------------------------------------------------------
# 遗留 CSV 迁移
# ---------------------------------------------------------------------------
def legacy_csv_names():
    root = depth_files_dir()
    if not os.path.isdir(root):
        return []
    return sorted(n for n in os.listdir(root) if is_depth_file(root, n))


def migrate_legacy(progress=None):
    """把 depth_files 根目录里的遗留 CSV 迁移进行情库。返回 {migrated, failed:[{name,error,size,mtime}], skippedDup}。

    每个文件：解析成功 -> 存 npz -> 登记台账 -> 删除 CSV；解析失败 -> 保留 CSV，记进 failed（页面「无法识别的文件」）。
    单元名只编码「合约 + 交易日」，不代表内容相同，所以库里已有同名单元时不能想当然地删 CSV：
    - 内容一致（tick 数和起止时间都相同）：确实是重复导入，删除多余的 CSV，计入 skippedDup；
    - 内容不同：CSV 里可能是更完整的一天，或唯一一份修正过的导出，**保留 CSV** 并记进 failed，让用户自己决定
      （CSV 导入后不再保留，删了就找不回来）。
    写入走 only_if_absent：迁移在解析 CSV 的那几秒里，用户可能刚导入了同一份数据，不能被旧数据盖掉。
    台账每处理若干个就落盘一次：迁移中途被关闭，已入库的不丢，下次接着迁（CSV 只在入库成功后才删除）。
    """
    base = depth_files_dir()
    out = {"migrated": 0, "skippedDup": 0, "failed": []}
    with _migrate_lock:
        names = legacy_csv_names()
        total = len(names)
        for i, name in enumerate(names):
            if progress:
                progress(i, total, name, out)
            path = safe_depth_path(name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            try:
                with open(path, 'rb') as fh:
                    content = fh.read()
                meta0 = depth_market.peek_meta(content, name)
                canon = depth_market.canonical_name(content, name, '.csv', meta0)
                n = unit_name(canon)
                verdict = _compare_with_stored(base, n, meta0)
                if verdict == 'same':
                    os.remove(path)
                    out["skippedDup"] += 1
                    continue
                if verdict == 'different':
                    out["failed"].append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime),
                                          "error": f"行情库里已有同一合约同一交易日的数据（{n}），但内容不同"
                                                   f"（本文件 {meta0['tickCount']} 笔，库里 {_stored_ticks(base, n)} 笔）。"
                                                   "为避免丢数据，本文件没有删除，请确认后手动处理"})
                    continue
                td = depth_market.parse(content, name)
                if tick_store.import_unit(base, n, td, name, only_if_absent=True, save=False) is None:
                    # 解析期间别处刚导入了同一份数据：以刚导入的为准，这份 CSV 留给下一轮按「内容是否一致」处理
                    continue
                os.remove(path)
                out["migrated"] += 1
            except depth_market.DepthParseError as e:
                out["failed"].append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime), "error": str(e)})
            except Exception as e:  # noqa: BLE001
                out["failed"].append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime),
                                      "error": f"迁移失败：{e}"})
            if (i + 1) % MIGRATE_FLUSH_EVERY == 0:
                tick_store.flush(base)
        tick_store.flush(base)
        if progress:
            progress(total, total, '', out)
    return out


def _stored_ticks(base, n):
    e = tick_store.get_entry(base, n)
    return e.get("tickCount") if e else 0


def _compare_with_stored(base, n, meta):
    """CSV 的元数据和行情库里同名单元的台账条目比较：'absent'（库里没有）/ 'same' / 'different'。"""
    e = tick_store.get_entry(base, n)
    if e is None:
        return 'absent'
    same = (e.get("tickCount") == meta.get("tickCount") and e.get("start") == meta.get("start")
            and e.get("end") == meta.get("end") and e.get("symbol") == meta.get("symbol"))
    return 'same' if same else 'different'


# 迁移是后台任务：首次打开列表时遗留 CSV 可能有几百个（实测 769 个约 200 秒），不能卡住请求。
_MIGRATION = {"running": False, "total": 0, "done": 0, "current": "", "migrated": 0, "skippedDup": 0,
              "failed": [], "finishedAt": 0}
_MIGRATION_LOCK = threading.Lock()


def migration_status():
    """迁移状态快照：running / total（本轮待迁移文件数）/ done（已处理）/ failed（无法识别的文件，保留在原处）。"""
    names = set(legacy_csv_names())
    with _MIGRATION_LOCK:
        if not _MIGRATION["running"]:
            # 失败的文件被用户在外面删掉 / 改走了：不再算失败，否则列表里会留着幽灵条目，pending 还会变成负数
            _MIGRATION["failed"] = [f for f in _MIGRATION["failed"] if f["name"] in names]
        s = dict(_MIGRATION)
        s["failed"] = list(_MIGRATION["failed"])
    if s["running"]:
        s["pending"] = max(s["total"] - s["done"], 0)
    else:
        s["pending"] = max(len(names) - len(s["failed"]), 0)
    return s


def start_migration():
    """有遗留 CSV 且当前没在迁移时，启动后台迁移线程。返回是否已经在运行 / 刚启动。"""
    with _MIGRATION_LOCK:
        if _MIGRATION["running"]:
            return True
        names = legacy_csv_names()
        # 上一轮解析失败的文件还躺在原处：不要每次打开列表都重试，除非文件本身变了
        bad = {f["name"]: f for f in _MIGRATION["failed"]}
        todo = [n for n in names if n not in bad or _file_changed(n, bad[n])]
        if not todo:
            return False
        _MIGRATION.update(running=True, total=len(todo), done=0, current="", migrated=0, skippedDup=0,
                          failed=[f for f in _MIGRATION["failed"] if f["name"] in names and f["name"] not in todo])

    def on_progress(i, total, name, out):
        with _MIGRATION_LOCK:
            _MIGRATION.update(done=i, total=total, current=name, migrated=out["migrated"], skippedDup=out["skippedDup"])

    def run():
        try:
            res = migrate_legacy(on_progress)
            with _MIGRATION_LOCK:
                _MIGRATION["failed"] = _MIGRATION["failed"] + res["failed"]
        except Exception as e:  # noqa: BLE001
            print(f"[Depth] 迁移遗留 CSV 失败: {e}")
        finally:
            with _MIGRATION_LOCK:
                _MIGRATION.update(running=False, finishedAt=int(time.time()))

    threading.Thread(target=run, name='depth-migrate', daemon=True).start()
    return True


def _file_changed(name, fail):
    try:
        st = os.stat(safe_depth_path(name))
    except (OSError, TypeError):
        return False
    return st.st_size != fail.get("size") or int(st.st_mtime) != fail.get("mtime")

# ---------------------------------------------------------------------------
# 台账 -> 合约分组
# ---------------------------------------------------------------------------
def scan(*, migrate='background'):
    """返回 (按合约分组的列表, 无法识别的遗留文件列表)。合约按「最近导入」倒序。

    只读台账，不碰任何数据文件。目录里还有遗留 CSV 时（以前版本导入的），按 migrate 处理：
    - 'background'（默认，给页面用）：启动后台迁移线程就返回，已迁移的数据随进度陆续出现；
    - 'sync'：当场迁移完再返回（测试 / 脚本用，数据量大时会很慢）；
    - 'none'：不迁移（回测 / 复盘取合约时用：有什么数据用什么，别触发几分钟的迁移）。
    每个合约的 files 是它名下的数据单元（name = 单元名，如 fu2611_20261102）。
    """
    base = depth_files_dir()
    bad = []
    if migrate == 'sync':
        if legacy_csv_names():
            bad = migrate_legacy()["failed"]
    elif migrate == 'background':
        start_migration()
        bad = migration_status()["failed"]
    ents = tick_store.entries(base)
    groups = {}
    for name, e in ents.items():
        sym = e.get("symbol") or ''
        g = groups.setdefault(sym, {"symbol": sym, "name": "", "files": []})
        g["name"] = g["name"] or (e.get("name") or "")
        g["files"].append({"name": name, "size": e.get("size", 0), "mtime": int(e.get("importedAt") or 0),
                           "tickCount": e.get("tickCount", 0), "days": e.get("days", []),
                           "start": e.get("start", ""), "end": e.get("end", ""), "hasBs": bool(e.get("hasBs")),
                           "importedAt": int(e.get("importedAt") or 0), "source": e.get("source") or ""})
    out = []
    for g in groups.values():
        fs = g["files"]
        days = sorted({d for f in fs for d in f["days"]})
        # 起止范围内「是交易日却没导入」的日期。交易日历没缓存时为 None（前端不显示缺失，也不当成"没缺"）
        missing = calendar_service.missing_days(days)
        out.append({
            "symbol": g["symbol"], "name": g["name"],
            "fileCount": len(fs), "files": sorted(fs, key=lambda f: f["start"]),
            "tickCount": sum(f["tickCount"] for f in fs),
            "days": days, "dayCount": len(days), "missingDays": missing,
            "start": min(f["start"] for f in fs), "end": max(f["end"] for f in fs),
            "hasBs": all(f["hasBs"] for f in fs),
            "mtime": max(f["mtime"] for f in fs),
            "size": sum(f["size"] for f in fs),
        })
    out.sort(key=lambda g: (-g["mtime"], g["symbol"]))
    bad.sort(key=lambda x: (-x["mtime"], x["name"]))
    return out, bad


def list_files():
    """行情库里的全部数据单元（最近导入的在前），给 /api/depth/files。"""
    ents = tick_store.entries(depth_files_dir())
    files = [{"name": n, "size": e.get("size", 0), "mtime": int(e.get("importedAt") or 0)} for n, e in ents.items()]
    files.sort(key=lambda x: (-x["mtime"], x["name"]))
    return files


def imported_days(symbol=None):
    """台账里已导入的 {合约: [交易日...]}（升序），批量导入前用来提示「哪些已经导入过」。"""
    out = {}
    for e in tick_store.entries(depth_files_dir()).values():
        if symbol and e.get("symbol") != symbol:
            continue
        out.setdefault(e.get("symbol") or '', set()).update(e.get("days") or [])
    return {k: sorted(v) for k, v in out.items()}
