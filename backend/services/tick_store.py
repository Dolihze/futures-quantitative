"""行情库：把解析好的 tick 数据（TickData）持久化成列式文件，打开时直接加载，不再解析 CSV。

存储布局（都在 depth_files 目录下，位置规则见 depth_service.depth_files_dir）：

    depth_files/
    ├── store/                       行情库
    │   ├── fu2611_20261102.npz      一个导入单元（原来的一份 CSV）= 一份已解析的 TickData
    │   └── ...
    └── .ledger.json                 台账：每个 npz 的合约 / 交易日 / tick 数 / 时间范围 / 导入时间等

为什么「一个导入单元一个 npz」而不是「一个合约一个文件」：
- 多文件合并（depth_market.merge）要按文件单独处理重叠时段、成交量差分，保持单元粒度才能让合并结果和以前完全一致；
- 导入新交易日 = 新增一个 npz，不用重写整个合约；删除 / 覆盖同理，是原子的文件操作；
- 台账只是「目录」，npz 自身带有完整元数据（_meta），台账丢了可以从 npz 重建。

CSV 导入成功后不再保留，所以「哪些数据已经导入」由台账回答（合约、交易日、导入时间、来源文件名）。
"""
import json
import os
import threading
import time
import zipfile
import zlib

import numpy as np

from backend.core import depth_market

STORE_DIRNAME = 'store'
LEDGER_NAME = '.ledger.json'
STORE_EXT = '.npz'
FORMAT_VERSION = 1       # npz 内容格式版本；不符的文件视为无法读取（提示重新导入）
LEDGER_VERSION = 1

_lock = threading.RLock()
# 写锁：导入、遗留 CSV 迁移、覆盖、删除共用同一把。它保护的是「检查是否已导入 -> 决定 -> 写 npz -> 登记台账」整段，
# 否则迁移线程在 parse 的那几秒里，用户同一份数据的导入会被它事后覆盖（旧数据盖掉新数据）。
# 只在真正写盘的那一小段持有（不包含解析 CSV 的时间），所以不会长时间阻塞导入。
_write_lock = threading.RLock()
_state = {"dir": None, "entries": None, "dirty": False}   # entries: name -> meta dict


class StoreError(Exception):
    """库文件损坏 / 版本不符：message 直接展示给用户。"""


# 读 npz 时「文件坏了」可能抛出的异常。zlib.error（压缩数据损坏）既不是 OSError 也不是 ValueError，
# 漏掉它会让一份坏文件把整个列表接口打成 500。
CORRUPT_ERRORS = (KeyError, ValueError, OSError, EOFError, zipfile.BadZipFile, zlib.error)


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
def _root(base):
    return os.path.realpath(base)


def store_dir(base):
    return os.path.join(base, STORE_DIRNAME)


def ledger_path(base):
    return os.path.join(base, LEDGER_NAME)


def safe_store_path(base, name):
    """单元名（如 fu2611_20261102）-> store 里的真实路径；名字不合法返回 None。"""
    if not name or name != os.path.basename(name) or name in ('.', '..'):
        return None
    if name.lower().endswith(STORE_EXT):
        name = name[:-len(STORE_EXT)]
    if not name or name.startswith('.'):
        return None
    root = os.path.realpath(store_dir(base))
    path = os.path.realpath(os.path.join(root, name + STORE_EXT))
    if os.path.dirname(path) != root:
        return None
    return path


def unit_name(file_name):
    """规范文件名（fu2611_20261102.csv）-> 单元名（fu2611_20261102）。"""
    base = os.path.basename(file_name or '')
    for ext in ('.csv', STORE_EXT):
        if base.lower().endswith(ext):
            return base[:-len(ext)]
    return base


# ---------------------------------------------------------------------------
# TickData <-> npz
# ---------------------------------------------------------------------------
def _pack(td, source=''):
    """TickData -> (npz 数组字典, 元数据 dict)。object 数组（交易日、BS）转定长 unicode，npz 里不用 pickle。"""
    meta = {
        'symbol': td.symbol, 'name': td.name, 'tickCount': td.count, 'days': list(td.days),
        'start': depth_market.fmt_ts(td.ts[0], True), 'end': depth_market.fmt_ts(td.ts[-1], True),
        'hasBs': td.bs is not None, 'levels': td.levels, 'warnings': list(td.warnings),
        'source': source, 'importedAt': int(time.time()),
    }
    arrays = {
        'ts': td.ts, 'price': td.price, 'vol': td.vol, 'cum_vol': td.cum_vol, 'money': td.money,
        'position': td.position, 'day': td.day.astype(str),
    }
    if td.bs is not None:
        arrays['bs'] = td.bs.astype(str)
    for n in range(td.levels):
        arrays[f'ask_p{n}'], arrays[f'ask_v{n}'] = td.ask_p[n], td.ask_v[n]
        arrays[f'bid_p{n}'], arrays[f'bid_v{n}'] = td.bid_p[n], td.bid_v[n]
    full = dict(meta, version=FORMAT_VERSION)
    arrays['_meta'] = np.frombuffer(json.dumps(full, ensure_ascii=False).encode('utf-8'), dtype=np.uint8)
    return arrays, meta


def write_unit(base, name, td, source='', *, only_if_absent=False):
    """把一份 TickData 写进行情库（原子替换），返回台账条目 meta。

    only_if_absent=True：在写锁内再确认一次这份数据还没入库，已存在就什么也不写并返回 None。
    迁移线程用它——它在解析 CSV 的那几秒里，用户可能刚导入了同一份数据，不能被旧数据盖掉。
    """
    path = safe_store_path(base, name)
    if path is None:
        raise StoreError(f'名称不合法：{name}')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arrays, meta = _pack(td, source)
    tmp = path + '.writing'
    with _write_lock:
        if only_if_absent and has_unit(base, name):
            return None
        return _write_locked(path, tmp, arrays, meta)


def import_unit(base, name, td, source='', *, only_if_absent=False, save=True):
    """写 npz 并登记台账，二者在同一把写锁里一气呵成（别的写入者不会插在「写文件」和「登记」之间）。

    返回台账 meta；only_if_absent=True 且这份数据已入库时什么也不做，返回 None。
    save=False：批量导入时先不落盘台账，由调用方每隔若干个 flush 一次。
    """
    with _write_lock:
        meta = write_unit(base, name, td, source, only_if_absent=only_if_absent)
        if meta is not None:
            record(base, name, meta, save=save)
        return meta


def _write_locked(path, tmp, arrays, meta):
    try:
        with open(tmp, 'wb') as fh:
            # 压缩：tick 数据重复度极高（交易日字符串、盘口价量），实测压到未压缩的约 5%（比原 CSV 小一个数量级），
            # 而解压只多花几毫秒（一个 6 万笔的单元读取 3ms -> 6ms），不压缩的话库文件反而比 CSV 还大。
            np.savez_compressed(fh, **arrays)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return meta


def _read_meta(npz):
    try:
        meta = json.loads(bytes(npz['_meta']).decode('utf-8'))
    except (KeyError, ValueError, UnicodeDecodeError):
        raise StoreError('库文件缺少元数据，可能已损坏')
    if meta.get('version') != FORMAT_VERSION:
        raise StoreError(f"库文件版本不符（{meta.get('version')}），请重新导入")
    return meta


def read_unit(base, name):
    """从行情库加载一份 TickData；文件不存在 / 损坏抛 StoreError / OSError。"""
    path = safe_store_path(base, name)
    if path is None:
        raise StoreError(f'名称不合法：{name}')
    try:
        with np.load(path, allow_pickle=False) as z:
            meta = _read_meta(z)
            levels = int(meta.get('levels', 0))
            td = depth_market.TickData(
                ts=z['ts'], price=z['price'], vol=z['vol'], cum_vol=z['cum_vol'], money=z['money'],
                position=z['position'], day=z['day'].astype(object),
                bs=z['bs'].astype(object) if 'bs' in z.files else None,
                ask_p=[z[f'ask_p{n}'] for n in range(levels)], ask_v=[z[f'ask_v{n}'] for n in range(levels)],
                bid_p=[z[f'bid_p{n}'] for n in range(levels)], bid_v=[z[f'bid_v{n}'] for n in range(levels)],
                symbol=meta.get('symbol', ''), name=meta.get('name', ''),
                days=list(meta.get('days', [])), warnings=list(meta.get('warnings', [])),
            )
    except StoreError:
        raise
    except FileNotFoundError:
        raise
    except CORRUPT_ERRORS as e:
        raise StoreError(f'库文件无法读取（可能已损坏）：{e}')
    return td


def peek_unit_meta(base, name):
    """只读 npz 里的元数据；不加载数组。"""
    path = safe_store_path(base, name)
    with np.load(path, allow_pickle=False) as z:
        return _read_meta(z)


def verify_unit(base, name):
    """重建台账时用：除了元数据，还校验 npz 压缩包的每个成员都能完整解出（CRC），返回元数据。

    只读元数据会把「元数据完好、数组被截断 / 损坏」的文件当成已导入：台账显示有数据、阻止重新导入，
    真正打开合约时才报错。台账是用户判断「哪些已经导入」的唯一依据，不能在这个方向上出错。
    """
    path = safe_store_path(base, name)
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise StoreError(f'库文件损坏（{bad}）')
        return peek_unit_meta(base, name)
    except StoreError:
        raise
    except CORRUPT_ERRORS as e:
        raise StoreError(f'库文件损坏：{e}')


# ---------------------------------------------------------------------------
# 台账
# ---------------------------------------------------------------------------
def _entry_from_meta(meta, size, mtime_ns):
    keep = ('symbol', 'name', 'tickCount', 'days', 'start', 'end', 'hasBs', 'levels', 'source', 'importedAt')
    out = {k: meta.get(k) for k in keep}
    out['size'], out['mtimeNs'] = int(size), int(mtime_ns)
    return out


def _load(base):
    """加载台账到内存（每个目录一次），并和 store 目录对账：多出的 npz 补进台账，台账里已不存在的 npz 去掉。"""
    root = _root(base)
    with _lock:
        if _state["dir"] == root and _state["entries"] is not None:
            return _state["entries"]
        entries = {}
        try:
            with open(ledger_path(base), 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if data.get('version') == LEDGER_VERSION and isinstance(data.get('units'), dict):
                entries = {k: v for k, v in data['units'].items() if isinstance(v, dict)}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError) as e:
            print(f"[Depth] 台账读取失败，将从库文件重建：{e}")
        _state.update(dir=root, entries=entries, dirty=False)
        _reconcile(base, entries)
        _save(base)
        return entries


def _reconcile(base, entries):
    """台账和 store 目录对账。npz 自带元数据，所以台账丢失 / 损坏 / 手工拷入 npz 都能自动恢复。"""
    sdir = store_dir(base)
    on_disk = {}
    if os.path.isdir(sdir):
        for fn in os.listdir(sdir):
            if fn.lower().endswith(STORE_EXT) and not fn.startswith('.'):
                on_disk[fn[:-len(STORE_EXT)]] = os.path.join(sdir, fn)
    for name in set(entries) - set(on_disk):
        entries.pop(name, None)
        _state["dirty"] = True
    for name, path in on_disk.items():
        try:
            st = os.stat(path)
        except OSError:
            continue
        ent = entries.get(name)
        if ent and ent.get('size') == st.st_size and ent.get('mtimeNs') == st.st_mtime_ns:
            continue
        try:
            entries[name] = _entry_from_meta(verify_unit(base, name), st.st_size, st.st_mtime_ns)
        except (StoreError, *CORRUPT_ERRORS) as e:
            print(f"[Depth] 库文件 {name} 无法读取，已忽略：{e}")
            entries.pop(name, None)
        _state["dirty"] = True


def _save(base):
    with _lock:
        if not _state["dirty"] or _state["entries"] is None:
            return
        if not os.path.isdir(base):
            return
        tmp = ledger_path(base) + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'version': LEDGER_VERSION, 'units': _state["entries"]}, fh, ensure_ascii=False)
            os.replace(tmp, ledger_path(base))
            _state["dirty"] = False
        except OSError as e:
            print(f"[Depth] 台账写入失败（不影响使用，下次启动会从库文件重建）：{e}")
            try:
                os.remove(tmp)
            except OSError:
                pass


def entries(base):
    """全部台账条目的浅拷贝：{单元名: meta}。"""
    with _lock:
        return dict(_load(base))


def has_unit(base, name):
    with _lock:
        return name in _load(base)


def get_entry(base, name):
    with _lock:
        return _load(base).get(name)


def record(base, name, meta, save=True):
    """写入 npz 之后登记进台账。批量导入传 save=False，整批结束后调一次 flush()。"""
    path = safe_store_path(base, name)
    try:
        st = os.stat(path)
    except (OSError, TypeError):
        return
    with _lock:
        _load(base)[name] = _entry_from_meta(meta, st.st_size, st.st_mtime_ns)
        _state["dirty"] = True
        if save:
            _save(base)


def flush(base):
    _save(base)


def remove_unit(base, name):
    """删除一份库文件并更新台账；文件不存在也当作成功。其它 OSError 抛出（如被占用）。"""
    path = safe_store_path(base, name)
    if path is None:
        raise StoreError(f'名称不合法：{name}')
    with _write_lock:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        with _lock:
            _load(base).pop(name, None)
            _state["dirty"] = True
            _save(base)


def signature(base, name):
    """单元的 (名称, 大小, mtime_ns)：文件变化后不同，用来判断缓存是否过期。"""
    path = safe_store_path(base, name)
    try:
        st = os.stat(path)
        return (name, st.st_size, st.st_mtime_ns)
    except (OSError, TypeError):
        return (name, -1, -1)


def write_lock():
    """写锁（可重入）：with tick_store.write_lock(): 内做「检查 -> 写入 -> 登记」。"""
    return _write_lock


def covered_days(base, symbol):
    """台账里该合约已导入的交易日集合（含多日单元覆盖的每一天）。按合约代码精确匹配。"""
    out = set()
    with _lock:
        for e in _load(base).values():
            if e.get('symbol') == symbol:
                out.update(e.get('days') or [])
    return out


def reset_state():
    """测试 / 切换目录用：丢弃内存台账。"""
    with _lock:
        _state.update(dir=None, entries=None, dirty=False)
